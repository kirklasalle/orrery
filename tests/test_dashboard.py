"""
Tests for Orrery Governance Dashboard & Telemetry Server.
"""

import json
import urllib.request
import pytest

from orrery.core.ledger import EventLedger
from orrery.web.server import GovernanceDashboardServer, start_dashboard_server


@pytest.fixture
def test_server() -> GovernanceDashboardServer:
    ledger = EventLedger(persist=False)
    ledger.append(
        "action.executed",
        summary="Test action executed",
        policy_id="LAW9-LEDGER",
        action_name="test_act",
    )
    server = start_dashboard_server(host="127.0.0.1", port=8991, ledger=ledger)
    yield server
    server.stop()


def test_dashboard_html_endpoint(test_server: GovernanceDashboardServer) -> None:
    req = urllib.request.Request("http://127.0.0.1:8991/")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "<title>Orrery — Autonomous Governance & Audit Console</title>" in content
        assert "6-Gate Composition Ladder" in content


def test_dashboard_ledger_api(test_server: GovernanceDashboardServer) -> None:
    req = urllib.request.Request("http://127.0.0.1:8991/api/ledger")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "events" in data
        assert data["total_events"] >= 1
        assert data["events"][0]["title"] == "Test action executed"


def test_dashboard_status_api(test_server: GovernanceDashboardServer) -> None:
    req = urllib.request.Request("http://127.0.0.1:8991/api/status")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["system"] == "Orrery Agentic Governance"
        assert "gate_stack" in data
        assert "critique_threshold" in data


def test_dashboard_compliance_api(test_server: GovernanceDashboardServer) -> None:
    req = urllib.request.Request("http://127.0.0.1:8991/api/compliance")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "compliance_score_percent" in data
        assert "frameworks_evaluated" in data
        assert data["compliance_score_percent"] > 50.0


def test_dashboard_not_found(test_server: GovernanceDashboardServer) -> None:
    req = urllib.request.Request("http://127.0.0.1:8991/unknown/route")
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 404


def test_dashboard_cli(monkeypatch) -> None:
    import sys
    from unittest.mock import MagicMock, patch
    from orrery.tools.dashboard import main

    mock_server = MagicMock()
    test_args = ["dashboard", "--port", "9000", "--host", "127.0.0.1"]
    with patch.object(sys, "argv", test_args):
        with patch("orrery.tools.dashboard.start_dashboard_server", return_value=mock_server):
            with patch("time.sleep", side_effect=KeyboardInterrupt):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 0
                mock_server.stop.assert_called_once()

