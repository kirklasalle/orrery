"""
Tamper-evidence for the checkpoint chain.

Every checkpoint carries a SHA-256 digest of its own content plus the digest of its
predecessor, so a cycle's history is a hash chain: altering any past checkpoint breaks
every link after it.

Honest limits. An unsigned chain detects corruption and casual editing, not a motivated
attacker, who can simply recompute the chain.

Two signing modes, and they do not prove the same thing. `ORRERY_CHECKPOINT_KEY` adds an
HMAC-SHA256 signature: forgery then requires the secret, but every party that can verify
also holds it, so it proves custody rather than authorship. Configure an operator identity
(`ORRERY_OPERATOR_ID` + `ORRERY_OPERATOR_PRIVATE_KEY`) and the chain is signed with
Ed25519 instead, which the framework can verify from a public keyring it could not sign
with. Set `integrity.require_signature` to refuse unsigned checkpoints, and
`integrity.require_asymmetric` to refuse HMAC ones.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from orrery.core import signing

logger = logging.getLogger(__name__)

CHECKPOINT_KEY_ENV = "ORRERY_CHECKPOINT_KEY"

# Excluded from the digest because they are the digest.
_INTEGRITY_FIELDS = ("content_hash", "signature")

GENESIS_HASH = "0" * 64


class IntegrityError(Exception):
    """Raised when a checkpoint fails verification and `require_signature` is set."""


class ChainVerification(BaseModel):
    cycle_id: str
    verified: bool
    checked: int = 0
    truncated: bool = False
    failures: List[str] = []

    @property
    def summary(self) -> str:
        if self.verified:
            note = " (chain begins after retention pruning)" if self.truncated else ""
            return f"{self.checked} checkpoint(s) verified{note}."
        return "; ".join(self.failures)


def canonical_json(payload: Dict[str, Any]) -> str:
    """
    Byte-stable JSON. Two equal states must produce one digest, on any machine, in any order.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def checkpoint_digest(checkpoint: Any) -> str:
    """
    SHA-256 over the checkpoint's content and its `prev_hash` link.
    """
    payload = checkpoint.model_dump(mode="json", exclude=set(_INTEGRITY_FIELDS))
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def get_signing_key() -> Optional[bytes]:
    key = os.environ.get(CHECKPOINT_KEY_ENV)
    return key.encode("utf-8") if key else None


def sign_digest(digest: str, key: Optional[bytes] = None) -> Optional[str]:
    """
    Signs with the operator's Ed25519 key when one is configured, and falls back to HMAC
    only when no operator identity exists. The stronger proof is never silently replaced
    by the weaker one.
    """
    if key is None:
        signer = signing.signer_from_env()
        if signer is not None:
            return signer.sign(digest)

    key = key if key is not None else get_signing_key()
    if not key:
        return None
    return hmac.new(key, digest.encode("utf-8"), hashlib.sha256).hexdigest()


def signature_matches(digest: str, signature: Optional[str], key: Optional[bytes] = None) -> bool:
    if signature is None:
        return False

    if signing.is_asymmetric(signature):
        return signing.keyring_from_env().verify(digest, signature)

    expected = _hmac_digest(digest, key if key is not None else get_signing_key())
    if expected is None:
        return False
    return hmac.compare_digest(expected, signature)


def _hmac_digest(digest: str, key: Optional[bytes]) -> Optional[str]:
    if not key:
        return None
    return hmac.new(key, digest.encode("utf-8"), hashlib.sha256).hexdigest()


def seal(checkpoint: Any, prev_hash: Optional[str], key: Optional[bytes] = None) -> Any:
    """
    Links a checkpoint to its predecessor and stamps it with a digest and, if a key is
    configured, a signature. Called once, at creation.
    """
    checkpoint.prev_hash = prev_hash or GENESIS_HASH
    checkpoint.content_hash = checkpoint_digest(checkpoint)
    checkpoint.signature = sign_digest(checkpoint.content_hash, key)
    return checkpoint


def verify(
    checkpoint: Any,
    require_signature: bool = False,
    key: Optional[bytes] = None,
    require_asymmetric: bool = False,
) -> Optional[str]:
    """
    Returns None when the checkpoint is intact, or a human-readable reason when it is not.
    """
    if not checkpoint.content_hash:
        return f"checkpoint {checkpoint.checkpoint_id} carries no content hash"

    expected = checkpoint_digest(checkpoint)
    if not hmac.compare_digest(expected, checkpoint.content_hash):
        return (
            f"checkpoint {checkpoint.checkpoint_id} content hash mismatch "
            f"(stored {checkpoint.content_hash[:12]}..., computed {expected[:12]}...)"
        )

    if require_asymmetric and not signing.is_asymmetric(checkpoint.signature):
        return (
            f"checkpoint {checkpoint.checkpoint_id} is not signed with an operator key; "
            f"an HMAC signature proves custody of a shared secret, not authorship"
        )

    if require_signature or require_asymmetric:
        if not signature_matches(checkpoint.content_hash, checkpoint.signature, key):
            return f"checkpoint {checkpoint.checkpoint_id} signature is missing or invalid"
    elif checkpoint.signature is not None and (
        get_signing_key() is not None or signing.is_asymmetric(checkpoint.signature)
    ):
        if not signature_matches(checkpoint.content_hash, checkpoint.signature, key):
            return f"checkpoint {checkpoint.checkpoint_id} signature does not match the configured key"

    return None
