"""
Human-in-the-loop approval for actions the framework cannot undo.

This is the narrowest useful foothold Laws 1 and 2 have in a cycle engine. Orrery cannot
evaluate whether an action causes harm, but it can refuse to take an irreversible step
without a human saying so first, and it can record who said it.

Honest limits. Without ORRERY_APPROVAL_KEY set, a token is an unsigned assertion: any code
running in the same process can mint one, so it documents intent rather than proving
consent. Set the key and `require_signed_approval` to make forgery require the secret.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel

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
    """
    token = ApprovalToken(action_id=action.action_id, approver=approver, reason=reason)
    key = _signing_key() if sign else None
    if key:
        token.signature = hmac.new(key, _token_digest(token).encode("utf-8"), hashlib.sha256).hexdigest()
    return token


def signature_is_valid(token: ApprovalToken) -> bool:
    key = _signing_key()
    if not key or not token.signature:
        return False
    expected = hmac.new(key, _token_digest(token).encode("utf-8"), hashlib.sha256).hexdigest()
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
    ):
        self.require_approval_for_irreversible = require_approval_for_irreversible
        self.require_approval_for_compensable = require_approval_for_compensable
        self.require_signed_approval = require_signed_approval
        self.approval_ttl_seconds = approval_ttl_seconds

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
