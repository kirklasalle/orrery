"""
Tests for quarantine.

The load-bearing test here is `test_a_classification_is_not_an_authorisation`. If that ever
inverts, quarantine has become a permission cache with a governance label on it.
"""

import json
from pathlib import Path

import pytest

from orrery.adapters.base import BaseAdapter
from orrery.core import signing
from orrery.core.approval import grant
from orrery.core.config import (
    CheckpointSettings,
    InterdictionSettings,
    LedgerSettings,
    QuarantineSettings,
    Settings,
)
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.quarantine import (
    Classification,
    ClassificationStore,
    QuarantineGate,
    classification_is_valid,
    sign_classification,
)
from orrery.core.types import ActionPayload, ActionRisk, ExecutionReceipt, StateContext


class NoteAdapter(BaseAdapter):
    """A third-party adapter that declares one action and implements two."""

    declared_risks = {"read_note": ActionRisk.READ_ONLY}

    def __init__(self):
        super().__init__(name="notes")
        self.performed = []

    async def perceive_environment(self, context):
        return {"platform": "notes"}

    async def execute_action(self, action):
        self.performed.append(action.action_name)
        return ExecutionReceipt(
            action_id=action.action_id, action_name=action.action_name, success=True
        )


@pytest.fixture
def env(tmp_path):
    settings = Settings(
        checkpointing=CheckpointSettings(storage_dir=str(tmp_path / "checkpoints")),
        ledger=LedgerSettings(persist=False, storage_dir=str(tmp_path / "ledger")),
        interdiction=InterdictionSettings(halt_file=str(tmp_path / "halt")),
        quarantine=QuarantineSettings(
            enabled=True,
            store=str(tmp_path / "classifications.json"),
            record_path=str(tmp_path / "quarantine" / "held.jsonl"),
        ),
    )
    dispatcher = CycleDispatcher(settings=settings)
    adapter = NoteAdapter()
    dispatcher.register_adapter(adapter)
    return {"dispatcher": dispatcher, "adapter": adapter, "settings": settings, "tmp": tmp_path}


def _act(name, **params):
    return ActionPayload(action_name=name, params=params, target_adapter="notes")


async def test_a_declared_action_is_not_held(env):
    receipt = await env["dispatcher"].execute_action(_act("read_note", id="1"))

    assert receipt.success, receipt.error
    assert env["adapter"].performed == ["read_note"]


async def test_an_undeclared_action_is_held_not_guessed_at(env):
    """
    The adapter never declared `purge_notes`. Its risk is unknown, and an unknown is not an
    IRREVERSIBLE — it is an unknown.
    """
    receipt = await env["dispatcher"].execute_action(_act("purge_notes", id="1"))

    assert not receipt.success
    assert "LAW1-QUARANTINE" in receipt.error
    assert "does not declare action" in receipt.error
    assert env["adapter"].performed == [], "a held action must not reach the adapter"


async def test_approval_cannot_release_an_action_from_quarantine(env):
    """
    Quarantine and approval answer different questions. Consent to an action nobody has
    characterised is not consent to anything in particular.
    """
    action = _act("purge_notes", id="1")
    action.approval = grant(action, approver="operator", reason="go ahead")

    receipt = await env["dispatcher"].execute_action(action)

    assert not receipt.success
    assert "LAW1-QUARANTINE" in receipt.error
    assert env["adapter"].performed == []


async def test_a_classification_releases_the_action(env):
    store_path = Path(env["settings"].quarantine.store)
    store = ClassificationStore(
        [
            Classification(
                adapter="notes",
                action_name="purge_notes",
                risk=ActionRisk.READ_ONLY,
                classified_by="kirk",
                note="reviewed the implementation; it only reads",
            )
        ]
    )
    store.save(store_path)
    env["dispatcher"].quarantine_gate.store = ClassificationStore.from_file(store_path)

    receipt = await env["dispatcher"].execute_action(_act("purge_notes", id="1"))

    assert receipt.success, receipt.error
    assert env["adapter"].performed == ["purge_notes"]


