"""
Tests for effect envelopes.

The point of an envelope is that it works on actions nobody anticipated, so the tests use
action names the framework has never heard of and adapters that were written after the rule.
"""

from pathlib import Path

import pytest

from orrery.adapters.base import BaseAdapter
from orrery.adapters.filesystem import FileSystemAdapter
from orrery.core.approval import grant
from orrery.core.config import (
    CheckpointSettings,
    EnvelopeSettings,
    InterdictionSettings,
    LedgerSettings,
    Settings,
)
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.envelope import EffectEnvelope, EnvelopeGate
from orrery.core.types import ActionPayload, ActionRisk, ExecutionReceipt, StateContext


class LateAdapter(BaseAdapter):
    """
    An adapter written long after the envelope rule, with an action nobody enumerated.
    """

    declared_risks = {"sync_everything": ActionRisk.REVERSIBLE}
    target_params = ("target", "batch")

    def __init__(self, root: str, envelope: EffectEnvelope = None):
        super().__init__(name="late")
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.effect_envelope = envelope
        self.performed = []

    async def perceive_environment(self, context):
        return {"platform": "late"}

    async def execute_action(self, action):
        self.performed.append(action)
        return ExecutionReceipt(
            action_id=action.action_id, action_name=action.action_name, success=True
        )


def _settings(tmp_path, **envelope) -> Settings:
    return Settings(
        checkpointing=CheckpointSettings(storage_dir=str(tmp_path / "checkpoints")),
        ledger=LedgerSettings(persist=False, storage_dir=str(tmp_path / "ledger")),
        interdiction=InterdictionSettings(halt_file=str(tmp_path / "halt")),
        envelope=EnvelopeSettings(**envelope),
    )


def _act(name, **params):
    return ActionPayload(action_name=name, params=params, target_adapter="late")


async def test_an_action_nobody_enumerated_is_judged_by_where_it_lands(tmp_path):
    """
    The whole thesis. `sync_everything` appears on no list anywhere; it is refused because
    of where it points.
    """
    root = tmp_path / "workspace"
    adapter = LateAdapter(str(root), EffectEnvelope(paths=[str(root / "data")]))

    dispatcher = CycleDispatcher(settings=_settings(tmp_path, enforce=True))
    dispatcher.register_adapter(adapter)

    inside = await dispatcher.execute_action(_act("sync_everything", target="data/report.csv"))
    assert inside.success, inside.error

    outside = await dispatcher.execute_action(_act("sync_everything", target="secrets/keys.txt"))
    assert not outside.success
    assert "LAW1-ENVELOPE" in outside.error
    assert "outside the envelope adapter 'late' declares for itself" in outside.error


async def test_approval_does_not_open_the_envelope(tmp_path):
    root = tmp_path / "workspace"
    adapter = LateAdapter(str(root), EffectEnvelope(paths=[str(root / "data")]))
    dispatcher = CycleDispatcher(settings=_settings(tmp_path, enforce=True))
    dispatcher.register_adapter(adapter)

    action = _act("sync_everything", target="secrets/keys.txt")
    action.approval = grant(action, approver="operator", reason="I want it")

    receipt = await dispatcher.execute_action(action)

    assert not receipt.success
    assert "LAW1-ENVELOPE" in receipt.error
    assert adapter.performed == []


async def test_the_deployment_narrows_what_an_adapter_claims_for_itself(tmp_path):
    """
    The intersection. The adapter's sandbox is the whole workspace; this deployment permits
    only part of it, and the adapter is not consulted about that.
    """
    root = tmp_path / "workspace"
    adapter = FileSystemAdapter(root=str(root))
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "archive").mkdir(parents=True, exist_ok=True)

    dispatcher = CycleDispatcher(
        settings=_settings(tmp_path, enforce=True, paths=[str(root / "data")])
    )
    dispatcher.register_adapter(adapter)

    permitted = await dispatcher.execute_action(
        ActionPayload(
            action_name="write_file",
            params={"path": "data/ok.txt", "content": "fine"},
            target_adapter="filesystem",
        )
    )
    assert permitted.success, permitted.error

    refused = await dispatcher.execute_action(
        ActionPayload(
            action_name="write_file",
            params={"path": "archive/nope.txt", "content": "no"},
            target_adapter="filesystem",
        )
    )
    assert not refused.success
    assert "outside the envelope this deployment permits" in refused.error
    assert not (root / "archive" / "nope.txt").exists()


async def test_an_adapter_cannot_widen_the_deployment_envelope(tmp_path):
    """
    Intersection, not union. A generous self-declaration buys nothing.
    """
    root = tmp_path / "workspace"
    adapter = LateAdapter(str(root), EffectEnvelope(paths=[str(tmp_path)]))

    dispatcher = CycleDispatcher(
        settings=_settings(tmp_path, enforce=True, paths=[str(root / "data")])
    )
    dispatcher.register_adapter(adapter)

    receipt = await dispatcher.execute_action(_act("sync_everything", target="elsewhere/x.txt"))

    assert not receipt.success
    assert "outside the envelope this deployment permits" in receipt.error


