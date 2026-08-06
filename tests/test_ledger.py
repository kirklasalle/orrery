"""
Tests for the append-only event ledger (Law 9).
"""

import asyncio

from orrery.core.config import LedgerSettings, Settings
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.ledger import EventLedger
from orrery.core.types import CycleTier, StateContext
from tests.conftest import StubAdapter


def _ledger(tmp_path) -> EventLedger:
    return EventLedger(storage_dir=str(tmp_path / "ledger"))


def _dispatcher(tmp_path, **adapter_kwargs) -> CycleDispatcher:
    settings = Settings(ledger=LedgerSettings(storage_dir=str(tmp_path / "ledger")))
    dispatcher = CycleDispatcher(settings=settings)
    dispatcher.register_adapter(StubAdapter(**adapter_kwargs), name="default")
    return dispatcher


def test_ledger_is_hash_linked(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.append("a", summary="first")
    ledger.append("b", summary="second")

    events = ledger.events
    assert events[1].prev_hash == events[0].content_hash
    assert ledger.verify().verified


def test_tampered_event_breaks_verification(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.append("a", summary="first")
    ledger.append("b", summary="second")

    ledger._events[0].summary = "rewritten history"

    result = ledger.verify()
    assert not result.verified
    assert "content hash mismatch" in result.summary


def test_ledger_exposes_no_mutation_api():
    forbidden = {"delete", "remove", "update", "truncate", "clear", "pop"}
    assert not forbidden & {name for name in dir(EventLedger) if not name.startswith("_")}


def test_ledger_survives_backtracking(tmp_path):
    """
    Backtracking rewinds the context. The ledger must keep every event from the attempts
    that the rollback erased, including the rollback itself.
    """

    async def run():
        dispatcher = _dispatcher(tmp_path, succeed=False)
        context = StateContext(goal="fail repeatedly", tier=CycleTier.MICRO)

        result = await dispatcher.run_full_cycle(context)

        assert result.backtrack_count == result.max_backtracks
        events = dispatcher.ledger.events
        backtracks = [e for e in events if e.event_type == "cycle.backtracked"]
        failures = [e for e in events if e.event_type == "action.failed"]

        assert len(backtracks) == result.max_backtracks
        assert len(failures) > result.max_backtracks, "erased attempts must remain in the ledger"
        assert dispatcher.ledger.verify().verified

    asyncio.run(run())


def test_ledger_records_simulation_adapters(tmp_path):
    dispatcher = _dispatcher(tmp_path)
    registrations = [e for e in dispatcher.ledger.events if e.event_type == "adapter.registered"]

    assert len(registrations) == 1
    assert registrations[0].data["is_simulation"] is False


def test_ledger_persists_to_disk_and_reloads(tmp_path):
    async def run():
        dispatcher = _dispatcher(tmp_path)
        await dispatcher.run_full_cycle(StateContext(goal="write me down", tier=CycleTier.MICRO))

        path = dispatcher.ledger.path
        assert path is not None and path.exists()

        reloaded = EventLedger.read(path)
        assert len(reloaded) == len(dispatcher.ledger.events)
        assert reloaded[0].prev_hash == "0" * 64

    asyncio.run(run())


def test_delegation_decisions_reach_the_ledger(tmp_path):
    from orrery.cycles.meta import MetaCycle

    async def run():
        settings = Settings(ledger=LedgerSettings(storage_dir=str(tmp_path / "ledger")))
        root = MetaCycle(context=StateContext(goal="delegate", tier=CycleTier.META), settings=settings)
        root.register_adapter(StubAdapter(), name="default")

        await root.run_cycle()

        decisions = [
            e for e in root.dispatcher.ledger.events if e.event_type.startswith("delegation.")
        ]
        assert len(decisions) == 3
        assert all(e.policy_id == "DEL-000" for e in decisions)

    asyncio.run(run())
