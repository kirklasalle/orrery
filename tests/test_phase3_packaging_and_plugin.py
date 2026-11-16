"""
Phase 3 Standalone Packaging, CLI, SSE Stream & Universal Plugin Bundle tests.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from orrery.cli import build_parser, main as cli_main
from orrery.core.ledger import EventLedger
from orrery.web.server import GovernanceDashboardServer


ALLOWED_PLUGIN_JSON_KEYS = {
    "name",
    "description",
    "logo",
    "suggestedPrompts",
    "displayName",
    "version",
    "author",
    "homepage",
    "repository",
    "disabled",
}


def test_phase3_cli_parser_and_charter():
    parser = build_parser()
    args = parser.parse_args(["dashboard", "--port", "9090", "--gyroscope"])
    assert args.port == 9090
    assert args.gyroscope is True

    assert cli_main(["charter"]) == 0


def test_phase3_sse_stream_and_auth():
    ledger = EventLedger(persist=False)
    ledger.append("action.executed", summary="SSE test event", policy_id="LAW9-LEDGER")

    # Loopback SSE stream returns text/event-stream and emits event: ledger
    srv = GovernanceDashboardServer(host="127.0.0.1", port=0, ledger=ledger)
    srv.start()
    try:
        port = srv._server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/stream", timeout=3) as resp:
            assert resp.status == 200
            assert "text/event-stream" in resp.headers.get("Content-Type", "")
            line1 = resp.readline().decode("utf-8", errors="replace")
            line2 = resp.readline().decode("utf-8", errors="replace")
            assert "event: ledger" in line1
            assert "SSE test event" in line2
    finally:
        srv.stop()

    # Non-loopback SSE stream requires Bearer auth
    srv_ext = GovernanceDashboardServer(host="0.0.0.0", port=0, ledger=ledger, auth_token="tok-sse-123")
    srv_ext.start()
    try:
        port = srv_ext._server.server_address[1]
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/stream", timeout=2)
            assert False, "Expected 401 Unauthorized"
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
    finally:
        srv_ext.stop()


def test_phase3_universal_plugin_bundle_valid():
    root = Path(__file__).resolve().parent.parent
    manifest = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
    assert set(manifest.keys()).issubset(ALLOWED_PLUGIN_JSON_KEYS)
    assert manifest["name"] == "orrery-governance"
    assert (root / manifest["logo"]).is_file()

    for mcp_file in ("mcp_config.json", ".mcp.json"):
        cfg = json.loads((root / mcp_file).read_text(encoding="utf-8"))
        assert "orrery-governance" in cfg["mcpServers"]

    assert (root / "skills" / "orrery-governance" / "SKILL.md").is_file()
    assert (root / "rules" / "AGENTS.md").is_file()
