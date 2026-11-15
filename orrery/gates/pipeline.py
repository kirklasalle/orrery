"""
Standalone Governance Pipeline (Orrery Gates SDK).

Encapsulates Orrery's 6-gate defense-in-depth stack into an embeddable middleware pipeline:
1. InterdictionGate (operator prohibitions & protected path containment)
2. EnvelopeGate (deployment reach boundary intersection)
3. QuarantineGate (holding undeclared/unclassified actions)
4. RateLimitGate (sliding-window burst & quota defense)
5. ApprovalGate (human authorization & Ed25519 token verification)

Usable in any Python project, web service, or agent framework.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from orrery.adapters.base import BaseAdapter
from orrery.core.approval import ApprovalGate
from orrery.core.config import Settings, get_settings
from orrery.core.envelope import EffectEnvelope, EnvelopeGate
from orrery.core.interdiction import InterdictionGate, Prohibition, runtime_paths
from orrery.core.ledger import EventLedger
from orrery.core.quarantine import ClassificationStore, QuarantineGate
from orrery.core.ratelimit import RateLimitGate, RateLimitRule
from orrery.core.telemetry import trace_span
from orrery.core.types import ActionPayload, ActionRisk, ExecutionReceipt

logger = logging.getLogger(__name__)


_RISK_SEVERITY: Dict[ActionRisk, int] = {
    ActionRisk.READ_ONLY: 0,
    ActionRisk.REVERSIBLE: 1,
    ActionRisk.COMPENSABLE: 2,
    ActionRisk.IRREVERSIBLE: 3,
}


class GateVerdict(BaseModel):
    """
    Unified verdict returned by the governance pipeline.
    """

    allowed: bool
    gate_name: str
    policy_id: Optional[str] = None
    reason: Optional[str] = None


class GovernancePipeline:
    """
    Modular, embeddable governance pipeline evaluating actions against Orrery's defense gates.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        ledger: Optional[EventLedger] = None,
        interdiction_gate: Optional[InterdictionGate] = None,
        envelope_gate: Optional[EnvelopeGate] = None,
        quarantine_gate: Optional[QuarantineGate] = None,
        rate_limit_gate: Optional[RateLimitGate] = None,
        approval_gate: Optional[ApprovalGate] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.ledger = ledger

        self.interdiction_gate = interdiction_gate or InterdictionGate(
            prohibitions=[
                Prohibition(**rule.model_dump())
                for rule in self.settings.interdiction.prohibitions
            ],
            protected_paths=(
                runtime_paths(self.settings)
                if self.settings.interdiction.protect_runtime_paths
                else ()
            ),
            halt_file=self.settings.interdiction.halt_file,
        )

        self.envelope_gate = envelope_gate or EnvelopeGate(
            enforce=self.settings.envelope.enforce,
            deployment=EffectEnvelope(paths=list(self.settings.envelope.paths)),
        )

        self.quarantine_gate = quarantine_gate or QuarantineGate(
            enabled=self.settings.quarantine.enabled,
            require_signed=self.settings.quarantine.require_signed,
        )

        self.rate_limit_gate = rate_limit_gate or RateLimitGate(
            rules=[
                RateLimitRule(**rule.model_dump())
                for rule in self.settings.ratelimit.rules
            ],
            enabled=self.settings.ratelimit.enabled,
        )

        self.approval_gate = approval_gate or ApprovalGate(
            require_approval_for_irreversible=self.settings.approval.require_for_irreversible,
            require_approval_for_compensable=self.settings.approval.require_for_compensable,
            require_signed_approval=self.settings.approval.require_signed,
            approval_ttl_seconds=self.settings.approval.ttl_seconds,
            require_asymmetric_approval=self.settings.approval.require_asymmetric,
        )

    def add_prohibition(
        self,
        reason: str,
        adapters: Optional[List[str]] = None,
        actions: Optional[List[str]] = None,
        paths: Optional[List[str]] = None,
    ) -> None:
        """Adds an operator prohibition rule dynamically."""
        self.interdiction_gate.prohibitions.append(
            Prohibition(
                reason=reason,
                adapters=adapters or [],
                actions=actions or [],
                paths=paths or [],
            )
        )

    def add_rate_limit(
        self,
        name: str,
        max_calls: int,
        window_seconds: float,
        adapter: Optional[str] = None,
        action: Optional[str] = None,
    ) -> None:
        """Adds a sliding-window rate limit rule dynamically."""
        self.rate_limit_gate.enabled = True
        self.rate_limit_gate.add_rule(
            RateLimitRule(
                name=name,
                adapter=adapter,
                action=action,
                max_calls=max_calls,
                window_seconds=window_seconds,
            )
        )

    def evaluate(
        self, action: ActionPayload, adapter: Optional[BaseAdapter] = None
    ) -> GateVerdict:
        """
        Evaluates the action against all 5 gates sequentially (fail-closed).
        Does not execute the underlying action.
        """
        with trace_span(
            f"orrery.gate.evaluate.{action.action_name}",
            attributes={
                "orrery.action_name": action.action_name,
                "orrery.target_adapter": action.target_adapter,
            },
        ):
            # 1. Interdiction Gate
            root = getattr(adapter, "root", None) if adapter else None
            interdiction = self.interdiction_gate.evaluate(action, root)
            if not interdiction.allowed:
                return GateVerdict(
                    allowed=False,
                    gate_name="InterdictionGate",
                    policy_id=interdiction.policy_id,
                    reason=interdiction.reason,
                )

            # 2. Envelope Gate
            if adapter is not None:
                reach = self.envelope_gate.evaluate(action, adapter)
                if not reach.allowed:
                    return GateVerdict(
                        allowed=False,
                        gate_name="EnvelopeGate",
                        policy_id=reach.policy_id,
                        reason=reach.reason,
                    )

            # 3. Quarantine Gate
            held = self.quarantine_gate.evaluate(action, adapter)
            if not held.allowed:
                return GateVerdict(
                    allowed=False,
                    gate_name="QuarantineGate",
                    policy_id=held.policy_id,
                    reason=held.reason,
                )

            # 4. Approval Gate
            # Determine effective risk without mutating caller's ActionPayload
            candidates = [action.risk]
            if adapter is not None:
                declared = getattr(adapter, "declared_risks", {}).get(action.action_name)
                if declared is not None:
                    candidates.append(declared)
                else:
                    candidates.append(ActionRisk.IRREVERSIBLE)
            effective_risk = max(candidates, key=lambda r: _RISK_SEVERITY[r])
            evaluated_action = action.model_copy(update={"risk": effective_risk})

            approval_dec = self.approval_gate.evaluate(evaluated_action)
            if not approval_dec.allowed:
                return GateVerdict(
                    allowed=False,
                    gate_name="ApprovalGate",
                    policy_id=approval_dec.policy_id,
                    reason=approval_dec.reason,
                )

            # 5. Rate-Limiting Gate (after approval so denied actions don't burn quota)
            rate_dec = self.rate_limit_gate.evaluate(evaluated_action)
            if not rate_dec.allowed:
                return GateVerdict(
                    allowed=False,
                    gate_name="RateLimitGate",
                    policy_id=rate_dec.policy_id,
                    reason=rate_dec.reason,
                )

            return GateVerdict(
                allowed=True,
                gate_name="AllGates",
                reason="All governance gates passed.",
            )

    async def execute(
        self, action: ActionPayload, adapter: BaseAdapter
    ) -> ExecutionReceipt:
        """
        Evaluates governance gates and dispatches the action to the adapter upon approval.
        Records events into the audit ledger if present.
        """
        verdict = self.evaluate(action, adapter)
        if not verdict.allowed:
            logger.warning("[GovernancePipeline] Refused %r: %s", action.action_name, verdict.reason)
            if self.ledger is not None:
                self.ledger.append(
                    "action.refused",
                    summary=f"{action.action_name} refused by {verdict.gate_name}: {verdict.reason}",
                    policy_id=verdict.policy_id or "LAW-REFUSED",
                    action_id=action.action_id,
                    action_name=action.action_name,
                    adapter=adapter.name,
                )
            return ExecutionReceipt(
                action_id=action.action_id,
                action_name=action.action_name,
                success=False,
                error=f"Refused by {verdict.gate_name} ({verdict.policy_id}): {verdict.reason}",
            )

        # Dispatch
        try:
            receipt = await adapter.execute_action(action)
        except Exception as exc:
            logger.exception("[GovernancePipeline] Adapter exception for %r", action.action_name)
            receipt = ExecutionReceipt(
                action_id=action.action_id,
                action_name=action.action_name,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )

        if self.ledger is not None:
            self.ledger.append(
                "action.executed" if receipt.success else "action.failed",
                summary=f"{action.action_name} on {adapter.name}: {'success' if receipt.success else receipt.error}",
                policy_id="LAW9-LEDGER",
                action_id=action.action_id,
                action_name=action.action_name,
                adapter=adapter.name,
                success=receipt.success,
            )

        return receipt
