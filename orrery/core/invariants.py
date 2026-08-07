"""
Ledger invariants: the violations that do not exist in any single action.

Every other control in Orrery examines one action at a time, and there is a whole class of
harm that is invisible at that resolution. No individual file read is exfiltration; ten
thousand of them in three seconds is. No single refusal is alarming; forty in a minute is a
planner probing its boundaries. No one approval is rubber-stamping; nineteen in the time it
takes to read one of them is. The shape is the violation, and the shape only exists across
events.

So invariants are evaluated over the **ledger**, which is the right substrate for a reason
worth stating: it is append-only and immune to rollback, so it retains the attempts that
backtracking discarded. A runaway loop that tries the same destructive thing forty times and
rewinds after each one leaves no trace in `StateContext` at all, and forty entries here.

**This is detection, not prevention, and the distinction is not a technicality.** An
invariant is evaluated after an action has already been dispatched. It cannot stop the
action that breached it. Configured to halt, it stops the *next* one, which is containment
and worth having — but anything that describes this as preventing exfiltration is lying.
The honest claim is: the shape becomes visible, and is recorded with the same tamper-evident
guarantees as everything else in the ledger.

**What an invariant can see is exactly what the ledger records** — event types, policy IDs,
action names, adapters, risk classes, approvers, success. It does not record parameter
values, so an invariant can count `read_file` actions but cannot tell you which files. That
is a deliberate limit on the audit trail rather than an oversight here, and widening it is a
privacy decision, not a feature request.

**Law 8 is not addressed by this.** Distributional fairness is the one Law that would
naturally live at this resolution, and a bias detector needs a domain model Orrery does not
have and cannot infer. This is the place such a control would go if an operator supplied the
grouping. Orrery ships none, and `LAW8-EQUITY` stays `NOT_ENFORCED`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel

logger = logging.getLogger(__name__)

POLICY_ID = "LAW10-INVARIANT"

ON_BREACH_RECORD = "record"
ON_BREACH_HALT = "halt"


class Invariant(BaseModel):
    """
    A shape the operator considers pathological, expressed as a limit over a time window.
    """

    invariant_id: str
    description: str
    window_seconds: float = 60.0

    # Which events count. Empty means any.
    event_types: List[str] = []
    policy_ids: List[str] = []
    match: Dict[str, Any] = {}

    max_events: Optional[int] = None
    distinct_field: Optional[str] = None
    max_distinct: Optional[int] = None

    def limits(self) -> bool:
        return self.max_events is not None or (
            self.distinct_field is not None and self.max_distinct is not None
        )

    def selects(self, event: Any) -> bool:
        if self.event_types and event.event_type not in self.event_types:
            return False
        if self.policy_ids and event.policy_id not in self.policy_ids:
            return False
        data = getattr(event, "data", {}) or {}
        return all(data.get(key) == value for key, value in self.match.items())


class InvariantBreach(BaseModel):
    invariant_id: str
    description: str
    policy_id: str = POLICY_ID
    kind: str
    observed: int
    limit: int
    window_seconds: float
    first_sequence: Optional[int] = None
    last_sequence: Optional[int] = None

    @property
    def summary(self) -> str:
        return (
            f"{self.invariant_id}: {self.observed} {self.kind} in "
            f"{self.window_seconds:.0f}s exceeds {self.limit} \u2014 {self.description}"
        )


def _parsed(timestamp: str) -> Optional[datetime]:
    try:
        moment = datetime.fromisoformat(timestamp)
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


class InvariantMonitor:
    """
    Watches the ledger for shapes no single action reveals.
    """

    def __init__(
        self,
        invariants: Sequence[Invariant] = (),
        on_breach: str = ON_BREACH_RECORD,
    ):
        self.invariants = [item for item in invariants if item.limits()]
        self.on_breach = on_breach
        # A breach stays true for as long as its window holds, so it is reported once per
        # window rather than on every action that keeps it true.
        self._reported: Dict[str, datetime] = {}

        for item in invariants:
            if not item.limits():
                logger.warning(
                    "Invariant %r sets no limit and will never fire.", item.invariant_id
                )

    @property
    def halts(self) -> bool:
        return self.on_breach == ON_BREACH_HALT

    def evaluate(self, events: Sequence[Any], now: Optional[datetime] = None) -> List[InvariantBreach]:
        moment = now or datetime.now(timezone.utc)
        breaches: List[InvariantBreach] = []

        for invariant in self.invariants:
            cutoff = moment - timedelta(seconds=invariant.window_seconds)
            window = [
                event
                for event in events
                if invariant.selects(event)
                and (parsed := _parsed(getattr(event, "timestamp", ""))) is not None
                and parsed >= cutoff
            ]
            if not window:
                continue

            breach = self._breach_for(invariant, window)
            if breach is None:
                continue

            last_reported = self._reported.get(invariant.invariant_id)
            if last_reported is not None and moment - last_reported < timedelta(
                seconds=invariant.window_seconds
            ):
                continue

            self._reported[invariant.invariant_id] = moment
            breaches.append(breach)

        return breaches

    @staticmethod
    def _breach_for(invariant: Invariant, window: Sequence[Any]) -> Optional[InvariantBreach]:
        sequences = [getattr(event, "sequence", None) for event in window]
        bounds = {
            "first_sequence": sequences[0] if sequences else None,
            "last_sequence": sequences[-1] if sequences else None,
        }

        if invariant.max_events is not None and len(window) > invariant.max_events:
            return InvariantBreach(
                invariant_id=invariant.invariant_id,
                description=invariant.description,
                kind="event(s)",
                observed=len(window),
                limit=invariant.max_events,
                window_seconds=invariant.window_seconds,
                **bounds,
            )

        if invariant.distinct_field is not None and invariant.max_distinct is not None:
            values = {
                (getattr(event, "data", {}) or {}).get(invariant.distinct_field)
                for event in window
            }
            values.discard(None)
            if len(values) > invariant.max_distinct:
                return InvariantBreach(
                    invariant_id=invariant.invariant_id,
                    description=invariant.description,
                    kind=f"distinct {invariant.distinct_field}",
                    observed=len(values),
                    limit=invariant.max_distinct,
                    window_seconds=invariant.window_seconds,
                    **bounds,
                )

        return None
