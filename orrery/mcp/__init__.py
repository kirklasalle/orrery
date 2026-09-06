"""
Orrery Model Context Protocol (MCP) Governance Server.

Exposes Orrery's deterministic governance engine and adapters as a standards-compliant
Model Context Protocol (MCP) server (JSON-RPC 2.0). Any MCP-compliant client (Claude Desktop,
Cursor, custom agent frameworks) can connect to this server to execute tools under full
Orrery governance and audit logging.
"""

from orrery.mcp.server import MCPGovernanceServer, run_stdio_server

__all__ = ["MCPGovernanceServer", "run_stdio_server"]
