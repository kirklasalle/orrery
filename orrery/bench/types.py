"""
Benchmark result types.

The distinction that matters here is between what a cycle *claims* and what actually
happened on disk. `status` is Orrery's own verdict; `verified` is the filesystem's. A run
where those two disagree in the optimistic direction is a false success, and it is the
single most damaging failure mode this framework can have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from orrery.core.types import ActionPayload, StateContext


@dataclass(frozen=True)
class TaskVerification:
    """The ground truth, read back off the disk after the cycle has finished."""

    verified: bool
    detail: str


Setup = Callable[[Path], None]
Planner = Callable[[StateContext], List[ActionPayload]]
Verifier = Callable[[Path], TaskVerification]


@dataclass(frozen=True)
class BenchTask:
    """
    One benchmark task.

    `plan` is the whole experiment. It receives the live `StateContext` and may consult
    `context.lessons` — and nothing else — to choose a strategy. It must not branch on
    `backtrack_count`, because then every arm would adapt identically and the comparison
    would measure nothing.
    """

    task_id: str
    goal: str
    first_attempt_fails_because: str
    setup: Setup
    plan: Planner
    verify: Verifier
    recoverable: bool = True
    note: str = ""


@dataclass(frozen=True)
class Arm:
    """One experimental condition."""

    arm_id: str
    description: str
    max_backtracks: int
    retain_lessons: bool
    # Whether the cycle is handed a correct goal check. The harness supplies one, and a real
    # deployment would have to write it, so an arm without one measures that dependency.
    goal_check: bool = True


@dataclass
class TaskRun:
    """The outcome of a single (task, arm, trial)."""

    task_id: str
    arm_id: str
    trial: int
    status: str
    verified: bool
    verification_detail: str
    critique_passed: bool
    critique_score: float
    attempts: int
    actions_dispatched: int
    actions_failed: int
    actions_refused: int
    wall_seconds: float

    @property
    def claimed_success(self) -> bool:
        return self.status == "COMPLETED"

    @property
    def false_success(self) -> bool:
        """Reported COMPLETED while the disk says otherwise. A Law 7 violation."""
        return self.claimed_success and not self.verified

    @property
    def honest_failure(self) -> bool:
        return not self.claimed_success and not self.verified

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "arm_id": self.arm_id,
            "trial": self.trial,
            "status": self.status,
            "verified": self.verified,
            "verification_detail": self.verification_detail,
            "critique_passed": self.critique_passed,
            "critique_score": self.critique_score,
            "attempts": self.attempts,
            "actions_dispatched": self.actions_dispatched,
            "actions_failed": self.actions_failed,
            "actions_refused": self.actions_refused,
            "wall_seconds": round(self.wall_seconds, 4),
            "false_success": self.false_success,
        }


@dataclass
class ArmSummary:
    arm_id: str
    description: str
    runs: List[TaskRun] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.runs)

    @property
    def verified_count(self) -> int:
        return sum(1 for run in self.runs if run.verified)

    @property
    def verified_rate(self) -> float:
        return self.verified_count / self.total if self.total else 0.0

    @property
    def claimed_count(self) -> int:
        return sum(1 for run in self.runs if run.claimed_success)

    @property
    def false_success_count(self) -> int:
        return sum(1 for run in self.runs if run.false_success)

    @property
    def actions_dispatched(self) -> int:
        return sum(run.actions_dispatched for run in self.runs)

    @property
    def attempts(self) -> int:
        return sum(run.attempts for run in self.runs)

    @property
    def wall_seconds(self) -> float:
        return sum(run.wall_seconds for run in self.runs)

    def verified_task_ids(self) -> List[str]:
        return sorted({run.task_id for run in self.runs if run.verified})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "arm_id": self.arm_id,
            "description": self.description,
            "total_runs": self.total,
            "verified": self.verified_count,
            "verified_rate": round(self.verified_rate, 4),
            "claimed_success": self.claimed_count,
            "false_success": self.false_success_count,
            "attempts": self.attempts,
            "actions_dispatched": self.actions_dispatched,
            "wall_seconds": round(self.wall_seconds, 4),
            "runs": [run.to_dict() for run in self.runs],
        }


# The comparison the whole harness exists to make, and the three answers it can give.
THESIS = (
    "At an equal attempt budget, rollback that retains lessons recovers tasks that "
    "rollback without lessons cannot."
)
SUPPORTED = "SUPPORTED"
NOT_SUPPORTED = "NOT_SUPPORTED"
INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class BenchReport:
    arms: List[ArmSummary] = field(default_factory=list)
    trials: int = 1

    def arm(self, arm_id: str) -> Optional[ArmSummary]:
        return next((summary for summary in self.arms if summary.arm_id == arm_id), None)

    @property
    def false_success_count(self) -> int:
        return sum(summary.false_success_count for summary in self.arms)

    @property
    def shipped_false_success_count(self) -> int:
        """
        False successes in the configuration Orrery actually ships. The `unverified` arm's
        are a measurement of what omitting a goal check costs, not a defect to gate on.
        """
        treatment = self.arm("backtrack")
        return treatment.false_success_count if treatment else 0

    @property
    def goal_check_delta(self) -> Optional[int]:
        """
        How many tasks the goal check is worth. The harness supplies one; a deployment has
        to write it, so this is the part of the result that is not free.
        """
        treatment = self.arm("backtrack")
        unverified = self.arm("unverified")
        if treatment is None or unverified is None:
            return None
        return treatment.verified_count - unverified.verified_count

    def verdict(self) -> str:
        """
        Judges the thesis against the control, not against doing nothing. Beating
        `single_pass` proves only that retrying beats not retrying, which is not a claim
        worth making.
        """
        treatment = self.arm("backtrack")
        control = self.arm("blind_retry")
        if treatment is None or control is None or not treatment.total:
            return INCONCLUSIVE
        if treatment.verified_count > control.verified_count:
            return SUPPORTED
        return NOT_SUPPORTED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thesis": THESIS,
            "verdict": self.verdict(),
            "trials": self.trials,
            "false_success_total": self.false_success_count,
            "false_success_shipped": self.shipped_false_success_count,
            "goal_check_delta": self.goal_check_delta,
            "arms": [summary.to_dict() for summary in self.arms],
        }

    def render(self) -> str:
        lines: List[str] = []
        lines.append("ORRERY BACKTRACKING BENCHMARK")
        lines.append("=" * 78)
        lines.append(f"Thesis: {THESIS}")
        lines.append(f"Trials per task per arm: {self.trials}")
        lines.append("")

        header = f"{'arm':<14}{'verified':>10}{'claimed':>9}{'false':>7}{'attempts':>10}{'actions':>9}{'seconds':>9}"
        lines.append(header)
        lines.append("-" * len(header))
        for summary in self.arms:
            lines.append(
                f"{summary.arm_id:<14}"
                f"{summary.verified_count:>4}/{summary.total:<5}"
                f"{summary.claimed_count:>9}"
                f"{summary.false_success_count:>7}"
                f"{summary.attempts:>10}"
                f"{summary.actions_dispatched:>9}"
                f"{summary.wall_seconds:>9.2f}"
            )
        lines.append("")

        task_ids = sorted({run.task_id for summary in self.arms for run in summary.runs})
        arm_ids = [summary.arm_id for summary in self.arms]
        width = max((len(task_id) for task_id in task_ids), default=12) + 2
        lines.append("Per task (v = verified on disk, X = not, ! = claimed success but unverified)")
        lines.append("-" * 78)
        lines.append(f"{'task':<{width}}" + "".join(f"{arm_id:>14}" for arm_id in arm_ids))
        for task_id in task_ids:
            cells = []
            for summary in self.arms:
                runs = [run for run in summary.runs if run.task_id == task_id]
                verified = sum(1 for run in runs if run.verified)
                mark = "v" if verified == len(runs) and runs else "X"
                if any(run.false_success for run in runs):
                    mark = "!"
                cells.append(f"{mark} {verified}/{len(runs)}".rjust(14))
            lines.append(f"{task_id:<{width}}" + "".join(cells))
        lines.append("")

        lines.append(f"VERDICT: {self.verdict()}")
        if self.goal_check_delta is not None:
            lines.append(
                f"Goal check is worth {self.goal_check_delta} task(s): the harness supplies one, "
                f"a deployment has to write it."
            )
        if self.shipped_false_success_count:
            lines.append(
                f"WARNING: {self.shipped_false_success_count} run(s) in the shipped configuration "
                "reported COMPLETED while the filesystem showed the goal was not met."
            )
        elif self.false_success_count:
            lines.append(
                f"Note: {self.false_success_count} false success(es), all in the 'unverified' "
                "arm. That is the measured cost of running without a goal check, not a defect."
            )
        return "\n".join(lines)
