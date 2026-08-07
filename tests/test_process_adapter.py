"""
Tests for the ProcessAdapter.

This adapter can run programs, so most of these are about what it refuses. The security
properties are the feature; the ability to run something is the easy part.
"""

import shutil
import sys
from pathlib import Path

import pytest

from orrery.adapters.process import ProcessAdapter
from orrery.core.approval import grant
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.ledger import EventLedger
from orrery.core.state import CheckpointManager
from orrery.core.types import ActionPayload, ActionRisk, StateContext


def _python_on_path() -> str:
    """
    The interpreter's own name is not always on PATH — CI images vary between `python`,
    `python3`, and `python3.10` — and the adapter resolves an allowlisted program by name.
    """
    for candidate in (Path(sys.executable).name, "python3", "python"):
        if shutil.which(candidate):
            return candidate
    return Path(sys.executable).name


PYTHON = _python_on_path()


@pytest.fixture
def adapter(tmp_path):
    return ProcessAdapter(root=str(tmp_path / "sandbox"), allowed_programs=[PYTHON])


def _run(**params) -> ActionPayload:
    return ActionPayload(action_name="run_program", params=params, target_adapter="process")


async def test_running_an_allowlisted_program_really_runs_it(adapter):
    receipt = await adapter.execute_action(
        _run(program=PYTHON, args=["-c", "print('hello from a real process')"])
    )

    assert receipt.success, receipt.error
    assert receipt.output["exit_code"] == 0
    assert "hello from a real process" in receipt.output["stdout"]


async def test_a_nonzero_exit_code_is_a_failed_receipt(adapter):
    """
    The program ran, and the work failed. Counting that as a success would feed a passing
    reflection score with a failing build.
    """
    receipt = await adapter.execute_action(
        _run(program=PYTHON, args=["-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"])
    )

    assert not receipt.success
    assert receipt.output["exit_code"] == 3
    assert "exited 3" in receipt.error
    assert "boom" in receipt.error


async def test_a_program_outside_the_allowlist_never_runs(adapter):
    receipt = await adapter.execute_action(_run(program="curl", args=["https://example.com"]))

    assert not receipt.success
    assert "not in this adapter's allowlist" in receipt.error


async def test_a_command_string_is_refused_rather_than_split(adapter):
    """
    Splitting a string here would reintroduce quoting rules, and quoting rules are where
    command injection lives.
    """
    receipt = await adapter.execute_action(
        _run(program=PYTHON, args="-c 'print(1)' ; rm -rf /")
    )

    assert not receipt.success
    assert "args must be a list of strings" in receipt.error


async def test_shell_metacharacters_are_inert_arguments(adapter, tmp_path):
    """
    With shell=False, a semicolon is just a character in argv.
    """
    canary = tmp_path / "sandbox" / "canary.txt"
    receipt = await adapter.execute_action(
        _run(program=PYTHON, args=["-c", "print('ok')", ";", f"touch {canary}"])
    )

    assert receipt.success, receipt.error
    assert not canary.exists(), "the second 'command' must never have executed"


async def test_working_directory_cannot_escape_the_sandbox(adapter):
    receipt = await adapter.execute_action(_run(program=PYTHON, args=["-c", "pass"], cwd="../.."))

    assert not receipt.success
    assert "escapes the adapter sandbox" in receipt.error


async def test_absolute_working_directory_is_refused(adapter, tmp_path):
    receipt = await adapter.execute_action(
        _run(program=PYTHON, args=["-c", "pass"], cwd=str(tmp_path))
    )

    assert not receipt.success
    assert "absolute working directories are not permitted" in receipt.error


async def test_a_runaway_program_is_stopped(adapter):
    receipt = await adapter.execute_action(
        _run(program=PYTHON, args=["-c", "import time; time.sleep(30)"], timeout_seconds=0.5)
    )

    assert not receipt.success
    assert "Timeout" in receipt.error or "timeout" in receipt.error.lower()


async def test_output_is_bounded(tmp_path):
    adapter = ProcessAdapter(
        root=str(tmp_path / "sandbox"),
        allowed_programs=[PYTHON],
        config={"max_output_bytes": 256},
    )

    receipt = await adapter.execute_action(
        _run(program=PYTHON, args=["-c", "print('x' * 100000)"])
    )

    assert receipt.success, receipt.error
    assert receipt.output["truncated"]
    assert len(receipt.output["stdout"]) <= 256


async def test_the_environment_is_not_inherited_by_default(adapter, monkeypatch):
    monkeypatch.setenv("ORRERY_APPROVAL_KEY", "a-secret-the-child-must-not-see")

    receipt = await adapter.execute_action(
        _run(program=PYTHON, args=["-c", "import os; print(os.environ.get('ORRERY_APPROVAL_KEY'))"])
    )

    assert receipt.success, receipt.error
    assert "a-secret-the-child-must-not-see" not in receipt.output["stdout"]


async def test_an_unsupported_action_fails_rather_than_pretending(adapter):
    receipt = await adapter.execute_action(
        ActionPayload(action_name="mine_bitcoin", target_adapter="process")
    )

    assert not receipt.success
    assert "does not implement action" in receipt.error


async def test_perception_reports_the_real_allowlist(adapter):
    observation = await adapter.perceive_environment(StateContext(goal="observe"))

    assert observation["platform"] == "process"
    assert PYTHON in observation["allowed_programs"]
    assert PYTHON in observation["resolved"]


def test_running_a_program_is_declared_irreversible():
    """
    The adapter cannot know what a program did, so it must assume the worst it could do.
    """
    assert ProcessAdapter.risk_for("run_program") is ActionRisk.IRREVERSIBLE
    assert ProcessAdapter.risk_for("which_program") is ActionRisk.READ_ONLY
    assert ProcessAdapter.risk_for("undeclared_action") is ActionRisk.IRREVERSIBLE


async def test_execution_is_refused_without_operator_approval(tmp_path):
    """
    Arbitrary code execution is exactly what the approval gate exists for.
    """
    dispatcher = CycleDispatcher(
        checkpoint_manager=CheckpointManager(storage_dir=str(tmp_path / "checkpoints")),
        ledger=EventLedger(storage_dir=str(tmp_path / "ledger"), persist=False),
    )
    dispatcher.register_adapter(
        ProcessAdapter(root=str(tmp_path / "sandbox"), allowed_programs=[PYTHON])
    )

    action = _run(program=PYTHON, args=["-c", "print('should not run')"])
    receipt = await dispatcher.execute_action(action)

    assert not receipt.success
    assert "RISK-001" in receipt.error


async def test_approved_execution_proceeds(tmp_path):
    dispatcher = CycleDispatcher(
        checkpoint_manager=CheckpointManager(storage_dir=str(tmp_path / "checkpoints")),
        ledger=EventLedger(storage_dir=str(tmp_path / "ledger"), persist=False),
    )
    dispatcher.register_adapter(
        ProcessAdapter(root=str(tmp_path / "sandbox"), allowed_programs=[PYTHON])
    )

    action = _run(program=PYTHON, args=["-c", "print('authorized')"])
    action.approval = grant(action, approver="operator", reason="reviewed the argv")

    receipt = await dispatcher.execute_action(action)

    assert receipt.success, receipt.error
    assert "authorized" in receipt.output["stdout"]


async def test_an_empty_allowlist_refuses_everything(tmp_path):
    adapter = ProcessAdapter(root=str(tmp_path / "sandbox"), allowed_programs=[])
    receipt = await adapter.execute_action(_run(program=PYTHON, args=["-c", "pass"]))

    assert not receipt.success
    assert "allowlist" in receipt.error
