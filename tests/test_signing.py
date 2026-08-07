"""
Tests for operator signing.

The point of these is the asymmetry itself. An HMAC test can only show that a holder of
the key can sign and a non-holder cannot. These show something stronger: that a process
holding *only the public keyring* can verify an approval and cannot produce one.
"""

import json
from pathlib import Path

import pytest

from orrery.core import integrity, signing
from orrery.core.approval import ApprovalGate, grant, signature_is_valid
from orrery.core.state import CheckpointManager
from orrery.core.types import ActionPayload, ActionRisk, ApprovalToken, StateContext


@pytest.fixture
def operator(tmp_path, monkeypatch):
    """A configured operator identity, plus the keyring that can check its signatures."""
    private_hex, public_hex = signing.generate_operator_key()

    key_file = tmp_path / "alice.key"
    key_file.write_text(private_hex, encoding="utf-8")

    keyring_file = tmp_path / "operators.json"
    keyring_file.write_text(json.dumps({"operators": {"alice": public_hex}}), encoding="utf-8")

    monkeypatch.setenv(signing.OPERATOR_ID_ENV, "alice")
    monkeypatch.setenv(signing.OPERATOR_PRIVATE_KEY_ENV, str(key_file))
    monkeypatch.setenv(signing.OPERATOR_KEYRING_ENV, str(keyring_file))
    monkeypatch.delenv("ORRERY_APPROVAL_KEY", raising=False)
    monkeypatch.delenv("ORRERY_CHECKPOINT_KEY", raising=False)
    signing._keyring_at.cache_clear()

    return {"public_hex": public_hex, "keyring": keyring_file, "key_file": key_file}


def _action() -> ActionPayload:
    return ActionPayload(action_name="delete_file", risk=ActionRisk.IRREVERSIBLE)


def test_operator_signed_approval_verifies_and_a_forged_one_does_not(operator):
    action = _action()
    token = grant(action, approver="alice", reason="reviewed")

    assert signing.is_asymmetric(token.signature)
    assert signature_is_valid(token)

    forged = token.model_copy(update={"reason": "reviewed and also deleted everything else"})
    assert not signature_is_valid(forged), "the signature must cover the whole token"


def test_verifier_without_the_private_key_can_check_but_not_sign(operator, monkeypatch):
    """
    The property HMAC cannot have: verification and forgery are different capabilities.
    """
    token = grant(_action(), approver="alice")

    monkeypatch.delenv(signing.OPERATOR_PRIVATE_KEY_ENV)
    monkeypatch.delenv(signing.OPERATOR_ID_ENV)

    assert signature_is_valid(token), "a public keyring is enough to verify"
    assert signing.signer_from_env() is None, "and not enough to sign"

    unsigned = grant(_action(), approver="alice")
    assert unsigned.signature is None
    assert not signature_is_valid(unsigned)


def test_a_signature_cannot_be_issued_in_another_operators_name(operator, tmp_path, monkeypatch):
    """
    Holding a key must not let you approve as somebody else.
    """
    mallory_private, mallory_public = signing.generate_operator_key()
    keyring = json.loads(operator["keyring"].read_text(encoding="utf-8"))
    keyring["operators"]["mallory"] = mallory_public
    operator["keyring"].write_text(json.dumps(keyring), encoding="utf-8")
    signing._keyring_at.cache_clear()

    mallory_key = tmp_path / "mallory.key"
    mallory_key.write_text(mallory_private, encoding="utf-8")
    monkeypatch.setenv(signing.OPERATOR_ID_ENV, "mallory")
    monkeypatch.setenv(signing.OPERATOR_PRIVATE_KEY_ENV, str(mallory_key))

    token = grant(_action(), approver="alice")

    assert not signature_is_valid(token), (
        "a token signed by mallory must not verify as an approval from alice"
    )


def test_unknown_key_id_is_a_failure_not_an_unverified_pass(operator, tmp_path, monkeypatch):
    stranger_private, _ = signing.generate_operator_key()
    stranger_key = tmp_path / "stranger.key"
    stranger_key.write_text(stranger_private, encoding="utf-8")
    monkeypatch.setenv(signing.OPERATOR_ID_ENV, "stranger")
    monkeypatch.setenv(signing.OPERATOR_PRIVATE_KEY_ENV, str(stranger_key))

    token = grant(_action(), approver="stranger")
    assert not signature_is_valid(token)


