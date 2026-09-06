"""
Governed Relational Database Adapter (Law 2, Law 4, Law 6).

Provides governed SQL execution against relational databases (SQLite built-in) with:
- Strict statement-level risk categorization:
    SELECT, EXPLAIN           -> ActionRisk.READ_ONLY
    INSERT, UPDATE            -> ActionRisk.COMPENSABLE
    DELETE, DROP, TRUNCATE    -> ActionRisk.IRREVERSIBLE (enforcing Approval Gate scrutiny)
- Path confinement / sandboxing for database files (Law 2 Envelope)
- Read-only enforcement mode option
- Memory exhaustion bounds (max_rows limits)
- Transaction rollbacks upon error
- Verifiable receipts with affected row counts and column schemas
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Mapping, Optional, Sequence, Tuple

from orrery.adapters.base import BaseAdapter
from orrery.core.types import ActionPayload, ActionRisk, ExecutionReceipt, StateContext

logger = logging.getLogger(__name__)

# SQL command classification patterns
_READ_COMMANDS = {"select", "explain", "pragma", "show", "describe"}
_COMPENSABLE_COMMANDS = {"insert", "update", "create", "replace"}
_DESTRUCTIVE_COMMANDS = {"delete", "drop", "truncate", "alter"}


def classify_sql_statement(sql: str) -> ActionRisk:
    """Extracts the leading SQL keyword to classify risk."""
    cleaned = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL).strip()
    if not cleaned:
        return ActionRisk.READ_ONLY

    first_word = cleaned.split()[0].lower()
    if first_word in _READ_COMMANDS:
        return ActionRisk.READ_ONLY
    elif first_word in _COMPENSABLE_COMMANDS:
        return ActionRisk.COMPENSABLE
    elif first_word in _DESTRUCTIVE_COMMANDS:
        return ActionRisk.IRREVERSIBLE
    return ActionRisk.IRREVERSIBLE


class DatabaseAdapter(BaseAdapter):
    """
    Adapter for governed SQL database operations.
    """

    adapter_name = "database"
    target_params: ClassVar[tuple] = ("database_path",)

    declared_risks: ClassVar[Mapping[str, ActionRisk]] = {
        "query": ActionRisk.READ_ONLY,
        "list_tables": ActionRisk.READ_ONLY,
        "table_info": ActionRisk.READ_ONLY,
        "execute": ActionRisk.COMPENSABLE,
        "execute_destructive": ActionRisk.IRREVERSIBLE,
    }

    def __init__(
        self,
        database_path: Union[str, Path] = ":memory:",
        sandbox_dir: Optional[Union[str, Path]] = None,
        read_only: bool = False,
        max_rows: int = 1000,
        is_simulation: bool = False,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(name=self.adapter_name, config=config)
        self.read_only = read_only
        self.max_rows = max_rows
        self.is_simulation = is_simulation
        self.sandbox_dir = Path(sandbox_dir).resolve() if sandbox_dir else None

        # Resolve database location
        if str(database_path) == ":memory:":
            self.database_path = ":memory:"
        else:
            p = Path(database_path).resolve()
            if self.sandbox_dir and not str(p).startswith(str(self.sandbox_dir)):
                raise ValueError(
                    f"database path '{p}' escapes configured sandbox directory '{self.sandbox_dir}'"
                )
            self.database_path = str(p)

    def classify_risk(self, action: ActionPayload) -> ActionRisk:
        action_name = action.action_name
        if action_name in ("query", "list_tables", "table_info"):
            return ActionRisk.READ_ONLY

        sql = str(action.params.get("sql") or "")
        return classify_sql_statement(sql)

    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        tables = []
        if not self.is_simulation:
            try:
                tables = self._get_tables()
            except Exception:
                pass

        return {
            "adapter": self.adapter_name,
            "database": self.database_path,
            "read_only": self.read_only,
            "max_rows": self.max_rows,
            "is_simulation": self.is_simulation,
            "existing_tables": tables,
        }

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        return self.execute(action)

    def execute(self, action: ActionPayload) -> ExecutionReceipt:
        action_name = action.action_name
        params = action.params

        if action_name not in self.declared_risks:
            return self._receipt(
                action=action,
                success=False,
                error=f"unknown action '{action_name}' on adapter '{self.adapter_name}'",
            )

        if self.is_simulation:
            return self._receipt(
                action=action,
                success=True,
                output={
                    "simulated": True,
                    "action": action_name,
                    "columns": ["id", "val"],
                    "rows": [[1, "simulated_record"]],
                    "rows_affected": 1,
                },
            )

        try:
            if action_name == "list_tables":
                tables = self._get_tables()
                return self._receipt(action=action, success=True, output={"tables": tables})

            elif action_name == "table_info":
                table = str(params.get("table") or "")
                if not table or not re.match(r"^[a-zA-Z0-9_]+$", table):
                    return self._receipt(action=action, success=False, error="invalid table name")
                info = self._get_table_info(table)
                return self._receipt(action=action, success=True, output={"columns": info})

            elif action_name in ("query", "execute", "execute_destructive"):
                sql = str(params.get("sql") or "")
                if not sql.strip():
                    return self._receipt(action=action, success=False, error="missing 'sql' query parameter")

                statement_risk = classify_sql_statement(sql)

                # Read-only enforcement check
                if self.read_only and statement_risk != ActionRisk.READ_ONLY:
                    return self._receipt(
                        action=action,
                        success=False,
                        error="mutating SQL statements are forbidden when database adapter is in read_only mode",
                    )

                # Query execution
                args = params.get("args") or ()
                return self._run_sql(action=action, sql=sql, args=args, is_query=(action_name == "query"))

        except Exception as exc:
            return self._receipt(
                action=action,
                success=False,
                error=f"Database execution error ({type(exc).__name__}): {exc}",
            )

        return self._receipt(action=action, success=False, error="unhandled operation")

    def _get_connection(self) -> sqlite3.Connection:
        if self.database_path == ":memory:":
            # Memory databases need persistent connection if state is preserved
            if not hasattr(self, "_mem_conn") or self._mem_conn is None:
                self._mem_conn = sqlite3.connect(":memory:")
            return self._mem_conn

        conn = sqlite3.connect(self.database_path)
        return conn

    def _get_tables(self) -> List[str]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            return [row[0] for row in cursor.fetchall()]
        finally:
            if self.database_path != ":memory:":
                conn.close()

    def _get_table_info(self, table: str) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"PRAGMA table_info({table});")
            return [
                {"cid": row[0], "name": row[1], "type": row[2], "notnull": bool(row[3]), "dflt_value": row[4], "pk": bool(row[5])}
                for row in cursor.fetchall()
            ]
        finally:
            if self.database_path != ":memory:":
                conn.close()

    def _run_sql(
        self,
        action: ActionPayload,
        sql: str,
        args: Union[Sequence[Any], Dict[str, Any]],
        is_query: bool,
    ) -> ExecutionReceipt:
        conn = self._get_connection()
        cursor = conn.cursor()
        start = time.time()
        try:
            cursor.execute(sql, args)
            latency = round(time.time() - start, 4)

            if cursor.description:  # Result set available (SELECT, etc.)
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchmany(self.max_rows + 1)
                truncated = len(rows) > self.max_rows
                if truncated:
                    rows = rows[: self.max_rows]

                return self._receipt(
                    action=action,
                    success=True,
                    output={
                        "columns": columns,
                        "rows": rows,
                        "row_count": len(rows),
                        "truncated": truncated,
                        "latency_seconds": latency,
                    },
                )
            else:  # Mutating statement (INSERT, UPDATE, DELETE)
                conn.commit()
                rows_affected = cursor.rowcount
                return self._receipt(
                    action=action,
                    success=True,
                    output={
                        "rows_affected": rows_affected,
                        "last_row_id": cursor.lastrowid,
                        "latency_seconds": latency,
                    },
                )
        except Exception as exc:
            conn.rollback()
            return self._receipt(
                action=action,
                success=False,
                error=f"SQL error: {exc}",
            )
        finally:
            if self.database_path != ":memory:":
                conn.close()
