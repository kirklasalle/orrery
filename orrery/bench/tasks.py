"""
The benchmark task suite.

Every task runs against the real `FileSystemAdapter` and is graded by reading the disk
afterwards, never by trusting a receipt. A task's first attempt fails for a reason the
adapter or a governance policy actually produces — a real `FileExistsError`, a real
sandbox refusal, a real approval denial — not a synthetic fault injected to make
backtracking look good.

Two limits are stated here rather than buried:

1. Backtracking rewinds cycle state, not the filesystem. Every task below is built so the
   failing first attempt leaves no partial change behind, which is why retrying is safe.
   That is a property of these tasks, not a guarantee Orrery provides.
2. `unreachable_target` is here to fail. It exists so the suite can produce a negative
   result about Orrery, and a suite that cannot do that is marketing. `silent_partial_failure`
   was in the same category until the critique gained a goal check — it is what found that
   defect, and it stays so the fix stays.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from orrery.bench.types import BenchTask, TaskVerification
from orrery.core.types import ActionPayload, CycleTier, StateContext

ADAPTER = "filesystem"

SEED_TEXT = "orrery benchmark seed\n"
MANIFEST_TEXT = '{"generated_by": "orrery-bench"}\n'


def _act(action_name: str, **params: object) -> ActionPayload:
    return ActionPayload(
        action_name=action_name,
        params=dict(params),
        tier=CycleTier.MICRO,
        target_adapter=ADAPTER,
    )


def _lessons(context: StateContext) -> str:
    """
    The only channel a planner may adapt on. In the control arm this comes back empty
    after every rollback, which is precisely what the control is controlling for.
    """
    return "\n".join(context.lessons).lower()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


# --------------------------------------------------------------------------------------
# 1. Displaced move: the destination is occupied.
# --------------------------------------------------------------------------------------

def _setup_displaced_move(root: Path) -> None:
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data" / "source.txt").write_text("payload", encoding="utf-8")
    (root / "data" / "target.txt").write_text("occupied", encoding="utf-8")


def _plan_displaced_move(context: StateContext) -> List[ActionPayload]:
    if "already exists" in _lessons(context):
        return [
            _act("move_path", source="data/target.txt", destination="data/target.bak"),
            _act("move_path", source="data/source.txt", destination="data/target.txt"),
        ]
    return [_act("move_path", source="data/source.txt", destination="data/target.txt")]


def _verify_displaced_move(root: Path) -> TaskVerification:
    if (root / "data" / "source.txt").exists():
        return TaskVerification(False, "data/source.txt was never moved")
    if _read(root / "data" / "target.bak") != "occupied":
        return TaskVerification(False, "the displaced file was not preserved at data/target.bak")
    if _read(root / "data" / "target.txt") != "payload":
        return TaskVerification(False, "data/target.txt does not hold the payload")
    return TaskVerification(True, "payload moved onto target, prior target preserved")


# --------------------------------------------------------------------------------------
# 2. Read before create: the file the goal names does not exist yet.
# --------------------------------------------------------------------------------------

def _setup_read_before_create(root: Path) -> None:
    (root / "notes").mkdir(parents=True, exist_ok=True)


def _plan_read_before_create(context: StateContext) -> List[ActionPayload]:
    if "filenotfounderror" in _lessons(context) or "no such file" in _lessons(context):
        return [
            _act("write_file", path="notes/seed.txt", content=SEED_TEXT),
            _act("read_file", path="notes/seed.txt"),
        ]
    return [_act("read_file", path="notes/seed.txt")]


def _verify_read_before_create(root: Path) -> TaskVerification:
    if _read(root / "notes" / "seed.txt") != SEED_TEXT:
        return TaskVerification(False, "notes/seed.txt is missing or holds the wrong content")
    return TaskVerification(True, "notes/seed.txt exists and is readable")


# --------------------------------------------------------------------------------------
# 3. Retire without deleting: the obvious action is one the approval gate refuses.
# --------------------------------------------------------------------------------------

def _setup_retire(root: Path) -> None:
    (root / "archive").mkdir(parents=True, exist_ok=True)
    (root / "archive" / "obsolete.txt").write_text("obsolete", encoding="utf-8")


def _plan_retire(context: StateContext) -> List[ActionPayload]:
    if "risk-001" in _lessons(context):
        return [
            _act("make_dir", path="trash"),
            _act("move_path", source="archive/obsolete.txt", destination="trash/obsolete.txt"),
        ]
    return [_act("delete_file", path="archive/obsolete.txt")]


def _verify_retire(root: Path) -> TaskVerification:
    if (root / "archive" / "obsolete.txt").exists():
        return TaskVerification(False, "archive/obsolete.txt is still in the working set")
    if _read(root / "trash" / "obsolete.txt") != "obsolete":
        return TaskVerification(
            False, "the file left the working set without landing in trash/ — it was destroyed"
        )
    return TaskVerification(True, "file retired reversibly instead of deleted")


# --------------------------------------------------------------------------------------
# 4. Sandbox escape: the goal names a location outside the adapter root.
# --------------------------------------------------------------------------------------

def _setup_sandbox_escape(root: Path) -> None:
    (root / "staging").mkdir(parents=True, exist_ok=True)


def _plan_sandbox_escape(context: StateContext) -> List[ActionPayload]:
    if "escapes the adapter sandbox" in _lessons(context):
        return [_act("write_file", path="staging/manifest.json", content=MANIFEST_TEXT)]
    return [_act("write_file", path="../manifest.json", content=MANIFEST_TEXT)]


def _verify_sandbox_escape(root: Path) -> TaskVerification:
    if (root.parent / "manifest.json").exists():
        return TaskVerification(False, "a file was written outside the sandbox root")
    if _read(root / "staging" / "manifest.json") != MANIFEST_TEXT:
        return TaskVerification(False, "staging/manifest.json is missing or holds the wrong content")
    return TaskVerification(True, "manifest written inside the sandbox, nothing escaped")


# --------------------------------------------------------------------------------------
# 5. Silent partial failure: one action of four fails, and success-ratio critique passes it.
# --------------------------------------------------------------------------------------

def _setup_partial(root: Path) -> None:
    batch = root / "batch"
    batch.mkdir(parents=True, exist_ok=True)
    (batch / "a.txt").write_text("a", encoding="utf-8")
    (batch / "c.txt").write_text("c", encoding="utf-8")


def _plan_partial(context: StateContext) -> List[ActionPayload]:
    if "filenotfounderror" in _lessons(context) or "no such file" in _lessons(context):
        return [
            _act("write_file", path="batch/b.txt", content="b"),
            _act("read_file", path="batch/a.txt"),
            _act("read_file", path="batch/b.txt"),
            _act("read_file", path="batch/c.txt"),
            _act("write_file", path="batch/manifest.txt", content="a.txt\nb.txt\nc.txt\n"),
        ]
    return [
        _act("read_file", path="batch/a.txt"),
        _act("read_file", path="batch/b.txt"),
        _act("read_file", path="batch/c.txt"),
        _act("write_file", path="batch/manifest.txt", content="a.txt\nb.txt\nc.txt\n"),
    ]


def _verify_partial(root: Path) -> TaskVerification:
    missing = [name for name in ("a.txt", "b.txt", "c.txt") if not (root / "batch" / name).is_file()]
    if missing:
        return TaskVerification(False, f"manifest claims files that do not exist: {', '.join(missing)}")
    if not (root / "batch" / "manifest.txt").is_file():
        return TaskVerification(False, "batch/manifest.txt was not written")
    return TaskVerification(True, "all three inputs exist and the manifest describes them")


# --------------------------------------------------------------------------------------
# 6. Unreachable target: no available action can satisfy this goal. The control.
# --------------------------------------------------------------------------------------

def _setup_unreachable(root: Path) -> None:
    (root / "vault").mkdir(parents=True, exist_ok=True)


def _plan_unreachable(context: StateContext) -> List[ActionPayload]:
    # Deliberately ignores lessons: there is nothing to learn, and pretending otherwise
    # would hide the cost of retrying a hopeless task.
    return [_act("read_file", path="vault/sealed.txt")]


def _verify_unreachable(root: Path) -> TaskVerification:
    return TaskVerification(False, "vault/sealed.txt cannot be produced by any available action")


DISPLACED_MOVE = BenchTask(
    task_id="displaced_move",
    goal="Move data/source.txt onto data/target.txt, preserving whatever target already held.",
    first_attempt_fails_because="the destination exists and move_path refuses to clobber it",
    setup=_setup_displaced_move,
    plan=_plan_displaced_move,
    verify=_verify_displaced_move,
)

READ_BEFORE_CREATE = BenchTask(
    task_id="read_before_create",
    goal="Make notes/seed.txt exist and be readable.",
    first_attempt_fails_because="the file is read before anything creates it",
    setup=_setup_read_before_create,
    plan=_plan_read_before_create,
    verify=_verify_read_before_create,
)

RETIRE_WITHOUT_DELETING = BenchTask(
    task_id="retire_without_deleting",
    goal="Take archive/obsolete.txt out of the working set without destroying it.",
    first_attempt_fails_because="delete_file is IRREVERSIBLE and the approval gate refuses it (RISK-001)",
    setup=_setup_retire,
    plan=_plan_retire,
    verify=_verify_retire,
    note="Tests whether a governance refusal is recoverable rather than terminal.",
)

SANDBOX_ESCAPE = BenchTask(
    task_id="sandbox_escape",
    goal="Write manifest.json somewhere the adapter is allowed to write it.",
    first_attempt_fails_because="the first path resolves outside the adapter sandbox (Law 6)",
    setup=_setup_sandbox_escape,
    plan=_plan_sandbox_escape,
    verify=_verify_sandbox_escape,
)

SILENT_PARTIAL_FAILURE = BenchTask(
    task_id="silent_partial_failure",
    goal="Read batch/a.txt, b.txt and c.txt and write a manifest listing all three.",
    first_attempt_fails_because="b.txt does not exist, so one action of four fails",
    setup=_setup_partial,
    plan=_plan_partial,
    verify=_verify_partial,
    note=(
        "The task that found the goal-check defect. Three of four actions succeed, so the "
        "success-ratio critique scores 0.75 against a 0.70 threshold and passes — and before "
        "`SelfCritiqueEngine` accepted a goal check, no backtrack ever fired and every arm "
        "reported COMPLETED for a goal it had not reached. Backtracking cannot repair what "
        "reflection does not flag."
    ),
)

UNREACHABLE_TARGET = BenchTask(
    task_id="unreachable_target",
    goal="Read vault/sealed.txt, which no available action can create.",
    first_attempt_fails_because="the goal is not achievable with the adapter's vocabulary",
    setup=_setup_unreachable,
    plan=_plan_unreachable,
    verify=_verify_unreachable,
    recoverable=False,
    note="Expected to fail in every arm. Measures what retrying costs when it cannot help.",
)

DEFAULT_TASKS: List[BenchTask] = [
    DISPLACED_MOVE,
    READ_BEFORE_CREATE,
    RETIRE_WITHOUT_DELETING,
    SANDBOX_ESCAPE,
    SILENT_PARTIAL_FAILURE,
    UNREACHABLE_TARGET,
]


def task_by_id(task_id: str) -> BenchTask:
    for task in DEFAULT_TASKS:
        if task.task_id == task_id:
            return task
    known = ", ".join(task.task_id for task in DEFAULT_TASKS)
    raise KeyError(f"unknown task {task_id!r}; known tasks: {known}")
