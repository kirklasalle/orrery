"""
Model Context Protocol (MCP) Server for Orrery Governance.

Implements the MCP JSON-RPC 2.0 specification (protocol version: 2024-11-05).
Exposes governed filesystem and process operations as MCP tools, ensuring that
any external LLM agent (Claude Desktop, Cursor, external pipelines) calling tools
is subject to Orrery's 6-gate defense-in-depth governance stack and tamper-evident audit ledger.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Optional

from orrery.core.dispatcher import CycleDispatcher
from orrery.core.types import ActionPayload, ActionRisk
from orrery.core.telemetry import trace_span

logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "orrery-governance"
SERVER_VERSION = "1.0.0"


class MCPGovernanceServer:
    """
    MCP Server that routes all tool execution requests through Orrery's
    CycleDispatcher governance stack.
    """

    def __init__(self, dispatcher: Optional[CycleDispatcher] = None) -> None:
        self.dispatcher = dispatcher or CycleDispatcher()
        self.initialized = False

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Returns JSON-Schema tool descriptions for all governed tools.
        """
        return [
            {
                "name": "orrery_read_file",
                "description": "Reads file contents safely within the sandboxed filesystem root.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path relative to the sandboxed storage root.",
                        }
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "orrery_write_file",
                "description": "Writes content to a file safely within the sandboxed filesystem root.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Destination path relative to the sandboxed root.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Text content to write.",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "orrery_list_directory",
                "description": "Lists directory entries safely within the sandboxed filesystem root.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path relative to sandbox root (default: root).",
                            "default": ".",
                        }
                    },
                },
            },
            {
                "name": "orrery_run_program",
                "description": "Executes an allowlisted program inside the process sandbox.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "program": {
                            "type": "string",
                            "description": "Name of the allowlisted executable program.",
                        },
                        "args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Command-line arguments.",
                            "default": [],
                        },
                        "timeout_seconds": {
                            "type": "number",
                            "description": "Execution timeout limit in seconds.",
                            "default": 30.0,
                        },
                    },
                    "required": ["program"],
                },
            },
            {
                "name": "orrery_audit_verify",
                "description": "Verifies cryptographic hash-chain integrity of the append-only audit ledger.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "orrery_governance_status",
                "description": "Returns current governance mode, active gates, and runtime limits.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    async def handle_message(self, raw_message: str | Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Processes a JSON-RPC 2.0 message and returns the response dictionary,
        or None for notifications.
        """
        if isinstance(raw_message, str):
            try:
                msg = json.loads(raw_message)
            except json.JSONDecodeError as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                }
        else:
            msg = raw_message

        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params", {})

        # Handle notifications
        if msg_id is None:
            if method == "notifications/initialized":
                self.initialized = True
            return None

        # Route methods
        if method == "initialize":
            self.initialized = True
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION,
                    },
                },
            }

        if method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": self.get_tool_definitions()},
            }

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            call_result = await self._execute_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": call_result,
            }

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    async def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Maps tool calls into governed ActionPayloads and dispatches them through
        the 6-gate stack.
        """
        with trace_span(f"orrery.mcp.{tool_name}", attributes={"orrery.mcp.tool": tool_name}):
            # Non-adapter meta-tools
            if tool_name == "orrery_audit_verify":
                is_valid = True
                error_msg = None
                if hasattr(self.dispatcher.ledger, "verify_chain"):
                    is_valid, error_msg = self.dispatcher.ledger.verify_chain()
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "ledger_valid": is_valid,
                                    "error": error_msg,
                                    "event_count": len(self.dispatcher.ledger.events),
                                },
                                indent=2,
                            ),
                        }
                    ],
                    "isError": not is_valid,
                }

            if tool_name == "orrery_governance_status":
                status_info = {
                    "governance_mode": "strict" if self.dispatcher.attestation.allowed else "standard",
                    "attestation_allowed": self.dispatcher.attestation.allowed,
                    "active_adapters": list(self.dispatcher._adapters.keys()),
                    "quarantine_enabled": self.dispatcher.quarantine_gate.enabled,
                    "rate_limit_enabled": self.dispatcher.rate_limit_gate.enabled,
                    "ledger_events": len(self.dispatcher.ledger.events),
                }
                return {
                    "content": [{"type": "text", "text": json.dumps(status_info, indent=2)}],
                    "isError": False,
                }

            # Map to adapter actions
            action_map = {
                "orrery_read_file": ("filesystem", "read_file", ActionRisk.READ_ONLY),
                "orrery_list_directory": ("filesystem", "list_dir", ActionRisk.READ_ONLY),
                "orrery_write_file": ("filesystem", "write_file", ActionRisk.COMPENSABLE),
                "orrery_run_program": ("process", "run_program", ActionRisk.IRREVERSIBLE),
            }

            if tool_name not in action_map:
                return {
                    "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                    "isError": True,
                }

            target_adapter, action_name, default_risk = action_map[tool_name]
            payload = ActionPayload(
                action_name=action_name,
                target_adapter=target_adapter,
                params=arguments,
                risk=default_risk,
            )

            receipt = await self.dispatcher.execute_action(payload)

            if not receipt.success:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"GOVERNANCE REFUSAL / ERROR: {receipt.error}",
                        }
                    ],
                    "isError": True,
                }

            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(receipt.output, indent=2)
                        if not isinstance(receipt.output, str)
                        else receipt.output,
                    }
                ],
                "isError": False,
            }


async def run_stdio_server(server: Optional[MCPGovernanceServer] = None) -> None:
    """
    Runs the MCP server over standard input / output (stdio transport).
    """
    mcp_server = server or MCPGovernanceServer()
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        text = line.decode("utf-8").strip()
        if not text:
            continue

        response = await mcp_server.handle_message(text)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
