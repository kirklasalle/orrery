"""
Human-in-the-loop approval for actions the framework cannot undo.

This is the narrowest useful foothold Laws 1 and 2 have in a cycle engine. Orrery cannot
evaluate whether an action causes harm, but it can refuse to take an irreversible step
without a human saying so first, and it can record who said it.

Honest limits. Without any signing configured, a token is an unsigned assertion: any code
in the process can mint one, so it documents intent rather than proving consent.
`ORRERY_APPROVAL_KEY` adds an HMAC, which raises the bar to holding a shared secret the
agent process also holds — custody, not authorship. An operator identity
(`ORRERY_OPERATOR_ID` + `ORRERY_OPERATOR_PRIVATE_KEY`) signs with Ed25519 instead, and
because the framework holds only the public keyring it can check the signature without
being able to produce one. That is the only configuration in which "a human approved this"
is a claim the framework can substantiate rather than merely repeat.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel

from orrery.core import signing
from orrery.core.integrity import canonical_json
from orrery.core.types import ActionPayload, ActionRisk, ApprovalToken

logger = logging.getLogger(__name__)

APPROVAL_KEY_ENV = "ORRERY_APPROVAL_KEY"


class ApprovalDecision(BaseModel):
    allowed: bool
    policy_id: str
    reason: Optional[str] = None


def _signing_key() -> Optional[bytes]:
    key = os.environ.get(APPROVAL_KEY_ENV)
    return key.encode("utf-8") if key else None


def _token_digest(token: ApprovalToken) -> str:
    payload = token.model_dump(mode="json", exclude={"signature"})
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def grant(
    action: ActionPayload,
    approver: str,
    reason: str = "",
    sign: bool = True,
) -> ApprovalToken:
    """
    Mints an approval for one specific action. The caller is asserting that a human decided.

    With an operator identity configured the token is signed with that operator's Ed25519
    key and `approver` defaults to the key id, so the name on the token and the key that
    signed it cannot disagree.
    """
    signer = signing.signer_from_env() if sign else None
    if signer is not None and not approver:
        approver = signer.key_id

    token = ApprovalToken(action_id=action.action_id, approver=approver, reason=reason)
    if signer is not None:
        token.signature = signer.sign(_token_digest(token))
        return token

    key = _signing_key() if sign else None
    if key:
        token.signature = hmac.new(key, _token_digest(token).encode("utf-8"), hashlib.sha256).hexdigest()
    return token


def signature_is_valid(token: ApprovalToken) -> bool:
    if not token.signature:
        return False

    digest = _token_digest(token)
    envelope = signing.decode_signature(token.signature)
    if envelope is not None and envelope.algorithm == signing.ED25519:
        # The key that signed must be the operator the token names, or any keyholder could
        # issue approvals in a colleague's name.
        if envelope.key_id != token.approver:
            logger.warning(
                "Approval names approver %r but was signed by key %r.",
                token.approver,
                envelope.key_id,
            )
            return False
        return signing.keyring_from_env().verify(digest, token.signature)

    key = _signing_key()
    if not key:
        return False
    expected = hmac.new(key, digest.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, token.signature)


class ApprovalGate:
    """
    Decides whether an action may execute given its risk class and any attached approval.
    """

    def __init__(
        self,
        require_approval_for_irreversible: bool = True,
        require_approval_for_compensable: bool = False,
        require_signed_approval: bool = False,
        approval_ttl_seconds: float = 900.0,
        require_asymmetric_approval: bool = False,
    ):
        self.require_approval_for_irreversible = require_approval_for_irreversible
        self.require_approval_for_compensable = require_approval_for_compensable
        self.require_signed_approval = require_signed_approval or require_asymmetric_approval
        self.approval_ttl_seconds = approval_ttl_seconds
        self.require_asymmetric_approval = require_asymmetric_approval

    def _needs_approval(self, risk: ActionRisk) -> bool:
        if risk is ActionRisk.IRREVERSIBLE:
            return self.require_approval_for_irreversible
        if risk is ActionRisk.COMPENSABLE:
            return self.require_approval_for_compensable
        return False

    def evaluate(self, action: ActionPayload) -> ApprovalDecision:
        if not self._needs_approval(action.risk):
            return ApprovalDecision(allowed=True, policy_id="RISK-000")

        token = action.approval
        if token is None:
            return ApprovalDecision(
                allowed=False,
                policy_id="RISK-001",
                reason=(
                    f"action {action.action_name!r} is {action.risk.value} and has no operator "
                    f"approval attached"
                ),
            )

        if token.action_id != action.action_id:
            # A token minted for one action must not authorize another.
            return ApprovalDecision(
                allowed=False,
                policy_id="RISK-002",
                reason=(
                    f"approval was granted for action {token.action_id} but attached to "
                    f"{action.action_id}"
                ),
            )

        if self.require_asymmetric_approval and not signing.is_asymmetric(token.signature):
            return ApprovalDecision(
                allowed=False,
                policy_id="RISK-005",
                reason=(
                    f"approval from {token.approver!r} is not signed with an operator key; "
                    f"a shared-secret signature cannot distinguish the operator from the agent"
                ),
            )

        if self.require_signed_approval and not signature_is_valid(token):
            return ApprovalDecision(
                allowed=False,
                policy_id="RISK-003",
                reason=f"approval from {token.approver!r} is unsigned or its signature is invalid",
            )

        if self.approval_ttl_seconds > 0 and self._is_expired(token):
            return ApprovalDecision(
                allowed=False,
                policy_id="RISK-004",
                reason=(
                    f"approval from {token.approver!r} expired "
                    f"({self.approval_ttl_seconds:.0f}s time-to-live)"
                ),
            )

        return ApprovalDecision(allowed=True, policy_id="RISK-000")

    def _is_expired(self, token: ApprovalToken) -> bool:
        try:
            granted = datetime.fromisoformat(token.granted_at)
        except ValueError:
            return True
        if granted.tzinfo is None:
            granted = granted.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - granted > timedelta(seconds=self.approval_ttl_seconds)
