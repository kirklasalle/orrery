"""
Tests for the append-only event ledger (Law 9).
"""

import asyncio

import pytest

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
    """
    LAW7-SIM. This test previously registered a *real* adapter and asserted
    `is_simulation is False`, so the policy it backs was enforced by a test that never
    exercised it. Simulated work must be distinguishable from real work in the record.
    """
    from examples.simulated.hermes import HermesAdapter
    from orrery.core.config import Settings

    dispatcher = _dispatcher(tmp_path)
    real = [e for e in dispatcher.ledger.events if e.event_type == "adapter.registered"]
    assert len(real) == 1
    assert real[0].data["is_simulation"] is False

    dispatcher.settings = dispatcher.settings.model_copy(
        update={"allow_simulated_adapters": True}
    )
    dispatcher.register_adapter(HermesAdapter())

    registrations = [e for e in dispatcher.ledger.events if e.event_type == "adapter.registered"]
    assert registrations[-1].data["is_simulation"] is True
    assert registrations[-1].data["adapter"] == "hermes"
    assert registrations[-1].policy_id == "LAW7-SIM"


def test_a_simulated_adapter_is_refused_unless_explicitly_allowed(tmp_path):
    from examples.simulated.hermes import HermesAdapter

    dispatcher = _dispatcher(tmp_path)

    with pytest.raises(ValueError, match="simulation"):
        dispatcher.register_adapter(HermesAdapter())


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


def test_ledger_hydrates_existing_chain_across_restarts(tmp_path):
    ledger_dir = str(tmp_path / "ledger")
    first = EventLedger(storage_dir=ledger_dir)
    e0 = first.append("first", summary="first event")
    e1 = first.append("second", summary="second event")

    second = EventLedger(storage_dir=ledger_dir)
    e2 = second.append("third", summary="third event")
    e3 = second.append("fourth", summary="fourth event")

    assert [e.sequence for e in second.events] == [0, 1, 2, 3]
    assert e2.prev_hash == e1.content_hash
    assert e3.prev_hash == e2.content_hash
    assert second.verify().verified is True

    reloaded = EventLedger.read(second.path)
    assert len(reloaded) == 4
    assert reloaded[0].content_hash == e0.content_hash
    assert reloaded[2].prev_hash == reloaded[1].content_hash


def test_ledger_fails_closed_on_corrupted_existing_file(tmp_path):
    ledger_dir = tmp_path / "ledger"
    first = EventLedger(storage_dir=str(ledger_dir))
    first.append("a", summary="one")
    first.append("b", summary="two")

    # Corrupt prev_hash of line 2 on disk
    lines = (ledger_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    corrupted = lines[0] + "\n" + lines[1].replace('"sequence":1', '"sequence":99') + "\n"
    (ledger_dir / "events.jsonl").write_text(corrupted, encoding="utf-8")

    with pytest.raises(ValueError, match="corrupt|integrity|verify"):
        EventLedger(storage_dir=str(ledger_dir))


def test_two_live_ledgers_interleaved_writes_stay_chained(tmp_path):
    ledger_dir = str(tmp_path / "ledger")
    l1 = EventLedger(storage_dir=ledger_dir)
    l2 = EventLedger(storage_dir=ledger_dir)

    l1.append("a", summary="from l1")
    l2.append("b", summary="from l2")
    l1.append("c", summary="from l1 again")

    reloaded = EventLedger(storage_dir=ledger_dir)
    assert [e.sequence for e in reloaded.events] == [0, 1, 2]
    assert reloaded.verify().verified is True
