"""
Signatures, and what each kind actually proves.

HMAC proves custody of a shared secret. Anyone who can verify an HMAC can also produce
one, so an HMAC on an approval token establishes only that *something holding the key*
minted it — and the agent process holds the key. It is evidence of custody, not of
authorship, and it cannot distinguish a human operator from the code asking for consent.

Ed25519 separates the two. The operator keeps a private key the framework never sees; the
framework keeps only public keys, so it can check a signature and cannot forge one. That
is what makes an approval evidence about *who*, which is what Laws 2 and 9 actually ask
for and what HMAC could never supply.

Signatures are stored as `algorithm:key_id:value`. A bare hex string with no prefix is a
legacy HMAC signature and is still verified as one, so existing checkpoints and ledgers
remain readable.
"""

from __future__ import annotations

import binascii
import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Mapping, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

HMAC_SHA256 = "hmac-sha256"
ED25519 = "ed25519"

OPERATOR_ID_ENV = "ORRERY_OPERATOR_ID"
OPERATOR_PRIVATE_KEY_ENV = "ORRERY_OPERATOR_PRIVATE_KEY"
OPERATOR_KEYRING_ENV = "ORRERY_OPERATOR_KEYRING"

_SEPARATOR = ":"


class SigningError(Exception):
    """Raised when signing or verification cannot be performed as configured."""


def _ed25519():
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise SigningError(
            "Ed25519 signing requires the 'cryptography' package. Install orrery[signing]. "
            "Falling back to HMAC here would silently downgrade a proof of authorship to a "
            "proof of custody."
        ) from exc
    return ed25519


def ed25519_available() -> bool:
    try:
        _ed25519()
    except SigningError:
        return False
    return True


class SignatureEnvelope(BaseModel):
    """A signature that names the algorithm and the key that produced it."""

    algorithm: str
    key_id: str
    value: str

    def encode(self) -> str:
        return _SEPARATOR.join((self.algorithm, self.key_id, self.value))


def decode_signature(raw: Optional[str]) -> Optional[SignatureEnvelope]:
    """
    Returns the envelope, or None for a legacy bare-hex HMAC signature or absent value.
    """
    if not raw:
        return None
    parts = raw.split(_SEPARATOR, 2)
    if len(parts) != 3:
        return None
    algorithm, key_id, value = parts
    if algorithm not in (HMAC_SHA256, ED25519):
        return None
    return SignatureEnvelope(algorithm=algorithm, key_id=key_id, value=value)


def is_asymmetric(raw: Optional[str]) -> bool:
    envelope = decode_signature(raw)
    return envelope is not None and envelope.algorithm == ED25519


def generate_operator_key() -> tuple[str, str]:
    """
    Returns `(private_seed_hex, public_key_hex)` for a new operator identity.
    """
    ed25519 = _ed25519()
    from cryptography.hazmat.primitives import serialization

    private = ed25519.Ed25519PrivateKey.generate()
    seed = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return seed.hex(), public.hex()


def _read_key_material(value: str) -> bytes:
    """
    Accepts raw hex or a path to a file containing it. A key on disk with restrictive
    permissions beats a key in an environment variable that every child process inherits.
    """
    candidate = Path(value)
    try:
        if candidate.is_file():
            value = candidate.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SigningError(f"could not read key material from {candidate}: {exc}") from exc

    try:
        return bytes.fromhex(value.strip())
    except (ValueError, binascii.Error) as exc:
        raise SigningError("key material must be hex, or a path to a file containing hex") from exc


class OperatorSigner:
    """
    One operator's private key. Held by whoever is authorizing, not by the framework.
    """

    algorithm = ED25519

    def __init__(self, key_id: str, private_seed: bytes):
        if not key_id:
            raise SigningError("an operator signer must have a key id")
        ed25519 = _ed25519()
        try:
            self._private = ed25519.Ed25519PrivateKey.from_private_bytes(private_seed)
        except ValueError as exc:
            raise SigningError(f"invalid Ed25519 private key: {exc}") from exc
        self.key_id = key_id

    @classmethod
    def from_env(cls) -> Optional["OperatorSigner"]:
        key_id = os.environ.get(OPERATOR_ID_ENV)
        material = os.environ.get(OPERATOR_PRIVATE_KEY_ENV)
        if not key_id or not material:
            return None
        return cls(key_id, _read_key_material(material))

    def public_key_hex(self) -> str:
        from cryptography.hazmat.primitives import serialization

        return self._private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        ).hex()

    def sign(self, digest: str) -> str:
        signature = self._private.sign(digest.encode("utf-8"))
        return SignatureEnvelope(
            algorithm=ED25519, key_id=self.key_id, value=signature.hex()
        ).encode()


class OperatorKeyring:
    """
    The public half. Enough to check who signed something, never enough to sign as them.
    """

    def __init__(self, public_keys: Optional[Mapping[str, str]] = None):
        self._keys: Dict[str, bytes] = {}
        for key_id, material in (public_keys or {}).items():
            self._keys[key_id] = bytes.fromhex(material) if isinstance(material, str) else material

    @property
    def key_ids(self) -> list[str]:
        return sorted(self._keys)

    def add(self, key_id: str, public_key_hex: str) -> None:
        self._keys[key_id] = bytes.fromhex(public_key_hex)

    @classmethod
    def from_file(cls, path: Path) -> "OperatorKeyring":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, json.JSONDecodeError) as exc:
            raise SigningError(f"could not read operator keyring at {path}: {exc}") from exc

        operators = raw.get("operators", raw)
        if not isinstance(operators, dict):
            raise SigningError(f"operator keyring at {path} must map key ids to public keys")
        return cls(operators)

    @classmethod
    def from_env(cls) -> "OperatorKeyring":
        path = os.environ.get(OPERATOR_KEYRING_ENV)
        return cls.from_file(Path(path)) if path else cls()

    def verify(self, digest: str, raw_signature: Optional[str]) -> bool:
        """
        True only if the signature is Ed25519, names a key this ring holds, and checks out.
        An unknown key id is a verification failure, not an unverified pass.
        """
        envelope = decode_signature(raw_signature)
        if envelope is None or envelope.algorithm != ED25519:
            return False

        public_key_bytes = self._keys.get(envelope.key_id)
        if public_key_bytes is None:
            logger.warning("Signature names unknown operator key id %r.", envelope.key_id)
            return False

        ed25519 = _ed25519()
        try:
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            public_key.verify(bytes.fromhex(envelope.value), digest.encode("utf-8"))
        except Exception:
            return False
        return True


Keyring = OperatorKeyring


def signer_from_env() -> Optional[OperatorSigner]:
    """
    The configured operator signer, or None. Returns None rather than raising when nothing
    is configured; a missing signer is a deployment choice, and the policy layer decides
    whether that choice is acceptable.
    """
    try:
        return OperatorSigner.from_env()
    except SigningError as exc:
        logger.error("Operator signing key is configured but unusable: %s", exc)
        raise


@lru_cache(maxsize=8)
def _keyring_at(path: str, mtime: float) -> OperatorKeyring:
    return OperatorKeyring.from_file(Path(path))


def keyring_from_env() -> OperatorKeyring:
    """
    The configured keyring, cached against the file's mtime so verifying a long ledger does
    not re-read it per event, while an edited keyring still takes effect.
    """
    path = os.environ.get(OPERATOR_KEYRING_ENV)
    if not path:
        return OperatorKeyring()
    try:
        mtime = Path(path).stat().st_mtime
    except OSError:
        return OperatorKeyring()
    return _keyring_at(path, mtime)