def test_hmac_approval_is_refused_when_asymmetric_is_required(monkeypatch):
    """
    RISK-005. A valid shared-secret signature is still the wrong kind of evidence.
    """
    monkeypatch.delenv(signing.OPERATOR_ID_ENV, raising=False)
    monkeypatch.delenv(signing.OPERATOR_PRIVATE_KEY_ENV, raising=False)
    monkeypatch.setenv("ORRERY_APPROVAL_KEY", "a-shared-secret")

    action = _action()
    token = grant(action, approver="alice")
    action.approval = token

    assert signature_is_valid(token), "the HMAC itself is valid"

    permissive = ApprovalGate(require_signed_approval=True)
    assert permissive.evaluate(action).allowed

    strict = ApprovalGate(require_asymmetric_approval=True)
    decision = strict.evaluate(action)
    assert not decision.allowed
    assert decision.policy_id == "RISK-005"
    assert "cannot distinguish the operator from the agent" in decision.reason


def test_asymmetric_approval_satisfies_the_strict_gate(operator):
    action = _action()
    action.approval = grant(action, approver="alice")

    decision = ApprovalGate(require_asymmetric_approval=True).evaluate(action)
    assert decision.allowed, decision.reason


def test_unsigned_approval_is_refused_when_asymmetric_is_required(operator, monkeypatch):
    monkeypatch.delenv(signing.OPERATOR_PRIVATE_KEY_ENV)
    action = _action()
    action.approval = ApprovalToken(action_id=action.action_id, approver="alice")

    decision = ApprovalGate(require_asymmetric_approval=True).evaluate(action)
    assert not decision.allowed
    assert decision.policy_id == "RISK-005"


def test_checkpoints_are_signed_with_the_operator_key(operator, tmp_path):
    """
    LAW9-SIGN. The chain becomes attributable to a person, not to whoever held a secret.
    """
    manager = CheckpointManager(storage_dir=str(tmp_path / "checkpoints"), require_asymmetric=True)
    context = StateContext(goal="attributable history")

    checkpoint = manager.create_checkpoint(context)

    assert signing.is_asymmetric(checkpoint.signature)
    envelope = signing.decode_signature(checkpoint.signature)
    assert envelope.key_id == "alice"
    assert integrity.verify(checkpoint, require_asymmetric=True) is None
    assert manager.verify_chain(context.cycle_id).verified


def test_hmac_signed_checkpoint_is_refused_when_asymmetric_is_required(monkeypatch, tmp_path):
    monkeypatch.delenv(signing.OPERATOR_ID_ENV, raising=False)
    monkeypatch.delenv(signing.OPERATOR_PRIVATE_KEY_ENV, raising=False)
    monkeypatch.setenv("ORRERY_CHECKPOINT_KEY", "a-shared-secret")

    manager = CheckpointManager(storage_dir=str(tmp_path / "checkpoints"))
    checkpoint = manager.create_checkpoint(StateContext(goal="shared secret only"))

    assert not signing.is_asymmetric(checkpoint.signature)
    reason = integrity.verify(checkpoint, require_asymmetric=True)
    assert reason and "proves custody of a shared secret, not authorship" in reason


def test_legacy_bare_hex_signatures_still_verify(monkeypatch, tmp_path):
    """
    Existing HMAC-signed history must remain readable after the upgrade.
    """
    monkeypatch.delenv(signing.OPERATOR_ID_ENV, raising=False)
    monkeypatch.delenv(signing.OPERATOR_PRIVATE_KEY_ENV, raising=False)
    monkeypatch.setenv("ORRERY_CHECKPOINT_KEY", "legacy-key")

    signature = integrity.sign_digest("a" * 64)
    assert signing.decode_signature(signature) is None, "legacy format is bare hex"
    assert integrity.signature_matches("a" * 64, signature)


def test_key_material_may_be_hex_or_a_file(tmp_path):
    private_hex, public_hex = signing.generate_operator_key()
    from_hex = signing.OperatorSigner("alice", bytes.fromhex(private_hex))

    key_file = tmp_path / "alice.key"
    key_file.write_text(f"  {private_hex}\n", encoding="utf-8")
    from_file = signing.OperatorSigner("alice", signing._read_key_material(str(key_file)))

    assert from_hex.public_key_hex() == from_file.public_key_hex() == public_hex


def test_malformed_key_material_is_rejected():
    with pytest.raises(signing.SigningError):
        signing._read_key_material("not-hex-at-all")


def test_keyring_file_may_be_absent():
    assert signing.OperatorKeyring.from_file(Path("does-not-exist.json")).key_ids == []
