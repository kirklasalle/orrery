"""
Regression tests for SEC-08 dispatcher/config/adapter-root enforcement.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from orrery.adapters.database import DatabaseAdapter
from orrery.adapters.storage import StorageAdapter
from orrery.core.config import (
    InterdictionSettings,
    LedgerSettings,
    Settings,
    load_settings,
)
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.types import ActionPayload, ActionRisk, CycleStatus, CycleTier, StateContext
from tests.conftest import StubAdapter


def test_load_settings_preserves_ratelimit_section(tmp_path: Path):
    cfg = tmp_path / "settings.yaml"
    cfg.write_text(
        """
ratelimit:
  enabled: true
  rules:
    - name: burst
      adapter: filesystem
      action: read_file
      max_calls: 2
      window_seconds: 10.0
""",
        encoding="utf-8",
    )
    settings = load_settings(cfg)
    assert settings.ratelimit.enabled is True
    assert len(settings.ratelimit.rules) == 1
    assert settings.ratelimit.rules[0].name == "burst"
    assert settings.ratelimit.rules[0].max_calls == 2


@pytest.mark.asyncio
async def test_dispatch_actions_checks_halt_between_planned_actions(tmp_path: Path):
    halt_file = tmp_path / ".halt"
    settings = Settings(
        ledger=LedgerSettings(storage_dir=str(tmp_path / "ledger")),
        interdiction=InterdictionSettings(halt_file=str(halt_file)),
    )
    dispatcher = CycleDispatcher(settings=settings)
    calls = []

    class HaltTriggerAdapter(StubAdapter):
        declared_risks = {
            "first": ActionRisk.READ_ONLY,
            "second": ActionRisk.READ_ONLY,
        }

        async def execute_action(self, action: ActionPayload):
            calls.append(action.action_name)
            if action.action_name == "first":
                halt_file.write_text("stop mid-batch", encoding="utf-8")
            return await super().execute_action(action)

    dispatcher.register_adapter(HaltTriggerAdapter(), name="default")
    ctx = StateContext(
        goal="batch",
        tier=CycleTier.MICRO,
        planned_actions=[
            ActionPayload(action_name="first", risk=ActionRisk.READ_ONLY),
            ActionPayload(action_name="second", risk=ActionRisk.READ_ONLY),
        ],
    )
    result = await dispatcher.dispatch_actions(ctx)
    assert calls == ["first"]
    assert result.status == CycleStatus.HALTED
    assert any(e.event_type == "cycle.halted" for e in dispatcher.ledger.events)


@pytest.mark.asyncio
async def test_dispatcher_protects_runtime_paths_on_database_and_storage_adapters(tmp_path: Path):
    ledger_dir = tmp_path / "ledger"
    settings = Settings(
        ledger=LedgerSettings(storage_dir=str(ledger_dir)),
        interdiction=InterdictionSettings(protect_runtime_paths=True),
    )
    dispatcher = CycleDispatcher(settings=settings)
    db = DatabaseAdapter(database_path=tmp_path / "app.db", sandbox_dir=tmp_path)
    storage = StorageAdapter(storage_root=tmp_path / "store")
    dispatcher.register_adapter(db, name="database")
    dispatcher.register_adapter(storage, name="storage")

    assert db.sandbox_roots()
    assert storage.sandbox_roots()

    # Relative path from storage root pointing at protected ledger dir must be refused
    r_storage = await dispatcher.execute_action(
        ActionPayload(
            action_name="put_object",
            target_adapter="storage",
            params={"bucket": "b", "key": "../ledger/events.jsonl", "data": "x"},
        )
    )
    assert not r_storage.success
    assert "LAW3-SUBORDINATE" in (r_storage.error or "")

    # Database adapter targeting a protected runtime path must be refused
    r_db = await dispatcher.execute_action(
        ActionPayload(
            action_name="query",
            target_adapter="database",
            params={"database_path": str(ledger_dir / "events.jsonl"), "sql": "SELECT 1;"},
        )
    )
    assert not r_db.success
    assert "LAW3-SUBORDINATE" in (r_db.error or "")
