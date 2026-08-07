"""
Tests for configuration attestation (LAW10-APPROVAL).

Every control in this framework is a boolean away from being off. These tests check that
turning one off is an attributable act rather than a quiet edit.
"""

import json

import pytest

from orrery.core import attestation, signing
from orrery.core.attestation import GovernanceError
from orrery.core.config import (
    ApprovalSettings,
    CheckpointSettings,
    GovernanceSettings,
    LedgerSettings,
    Settings,
)
from orrery.core.dispatcher import CycleDispatcher


@pytest.fixture
def operator(tmp_path, monkeypatch):
    private_hex, public_hex = signing.generate_operator_key()
    key_file = tmp_path / "governance.key"
    key_file.write_text(private_hex, encoding="utf-8")
    keyring_file = tmp_path / "operators.json"
    keyring_file.write_text(json.dumps({"operators": {"governance": public_hex}}), encoding="utf-8")

    monkeypatch.setenv(signing.OPERATOR_ID_ENV, "governance")
    monkeypatch.setenv(signing.OPERATOR_PRIVATE_KEY_ENV, str(key_file))
    monkeypatch.setenv(signing.OPERATOR_KEYRING_ENV, str(keyring_file))
    signing._keyring_at.cache_clear()
    return keyring_file


@pytest.fixture
def settings(tmp_path):
    return Settings(
        checkpointing=CheckpointSettings(storage_dir=str(tmp_path / "checkpoints")),
        ledger=LedgerSettings(persist=False, storage_dir=str(tmp_path / "ledger")),
        governance=GovernanceSettings(attestation_path=str(tmp_path / "attestation.json")),
    )


def test_digest_ignores_paths_but_tracks_authority(tmp_path, settings):
    """
    Storage paths vary per machine and grant no authority. Limits do.
    """
    relocated = settings.model_copy(
        update={"checkpointing": CheckpointSettings(storage_dir=str(tmp_path / "elsewhere"))}
    )
    assert attestation.configuration_digest(relocated) == attestation.configuration_digest(settings)

    loosened = settings.model_copy(
        update={"approval": ApprovalSettings(require_for_irreversible=False)}
    )
    assert attestation.configuration_digest(loosened) != attestation.configuration_digest(settings)


def test_digest_covers_the_governance_registry(monkeypatch, settings):
    """
    Downgrading a policy to NOT_ENFORCED must break the attestation, or the registry is
    just a comment.
    """
    before = attestation.configuration_digest(settings)
    monkeypatch.setattr(attestation, "POLICIES", attestation.POLICIES[:-1])
    assert attestation.configuration_digest(settings) != before


def test_attest_then_verify_round_trip(operator, settings):
    signed = attestation.attest(settings, note="reviewed by governance")
    attestation.save_attestation(signed, settings.governance.attestation_path)

    decision = attestation.evaluate(settings)
    assert decision.allowed, decision.reason
    assert signed.approved_by == "governance"


def test_a_changed_limit_invalidates_the_attestation(operator, settings):
    attestation.save_attestation(
        attestation.attest(settings), settings.governance.attestation_path
    )

    loosened = settings.model_copy(
        update={"approval": ApprovalSettings(require_for_irreversible=False)}
    )
    decision = attestation.evaluate(loosened)

    assert not decision.allowed
    assert "configuration has changed since it was approved" in decision.reason


def test_missing_attestation_is_a_refusal(settings):
    decision = attestation.evaluate(settings)
    assert not decision.allowed
    assert "no attestation found" in decision.reason


def test_attestation_requires_an_operator_key(monkeypatch, settings):
    monkeypatch.delenv(signing.OPERATOR_ID_ENV, raising=False)
    monkeypatch.delenv(signing.OPERATOR_PRIVATE_KEY_ENV, raising=False)

    with pytest.raises(GovernanceError, match="requires an operator identity"):
        attestation.attest(settings)


def test_hmac_signature_is_not_accepted_as_governance_approval(operator, settings):
    forged = attestation.Attestation(
        digest=attestation.configuration_digest(settings),
        signature="a" * 64,
        approved_by="governance",
    )
    attestation.save_attestation(forged, settings.governance.attestation_path)

    decision = attestation.evaluate(settings)
    assert not decision.allowed
    assert "not signed with an operator key" in decision.reason


def test_attestation_cannot_claim_someone_elses_approval(operator, tmp_path, settings, monkeypatch):
    other_private, other_public = signing.generate_operator_key()
    keyring = json.loads(operator.read_text(encoding="utf-8"))
    keyring["operators"]["intern"] = other_public
    operator.write_text(json.dumps(keyring), encoding="utf-8")
    signing._keyring_at.cache_clear()

    intern_key = tmp_path / "intern.key"
    intern_key.write_text(other_private, encoding="utf-8")
    monkeypatch.setenv(signing.OPERATOR_ID_ENV, "intern")
    monkeypatch.setenv(signing.OPERATOR_PRIVATE_KEY_ENV, str(intern_key))

    signed = attestation.attest(settings)
    relabelled = signed.model_copy(update={"approved_by": "governance"})
    attestation.save_attestation(relabelled, settings.governance.attestation_path)

    decision = attestation.evaluate(settings)
    assert not decision.allowed
    assert "signed by a different key" in decision.reason


def test_dispatcher_refuses_to_start_on_an_unattested_configuration(settings):
    """
    LAW10-APPROVAL. A check that runs after the dispatcher is usable is not a check.
    """
    guarded = settings.model_copy(
        update={
            "governance": GovernanceSettings(
                require_attestation=True,
                attestation_path=settings.governance.attestation_path,
            )
        }
    )

    with pytest.raises(GovernanceError, match="LAW10-APPROVAL"):
        CycleDispatcher(settings=guarded)


def test_dispatcher_starts_on_an_attested_configuration(operator, settings):
    guarded = settings.model_copy(
        update={
            "governance": GovernanceSettings(
                require_attestation=True,
                attestation_path=settings.governance.attestation_path,
            )
        }
    )
    attestation.save_attestation(
        attestation.attest(guarded), guarded.governance.attestation_path
    )

    dispatcher = CycleDispatcher(settings=guarded)
    assert dispatcher.attestation.allowed


def test_unattested_configuration_runs_when_enforcement_is_off(settings):
    dispatcher = CycleDispatcher(settings=settings)
    assert not dispatcher.attestation.allowed, "the report is honest even when not enforced"
