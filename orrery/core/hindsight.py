"""
Hindsight: turning abandoned attempts into proposed governance.

Every constraint in this framework is enumerative, and they all share one wall — somebody
has to think of the rule in advance. Prohibitions need an operator who anticipated the
danger; classifications need one who has seen the action before; envelopes need a boundary
drawn ahead of time. Fail-closed defaults route around that wall. They do not remove it.

The ledger removes it from the other side. Because it lives outside rewindable state, it
retains what backtracking erased: the attempts a cycle made and abandoned. That record is
the only place a system can learn what it keeps trying and keeps failing to be allowed to
do — and a framework that stores history *inside* agent state destroys exactly this data.

So Orrery reads its own past and **proposes** constraints, with the ledger sequences that
justify each one. Two properties keep this from being self-granted authority:

- A proposal is inert. It is a draft with no signature, and nothing enforces it. Enacting
  one is an operator action through the ordinary signing path, identical to any other
  classification or prohibition.
- A proposal carries its evidence. It is an argument the operator can check, not a verdict
  they are asked to trust.

The honest limit: **a pattern is not a judgement.** Repetition means an action was tried
often and refused often, which is a reason to look, not a reason to forbid. Orrery cannot
tell a genuinely dangerous action from one an operator simply has not authorised yet, and
a proposal nobody reviews constrains precisely nothing.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from pydantic import BaseModel

from orrery.core.ledger import LedgerEvent
from orrery.core.types import ActionRisk

logger = logging.getLogger(__name__)

POLICY_ID = "LAW9-HINDSIGHT"

KIND_CLASSIFICATION = "classification"
KIND_PROHIBITION = "prohibition"


class Evidence(BaseModel):
    """The ledger entries that justify a proposal, so it can be checked rather than trusted."""

    occurrences: int
    cycles: int
    sequences: List[int] = []

    @property
    def summary(self) -> str:
        shown = ", ".join(str(item) for item in self.sequences[:8])
        more = f" (+{len(self.sequences) - 8} more)" if len(self.sequences) > 8 else ""
        return f"{self.occurrences} occurrence(s) across {self.cycles} cycle(s); events {shown}{more}"


class Proposal(BaseModel):
    """
    A draft constraint. Unsigned, unenforced, and carrying the evidence for itself.
    """

    kind: str
    adapter: str
    action_name: str
    reason: str
    evidence: Evidence
    # Left unset for classifications: repetition shows an action recurs, never what it does.
    risk: Optional[ActionRisk] = None

    @property
    def key(self) -> str:
        return f"{self.adapter}:{self.action_name}"

    def command(self) -> str:
        if self.kind == KIND_CLASSIFICATION:
            return (
                f'python -m orrery.tools.quarantine --classify {self.key} '
                f'--risk <RISK> --note "{self.reason}"'
            )
        return (
            "add to interdiction.prohibitions in your settings:\n"
            f'    - reason: "{self.reason}"\n'
            f'      adapters: ["{self.adapter}"]\n'
            f'      actions: ["{self.action_name}"]'
        )

    def render(self) -> str:
        return (
            f"  {self.key}  [{self.kind}]\n"
            f"    because:  {self.reason}\n"
            f"    evidence: {self.evidence.summary}\n"
            f"    enact:    {self.command()}"
        )


@dataclass
class _Tally:
    executed: int = 0
    failed: int = 0
    refused: int = 0
    quarantined: int = 0
    cycles: Set[str] = field(default_factory=set)
    sequences: List[int] = field(default_factory=list)

    def evidence(self, occurrences: int) -> Evidence:
        return Evidence(
            occurrences=occurrences, cycles=len(self.cycles) or 1, sequences=sorted(self.sequences)
        )


_COUNTED = {
    "action.executed": "executed",
    "action.failed": "failed",
    "action.refused": "refused",
    "action.quarantined": "quarantined",
}


def read_ledger(path: Path) -> List[LedgerEvent]:
    """
    Loads a persisted ledger. A malformed line is skipped rather than fatal: hindsight is
    advisory, and a truncated tail should not stop an operator reading their own history.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []

    events: List[LedgerEvent] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            events.append(LedgerEvent.model_validate_json(line))
        except ValueError:
            logger.warning("Skipping unreadable ledger line while reading history.")
    return events


def _tally(events: Iterable[LedgerEvent]) -> Dict[str, _Tally]:
    tallies: Dict[str, _Tally] = defaultdict(_Tally)
    for event in events:
        field_name = _COUNTED.get(event.event_type)
        if field_name is None:
            continue
        data: Dict[str, Any] = event.data or {}
        adapter, action_name = data.get("adapter"), data.get("action_name")
        if not adapter or not action_name:
            continue

        tally = tallies[f"{adapter}:{action_name}"]
        setattr(tally, field_name, getattr(tally, field_name) + 1)
        tally.sequences.append(event.sequence)
        if event.cycle_id:
            tally.cycles.add(event.cycle_id)
    return tallies


def propose(
    events: Sequence[LedgerEvent],
    min_occurrences: int = 3,
    min_cycles: int = 2,
    known: Iterable[str] = (),
) -> List[Proposal]:
    """
    Reads history and drafts constraints for the operator to accept or discard.

    A signal must recur across several *cycles*, not merely several times: one runaway loop
    repeating itself is a single mistake, not a pattern worth encoding as governance.
    """
    already = set(known)
    proposals: List[Proposal] = []

    for key, tally in sorted(_tally(events).items()):
        if key in already:
            continue
        adapter, _, action_name = key.partition(":")
        if len(tally.cycles) < min_cycles:
            continue

        if tally.quarantined >= min_occurrences:
            proposals.append(
                Proposal(
                    kind=KIND_CLASSIFICATION,
                    adapter=adapter,
                    action_name=action_name,
                    reason=(
                        f"held {tally.quarantined} times because {adapter!r} never declares it; "
                        f"classifying it once closes the gap permanently"
                    ),
                    evidence=tally.evidence(tally.quarantined),
                )
            )
            continue

        if tally.refused >= min_occurrences and tally.executed == 0:
            proposals.append(
                Proposal(
                    kind=KIND_PROHIBITION,
                    adapter=adapter,
                    action_name=action_name,
                    reason=(
                        f"refused {tally.refused} times and never once permitted; if it is never "
                        f"to be allowed, say so explicitly instead of refusing it repeatedly"
                    ),
                    evidence=tally.evidence(tally.refused),
                )
            )
            continue

        if tally.failed >= min_occurrences and tally.executed == 0:
            proposals.append(
                Proposal(
                    kind=KIND_PROHIBITION,
                    adapter=adapter,
                    action_name=action_name,
                    reason=(
                        f"attempted {tally.failed} times and never succeeded; planners keep "
                        f"spending attempts on it"
                    ),
                    evidence=tally.evidence(tally.failed),
                )
            )

    return proposals
