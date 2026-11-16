"""
Orrery CLI entry points for standalone and plugin deployments.

Provides:
- `orrery dashboard` / `orrery gyroscope`: Launch the Governance Web Console & 3D WebGL Gyroscope.
- `orrery mcp`: Start the governed MCP JSON-RPC 2.0 stdio server.
- `orrery verify`: Run formal gate composition soundness verification.
- `orrery charter`: Verify charter document consistency against the pinned manifest.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import webbrowser
from pathlib import Path
from typing import List, Optional

from orrery.core.config import get_settings
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.ledger import EventLedger
from orrery.mcp.server import MCPGovernanceServer, run_stdio_server
from orrery.web.server import GovernanceDashboardServer


def _build_default_dispatcher(sandbox_root: Optional[str] = None) -> CycleDispatcher:
    settings = get_settings()
    dispatcher = CycleDispatcher(settings=settings)
    if sandbox_root:
        from orrery.adapters.filesystem import FileSystemAdapter

        root_path = Path(sandbox_root).resolve()
        root_path.mkdir(parents=True, exist_ok=True)
        dispatcher.register_adapter(FileSystemAdapter(root=str(root_path)))
    return dispatcher


def cmd_dashboard(args: argparse.Namespace) -> int:
    settings = get_settings()
    ledger = EventLedger(persist=True)
    server = GovernanceDashboardServer(
        host=args.host,
        port=args.port,
        ledger=ledger,
        settings=settings,
        auth_token=args.auth_token,
    )
    server.start()
    bound_port = server._server.server_address[1] if server._server else args.port
    base_url = f"http://{args.host}:{bound_port}"
    print(f"Orrery Governance Console: {base_url}/")
    print(f"Orrery 3D Gyroscope (WebGL): {base_url}/gyroscope")
    if server.auth_token:
        print("Bearer token authentication is ENABLED for /api/* endpoints.")
    if args.open_browser:
        target = f"{base_url}/gyroscope" if args.gyroscope else f"{base_url}/"
        webbrowser.open(target)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nShutting down Orrery Dashboard Server...")
        server.stop()
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    dispatcher = _build_default_dispatcher(sandbox_root=args.sandbox_root)
    server = MCPGovernanceServer(dispatcher=dispatcher)
    asyncio.run(run_stdio_server(server))
    return 0


def cmd_verify(_args: argparse.Namespace) -> int:
    from orrery.tools.verify_soundness import main as verify_main

    return int(verify_main() or 0)


def cmd_charter(args: argparse.Namespace) -> int:
    from orrery.tools.charter import main as charter_main

    argv = ["--update"] if getattr(args, "update", False) else []
    return int(charter_main(argv) or 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orrery",
        description="Orrery: Deterministic Fail-Closed Governance Runtime for Autonomous Agents",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_dash = sub.add_parser("dashboard", aliases=["gyroscope"], help="Start the Governance Dashboard & 3D WebGL Gyroscope")
    p_dash.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    p_dash.add_argument("--port", type=int, default=8080, help="Listen port (default: 8080)")
    p_dash.add_argument("--auth-token", default=None, help="Optional Bearer token for /api/* routes")
    p_dash.add_argument("--open", dest="open_browser", action="store_true", help="Open browser automatically")
    p_dash.add_argument("--gyroscope", action="store_true", help="Open /gyroscope directly when --open is set")
    p_dash.set_defaults(func=cmd_dashboard)

    p_mcp = sub.add_parser("mcp", help="Run the governed MCP JSON-RPC 2.0 stdio server")
    p_mcp.add_argument("--sandbox-root", default=None, help="Optional FileSystemAdapter sandbox root directory")
    p_mcp.set_defaults(func=cmd_mcp)

    p_ver = sub.add_parser("verify", help="Run formal gate composition soundness verification")
    p_ver.set_defaults(func=cmd_verify)

    p_chr = sub.add_parser("charter", help="Verify charter manifest consistency")
    p_chr.add_argument("--update", action="store_true", help="Re-pin charter manifest digests")
    p_chr.set_defaults(func=cmd_charter)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


def mcp_main() -> int:
    return main(["mcp", *sys.argv[1:]])


def dashboard_main() -> int:
    return main(["dashboard", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
