"""
Command line entry point: `python -m orrery.bench`.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

from orrery.bench.runner import DEFAULT_ARMS, run_benchmark_sync
from orrery.bench.tasks import DEFAULT_TASKS, task_by_id
from orrery.bench.types import NOT_SUPPORTED


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m orrery.bench",
        description="Measure whether backtracking with retained lessons beats blind retry.",
    )
    parser.add_argument("--trials", type=int, default=1, help="Trials per task per arm.")
    parser.add_argument(
        "--task",
        action="append",
        dest="tasks",
        metavar="TASK_ID",
        help="Run only this task. Repeatable.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Directory for benchmark sandboxes. A temporary directory is used if omitted.",
    )
    parser.add_argument("--json", type=Path, dest="json_path", help="Write the full report as JSON.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any run reported success the filesystem does not confirm.",
    )
    parser.add_argument("--list", action="store_true", help="List the task suite and exit.")
    parser.add_argument("--verbose", action="store_true", help="Show framework logging.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.ERROR)
    if not args.verbose:
        # Failure is the subject of this benchmark, not an incident. Logging every refused
        # action at ERROR would bury the report it exists to produce.
        logging.getLogger("orrery").setLevel(logging.CRITICAL)

    if args.list:
        for task in DEFAULT_TASKS:
            print(f"{task.task_id}\n    goal: {task.goal}")
            print(f"    first attempt fails because: {task.first_attempt_fails_because}")
            if task.note:
                print(f"    note: {task.note}")
        return 0

    try:
        tasks = [task_by_id(task_id) for task_id in args.tasks] if args.tasks else DEFAULT_TASKS
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.workspace:
        report = run_benchmark_sync(
            args.workspace, tasks=tasks, arms=DEFAULT_ARMS, trials=args.trials
        )
    else:
        with tempfile.TemporaryDirectory(prefix="orrery-bench-") as tmp:
            report = run_benchmark_sync(
                Path(tmp), tasks=tasks, arms=DEFAULT_ARMS, trials=args.trials
            )

    print(report.render())

    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        print(f"\nJSON report written to {args.json_path}")

    if args.strict and (report.shipped_false_success_count or report.verdict() == NOT_SUPPORTED):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
