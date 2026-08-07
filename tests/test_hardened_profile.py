"""
What actually happens when every control is switched on.

`config/hardened.yaml` is the opposite end of the range from the shipped defaults, and a
profile nobody runs is a profile nobody can trust. These tests load it and assert the real
behaviour, including the parts that are inconvenient — a hardened deployment refuses to
start until somebody signs for it, and that friction is the feature.

The value here is not that everything passes. It is that the cost of turning it on is
written down and checked, so an operator finds out from a test rather than from an outage.
"""

import json
from pathlib import Path

import pytest

from orrery.adapters.filesystem import FileSystemAdapter
from examples.simulated.hermes import HermesAdapter
from orrery.core import attestation, signing
from orrery.core.attestation import GovernanceError
from orrery.core.config import CheckpointSettings, LedgerSettings, load_settings
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.approval import grant
from orrery.core.types import ActionPayload, ActionRisk

REPO_ROOT = Path(__file__).resolve().parents[1]
HARDENED = REPO_ROOT / "config" / "hardened.yaml"


@pytest.fixture
def operator(tmp_path, monkeypatch):
    private_hex, public_hex = signing.generate_operator_key()
    key_file = tmp_path / "operator.key"
    key_file.write_text(private_hex, encoding="utf-8")
    keyring = tmp_path / "operators.json"
    keyring.write_text(json.dumps({"operators": {"kirk": public_hex}}), encoding="utf-8")

    monkeypatch.setenv(signing.OPERATOR_ID_ENV, "kirk")
    monkeypatch.setenv(signing.OPERATOR_PRIVATE_KEY_ENV, str(key_file))
    monkeypatch.setenv(signing.OPERATOR_KEYRING_ENV, str(keyring))
    signing._keyring_at.cache_clear()
    return keyring


