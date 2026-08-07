"""
Tests for ledger invariants.

These check detection, and the tests say so. An invariant fires *after* the action that
breached it; nothing here claims otherwise, and `test_an_invariant_cannot_prevent_the_action_that_breached_it`
exists to keep the claim honest if someone later reads these as prevention.
"""

from datetime import datetime, timedelta, timezone

import pytest

from orrery.core.config import (
    CheckpointSettings,
    InterdictionSettings,
    InvariantSettings,
    LedgerSettings,
    Settings,
)
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.invariants import (
    ON_BREACH_HALT,
    Invariant,
    InvariantMonitor,
)
from orrery.core.ledger import EventLedger
from orrery.core.types import ActionPayload, CyclePhase, CycleStatus, CycleTier, StateContext
from tests.conftest import StubAdapter

READ_STORM = {
    "invariant_id": "read-storm",
    "description": "bulk reads in a short window look like exfiltration",
    "window_seconds": 60,
    "event_types": ["action.executed"],
    "match": {"action_name": "anything"},
    "max_events": 3,
}

REFUSAL_STORM = {
    "invariant_id": "refusal-storm",
    "description": "a planner probing its boundaries",
    "window_seconds": 60,
    "event_types": ["action.refused"],
    "max_events": 2,
}


def _ledger(tmp_path) -> EventLedger:
    return EventLedger(storage_dir=str(tmp_path / "ledger"), persist=False)


def _settings(tmp_path, rules, on_breach="record") -> Settings:
    return Settings(
        checkpointing=CheckpointSettings(storage_dir=str(tmp_path / "checkpoints")),
        ledger=LedgerSettings(persist=False, storage_dir=str(tmp_path / "ledger")),
        interdiction=InterdictionSettings(halt_file=str(tmp_path / "halt")),
        invariants=InvariantSettings(rules=rules, on_breach=on_breach),
    )


def test_a_shape_no_single_action_reveals_is_detected(tmp_path):
    ledger = _ledger(tmp_path)
    monitor = InvariantMonitor([Invariant(**READ_STORM)])

    for _ in range(3):
        ledger.append("action.executed", action_name="anything")
    assert monitor.evaluate(ledger.events) == []

    ledger.append("action.executed", action_name="anything")
    breaches = monitor.evaluate(ledger.events)

    assert len(breaches) == 1
    assert breaches[0].invariant_id == "read-storm"
    assert breaches[0].observed == 4
    assert breaches[0].limit == 3


def test_events_outside_the_window_do_not_count(tmp_path):
    ledger = _ledger(tmp_path)
    monitor = InvariantMonitor([Invariant(**READ_STORM)])

    for _ in range(6):
        ledger.append("action.executed", action_name="anything")

    later = datetime.now(timezone.utc) + timedelta(seconds=120)
    assert monitor.evaluate(ledger.events, now=later) == []


def test_a_breach_is_reported_once_per_window_not_once_per_action(tmp_path):
    ledger = _ledger(tmp_path)
    monitor = InvariantMonitor([Invariant(**READ_STORM)])

    for _ in range(8):
        ledger.append("action.executed", action_name="anything")

    assert len(monitor.evaluate(ledger.events)) == 1
    assert monitor.evaluate(ledger.events) == [], "a standing breach must not spam the ledger"


def test_a_distinct_count_limit_catches_breadth(tmp_path):
    ledger = _ledger(tmp_path)
    monitor = InvariantMonitor(
        [
            Invariant(
                invariant_id="breadth",
                description="one cycle touching many adapters",
                event_types=["action.executed"],
                distinct_field="adapter",
                max_distinct=2,
            )
        ]
    )

    for name in ("alpha", "beta"):
        ledger.append("action.executed", adapter=name)
    assert monitor.evaluate(ledger.events) == []

    ledger.append("action.executed", adapter="gamma")
    breaches = monitor.evaluate(ledger.events)

    assert len(breaches) == 1
    assert breaches[0].kind == "distinct adapter"
    assert breaches[0].observed == 3


def test_volume_alone_does_not_trip_a_breadth_limit(tmp_path):
    ledger = _ledger(tmp_path)
    monitor = InvariantMonitor(
        [
            Invariant(
                invariant_id="breadth",
                description="many adapters",
                event_types=["action.executed"],
                distinct_field="adapter",
                max_distinct=2,
            )
        ]
    )

    for _ in range(50):
        ledger.append("action.executed", adapter="alpha")

    assert monitor.evaluate(ledger.events) == []