def test_reaching_a_parent_of_the_permitted_region_is_outside_it(tmp_path):
    """
    Containment runs one way here, unlike protected paths. An envelope covering `data/`
    does not permit an action aimed at everything above it.
    """
    root = tmp_path / "workspace"
    gate = EnvelopeGate(enforce=True, deployment=EffectEnvelope(paths=[str(root / "data")]))
    adapter = LateAdapter(str(root))

    assert gate.evaluate(_act("sync_everything", target=str(root / "data" / "f")), adapter).allowed
    assert not gate.evaluate(_act("sync_everything", target=str(root)), adapter).allowed


def test_enforcement_with_no_boundary_declared_refuses_rather_than_permits(tmp_path):
    gate = EnvelopeGate(enforce=True)
    adapter = LateAdapter(str(tmp_path / "workspace"))

    decision = gate.evaluate(_act("sync_everything", target="anywhere.txt"), adapter)

    assert not decision.allowed
    assert "nothing declares a boundary" in decision.reason


def test_enforcement_off_permits_everything(tmp_path):
    gate = EnvelopeGate(enforce=False)
    adapter = LateAdapter(str(tmp_path / "workspace"))

    assert gate.evaluate(_act("sync_everything", target="/etc/passwd"), adapter).allowed


def test_an_action_pointing_nowhere_visible_is_permitted_and_documented(tmp_path):
    """
    The honest limit: reach is inferred from the values an action carries. An action with no
    such values is not checked, and this pins that so it is a known limit rather than a
    surprise.
    """
    root = tmp_path / "workspace"
    gate = EnvelopeGate(enforce=True, deployment=EffectEnvelope(paths=[str(root / "data")]))
    adapter = LateAdapter(str(root))

    assert gate.evaluate(ActionPayload(action_name="sync_everything", target_adapter="late"), adapter).allowed


def test_a_path_nested_in_a_structure_is_still_checked(tmp_path):
    root = tmp_path / "workspace"
    gate = EnvelopeGate(enforce=True, deployment=EffectEnvelope(paths=[str(root / "data")]))
    adapter = LateAdapter(str(root))

    nested = ActionPayload(
        action_name="sync_everything",
        params={"batch": [{"to": str(root / "secrets" / "k.txt")}]},
        target_adapter="late",
    )

    assert not gate.evaluate(nested, adapter).allowed


def test_the_real_adapters_declare_their_sandboxes(tmp_path):
    from orrery.adapters.process import ProcessAdapter

    filesystem = FileSystemAdapter(root=str(tmp_path / "fs"))
    process = ProcessAdapter(root=str(tmp_path / "proc"), allowed_programs=["python"])

    assert EnvelopeGate.declared_by(filesystem).paths == [str(filesystem.root)]
    assert EnvelopeGate.declared_by(process).paths == [str(process.root)]


def test_an_adapter_declaring_nothing_declares_nothing(tmp_path):
    adapter = LateAdapter(str(tmp_path / "workspace"))

    assert EnvelopeGate.declared_by(adapter) is None
    assert EnvelopeGate.declared_by(LateAdapter(str(tmp_path), EffectEnvelope())) is None


def test_an_adapter_that_never_says_which_parameters_are_targets_is_refused(tmp_path):
    """
    An allowlist cannot over-scan the way protection does — the *contents* of a file being
    written are not a path and would be refused for not living inside a directory. So the
    adapter must say which parameters name a location, and silence is refusal, not consent.
    """

    class SilentAdapter(LateAdapter):
        target_params = None

    root = tmp_path / "workspace"
    gate = EnvelopeGate(enforce=True, deployment=EffectEnvelope(paths=[str(root)]))

    decision = gate.evaluate(_act("sync_everything", target="data/x"), SilentAdapter(str(root)))

    assert not decision.allowed
    assert "declares no target_params" in decision.reason


def test_an_adapter_may_state_that_none_of_its_parameters_are_targets(tmp_path):
    class Targetless(LateAdapter):
        target_params = ()

    root = tmp_path / "workspace"
    gate = EnvelopeGate(enforce=True, deployment=EffectEnvelope(paths=[str(root)]))

    assert gate.evaluate(_act("sync_everything", note="anything at all"), Targetless(str(root))).allowed


def test_payload_values_are_not_mistaken_for_targets(tmp_path):
    """
    The regression this design exists for: file content is not a location.
    """
    root = tmp_path / "workspace"
    adapter = FileSystemAdapter(root=str(root))
    gate = EnvelopeGate(enforce=True, deployment=EffectEnvelope(paths=[str(root / "data")]))

    write = ActionPayload(
        action_name="write_file",
        params={"path": "data/report.txt", "content": "prose that is not a path"},
        target_adapter="filesystem",
    )

    assert gate.evaluate(write, adapter).allowed
