"""
Agent-to-Agent (A2A) Protocol and Governance Router.

Provides:
- Cryptographically signed A2AMessage and envelope specifications.
- Intent-based routing with delegation policy enforcement (DEL-001 through DEL-005).
- Non-repudiation: Ed25519 signature verification on inter-agent messages.
- Tamper-evident ledger recording for all inter-agent dispatches and refusals.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from orrery.core.delegation import DelegationBudget, DelegationPolicy, DelegationRequest
from orrery.core.ledger import EventLedger
from orrery.core.signing import Keyring, OperatorSigner
from orrery.core.integrity import canonical_json
from orrery.core.types import CycleTier

logger = logging.getLogger(__name__)

A2A_POLICY = "A2A-ROUTER"


def validate_agent_id(value: str) -> str:
    """Ensures agent_id does not contain path separators, null bytes, or traversal tokens."""
    if not value or not isinstance(value, str):
        raise ValueError("agent_id must be a non-empty string")
    if "/" in value or "\\" in value or ".." in value or "\0" in value:
        raise ValueError(f"agent_id contains forbidden characters or path separators: {value!r}")
    if len(value) > 128:
        raise ValueError("agent_id exceeds maximum length of 128")
    return value


class A2AMessage(BaseModel):
    """
    Standard message envelope for inter-agent communication.
    """

    model_config = ConfigDict(validate_assignment=True)

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str
    recipient_id: str
    sender_tier: CycleTier
    recipient_tier: Optional[CycleTier] = None
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    intent: str = Field(description="Action intent: delegate_task, query_status, submit_receipt, etc.")
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signature: Optional[str] = None
    ancestry: Tuple[str, ...] = ()
    depth: int = 0

    def body_dict(self) -> Dict[str, Any]:
        """Returns message payload excluding signature for canonical signing."""
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "sender_tier": self.sender_tier.value,
            "recipient_tier": self.recipient_tier.value if self.recipient_tier else None,
            "conversation_id": self.conversation_id,
            "intent": self.intent,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "ancestry": list(self.ancestry),
            "depth": self.depth,
        }

    def sign(self, signer: OperatorSigner) -> None:
        """Signs the canonical body using the sender's private key."""
        canonical_str = canonical_json(self.body_dict())
        self.signature = signer.sign(canonical_str)

    def verify_signature(self, keyring: Keyring) -> bool:
        """Verifies message signature against trusted public keyring."""
        if not self.signature:
            return False
        canonical_str = canonical_json(self.body_dict())
        return keyring.verify(canonical_str, self.signature)


class A2ADeliveryResult(BaseModel):
    """
    Delivery verdict and handler response.
    """

    delivered: bool
    reason: Optional[str] = None
    policy_id: Optional[str] = None
    response_payload: Optional[Dict[str, Any]] = None


# Type for async agent message handler
AgentHandler = Callable[[A2AMessage], Any]


class A2AGovernanceRouter:
    """
    Governed message bus for Agent-to-Agent communication.
    Evaluates delegation caps, cryptographic signatures, and audit logs.
    """

    def __init__(
        self,
        delegation_policy: Optional[DelegationPolicy] = None,
        delegation_budget: Optional[DelegationBudget] = None,
        keyring: Optional[Keyring] = None,
        ledger: Optional[EventLedger] = None,
        require_signatures: bool = False,
    ) -> None:
        self.delegation_policy = delegation_policy or DelegationPolicy()
        self.delegation_budget = delegation_budget or DelegationBudget()
        self.keyring = keyring or Keyring()
        self.ledger = ledger
        self.require_signatures = require_signatures
        self._endpoints: Dict[str, Tuple[CycleTier, AgentHandler]] = {}

    def register_agent(
        self,
        agent_id: str,
        tier: CycleTier,
        handler: AgentHandler,
    ) -> None:
        """Registers an agent endpoint with its tier rank and message handler."""
        validate_agent_id(agent_id)
        self._endpoints[agent_id] = (tier, handler)
        logger.info("[A2ARouter] Registered agent %r (Tier: %s)", agent_id, tier.value)

    async def route_message(self, message: A2AMessage) -> A2ADeliveryResult:
        """
        Dispatches an A2A message through the governance checks:
        1. Endpoint existence
        2. Cryptographic signature check (if required, on unaltered message)
        3. Delegation constraint check (if intent is 'delegate_task')
        4. Handler dispatch and audit ledgering
        """
        # 1. Target check
        if message.recipient_id not in self._endpoints:
            reason = f"Recipient agent {message.recipient_id!r} not registered."
            self._log_refusal(message, "A2A-UNKNOWN-RECIPIENT", reason)
            return A2ADeliveryResult(delivered=False, policy_id="A2A-UNKNOWN-RECIPIENT", reason=reason)

        recipient_tier, handler = self._endpoints[message.recipient_id]

        # 2. Cryptographic signature check on unaltered message
        if self.require_signatures:
            if not message.verify_signature(self.keyring):
                reason = f"Signature verification failed for sender {message.sender_id!r}."
                self._log_refusal(message, "A2A-SIGNATURE-INVALID", reason)
                return A2ADeliveryResult(delivered=False, policy_id="A2A-SIGNATURE-INVALID", reason=reason)

        # 3. Delegation checks if delegating
        if message.intent == "delegate_task":
            req = DelegationRequest(
                parent_cycle_id=message.sender_id,
                parent_tier=message.sender_tier,
                child_cycle_id=message.recipient_id,
                child_tier=recipient_tier,
                depth=message.depth,
                ancestry=message.ancestry,
            )
            decision = self.delegation_policy.authorize(req, self.delegation_budget)
            if not decision.allowed:
                self._log_refusal(message, decision.policy_id or "A2A-DELEGATION-DENIED", decision.reason or "Denied")
                return A2ADeliveryResult(
                    delivered=False,
                    policy_id=decision.policy_id or "A2A-DELEGATION-DENIED",
                    reason=decision.reason,
                )
            self.delegation_budget.record(req)

        if message.recipient_tier is None:
            message.recipient_tier = recipient_tier

        # 4. Dispatch to handler
        try:
            res = handler(message)
            import inspect
            if inspect.isawaitable(res):
                res = await res

            if self.ledger is not None:
                self.ledger.append(
                    "a2a.message_delivered",
                    summary=f"Delivered {message.intent} from {message.sender_id} to {message.recipient_id}.",
                    sender=message.sender_id,
                    recipient=message.recipient_id,
                    intent=message.intent,
                    conversation_id=message.conversation_id,
                )

            return A2ADeliveryResult(
                delivered=True,
                response_payload=res if isinstance(res, dict) else {"result": res},
            )
        except Exception as exc:
            logger.exception("[A2ARouter] Handler exception for %r", message.recipient_id)
            return A2ADeliveryResult(
                delivered=False,
                policy_id="A2A-HANDLER-ERROR",
                reason=f"{type(exc).__name__}: {exc}",
            )

    def _log_refusal(self, message: A2AMessage, policy_id: str, reason: str) -> None:
        logger.warning("[A2ARouter] Refused message %r: %s", message.message_id, reason)
        if self.ledger is not None:
            self.ledger.append(
                "a2a.message_refused",
                summary=f"A2A message {message.message_id} refused: {reason}",
                policy_id=policy_id,
                sender=message.sender_id,
                recipient=message.recipient_id,
                intent=message.intent,
            )