def test_filters_select_only_the_events_that_matter(tmp_path):
    ledger = _ledger(tmp_path)
    monitor = InvariantMonitor([Invariant(**REFUSAL_STORM)])

    for _ in range(10):
        ledger.append("action.executed", action_name="harmless")
    assert monitor.evaluate(ledger.events) == []

    for _ in range(3):
        ledger.append("action.refused", policy_id="RISK-001")

    assert len(monitor.evaluate(ledger.events)) == 1


def test_an_invariant_with_no_limit_is_dropped_rather_than_silently_kept():
    """
    A rule that sets no limit can never fire. Keeping it would make the configuration look
    like it covers something it does not.
    """
    monitor = InvariantMonitor(
        [
            Invariant(invariant_id="toothless", description="sets no limit"),
            Invariant(**READ_STORM),
        ]
    )

    assert [item.invariant_id for item in monitor.invariants] == ["read-storm"]


async def test_a_breach_is_recorded_in_the_ledger(tmp_path):
    dispatcher = CycleDispatcher(settings=_settings(tmp_path, [READ_STORM]))
    dispatcher.register_adapter(StubAdapter(), name="default")

    context = StateContext(goal="bulk work", tier=CycleTier.MICRO)
    context.planned_actions.extend(
        ActionPayload(action_name="anything", target_adapter="default") for _ in range(5)
    )

    context = await dispatcher.dispatch_actions(context)

    breached = [e for e in dispatcher.ledger.events if e.event_type == "invariant.breached"]
    assert len(breached) == 1
    assert breached[0].policy_id == "LAW10-INVARIANT"
    assert breached[0].data["invariant_id"] == "read-storm"
    assert breached[0].data["halted"] is False
    assert any("Invariant breached" in lesson for lesson in context.lessons)


async def test_an_invariant_cannot_prevent_the_action_that_breached_it(tmp_path):
    """
    The claim this module must never overstate. Detection runs after dispatch: the fourth
    action executed, and only then did anything notice.
    """
    dispatcher = CycleDispatcher(settings=_settings(tmp_path, [READ_STORM], on_breach="halt"))
    adapter = StubAdapter()
    dispatcher.register_adapter(adapter, name="default")

    context = StateContext(goal="bulk work", tier=CycleTier.MICRO)
    context.planned_actions.extend(
        ActionPayload(action_name="anything", target_adapter="default") for _ in range(10)
    )

    context = await dispatcher.dispatch_actions(context)

    assert len(adapter.executed) == 4, "the breaching action ran; it could not be prevented"
    assert context.status is CycleStatus.HALTED, "but the next six were contained"


async def test_recording_mode_lets_the_cycle_continue(tmp_path):
    dispatcher = CycleDispatcher(settings=_settings(tmp_path, [READ_STORM]))
    adapter = StubAdapter()
    dispatcher.register_adapter(adapter, name="default")

    context = StateContext(goal="bulk work", tier=CycleTier.MICRO)
    context.planned_actions.extend(
        ActionPayload(action_name="anything", target_adapter="default") for _ in range(10)
    )

    context = await dispatcher.dispatch_actions(context)

    assert len(adapter.executed) == 10
    assert context.status is not CycleStatus.HALTED


async def test_invariants_see_attempts_that_backtracking_discarded(tmp_path):
    """
    The payoff for keeping the audit trail outside rewindable state. A loop that tries the
    same thing repeatedly and rewinds after each attempt leaves nothing in StateContext and
    a full history here.
    """
    dispatcher = CycleDispatcher(settings=_settings(tmp_path, [READ_STORM]))
    dispatcher.register_adapter(StubAdapter(succeed=False), name="default")

    context = StateContext(goal="doomed", tier=CycleTier.MICRO, max_backtracks=3)
    context = await dispatcher.run_full_cycle(context)

    assert context.execution_receipts == [] or len(context.execution_receipts) < 4
    dispatched = [
        e for e in dispatcher.ledger.events if e.event_type in ("action.executed", "action.failed")
    ]
    assert len(dispatched) >= 4, "the ledger retains the attempts the rollback discarded"


def test_no_invariants_configured_is_the_default(tmp_path):
    settings = Settings()
    assert settings.invariants.rules == []
    assert settings.invariants.on_breach == "record"

    monitor = InvariantMonitor()
    assert monitor.evaluate([]) == []
    assert not monitor.halts


def test_halt_mode_is_opt_in():
    assert not InvariantMonitor([], on_breach="record").halts
    assert InvariantMonitor([], on_breach=ON_BREACH_HALT).halts
