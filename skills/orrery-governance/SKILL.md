---
name: orrery-governance
description: Operate Orrery's deterministic 6-gate fail-closed governance runtime, SHA-256 hash-chained EventLedger, governed MCP server, formal soundness verifier, and real-time 3D WebGL gyroscope console. Use when auditing agent actions, verifying ledger/charter integrity, or launching the live 3D governance visualizer.
---

# Orrery Governance Runtime

Orrery enforces deterministic, fail-closed governance across four nested cognitive tiers (`META -> MACRO -> MESO -> MICRO`) and six sequential gates (`InterdictionGate -> EnvelopeGate -> PolicyEngine -> ApprovalGate -> RateLimitGate -> Sandboxed Adapter`), logging every decision to a SHA-256 hash-chained `EventLedger`.

## CLI Entry Points

When installed (`pip install -e .` or `pip install orrery`), use either the console scripts or `python -m orrery.cli`:

- `orrery dashboard --open --gyroscope` (or `orrery-dashboard --open --gyroscope`): Launch the Governance Console (`/`) and real-time SSE-connected **3D WebGL Gyroscope** (`/gyroscope`) with 60 FPS `.webm` video capture.
- `orrery mcp` (or `orrery-mcp --sandbox-root ./workspace`): Start the governed MCP JSON-RPC 2.0 stdio server (`orrery-governance`).
- `orrery verify`: Run formal gate composition soundness verification (`THM-01`..`THM-05`).
- `orrery charter`: Verify `AGENTIC_PRIME_DIRECTIVE.md`, `AGENTIC_SACRED_COVENANT.md`, and `Permanent_Active_Directives.txt` against `config/charter_manifest.json`.

## Governed MCP Tools (`orrery-governance`)

- `orrery_read_file` / `orrery_write_file`: Sandboxed filesystem operations confined to `FileSystemAdapter.sandbox_roots()`.
- `orrery_run_program`: Allowlisted, `shell=False` process execution with session isolation, clamped timeouts, and capped stream capture.
- `orrery_audit_verify`: Verifies the full cryptographic hash chain of `EventLedger` (`ledger.verify()`).

## Non-Negotiable Invariants

- Never bypass `InterdictionGate` (`.halt`), `EnvelopeGate`, or `ApprovalGate` for `IRREVERSIBLE` actions.
- Never fabricate success when `is_simulation=False` and required credentials/roots are absent (`ADP-011`).
- Always verify ledger integrity (`orrery_audit_verify` or `EventLedger.verify()`) after unexpected termination.
