"""
CLI Runner: Launch the Orrery Governance Web Dashboard.

Usage:
    python -m orrery.tools.dashboard [--port 8080] [--host 127.0.0.1]
"""

import argparse
import sys
import time

from orrery.core.ledger import EventLedger
from orrery.web.server import start_dashboard_server


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch the Orrery Governance Web Dashboard console."
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080)",
    )
    args = parser.parse_args()

    ledger = EventLedger(persist=True)
    print(f"[Orrery Dashboard] Starting console server at http://{args.host}:{args.port}...")
    server = start_dashboard_server(host=args.host, port=args.port, ledger=ledger)
    print(f"[Orrery Dashboard] Console active. Press Ctrl+C to terminate.")

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[Orrery Dashboard] Shutting down server...")
        server.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
