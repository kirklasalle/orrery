"""
What the operator forbids, and what the framework will not let a cycle do to its own
constraints.

Three of the ten Laws describe judgements Orrery cannot make. It has no harm model
(Law 1), no evaluator for whether an instruction conflicts with one (Law 2), and no
self-preservation drive to subordinate (Law 3). Those stay `NOT_ENFORCED` in the registry
and nothing here changes that. What this module adds is narrower, and each piece exists
because the alternative was a hole rather than a philosophical limit:

**Prohibitions.** The operator declares what must never happen. Orrery still cannot judge
harm; it can refuse what somebody who *can* judge it has written down. A prohibition is
deliberately not an approval question. An `ApprovalToken` answers "may I do this
irreversible thing?", and the whole point of a prohibition is that the question is not
open at execution time — so a prohibited action is refused with a token attached and the
refusal is ledgered either way.

**Protected paths.** No action may touch the machinery that audits and constrains the
cycle: its ledger, its checkpoints, its attestation, its operator keyring, its halt file.
This was a real hole, not a hypothetical one. A `FileSystemAdapter` rooted at the project
directory could `delete_tree(".ledger")` — or simply `delete_tree(".")` — and the
append-only audit log that Law 9 rests on was defended by nothing but the absence of a
plan to attack it. Containment is checked in both directions, because deleting a parent
destroys a child just as thoroughly.

**A halt switch.** An operator instruction to stop outranks the goal in progress. The
cycle cannot clear it, because the halt file is itself a protected path.

The honest limit on all three: they are enforced at the action boundary, by inspecting the
values an action carries. Every parameter value is examined, recursively, rather than a
list of parameter names somebody thought to enumerate — an earlier version checked only
`path`, `source`, `destination`, `cwd`, and `directory`, so an adapter whose parameter
happened to be called `target_file` walked straight past the ledger protection. There is
no opt-out and adapters are not consulted, because the whole point is defending against
adapters nobody vetted. What remains outside its reach is an adapter that reaches the
filesystem without naming the path in its action at all. This constrains actions, not
adapters.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Iterable, Iterator, List, Mapping, Optional, Sequence

from pydantic import BaseModel

from orrery.core.types import ActionPayload

logger = logging.getLogger(__name__)

# How far to descend into nested action parameters looking for paths.
_MAX_SCAN_DEPTH = 6

PROHIBITION_POLICY = "LAW1-PROHIBIT"
PROTECTION_POLICY = "LAW3-SUBORDINATE"
HALT_POLICY = "LAW2-HALT"


class Prohibition(BaseModel):
    """
    One operator-declared refusal. Empty criteria are wildcards; the prohibition applies
    when every criterion it *does* name matches.
    """

    reason: str
    adapters: List[str] = []
    actions: List[str] = []
    paths: List[str] = []

    def criteria_count(self) -> int:
        return sum(1 for group in (self.adapters, self.actions, self.paths) if group)


class InterdictionDecision(BaseModel):
    allowed: bool
    policy_id: Optional[str] = None
    reason: Optional[str] = None


def strings_in(value: Any, depth: int = 0) -> Iterator[str]:
    """
    Every string an action carries, however deeply nested. A path hidden inside a list or a
    dict is still a path. Shared with the envelope gate so both see the same values.
    """
    if depth > _MAX_SCAN_DEPTH:
        return
    if isinstance(value, str):
        if value:
            yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from strings_in(item, depth + 1)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from strings_in(item, depth + 1)


def resolve_under(value: str, root: Optional[Path]) -> Optional[Path]:
    """
    Resolves a caller-supplied string as a path, relative to an adapter root when it has
    one. Returns None for anything the filesystem cannot make sense of.
    """
    try:
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate.resolve()
        base = root or Path.cwd()
        return (base / candidate).resolve()
    except (OSError, ValueError):
        return None


def _overlaps(candidate: Path, protected: Path) -> bool:
    """
    True when acting on `candidate` would reach `protected`. Checked in both directions:
    deleting a parent destroys a child just as thoroughly as deleting the child.
    """
    if candidate == protected:
        return True
    return candidate.is_relative_to(protected) or protected.is_relative_to(candidate)


class InterdictionGate:
    """
    Refuses actions the operator has forbidden, and actions that would reach Orrery's own
    audit and governance machinery.
    """

    def __init__(
        self,
        prohibitions: Sequence[Prohibition] = (),
        protected_paths: Iterable[str] = (),
        halt_file: Optional[str] = None,
    ):
        self.prohibitions = list(prohibitions)
        self.halt_file = Path(halt_file).resolve() if halt_file else None
        self._protected: List[Path] = []

        for entry in protected_paths:
            self.protect(entry)
        if self.halt_file is not None:
            self.protect(str(self.halt_file))

        for prohibition in self.prohibitions:
            if prohibition.criteria_count() == 0:
                raise ValueError(
                    f"prohibition {prohibition.reason!r} names no adapter, action, or path; "
                    f"a rule that matches everything is almost always a typo"
                )

    @property
    def protected_paths(self) -> List[Path]:
        return list(self._protected)

    def protect(self, path: Optional[str]) -> None:
        if not path:
            return
        resolved = resolve_under(path, None)
        if resolved is not None and resolved not in self._protected:
            self._protected.append(resolved)

    def halted(self) -> Optional[str]:
        """
        The operator's stop instruction, if present. Read fresh every time: a halt raised
        mid-run must take effect on the next phase, not at the next restart.
        """
        if self.halt_file is None or not self.halt_file.is_file():
            return None
        try:
            note = self.halt_file.read_text(encoding="utf-8").strip()
        except OSError:
            note = ""
        return note or f"halt file present at {self.halt_file}"

    def action_paths(
        self, action: ActionPayload, adapter_root: Optional[Path] = None
    ) -> List[Path]:
        """
        Every parameter value that could name a location, resolved. Nothing is skipped for
        being unrecognized: an unrecognized parameter is exactly the case that used to slip
        through.

        A relative path is resolved under the adapter's claimed root **and** under the
        process directory, because the root is the adapter's own assertion about where it
        lives. An adapter that names a decoy sandbox would otherwise make every relative
        path resolve somewhere harmless while the real work happened elsewhere.
        """
        bases: List[Optional[Path]] = [adapter_root]
        if adapter_root is not None:
            bases.append(None)

        resolved: List[Path] = []
        for value in strings_in(action.params):
            for base in bases:
                candidate = resolve_under(value, base)
                if candidate is not None and candidate not in resolved:
                    resolved.append(candidate)
        return resolved

    def evaluate(
        self, action: ActionPayload, adapter_root: Optional[Path] = None
    ) -> InterdictionDecision:
        paths = self.action_paths(action, adapter_root)

        for protected in self._protected:
            for candidate in paths:
                if _overlaps(candidate, protected):
                    return InterdictionDecision(
                        allowed=False,
                        policy_id=PROTECTION_POLICY,
                        reason=(
                            f"action {action.action_name!r} would reach {protected}, which holds "
                            f"the record or the rules this cycle runs under"
                        ),
                    )

        for prohibition in self.prohibitions:
            if self._matches(prohibition, action, paths):
                return InterdictionDecision(
                    allowed=False,
                    policy_id=PROHIBITION_POLICY,
                    reason=(
                        f"action {action.action_name!r} is prohibited by operator declaration: "
                        f"{prohibition.reason}"
                    ),
                )

        return InterdictionDecision(allowed=True)

    def _matches(
        self, prohibition: Prohibition, action: ActionPayload, paths: Sequence[Path]
    ) -> bool:
        if prohibition.adapters and action.target_adapter not in prohibition.adapters:
            return False
        if prohibition.actions and action.action_name not in prohibition.actions:
            return False
        if prohibition.paths:
            forbidden = [p for p in (resolve_under(entry, None) for entry in prohibition.paths) if p]
            if not any(_overlaps(candidate, area) for candidate in paths for area in forbidden):
                return False
        return True


def runtime_paths(settings) -> List[str]:
    """
    The files and directories that carry Orrery's own record and rules. A cycle that could
    edit these could rewrite the evidence of what it did, or the limits it did it under.
    """
    paths = [
        settings.checkpointing.storage_dir,
        settings.ledger.storage_dir,
        settings.governance.attestation_path,
        os.environ.get("ORRERY_OPERATOR_KEYRING"),
        os.environ.get("ORRERY_OPERATOR_PRIVATE_KEY"),
    ]
    return [entry for entry in paths if entry]
