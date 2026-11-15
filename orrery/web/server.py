"""
Orrery Governance Web Dashboard & Real-Time Event Stream Server.

Serves the interactive dashboard console and provides JSON REST endpoints
for live audit ledger inspection, gate ladder health, and statutory compliance status.
Zero mandatory third-party dependencies: uses Python standard library http.server.
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

from orrery.compliance.auditor import ComplianceAuditor
from orrery.core.config import Settings, get_settings
from orrery.core.ledger import EventLedger

logger = logging.getLogger(__name__)

DASHBOARD_HTML_PATH = Path(__file__).parent / "dashboard.html"


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the governance dashboard."""

    ledger: Optional[EventLedger] = None
    settings: Optional[Settings] = None
    auth_token: Optional[str] = None

    def _is_authorized(self) -> bool:
        if not self.auth_token:
            return True
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:]
        return hmac.compare_digest(token.encode("utf-8"), self.auth_token.encode("utf-8"))

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, html_content: str, status: int = HTTPStatus.OK) -> None:
        payload = html_content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path.startswith("/api/") and not self._is_authorized():
            self._send_json({"error": "Unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
            return

        # Route requests
        if self.path in ("/", "/index.html"):
            if DASHBOARD_HTML_PATH.is_file():
                self._send_html(DASHBOARD_HTML_PATH.read_text(encoding="utf-8"))
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Dashboard HTML asset not found.")
            return

        if self.path.startswith("/api/ledger"):
            events_data = []
            if self.ledger is not None:
                for ev in self.ledger.events:
                    events_data.append({
                        "sequence": ev.sequence,
                        "type": ev.event_type.split(".")[-1] if "." in ev.event_type else ev.event_type,
                        "title": ev.summary,
                        "time": ev.timestamp,
                        "policy": ev.policy_id or "LAW9-LEDGER",
                        "hash": ev.content_hash or ev.digest(),
                        "cycle": ev.cycle_id or "MAIN",
                        "data": ev.data,
                    })
            self._send_json({"total_events": len(events_data), "events": events_data})
            return

        if self.path.startswith("/api/status"):
            st = self.settings or get_settings()
            status_data = {
                "system": "Orrery Agentic Governance",
                "version": "0.2.0",
                "gate_stack": {
                    "interdiction": len(st.interdiction.prohibitions),
                    "envelope": st.envelope.enforce,
                    "quarantine": st.quarantine.enabled,
                    "ratelimit": st.ratelimit.enabled,
                    "approval": st.approval.require_for_irreversible,
                },
                "critique_threshold": st.critique.threshold,
            }
            self._send_json(status_data)
            return

        if self.path.startswith("/api/compliance"):
            auditor = ComplianceAuditor(settings=self.settings or get_settings())
            report = auditor.audit()
            self._send_json(report.model_dump(mode="json"))
            return

        self.send_error(HTTPStatus.NOT_FOUND, f"Path not found: {self.path}")

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy standard request logging in production/tests
        pass


class GovernanceDashboardServer:
    """Threaded HTTP server for the Orrery Governance Dashboard."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        ledger: Optional[EventLedger] = None,
        settings: Optional[Settings] = None,
        auth_token: Optional[str] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.ledger = ledger
        self.settings = settings or get_settings()
        is_loopback = host in ("127.0.0.1", "localhost", "::1")
        if not is_loopback and not auth_token:
            auth_token = secrets.token_urlsafe(24)
            logger.warning(
                "Non-loopback dashboard bind (%s) without explicit auth_token; generated ephemeral bearer token.",
                host,
            )
        self.auth_token = auth_token
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Starts the server in a background thread."""
        handler_cls = type(
            "_BoundDashboardHandler",
            (DashboardRequestHandler,),
            {
                "ledger": self.ledger,
                "settings": self.settings,
                "auth_token": self.auth_token,
            },
        )

        self._server = HTTPServer((self.host, self.port), handler_cls)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Orrery Dashboard Server listening at http://%s:%d", self.host, self.port)

    def stop(self) -> None:
        """Stops the server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None


def start_dashboard_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    ledger: Optional[EventLedger] = None,
) -> GovernanceDashboardServer:
    server = GovernanceDashboardServer(host=host, port=port, ledger=ledger)
    server.start()
    return server
