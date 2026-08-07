"""
Tests for interdiction: operator prohibitions, protected paths, and the halt switch.

The protected-path tests describe an attack that worked before this module existed. A
`FileSystemAdapter` rooted at the project directory could delete the ledger, and the
append-only audit log Law 9 rests on was defended by nothing.
"""

from pathlib import Path

import pytest

from orrery.adapters.filesystem import FileSystemAdapter
from orrery.core.approval import grant
from orrery.core.config import (
    CheckpointSettings,
    GovernanceSettings,
    InterdictionSettings,
    LedgerSettings,
    ProhibitionSettings,
    Settings,
)
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.interdiction import InterdictionGate, Prohibition
from orrery.core.ledger import EventLedger
from orrery.core.state import CheckpointManager
from orrery.core.types import ActionPayload, CyclePhase, CycleStatus, CycleTier, StateContext


@pytest.fixture
def workspace(tmp_path):
    """A dispatcher whose ledger and checkpoints live inside the adapter's own sandbox."""
    root = tmp_path / "root"
    root.mkdir()
    ledger_dir = root / ".ledger"
    checkpoint_dir = root / ".checkpoints"

    settings = Settings(
        checkpointing=CheckpointSettings(storage_dir=str(checkpoint_dir)),
        ledger=LedgerSettings(persist=True, storage_dir=str(ledger_dir)),
        governance=GovernanceSettings(attestation_path=str(root / "attestation.json")),
        interdiction=InterdictionSettings(halt_file=str(tmp_path / "halt")),
    )
    dispatcher = CycleDispatcher(settings=settings)
    dispatcher.register_adapter(FileSystemAdapter(root=str(root)))
    return {"root": root, "dispatcher": dispatcher, "settings": settings, "tmp": tmp_path}


def _act(name, **params) -> ActionPayload:
    return ActionPayload(action_name=name, params=params, target_adapter="filesystem")


async def test_an_action_cannot_reach_the_ledger(workspace):
    """
    LAW3-SUBORDINATE. Before this, the audit trail was one `delete_tree` from gone.
    """
    dispatcher = workspace["dispatcher"]
    action = _act("delete_tree", path=".ledger")
    action.approval = grant(action, approver="operator", reason="cleanup")

    receipt = await dispatcher.execute_action(action)

    assert not receipt.success
    assert "LAW3-SUBORDINATE" in receipt.error
    assert (workspace["root"] / ".ledger").exists()


async def test_deleting_a_parent_of_the_ledger_is_also_refused(workspace):
    """
    Containment runs both ways: wiping the directory above the ledger destroys it too.
    """
    dispatcher = workspace["dispatcher"]
    action = _act("delete_tree", path=".")
    action.approval = grant(action, approver="operator")

    receipt = await dispatcher.execute_action(action)

    assert not receipt.success
    assert "LAW3-SUBORDINATE" in receipt.error


async def test_checkpoints_and_attestation_are_protected_too(workspace):
    dispatcher = workspace["dispatcher"]

    for path in (".checkpoints", "attestation.json"):
        action = _act("write_file", path=path, content="tampered")
        action.approval = grant(action, approver="operator")
        receipt = await dispatcher.execute_action(action)
        assert not receipt.success, path
        assert "LAW3-SUBORDINATE" in receipt.error


async def test_ordinary_work_in_the_same_sandbox_still_runs(workspace):
    """
    The protection must be surgical. Protecting the ledger cannot mean protecting everything.
    """
    dispatcher = workspace["dispatcher"]
    receipt = await dispatcher.execute_action(
        _act("write_file", path="notes/plan.txt", content="ordinary work")
    )

    assert receipt.success, receipt.error
    assert (workspace["root"] / "notes" / "plan.txt").read_text(encoding="utf-8") == "ordinary work"


async def test_a_refusal_to_touch_the_record_is_itself_recorded(workspace):
    dispatcher = workspace["dispatcher"]
    action = _act("delete_tree", path=".ledger")
    action.approval = grant(action, approver="operator")

    await dispatcher.execute_action(action)

    refusals = [e for e in dispatcher.ledger.events if e.event_type == "action.refused"]
    assert refusals
    assert refusals[-1].policy_id == "LAW3-SUBORDINATE"
    assert refusals[-1].data["approved_by"] == "operator"


async def test_a_prohibited_action_is_refused_even_with_approval(tmp_path):
    """
    LAW1-PROHIBIT. A prohibition is not a question an approval token gets to answer.
    """
    root = tmp_path / "root"
    settings = Settings(
        checkpointing=CheckpointSettings(storage_dir=str(tmp_path / "checkpoints")),
        ledger=LedgerSettings(persist=False, storage_dir=str(tmp_path / "ledger")),
        interdiction=InterdictionSettings(
            halt_file=str(tmp_path / "halt"),
            prohibitions=[
                ProhibitionSettings(
                    reason="payroll records are never modified by an agent",
                    paths=[str(root / "payroll")],
                )
            ],
        ),
    )
    dispatcher = CycleDispatcher(settings=settings)
    dispatcher.register_adapter(FileSystemAdapter(root=str(root)))

    action = _act("write_file", path="payroll/salaries.csv", content="tampered")
    action.approval = grant(action, approver="operator", reason="I said so")

    receipt = await dispatcher.execute_action(action)

    assert not receipt.success
    assert "LAW1-PROHIBIT" in receipt.error
    assert "payroll records are never modified by an agent" in receipt.error
    assert not (root / "payroll" / "salaries.csv").exists()