async def test_a_classification_is_not_an_authorisation(env):
    """
    The property that keeps quarantine from becoming a permission cache. Saying what an
    action *is* must never be the same act as permitting it.
    """
    store = ClassificationStore(
        [
            Classification(
                adapter="notes",
                action_name="purge_notes",
                risk=ActionRisk.IRREVERSIBLE,
                classified_by="kirk",
                note="it deletes; there is no undo",
            )
        ]
    )
    env["dispatcher"].quarantine_gate.store = store

    unapproved = await env["dispatcher"].execute_action(_act("purge_notes", id="1"))
    assert not unapproved.success
    assert "RISK-001" in unapproved.error, "classification must not satisfy the approval gate"
    assert env["adapter"].performed == []

    approved = _act("purge_notes", id="1")
    approved.approval = grant(approved, approver="kirk", reason="reviewed this specific purge")
    receipt = await env["dispatcher"].execute_action(approved)

    assert receipt.success, receipt.error
    assert env["adapter"].performed == ["purge_notes"]


async def test_a_classification_cannot_downgrade_a_declared_risk(env):
    """
    Same rule as planners: the strictest declaration wins, whoever made it.
    """
    env["adapter"].declared_risks = {"burn_notes": ActionRisk.IRREVERSIBLE}
    env["dispatcher"].quarantine_gate.store = ClassificationStore(
        [
            Classification(
                adapter="notes",
                action_name="burn_notes",
                risk=ActionRisk.READ_ONLY,
                classified_by="optimist",
            )
        ]
    )

    receipt = await env["dispatcher"].execute_action(_act("burn_notes"))

    assert not receipt.success
    assert "RISK-001" in receipt.error


async def test_a_held_action_is_ledgered_and_recorded_for_review(env):
    await env["dispatcher"].execute_action(_act("purge_notes", id="1", scope="all"))

    events = [e for e in env["dispatcher"].ledger.events if e.event_type == "action.quarantined"]
    assert events and events[0].policy_id == "LAW1-QUARANTINE"

    record_path = Path(env["settings"].quarantine.record_path)
    assert record_path.is_file()
    written = json.loads(record_path.read_text(encoding="utf-8").splitlines()[0])
    assert written["adapter"] == "notes"
    assert written["action_name"] == "purge_notes"
    assert sorted(written["parameter_keys"]) == ["id", "scope"]


async def test_the_review_queue_records_keys_but_not_values(env):
    """
    A reviewer needs to know an action carried a `patient_record` parameter. They do not
    need its contents, and the queue is not a place to accumulate them.
    """
    await env["dispatcher"].execute_action(_act("purge_notes", patient_record="Jane Doe, DOB..."))

    written = Path(env["settings"].quarantine.record_path).read_text(encoding="utf-8")
    assert "patient_record" in written
    assert "Jane Doe" not in written


async def test_records_outlive_the_cycle_and_deduplicate(env):
    for index in range(3):
        await env["dispatcher"].execute_action(_act("purge_notes", id=str(index)))
    await env["dispatcher"].execute_action(_act("archive_notes"))

    pending = env["dispatcher"].quarantine_gate.pending()

    assert sorted(item.key for item in pending) == ["notes:archive_notes", "notes:purge_notes"]


async def test_classifying_empties_the_queue(env):
    await env["dispatcher"].execute_action(_act("purge_notes"))
    gate = env["dispatcher"].quarantine_gate
    assert len(gate.pending()) == 1

    gate.store.add(
        Classification(
            adapter="notes",
            action_name="purge_notes",
            risk=ActionRisk.COMPENSABLE,
            classified_by="kirk",
        )
    )

    assert gate.pending() == []


