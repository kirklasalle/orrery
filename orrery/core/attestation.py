"""
Attestation of the running configuration (Law 10).

Every control in this framework is a setting away from being switched off. `require_signed`
is a boolean. `max_depth` is an integer. A policy marked ENFORCED in the registry is a line
in a Python file. None of that is enforcement if the configuration itself can be edited
without anyone noticing, which is what Law 10 is about: core directives may only be
modified with cryptographically secured Governance approval.

So Orrery digests the settings that bound its own authority, together with the governance
registry, and can refuse to start unless that exact digest carries an operator's Ed25519
signature. Changing a limit then requires re-attesting it as a deliberate, attributable act.

What this does not cover, stated plainly: **the code**. An attestation binds configuration
and policy declarations, not `approval.py`. Anyone who can edit the source can remove the
check entirely, and no amount of signing inside a program defends against an attacker who
controls that program. This raises the cost of a quiet configuration change; it is not a
substitute for controlling who can deploy.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from pydantic import BaseModel

from orrery.core import signing
from orrery.core.charter import charter_digest
from orrery.core.governance import POLICIES
from orrery.core.integrity import canonical_json

if TYPE_CHECKING:
    from orrery.core.config import Settings

logger = logging.getLogger(__name__)

POLICY_ID = "LAW10-APPROVAL"


class GovernanceError(Exception):
    """Raised when the running configuration is not covered by a valid attestation."""


class Attestation(BaseModel):
    digest: str
    signature: str
    approved_by: str
    approved_at: str = ""
    note: str = ""


class AttestationDecision(BaseModel):
    allowed: bool
    policy_id: str = POLICY_ID
    reason: Optional[str] = None


def governed_configuration(settings: "Settings") -> Dict[str, Any]:
    """
    The subset of configuration that bounds what Orrery may do, plus the governance
    registry itself. Storage paths and timeouts are excluded: they vary per machine and
    grant no authority, and an attestation that broke on every path change would be
    re-signed reflexively, which is worse than not having one.
    """
    return {
        "approval": settings.approval.model_dump(mode="json"),
        "integrity": settings.integrity.model_dump(mode="json"),
        "delegation": settings.delegation.model_dump(mode="json"),
        "critique": settings.critique.model_dump(mode="json"),
        "interdiction": settings.interdiction.model_dump(mode="json"),
        "quarantine": settings.quarantine.model_dump(mode="json"),
        "envelope": settings.envelope.model_dump(mode="json"),
        "invariants": settings.invariants.model_dump(mode="json"),
        "allow_simulated_adapters": settings.allow_simulated_adapters,
        "charter": charter_digest(),
        "policies": [
            {
                "policy_id": policy.policy_id,
                "law": policy.law,
                "status": policy.status.value,
                "test": policy.test,
            }
            for policy in POLICIES
        ],
    }


def configuration_digest(settings: "Settings") -> str:
    payload = canonical_json(governed_configuration(settings))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def attest(settings: "Settings", note: str = "") -> Attestation:
    """
    Signs the running configuration with the configured operator key.
    """
    signer = signing.signer_from_env()
    if signer is None:
        raise GovernanceError(
            "attestation requires an operator identity: set ORRERY_OPERATOR_ID and "
            "ORRERY_OPERATOR_PRIVATE_KEY. An unsigned attestation would attest to nothing."
        )

    digest = configuration_digest(settings)
    return Attestation(
        digest=digest,
        signature=signer.sign(digest),
        approved_by=signer.key_id,
        approved_at=datetime.now(timezone.utc).isoformat(),
        note=note,
    )


def load_attestation(path: Path) -> Optional[Attestation]:
    try:
        return Attestation.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.error("Attestation at %s is unreadable: %s", path, exc)
        return None


def save_attestation(attestation: Attestation, path: Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(attestation.model_dump_json(indent=2), encoding="utf-8")
    return target


def evaluate(settings: "Settings", path: Optional[Path] = None) -> AttestationDecision:
    """
    Decides whether the running configuration is covered by a valid operator attestation.
    Every failure mode is a refusal; none of them is a pass with a warning.
    """
    target = Path(path or settings.governance.attestation_path)
    attestation = load_attestation(target)
    if attestation is None:
        return AttestationDecision(
            allowed=False,
            reason=f"no attestation found at {target}; the running configuration is unapproved",
        )

    expected = configuration_digest(settings)
    if attestation.digest != expected:
        return AttestationDecision(
            allowed=False,
            reason=(
                f"configuration has changed since it was approved by "
                f"{attestation.approved_by!r} (approved {attestation.digest[:12]}..., "
                f"running {expected[:12]}...)"
            ),
        )

    if not signing.is_asymmetric(attestation.signature):
        return AttestationDecision(
            allowed=False,
            reason=(
                "attestation is not signed with an operator key; a shared-secret signature "
                "cannot distinguish Governance from the agent it governs"
            ),
        )

    envelope = signing.decode_signature(attestation.signature)
    if envelope is None or envelope.key_id != attestation.approved_by:
        return AttestationDecision(
            allowed=False,
            reason=(
                f"attestation claims approval by {attestation.approved_by!r} but was signed "
                f"by a different key"
            ),
        )

    if not signing.keyring_from_env().verify(expected, attestation.signature):
        return AttestationDecision(
            allowed=False,
            reason=(
                f"attestation signature from {attestation.approved_by!r} does not verify "
                f"against the operator keyring"
            ),
        )

    return AttestationDecision(allowed=True, reason=f"approved by {attestation.approved_by}")


def enforce(settings: "Settings") -> AttestationDecision:
    """
    Refuses to proceed when `governance.require_attestation` is set and the running
    configuration is not covered. Called before a dispatcher is usable, because a control
    checked after the fact is not a control.
    """
    decision = evaluate(settings)
    if settings.governance.require_attestation and not decision.allowed:
        raise GovernanceError(f"Refused by policy {POLICY_ID}: {decision.reason}")
    if not decision.allowed:
        logger.info("Configuration is not attested (%s). Enforcement is off.", decision.reason)
    return decision