def test_a_prohibition_can_name_an_adapter_or_an_action():
    gate = InterdictionGate(
        prohibitions=[
            Prohibition(reason="no arbitrary execution here", adapters=["process"]),
            Prohibition(reason="never delete trees", actions=["delete_tree"]),
        ]
    )

    assert not gate.evaluate(
        ActionPayload(action_name="run_program", target_adapter="process")
    ).allowed
    assert not gate.evaluate(
        ActionPayload(action_name="delete_tree", target_adapter="filesystem")
    ).allowed
    assert gate.evaluate(
        ActionPayload(action_name="read_file", target_adapter="filesystem")
    ).allowed


def test_a_prohibition_matching_everything_is_rejected_as_a_typo():
    with pytest.raises(ValueError, match="matches everything"):
        InterdictionGate(prohibitions=[Prohibition(reason="oops")])


def test_protection_does_not_depend_on_a_parameter_being_named_what_we_expected(tmp_path):
    """
    The hole this closed: protection used to inspect only parameters named `path`,
    `source`, `destination`, `cwd`, or `directory`. A third-party adapter calling its
    parameter `target_file` walked straight past the ledger protection, so the defence
    depended on an adapter author picking a name someone had thought of in advance.
    """
    gate = InterdictionGate(protected_paths=[str(tmp_path / ".ledger")])

    for key in ("path", "target_file", "destination_file", "wherever"):
        decision = gate.evaluate(
            ActionPayload(action_name="purge", params={key: ".ledger"}, target_adapter="notes"),
            tmp_path,
        )
        assert not decision.allowed, f"parameter {key!r} reached the ledger unchecked"
        assert decision.policy_id == "LAW3-SUBORDINATE"


def test_a_path_nested_inside_a_list_or_dict_is_still_found(tmp_path):
    gate = InterdictionGate(protected_paths=[str(tmp_path / ".ledger")])

    nested = ActionPayload(
        action_name="batch_purge",
        params={"targets": [{"where": ["notes", ".ledger"]}]},
        target_adapter="notes",
    )

    assert not gate.evaluate(nested, tmp_path).allowed


def test_scanning_everything_does_not_block_ordinary_parameters(tmp_path):
    """
    Fail-closed scanning is only useful if it stays quiet. A prose string is not a path to
    anything protected, and must not be treated as one.
    """
    gate = InterdictionGate(protected_paths=[str(tmp_path / ".ledger")])

    ordinary = ActionPayload(
        action_name="write_file",
        params={
            "path": "notes/plan.txt",
            "content": "Delete the .ledger directory, he said, and other prose.",
            "retries": 3,
        },
        target_adapter="filesystem",
    )

    assert gate.evaluate(ordinary, tmp_path).allowed


async def test_a_halt_stops_the_cycle_and_cannot_be_cleared_by_it(workspace):
    """
    LAW2-HALT. The operator's stop outranks the goal, and the cycle cannot revoke it.
    """
    dispatcher = workspace["dispatcher"]
    halt_file = Path(workspace["settings"].interdiction.halt_file)
    halt_file.write_text("stop: reviewing the plan", encoding="utf-8")

    context = await dispatcher.run_full_cycle(
        StateContext(tier=CycleTier.MICRO, goal="do the thing")
    )

    assert context.status is CycleStatus.HALTED
    assert context.status is not CycleStatus.FAILED, "an operator stop is not a work failure"
    assert any("halted by operator" in lesson.lower() for lesson in context.lessons)

    halted = [e for e in dispatcher.ledger.events if e.event_type == "cycle.halted"]
    assert halted and halted[0].policy_id == "LAW2-HALT"


async def test_the_cycle_cannot_delete_its_own_halt_file(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    halt_file = root / "halt"
    halt_file.write_text("stop", encoding="utf-8")

    settings = Settings(
        checkpointing=CheckpointSettings(storage_dir=str(tmp_path / "checkpoints")),
        ledger=LedgerSettings(persist=False, storage_dir=str(tmp_path / "ledger")),
        interdiction=InterdictionSettings(halt_file=str(halt_file)),
    )
    dispatcher = CycleDispatcher(settings=settings)
    dispatcher.register_adapter(FileSystemAdapter(root=str(root)))

    action = _act("delete_file", path="halt")
    action.approval = grant(action, approver="operator")
    receipt = await dispatcher.execute_action(action)

    assert not receipt.success
    assert "LAW3-SUBORDINATE" in receipt.error
    assert halt_file.exists()


async def test_a_halt_raised_mid_run_takes_effect_on_the_next_phase(workspace):
    dispatcher = workspace["dispatcher"]
    halt_file = Path(workspace["settings"].interdiction.halt_file)

    context = StateContext(tier=CycleTier.MICRO, goal="start clean")
    context = await dispatcher.step(context)
    assert context.status is CycleStatus.IN_PROGRESS
    assert context.current_phase is CyclePhase.PLANNING

    halt_file.write_text("stop now", encoding="utf-8")
    context = await dispatcher.step(context)

    assert context.status is CycleStatus.HALTED


def test_no_halt_file_means_no_halt(tmp_path):
    gate = InterdictionGate(halt_file=str(tmp_path / "absent"))
    assert gate.halted() is None


def test_protection_can_be_turned_off_but_says_so(tmp_path):
    """
    Nothing is hidden: with protect_runtime_paths off, only the halt file is defended.
    """
    settings = Settings(
        ledger=LedgerSettings(persist=False, storage_dir=str(tmp_path / "ledger")),
        checkpointing=CheckpointSettings(storage_dir=str(tmp_path / "checkpoints")),
        interdiction=InterdictionSettings(
            halt_file=str(tmp_path / "halt"), protect_runtime_paths=False
        ),
    )
    dispatcher = CycleDispatcher(settings=settings)

    protected = dispatcher.interdiction_gate.protected_paths
    assert protected == [Path(tmp_path / "halt").resolve()]