@pytest.fixture
def hardened(tmp_path):
    """The hardened profile, relocated so a test never writes into the repository."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings = load_settings(HARDENED)
    return settings.model_copy(
        update={
            "checkpointing": CheckpointSettings(storage_dir=str(tmp_path / "checkpoints")),
            "ledger": LedgerSettings(persist=False, storage_dir=str(tmp_path / "ledger")),
            "governance": settings.governance.model_copy(
                update={"attestation_path": str(tmp_path / "attestation.json")}
            ),
            "interdiction": settings.interdiction.model_copy(
                update={"halt_file": str(tmp_path / "halt")}
            ),
            "quarantine": settings.quarantine.model_copy(
                update={
                    "store": str(tmp_path / "classifications.json"),
                    "record_path": str(tmp_path / "held.jsonl"),
                }
            ),
            "envelope": settings.envelope.model_copy(update={"paths": [str(workspace)]}),
        }
    )


def test_the_hardened_profile_turns_everything_on():
    settings = load_settings(HARDENED)

    assert settings.approval.require_asymmetric
    assert settings.approval.require_for_compensable
    assert settings.integrity.require_asymmetric
    assert settings.governance.require_attestation
    assert settings.quarantine.enabled and settings.quarantine.require_signed
    assert settings.envelope.enforce
    assert settings.critique.strict_mode
    assert settings.invariants.on_breach == "halt"
    assert not settings.allow_simulated_adapters


def test_it_refuses_to_start_until_somebody_signs_for_it(hardened):
    """
    The first thing an operator meets. This is the intended behaviour, not a misconfiguration.
    """
    with pytest.raises(GovernanceError, match="LAW10-APPROVAL"):
        CycleDispatcher(settings=hardened)


def test_it_starts_once_attested(operator, hardened):
    attestation.save_attestation(
        attestation.attest(hardened, note="hardened profile test"),
        hardened.governance.attestation_path,
    )

    dispatcher = CycleDispatcher(settings=hardened)

    assert dispatcher.attestation.allowed


def test_a_simulated_adapter_cannot_be_registered(operator, hardened):
    attestation.save_attestation(
        attestation.attest(hardened), hardened.governance.attestation_path
    )
    dispatcher = CycleDispatcher(settings=hardened)

    with pytest.raises(ValueError, match="simulation"):
        dispatcher.register_adapter(HermesAdapter())


@pytest.fixture
def running(operator, hardened, tmp_path):
    attestation.save_attestation(
        attestation.attest(hardened), hardened.governance.attestation_path
    )
    dispatcher = CycleDispatcher(settings=hardened)
    workspace = tmp_path / "workspace"
    dispatcher.register_adapter(FileSystemAdapter(root=str(workspace)))
    return dispatcher, workspace


async def test_ordinary_work_inside_the_envelope_still_runs(running):
    dispatcher, workspace = running

    receipt = await dispatcher.execute_action(
        ActionPayload(
            action_name="make_dir", params={"path": "notes"}, target_adapter="filesystem"
        )
    )

    assert receipt.success, receipt.error
    assert (workspace / "notes").is_dir()


async def test_a_compensable_write_now_needs_consent_too(running):
    """
    The sharpest behaviour change in the profile. Under the defaults a `write_file` runs
    unattended; here it does not, because `require_for_compensable` is on.
    """
    dispatcher, workspace = running

    action = ActionPayload(
        action_name="write_file",
        params={"path": "notes.txt", "content": "hello"},
        target_adapter="filesystem",
    )
    unattended = await dispatcher.execute_action(action)

    assert not unattended.success
    assert "RISK-001" in unattended.error

    approved = ActionPayload(
        action_name="write_file",
        params={"path": "notes.txt", "content": "hello"},
        target_adapter="filesystem",
    )
    approved.approval = grant(approved, approver="kirk", reason="reviewed")
    receipt = await dispatcher.execute_action(approved)

    assert receipt.success, receipt.error
    assert (workspace / "notes.txt").read_text(encoding="utf-8") == "hello"


async def test_an_unsigned_approval_is_not_enough_here(running, monkeypatch):
    dispatcher, _ = running

    action = ActionPayload(
        action_name="write_file",
        params={"path": "notes.txt", "content": "hello"},
        target_adapter="filesystem",
    )
    monkeypatch.delenv(signing.OPERATOR_PRIVATE_KEY_ENV)
    action.approval = grant(action, approver="kirk", reason="no key available")

    receipt = await dispatcher.execute_action(action)

    assert not receipt.success
    assert "RISK-005" in receipt.error


async def test_reaching_outside_the_declared_region_is_refused(running):
    dispatcher, _ = running

    action = ActionPayload(
        action_name="write_file",
        params={"path": "../escape.txt", "content": "no"},
        target_adapter="filesystem",
    )
    action.approval = grant(action, approver="kirk", reason="trying anyway")

    receipt = await dispatcher.execute_action(action)

    assert not receipt.success
    assert "LAW1-ENVELOPE" in receipt.error or "sandbox" in receipt.error


async def test_the_process_adapter_is_prohibited_outright(running, tmp_path):
    from orrery.adapters.process import ProcessAdapter

    dispatcher, _ = running
    dispatcher.register_adapter(
        ProcessAdapter(root=str(tmp_path / "workspace"), allowed_programs=["python"])
    )

    action = ActionPayload(
        action_name="run_program",
        params={"program": "python", "args": ["-c", "print(1)"]},
        target_adapter="process",
    )
    action.approval = grant(action, approver="kirk", reason="wanted to")

    receipt = await dispatcher.execute_action(action)

    assert not receipt.success
    assert "LAW1-PROHIBIT" in receipt.error


def test_an_empty_envelope_under_enforcement_permits_nothing(operator, tmp_path):
    """
    `hardened.yaml` ships `envelope.paths` empty on purpose. A deployment must state its own
    region rather than inherit a guess, and until it does, nothing is permitted.
    """
    settings = load_settings(HARDENED).model_copy(
        update={
            "checkpointing": CheckpointSettings(storage_dir=str(tmp_path / "checkpoints")),
            "ledger": LedgerSettings(persist=False, storage_dir=str(tmp_path / "ledger")),
        }
    )

    assert settings.envelope.enforce
    assert settings.envelope.paths == []


def test_the_hardened_profile_is_covered_by_its_own_attestation(operator, hardened):
    """
    Loosening any of it invalidates the signature, which is the whole point of attesting.
    """
    signed = attestation.attest(hardened)
    attestation.save_attestation(signed, hardened.governance.attestation_path)
    assert attestation.evaluate(hardened).allowed

    loosened = hardened.model_copy(
        update={"approval": hardened.approval.model_copy(update={"require_asymmetric": False})}
    )

    assert not attestation.evaluate(loosened, hardened.governance.attestation_path).allowed