async def test_quarantine_is_off_by_default_and_falls_back_to_the_old_fail_safe(tmp_path):
    """
    With quarantine disabled, an undeclared action is still treated as IRREVERSIBLE. That is
    a safe guess — but it is a guess, which is the reason quarantine exists.
    """
    settings = Settings(
        checkpointing=CheckpointSettings(storage_dir=str(tmp_path / "checkpoints")),
        ledger=LedgerSettings(persist=False, storage_dir=str(tmp_path / "ledger")),
        interdiction=InterdictionSettings(halt_file=str(tmp_path / "halt")),
    )
    assert settings.quarantine.enabled is False

    dispatcher = CycleDispatcher(settings=settings)
    dispatcher.register_adapter(NoteAdapter())

    receipt = await dispatcher.execute_action(_act("purge_notes"))

    assert not receipt.success
    assert "RISK-001" in receipt.error


@pytest.fixture
def operator(tmp_path, monkeypatch):
    private_hex, public_hex = signing.generate_operator_key()
    key_file = tmp_path / "kirk.key"
    key_file.write_text(private_hex, encoding="utf-8")
    keyring = tmp_path / "operators.json"
    keyring.write_text(json.dumps({"operators": {"kirk": public_hex}}), encoding="utf-8")
    monkeypatch.setenv(signing.OPERATOR_ID_ENV, "kirk")
    monkeypatch.setenv(signing.OPERATOR_PRIVATE_KEY_ENV, str(key_file))
    monkeypatch.setenv(signing.OPERATOR_KEYRING_ENV, str(keyring))
    signing._keyring_at.cache_clear()
    return keyring


def test_a_signed_classification_verifies_and_a_tampered_one_does_not(operator):
    classification = sign_classification(
        Classification(
            adapter="notes",
            action_name="purge_notes",
            risk=ActionRisk.COMPENSABLE,
            classified_by="kirk",
            note="moves to trash",
        )
    )

    assert classification_is_valid(classification)

    downgraded = classification.model_copy(update={"risk": ActionRisk.READ_ONLY})
    assert not classification_is_valid(downgraded), "the signature must cover the risk class"


def test_a_classification_cannot_be_issued_in_another_operators_name(operator, tmp_path, monkeypatch):
    other_private, other_public = signing.generate_operator_key()
    keyring = json.loads(operator.read_text(encoding="utf-8"))
    keyring["operators"]["intern"] = other_public
    operator.write_text(json.dumps(keyring), encoding="utf-8")
    signing._keyring_at.cache_clear()

    intern_key = tmp_path / "intern.key"
    intern_key.write_text(other_private, encoding="utf-8")
    monkeypatch.setenv(signing.OPERATOR_ID_ENV, "intern")
    monkeypatch.setenv(signing.OPERATOR_PRIVATE_KEY_ENV, str(intern_key))

    forged = Classification(
        adapter="notes", action_name="purge_notes", risk=ActionRisk.READ_ONLY, classified_by="kirk"
    )
    forged.signature = signing.signer_from_env().sign(forged.digest())

    assert not classification_is_valid(forged)


async def test_require_signed_refuses_an_unsigned_classification(env):
    env["dispatcher"].quarantine_gate.require_signed = True
    env["dispatcher"].quarantine_gate.store = ClassificationStore(
        [
            Classification(
                adapter="notes",
                action_name="purge_notes",
                risk=ActionRisk.READ_ONLY,
                classified_by="kirk",
            )
        ]
    )

    receipt = await env["dispatcher"].execute_action(_act("purge_notes"))

    assert not receipt.success
    assert "unsigned or its signature is invalid" in receipt.error


def test_the_classification_store_round_trips(tmp_path):
    path = tmp_path / "classifications.json"
    store = ClassificationStore(
        [
            Classification(
                adapter="notes",
                action_name="purge_notes",
                risk=ActionRisk.COMPENSABLE,
                classified_by="kirk",
            )
        ]
    )
    store.save(path)

    reloaded = ClassificationStore.from_file(path)
    found = reloaded.lookup("notes", "purge_notes")

    assert found is not None
    assert found.risk is ActionRisk.COMPENSABLE
    assert reloaded.lookup("notes", "never_seen") is None


def test_a_missing_store_is_empty_not_an_error(tmp_path):
    assert ClassificationStore.from_file(tmp_path / "absent.json").keys == []
