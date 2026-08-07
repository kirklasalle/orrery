"""
Tests for the benchmark harness.

These assert the harness measures honestly, not that it produces a flattering number.
Two of them exist specifically to fail if Orrery ever starts overstating what it achieved.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orrery.bench.runner import (
    BACKTRACK,
    BLIND_RETRY,
    DEFAULT_ARMS,
    SINGLE_PASS,
    run_benchmark,
    run_task,
)
from orrery.bench.tasks import DEFAULT_TASKS, task_by_id
from orrery.bench.types import NOT_SUPPORTED, SUPPORTED


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "bench"


async def test_recoverable_task_succeeds_only_with_retained_lessons(workspace: Path):
    """
    The core comparison. Same rollback, same attempt budget, one difference: lessons.
    """
    task = task_by_id("displaced_move")

    informed = await run_task(task, BACKTRACK, workspace)
    blind = await run_task(task, BLIND_RETRY, workspace)

    assert informed.verified, informed.verification_detail
    assert not blind.verified
    assert informed.attempts > 1, "the task must actually require a retry to be a fair test"
    assert blind.attempts == informed.attempts or blind.attempts > informed.attempts


async def test_blind_retry_repeats_itself(workspace: Path):
    """
    The control must actually be blind: without lessons every attempt costs the same.
    """
    blind = await run_task(task_by_id("read_before_create"), BLIND_RETRY, workspace)

    assert not blind.verified
    assert blind.actions_dispatched == blind.attempts, (
        "each blind attempt should re-run the identical one-action plan"
    )


async def test_governance_refusal_is_recoverable(workspace: Path):
    """
    An approval refusal must be a fact the planner can route around, not a dead end.
    """
    run = await run_task(task_by_id("retire_without_deleting"), BACKTRACK, workspace)

    assert run.actions_refused >= 1, "the first attempt should have been refused by RISK-001"
    assert run.verified, run.verification_detail


async def test_sandbox_refusal_never_writes_outside_the_root(workspace: Path):
    run = await run_task(task_by_id("sandbox_escape"), BACKTRACK, workspace)

    assert run.verified, run.verification_detail
    assert not (workspace / "manifest.json").exists()


async def test_unreachable_task_fails_honestly_in_every_arm(workspace: Path):
    """
    Retrying must not manufacture a success, and the cost of retrying must be visible.
    """
    task = task_by_id("unreachable_target")

    single = await run_task(task, SINGLE_PASS, workspace)
    informed = await run_task(task, BACKTRACK, workspace)

    for run in (single, informed):
        assert not run.verified
        assert not run.claimed_success
        assert run.honest_failure

    assert informed.actions_dispatched > single.actions_dispatched, (
        "backtracking is not free, and the report must show what it spent"
    )


async def test_goal_check_catches_the_partially_failed_plan(workspace: Path):
    """
    Was `test_success_ratio_critique_passes_a_partially_failed_plan`, and it used to assert
    the opposite: three of four actions succeeded, the critique scored 0.75 against a 0.70
    threshold, passed, and the cycle reported COMPLETED for a goal it had not reached.

    With a goal check wired in, reflection now refuses, backtracking fires, and the retry
    creates the missing file. The engine-level limitation it exposed has not vanished — see
    tests/test_critique.py::test_success_ratio_alone_passes_a_plan_that_did_not_reach_its_goal.
    """
    informed = await run_task(task_by_id("silent_partial_failure"), BACKTRACK, workspace)
    blind = await run_task(task_by_id("silent_partial_failure"), BLIND_RETRY, workspace)

    assert informed.attempts > 1, "reflection must have objected to the first attempt"
    assert informed.verified, informed.verification_detail
    assert not informed.false_success

    assert not blind.verified
    assert blind.honest_failure


async def test_full_suite_reports_a_verdict_and_no_false_success(workspace: Path):
    report = await run_benchmark(workspace, tasks=DEFAULT_TASKS, arms=DEFAULT_ARMS, trials=1)

    assert report.verdict() in (SUPPORTED, NOT_SUPPORTED)
    assert report.arm("backtrack").verified_count > report.arm("blind_retry").verified_count
    assert report.shipped_false_success_count == 0, (
        "a run in the shipped configuration reported COMPLETED for a goal the filesystem "
        "says was not reached"
    )

    rendered = report.render()
    assert "VERDICT:" in rendered
    assert "WARNING:" not in rendered

    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["verdict"] == report.verdict()
    assert len(payload["arms"]) == len(DEFAULT_ARMS)


async def test_the_harness_prices_the_oracle_it_hands_the_agent(workspace: Path):
    """
    The benchmark's biggest caveat, measured rather than merely disclosed. The `unverified`
    arm keeps rollback and lessons and loses only the goal check, so the gap between it and
    `backtrack` is exactly what the oracle is worth — and a deployment has to write that
    oracle itself.
    """
    report = await run_benchmark(workspace, tasks=DEFAULT_TASKS, arms=DEFAULT_ARMS, trials=1)

    unverified = report.arm("unverified")
    treatment = report.arm("backtrack")

    assert unverified.verified_count < treatment.verified_count
    assert report.goal_check_delta == treatment.verified_count - unverified.verified_count
    assert unverified.false_success_count > 0, (
        "without a goal check, success-ratio critique certifies goals it never checked — "
        "that is the cost being measured"
    )
    assert "not a defect" in report.render()


async def test_verification_reads_the_disk_not_the_receipts(workspace: Path):
    """
    Grading must be independent of what the cycle reported. Deleting the artifact after a
    verified run must flip the verdict.
    """
    task = task_by_id("read_before_create")
    run = await run_task(task, BACKTRACK, workspace)
    assert run.verified

    root = workspace / f"{task.task_id}__{BACKTRACK.arm_id}__0" / "root"
    (root / "notes" / "seed.txt").unlink()

    assert not task.verify(root).verified


def test_every_task_declares_why_its_first_attempt_fails():
    for task in DEFAULT_TASKS:
        assert task.first_attempt_fails_because.strip()
        if not task.recoverable:
            assert task.note.strip(), "a task that cannot be solved must say so"
