"""
The benchmark runner.

Three arms, one attempt budget:

  single_pass   one attempt, no rollback. The floor.
  blind_retry   the same rollback, the same number of attempts, but lessons discarded on
                every rewind, so each retry repeats the first attempt exactly.
  backtrack     Orrery as shipped: rollback plus retained lessons and attempt log.

`single_pass` is not the comparison that matters. Beating it only shows that retrying
beats not retrying, which no one disputes. The claim under test is that *informed*
rollback beats uninformed rollback at an identical attempt budget, and `blind_retry`
exists so that claim can come out false.

Grading is done by reading the sandbox after the cycle ends. Receipts are counted, never
believed.

One thing this harness hands the agent that a real deployment may not: each task's
verifier is also wired in as the cycle's `goal_check`, so reflection can tell whether the
goal was actually reached instead of only whether the adapters behaved. That makes the
measured claim narrower than it first looks — *given a correct goal check*, informed
rollback recovers where uninformed rollback does not. Supplying that check is the
operator's job, and Orrery cannot invent one.

The `unverified` arm exists to price that caveat rather than merely disclose it. It keeps
rollback and lessons and loses only the goal check, so the gap between it and `backtrack`
is exactly what the oracle is worth — and the false successes it produces are the measured
cost of running without one, not a defect in the framework.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import List, Optional, Sequence

from orrery.adapters.filesystem import FileSystemAdapter
from orrery.bench.tasks import DEFAULT_TASKS
from orrery.bench.types import Arm, ArmSummary, BenchReport, BenchTask, TaskRun
from orrery.core.config import (
    ApprovalSettings,
    CheckpointSettings,
    CritiqueSettings,
    DispatcherSettings,
    LedgerSettings,
    Settings,
)
from orrery.core.critique import GoalVerification, SelfCritiqueEngine
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.ledger import EventLedger
from orrery.core.state import CheckpointManager
from orrery.core.types import CyclePhase, CycleTier, StateContext

logger = logging.getLogger(__name__)

MAX_BACKTRACKS = 3
CYCLE_TIMEOUT_SECONDS = 30.0

SINGLE_PASS = Arm(
    arm_id="single_pass",
    description="One attempt. No rollback.",
    max_backtracks=0,
    retain_lessons=False,
)
BLIND_RETRY = Arm(
    arm_id="blind_retry",
    description="Rollback with lessons discarded. Same attempt budget as backtrack.",
    max_backtracks=MAX_BACKTRACKS,
    retain_lessons=False,
)
BACKTRACK = Arm(
    arm_id="backtrack",
    description="Rollback with lessons retained. Orrery as shipped.",
    max_backtracks=MAX_BACKTRACKS,
    retain_lessons=True,
)
UNVERIFIED = Arm(
    arm_id="unverified",
    description="Backtracking with lessons, but no goal check. Measures the oracle's worth.",
    max_backtracks=MAX_BACKTRACKS,
    retain_lessons=True,
    goal_check=False,
)

DEFAULT_ARMS: List[Arm] = [SINGLE_PASS, BLIND_RETRY, UNVERIFIED, BACKTRACK]


class _AmnesiacCheckpointManager(CheckpointManager):
    """
    The control. Rewinds identically to the real manager, then throws away everything the
    rewind was supposed to carry forward.
    """

    def backtrack(self, context: StateContext) -> StateContext:
        restored = super().backtrack(context)
        restored.lessons = []
        restored.attempt_log = []
        return restored


def _bench_settings(sandbox: Path) -> Settings:
    return Settings(
        dispatcher=DispatcherSettings(max_cycle_iterations=64, auto_checkpoint=True),
        critique=CritiqueSettings(),
        checkpointing=CheckpointSettings(storage_dir=str(sandbox / "checkpoints")),
        ledger=LedgerSettings(persist=False, storage_dir=str(sandbox / "ledger")),
        approval=ApprovalSettings(require_for_irreversible=True),
    )


async def run_task(task: BenchTask, arm: Arm, workspace: Path, trial: int = 0) -> TaskRun:
    """
    Runs one task under one arm in its own sandbox and grades it against the disk.
    """
    sandbox = workspace / f"{task.task_id}__{arm.arm_id}__{trial}"
    root = sandbox / "root"
    root.mkdir(parents=True, exist_ok=True)
    task.setup(root)

    settings = _bench_settings(sandbox)
    manager_type = CheckpointManager if arm.retain_lessons else _AmnesiacCheckpointManager
    manager = manager_type(
        max_checkpoints=settings.checkpointing.max_checkpoints_in_memory,
        storage_dir=settings.checkpointing.storage_dir,
        max_checkpoints_on_disk_per_cycle=settings.checkpointing.max_checkpoints_on_disk_per_cycle,
    )
    ledger = EventLedger(storage_dir=settings.ledger.storage_dir, persist=False)

    def goal_check(_: StateContext) -> GoalVerification:
        result = task.verify(root)
        return GoalVerification(verified=result.verified, detail=result.detail)

    critique_engine = SelfCritiqueEngine(
        threshold=settings.critique.threshold,
        goal_check=goal_check if arm.goal_check else None,
    )

    dispatcher = CycleDispatcher(
        checkpoint_manager=manager,
        critique_engine=critique_engine,
        settings=settings,
        ledger=ledger,
    )
    dispatcher.register_adapter(FileSystemAdapter(root=str(root)))

    async def planning_handler(context: StateContext) -> StateContext:
        if not context.planned_actions:
            context.planned_actions.extend(task.plan(context))
        return context

    dispatcher.register_handler(CyclePhase.PLANNING, planning_handler)

    context = StateContext(
        tier=CycleTier.MICRO,
        goal=task.goal,
        max_backtracks=arm.max_backtracks,
    )

    started = time.perf_counter()
    context = await dispatcher.run_full_cycle(context, timeout_seconds=CYCLE_TIMEOUT_SECONDS)
    elapsed = time.perf_counter() - started

    verification = task.verify(root)
    critique = context.critiques[-1] if context.critiques else None

    # The ledger survives rollback; context.execution_receipts does not. Counting work
    # from the ledger is the only way to see what the discarded attempts actually cost.
    events = ledger.events
    dispatched = sum(1 for e in events if e.event_type in ("action.executed", "action.failed"))
    failed = sum(1 for e in events if e.event_type == "action.failed")
    refused = sum(1 for e in events if e.event_type == "action.refused")

    return TaskRun(
        task_id=task.task_id,
        arm_id=arm.arm_id,
        trial=trial,
        status=context.status.value,
        verified=verification.verified,
        verification_detail=verification.detail,
        critique_passed=bool(critique.passed) if critique else False,
        critique_score=float(critique.score) if critique else 0.0,
        attempts=context.backtrack_count + 1,
        actions_dispatched=dispatched,
        actions_failed=failed,
        actions_refused=refused,
        wall_seconds=elapsed,
    )


async def run_benchmark(
    workspace: Path,
    tasks: Optional[Sequence[BenchTask]] = None,
    arms: Optional[Sequence[Arm]] = None,
    trials: int = 1,
) -> BenchReport:
    """
    Runs every task under every arm and returns the aggregated report.
    """
    tasks = list(tasks if tasks is not None else DEFAULT_TASKS)
    arms = list(arms if arms is not None else DEFAULT_ARMS)
    workspace.mkdir(parents=True, exist_ok=True)

    report = BenchReport(trials=trials)
    for arm in arms:
        summary = ArmSummary(arm_id=arm.arm_id, description=arm.description)
        for task in tasks:
            for trial in range(trials):
                summary.runs.append(await run_task(task, arm, workspace, trial))
        report.arms.append(summary)
    return report


def run_benchmark_sync(
    workspace: Path,
    tasks: Optional[Sequence[BenchTask]] = None,
    arms: Optional[Sequence[Arm]] = None,
    trials: int = 1,
) -> BenchReport:
    return asyncio.run(run_benchmark(workspace, tasks=tasks, arms=arms, trials=trials))
