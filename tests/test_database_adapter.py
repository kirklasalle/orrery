"""
Tests for Governed Relational Database Adapter.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from orrery.adapters.database import DatabaseAdapter, classify_sql_statement
from orrery.core.types import ActionPayload, ActionRisk, CycleTier, StateContext


def test_classify_sql_statement():
    assert classify_sql_statement("SELECT * FROM users") == ActionRisk.READ_ONLY
    assert classify_sql_statement("EXPLAIN SELECT 1") == ActionRisk.READ_ONLY
    assert classify_sql_statement("PRAGMA table_info(users)") == ActionRisk.READ_ONLY
    assert classify_sql_statement("INSERT INTO users VALUES (1, 'alice')") == ActionRisk.COMPENSABLE
    assert classify_sql_statement("UPDATE users SET name='bob'") == ActionRisk.COMPENSABLE
    assert classify_sql_statement("DELETE FROM users WHERE id=1") == ActionRisk.IRREVERSIBLE
    assert classify_sql_statement("DROP TABLE users") == ActionRisk.IRREVERSIBLE
    assert classify_sql_statement("TRUNCATE TABLE logs") == ActionRisk.IRREVERSIBLE


def test_database_adapter_in_memory_crud():
    adapter = DatabaseAdapter(database_path=":memory:")

    # 1. Create table
    create_act = ActionPayload(
        action_name="execute",
        params={"sql": "CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT);"},
        tier=CycleTier.MICRO,
        target_adapter="database",
    )
    r1 = adapter.execute(create_act)
    assert r1.success

    # 2. Insert records
    insert_act = ActionPayload(
        action_name="execute",
        params={"sql": "INSERT INTO test (name) VALUES (?);", "args": ["item_alpha"]},
        tier=CycleTier.MICRO,
        target_adapter="database",
    )
    r2 = adapter.execute(insert_act)
    assert r2.success
    assert r2.output["rows_affected"] == 1

    # 3. Query records
    query_act = ActionPayload(
        action_name="query",
        params={"sql": "SELECT id, name FROM test;"},
        tier=CycleTier.MICRO,
        target_adapter="database",
    )
    r3 = adapter.execute(query_act)
    assert r3.success
    assert r3.output["columns"] == ["id", "name"]
    assert len(r3.output["rows"]) == 1
    assert r3.output["rows"][0][1] == "item_alpha"

    # 4. List tables
    list_act = ActionPayload(action_name="list_tables", params={}, tier=CycleTier.MICRO, target_adapter="database")
    r4 = adapter.execute(list_act)
    assert r4.success
    assert "test" in r4.output["tables"]

    # 5. Table info
    info_act = ActionPayload(action_name="table_info", params={"table": "test"}, tier=CycleTier.MICRO, target_adapter="database")
    r5 = adapter.execute(info_act)
    assert r5.success
    cols = [c["name"] for c in r5.output["columns"]]
    assert "id" in cols and "name" in cols


def test_database_adapter_read_only_enforcement():
    adapter = DatabaseAdapter(database_path=":memory:", read_only=True)

    # Mutating statements must be rejected before execution
    insert_act = ActionPayload(
        action_name="execute",
        params={"sql": "INSERT INTO users VALUES (1);"},
        tier=CycleTier.MICRO,
        target_adapter="database",
    )
    r = adapter.execute(insert_act)
    assert not r.success
    assert "read_only mode" in r.error


def test_database_adapter_sandbox_confinement(tmp_path: Path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    # Valid path inside sandbox
    adapter_ok = DatabaseAdapter(database_path=sandbox / "data.db", sandbox_dir=sandbox)
    assert adapter_ok.database_path == str((sandbox / "data.db").resolve())

    # Path escaping sandbox
    with pytest.raises(ValueError) as exc:
        DatabaseAdapter(database_path=tmp_path / "outside.db", sandbox_dir=sandbox)
    assert "escapes configured sandbox" in str(exc.value)


def test_database_adapter_row_limits():
    adapter = DatabaseAdapter(database_path=":memory:", max_rows=3)
    adapter.execute(ActionPayload(action_name="execute", params={"sql": "CREATE TABLE nums (val INT);"}, tier=CycleTier.MICRO, target_adapter="database"))
    for i in range(10):
        adapter.execute(ActionPayload(action_name="execute", params={"sql": f"INSERT INTO nums VALUES ({i});"}, tier=CycleTier.MICRO, target_adapter="database"))

    r = adapter.execute(ActionPayload(action_name="query", params={"sql": "SELECT * FROM nums;"}, tier=CycleTier.MICRO, target_adapter="database"))
    assert r.success
    assert r.output["row_count"] == 3
    assert r.output["truncated"] is True


def test_database_adapter_transaction_rollback():
    adapter = DatabaseAdapter(database_path=":memory:")
    # Syntax error in SQL
    r = adapter.execute(ActionPayload(action_name="execute", params={"sql": "INVALID SQL COMMAND;"}, tier=CycleTier.MICRO, target_adapter="database"))
    assert not r.success
    assert "SQL error" in r.error


@pytest.mark.asyncio
async def test_database_adapter_async_interface():
    adapter = DatabaseAdapter(is_simulation=True)
    context = StateContext()
    env = await adapter.perceive_environment(context)
    assert env["adapter"] == "database"
    assert env["is_simulation"] is True

    act = ActionPayload(action_name="query", params={"sql": "SELECT 1;"}, tier=CycleTier.MICRO, target_adapter="database")
    r = await adapter.execute_action(act)
    assert r.success


def test_database_adapter_edge_cases(tmp_path: Path):
    db_file = tmp_path / "real.db"
    adapter = DatabaseAdapter(database_path=db_file)

    # 1. Unknown action
    r1 = adapter.execute(ActionPayload(action_name="drop_everything", params={}, tier=CycleTier.MICRO, target_adapter="database"))
    assert not r1.success
    assert "unknown action" in r1.error

    # 2. Empty SQL
    r2 = adapter.execute(ActionPayload(action_name="query", params={"sql": ""}, tier=CycleTier.MICRO, target_adapter="database"))
    assert not r2.success
    assert "missing 'sql'" in r2.error

    # 3. Invalid table name
    r3 = adapter.execute(ActionPayload(action_name="table_info", params={"table": "bad;table!"}, tier=CycleTier.MICRO, target_adapter="database"))
    assert not r3.success
    assert "invalid table name" in r3.error

    # 4. Perceive environment with real tables
    adapter.execute(ActionPayload(action_name="execute", params={"sql": "CREATE TABLE items (id INT);"}, tier=CycleTier.MICRO, target_adapter="database"))
    context = StateContext()
    import asyncio
    env = asyncio.run(adapter.perceive_environment(context))
    assert "items" in env["existing_tables"]
