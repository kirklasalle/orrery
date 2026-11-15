"""
Tests for Model Context Protocol (MCP) Governance Server (Task 2.2).

Verifies:
- JSON-RPC 2.0 handshake, ping, and tool listing.
- Tool call execution under full Orrery governance.
- Path traversal refusal reporting via MCP error format.
- Audit ledger verification and system status tools.
"""

import json
import pytest

from orrery.adapters.filesystem import FileSystemAdapter
from orrery.core.config import LedgerSettings, Settings
from orrery.core.dispatcher import CycleDispatcher
from orrery.mcp.server import MCPGovernanceServer, MCP_PROTOCOL_VERSION


@pytest.fixture
def governed_server(tmp_path):
    sandbox_dir = tmp_path / "sandbox"
    fs_adapter = FileSystemAdapter(root=str(sandbox_dir))

    dispatcher = CycleDispatcher(
        settings=Settings(
            allow_simulated_adapters=True,
            ledger=LedgerSettings(storage_dir=str(tmp_path / "ledger")),
        ),
    )
    dispatcher.register_adapter(fs_adapter)
    return MCPGovernanceServer(dispatcher=dispatcher)


@pytest.mark.asyncio
async def test_mcp_initialize(governed_server):
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {},
    }
    res = await governed_server.handle_message(req)
    assert res["jsonrpc"] == "2.0"
    assert res["id"] == 1
    result = res["result"]
    assert result["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert result["serverInfo"]["name"] == "orrery-governance"


@pytest.mark.asyncio
async def test_mcp_ping(governed_server):
    req = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    res = await governed_server.handle_message(req)
    assert res["id"] == 2
    assert res["result"] == {}


@pytest.mark.asyncio
async def test_mcp_tools_list(governed_server):
    req = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    res = await governed_server.handle_message(req)
    tools = res["result"]["tools"]
    tool_names = [t["name"] for t in tools]

    assert "orrery_read_file" in tool_names
    assert "orrery_write_file" in tool_names
    assert "orrery_list_directory" in tool_names
    assert "orrery_run_program" in tool_names
    assert "orrery_audit_verify" in tool_names
    assert "orrery_governance_status" in tool_names


@pytest.mark.asyncio
async def test_mcp_governance_status(governed_server):
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "orrery_governance_status", "arguments": {}},
    }
    res = await governed_server.handle_message(req)
    assert res["result"]["isError"] is False
    status_text = res["result"]["content"][0]["text"]
    status = json.loads(status_text)
    assert "active_adapters" in status
    assert "filesystem" in status["active_adapters"]


@pytest.mark.asyncio
async def test_mcp_audit_verify(governed_server):
    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "orrery_audit_verify", "arguments": {}},
    }
    res = await governed_server.handle_message(req)
    assert res["result"]["isError"] is False
    verify_text = res["result"]["content"][0]["text"]
    verify = json.loads(verify_text)
    assert verify["ledger_valid"] is True


@pytest.mark.asyncio
async def test_mcp_governed_write_and_read(governed_server):
    # Write file
    write_req = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "orrery_write_file",
            "arguments": {"path": "governed_doc.txt", "content": "Hello via MCP"},
        },
    }
    write_res = await governed_server.handle_message(write_req)
    assert write_res["result"]["isError"] is False

    # Read file back
    read_req = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "orrery_read_file",
            "arguments": {"path": "governed_doc.txt"},
        },
    }
    read_res = await governed_server.handle_message(read_req)
    assert read_res["result"]["isError"] is False
    content_text = read_res["result"]["content"][0]["text"]
    assert "Hello via MCP" in content_text


@pytest.mark.asyncio
async def test_mcp_path_traversal_refusal(governed_server):
    # Path traversal attack via MCP tool call
    attack_req = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {
            "name": "orrery_read_file",
            "arguments": {"path": "../../system_root/etc/shadow"},
        },
    }
    res = await governed_server.handle_message(attack_req)
    assert res["result"]["isError"] is True
    error_msg = res["result"]["content"][0]["text"]
    assert "GOVERNANCE REFUSAL" in error_msg


@pytest.mark.asyncio
async def test_mcp_invalid_json_handling(governed_server):
    bad_res = await governed_server.handle_message("not valid json {")
    assert bad_res["error"]["code"] == -32700

    unknown_method = {"jsonrpc": "2.0", "id": 9, "method": "unknown_method"}
    unknown_res = await governed_server.handle_message(unknown_method)
    assert unknown_res["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_mcp_audit_verify_detects_tampered_ledger(governed_server):
    governed_server.dispatcher.ledger.append("custom.event", summary="original")
    governed_server.dispatcher.ledger._events[0].summary = "tampered"

    req = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {"name": "orrery_audit_verify", "arguments": {}},
    }
    res = await governed_server.handle_message(req)
    assert res["result"]["isError"] is True
    payload = json.loads(res["result"]["content"][0]["text"])
    assert payload["ledger_valid"] is False
    assert payload["error"]


@pytest.mark.asyncio
async def test_mcp_execute_tool_respects_halt_and_records_ledger(tmp_path):
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()
    (sandbox_dir / "note.txt").write_text("ok", encoding="utf-8")
    halt_file = tmp_path / ".halt"

    from orrery.core.config import InterdictionSettings

    dispatcher = CycleDispatcher(
        settings=Settings(
            ledger=LedgerSettings(storage_dir=str(tmp_path / "ledger")),
            interdiction=InterdictionSettings(halt_file=str(halt_file)),
        )
    )
    dispatcher.register_adapter(FileSystemAdapter(root=str(sandbox_dir)))
    server = MCPGovernanceServer(dispatcher=dispatcher)

    # Normal call records action.executed in ledger
    ok_res = await server.handle_message({
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {"name": "orrery_read_file", "arguments": {"path": "note.txt"}},
    })
    assert ok_res["result"]["isError"] is False
    assert any(e.event_type == "action.executed" for e in dispatcher.ledger.events)

    # Active halt file must block subsequent MCP tool calls
    halt_file.write_text("emergency stop", encoding="utf-8")
    halted_res = await server.handle_message({
        "jsonrpc": "2.0",
        "id": 12,
        "method": "tools/call",
        "params": {"name": "orrery_read_file", "arguments": {"path": "note.txt"}},
    })
    assert halted_res["result"]["isError"] is True
    assert "halt" in halted_res["result"]["content"][0]["text"].lower()
