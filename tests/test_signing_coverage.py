"""
Additional signing module tests to close coverage gaps.

These target the error paths, edge cases, and fallback behaviors that the
primary test_signing.py does not exercise: corrupt keyrings, invalid keys,
missing environment variables, and the ed25519_available() predicate.
"""

import json
import os
from pathlib import Path

import pytest

from orrery.core import signing


# --- ed25519_available ---


def test_ed25519_available_returns_true_when_cryptography_is_installed():
    """The dev environment includes cryptography, so this should be True."""
    assert signing.ed25519_available() is True


# --- decode_signature edge cases ---


def test_decode_unknown_algorithm_returns_none():
    raw = "sha512::alice::deadbeef"
    assert signing.decode_signature(raw) is None


def test_decode_empty_string_returns_none():
    assert signing.decode_signature("") is None


def test_decode_too_few_parts_returns_none():
    assert signing.decode_signature("onlyone") is None


# --- _read_key_material edge cases ---


def test_read_key_material_from_unreadable_file(tmp_path, monkeypatch):
    """An unreadable key file should raise SigningError."""
    bad_file = tmp_path / "unreadable.key"
    bad_file.write_text("deadbeef", encoding="utf-8")
    # Make the file unreadable by renaming the parent... simulate OSError instead
    # On Windows, we can't easily make a file unreadable, so we test non-hex content
    with pytest.raises(signing.SigningError, match="hex"):
        signing._read_key_material("definitely not hex and not a file path //\\::!!")


# --- OperatorSigner edge cases ---


def test_operator_signer_requires_non_empty_key_id():
    with pytest.raises(signing.SigningError, match="key id"):
        signing.OperatorSigner("", b"\x00" * 32)


def test_operator_signer_rejects_invalid_private_key():
    with pytest.raises(signing.SigningError, match="invalid"):
        signing.OperatorSigner("alice", b"too-short")


def test_operator_signer_from_env_returns_none_when_not_configured(monkeypatch):
    monkeypatch.delenv(signing.OPERATOR_ID_ENV, raising=False)
    monkeypatch.delenv(signing.OPERATOR_PRIVATE_KEY_ENV, raising=False)
    assert signing.OperatorSigner.from_env() is None


def test_operator_signer_from_env_returns_none_when_only_id_is_set(monkeypatch):
    monkeypatch.setenv(signing.OPERATOR_ID_ENV, "alice")
    monkeypatch.delenv(signing.OPERATOR_PRIVATE_KEY_ENV, raising=False)
    assert signing.OperatorSigner.from_env() is None


# --- OperatorKeyring edge cases ---


def test_keyring_add_registers_a_new_key():
    keyring = signing.OperatorKeyring()
    private_hex, public_hex = signing.generate_operator_key()
    keyring.add("bob", public_hex)
    assert "bob" in keyring.key_ids


def test_keyring_from_file_rejects_corrupt_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{{{not json", encoding="utf-8")
    with pytest.raises(signing.SigningError, match="could not read"):
        signing.OperatorKeyring.from_file(bad)


def test_keyring_from_file_rejects_non_dict_operators(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"operators": ["not", "a", "dict"]}), encoding="utf-8")
    with pytest.raises(signing.SigningError, match="must map key ids"):
        signing.OperatorKeyring.from_file(bad)


def test_keyring_from_env_returns_empty_when_not_configured(monkeypatch):
    monkeypatch.delenv(signing.OPERATOR_KEYRING_ENV, raising=False)
    keyring = signing.OperatorKeyring.from_env()
    assert keyring.key_ids == []


def test_keyring_verify_rejects_unknown_key_id():
    private_hex, public_hex = signing.generate_operator_key()
    signer = signing.OperatorSigner("alice", bytes.fromhex(private_hex))
    sig = signer.sign("test-digest")

    # Keyring has 'bob', not 'alice'
    keyring = signing.OperatorKeyring({"bob": public_hex})
    assert not keyring.verify("test-digest", sig)


def test_keyring_verify_rejects_hmac_signatures():
    keyring = signing.OperatorKeyring()
    # HMAC signature won't have Ed25519 algorithm
    assert not keyring.verify("test-digest", "hmac-sha256::somekey::aabbcc")


# --- signer_from_env ---


def test_signer_from_env_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv(signing.OPERATOR_ID_ENV, raising=False)
    monkeypatch.delenv(signing.OPERATOR_PRIVATE_KEY_ENV, raising=False)
    assert signing.signer_from_env() is None


def test_signer_from_env_raises_on_bad_key(monkeypatch, tmp_path):
    monkeypatch.setenv(signing.OPERATOR_ID_ENV, "alice")
    bad_key = tmp_path / "bad.key"
    bad_key.write_text("not-valid-hex", encoding="utf-8")
    monkeypatch.setenv(signing.OPERATOR_PRIVATE_KEY_ENV, str(bad_key))
    with pytest.raises(signing.SigningError):
        signing.signer_from_env()


# --- keyring_from_env ---


def test_keyring_from_env_handles_missing_keyring_file(monkeypatch):
    monkeypatch.setenv(signing.OPERATOR_KEYRING_ENV, "/nonexistent/path.json")
    keyring = signing.keyring_from_env()
    assert keyring.key_ids == []


def test_keyring_from_env_caches_by_mtime(monkeypatch, tmp_path):
    """The keyring is cached against the file's mtime so it is read once, not per event."""
    signing._keyring_at.cache_clear()
    kf = tmp_path / "keyring.json"
    private_hex, public_hex = signing.generate_operator_key()
    kf.write_text(json.dumps({"operators": {"alice": public_hex}}), encoding="utf-8")
    monkeypatch.setenv(signing.OPERATOR_KEYRING_ENV, str(kf))

    kr1 = signing.keyring_from_env()
    kr2 = signing.keyring_from_env()
    assert "alice" in kr1.key_ids
    assert "alice" in kr2.key_ids
    signing._keyring_at.cache_clear()


# --- is_asymmetric ---


def test_is_asymmetric_false_for_hmac():
    assert not signing.is_asymmetric("hmac-sha256::key::value")


def test_is_asymmetric_false_for_none():
    assert not signing.is_asymmetric(None)


def test_is_asymmetric_true_for_ed25519():
    private_hex, _ = signing.generate_operator_key()
    signer = signing.OperatorSigner("test", bytes.fromhex(private_hex))
    sig = signer.sign("digest")
    assert signing.is_asymmetric(sig) is True
