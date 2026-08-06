"""
Tamper-evidence for the checkpoint chain.

Every checkpoint carries a SHA-256 digest of its own content plus the digest of its
predecessor, so a cycle's history is a hash chain: altering any past checkpoint breaks
every link after it.

Honest limits. An unsigned chain detects corruption and casual editing, not a motivated
attacker, who can simply recompute the chain. Set ORRERY_CHECKPOINT_KEY to add an
HMAC-SHA256 signature, which an attacker cannot forge without the key, and set
`integrity.require_signature` to refuse unsigned checkpoints outright.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

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
    key = key if key is not None else get_signing_key()
    if not key:
        return None
    return hmac.new(key, digest.encode("utf-8"), hashlib.sha256).hexdigest()


def signature_matches(digest: str, signature: Optional[str], key: Optional[bytes] = None) -> bool:
    expected = sign_digest(digest, key)
    if expected is None or signature is None:
        return False
    return hmac.compare_digest(expected, signature)


def seal(checkpoint: Any, prev_hash: Optional[str], key: Optional[bytes] = None) -> Any:
    """
    Links a checkpoint to its predecessor and stamps it with a digest and, if a key is
    configured, a signature. Called once, at creation.
    """
    checkpoint.prev_hash = prev_hash or GENESIS_HASH
    checkpoint.content_hash = checkpoint_digest(checkpoint)
    checkpoint.signature = sign_digest(checkpoint.content_hash, key)
    return checkpoint


def verify(checkpoint: Any, require_signature: bool = False, key: Optional[bytes] = None) -> Optional[str]:
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

    if require_signature:
        if not signature_matches(checkpoint.content_hash, checkpoint.signature, key):
            return f"checkpoint {checkpoint.checkpoint_id} signature is missing or invalid"
    elif checkpoint.signature is not None and get_signing_key() is not None:
        if not signature_matches(checkpoint.content_hash, checkpoint.signature, key):
            return f"checkpoint {checkpoint.checkpoint_id} signature does not match the configured key"

    return None
