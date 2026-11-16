# Orrery Governance Plugin Rules

- Route external filesystem, process, HTTP, database, and object-storage operations through Orrery's governed adapters or `orrery-governance` MCP tools rather than unguarded raw shell calls.
- Treat `IRREVERSIBLE` actions as denied by default unless explicit operator approval is attached.
- Never disable or bypass `.halt` interdiction checks, `EnvelopeGate` sandbox confinement, or `EventLedger` hash-chain verification.
