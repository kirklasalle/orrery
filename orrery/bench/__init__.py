"""
Benchmark harness for Orrery's backtracking claim.

Orrery asserts that checkpoint-and-rollback with retained lessons makes long-horizon work
more reliable. Until this package existed there was nothing in the repository that could
show that assertion to be false, which meant it was not a claim so much as a slogan.

The harness runs real tasks through the real `FileSystemAdapter` and grades every run by
reading the sandbox afterwards. Three metrics come out of it:

  verified rate   how often the goal was actually achieved on disk
  false success   how often a cycle reported COMPLETED when it was not — the failure mode
                  this framework exists to refuse
  cost            attempts and actions burned, including on tasks retrying cannot fix

Run it with `python -m orrery.bench`.
"""

from orrery.bench.runner import (
    BACKTRACK,
    BLIND_RETRY,
    DEFAULT_ARMS,
    SINGLE_PASS,
    UNVERIFIED,
    run_benchmark,
    run_benchmark_sync,
    run_task,
)
from orrery.bench.tasks import DEFAULT_TASKS, task_by_id
from orrery.bench.types import (
    Arm,
    ArmSummary,
    BenchReport,
    BenchTask,
    TaskRun,
    TaskVerification,
)

__all__ = [
    "Arm",
    "ArmSummary",
    "BACKTRACK",
    "BLIND_RETRY",
    "BenchReport",
    "BenchTask",
    "DEFAULT_ARMS",
    "DEFAULT_TASKS",
    "SINGLE_PASS",
    "TaskRun",
    "TaskVerification",
    "UNVERIFIED",
    "run_benchmark",
    "run_benchmark_sync",
    "run_task",
    "task_by_id",
]
