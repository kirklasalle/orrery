# Changelog

All notable changes to the **Orrery** framework (formerly *Cognition Cycles*) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Gate 3a — the first real adapter, and a gate on what cannot be undone.**
  - `orrery/adapters/filesystem.py` — `FileSystemAdapter`, the **first non-simulation adapter**.
    It reads, writes, appends, moves, and deletes real files inside a sandbox root, refusing
    absolute paths and any `..` traversal that escapes it. `perceive_environment` reports real
    disk usage and directory contents. All I/O runs on a worker thread. This matters beyond the
    adapter itself: risk classification was theatre until `delete_file` existed and could
    genuinely destroy something.
  - `ActionRisk` (`READ_ONLY` / `REVERSIBLE` / `COMPENSABLE` / `IRREVERSIBLE`) and `ApprovalToken`
    on `ActionPayload`. Adapters declare a risk per action name via `declared_risks`; an action
    the adapter does not declare is treated as `IRREVERSIBLE`, not as harmless.
  - `orrery/core/approval.py` — `ApprovalGate` refuses `IRREVERSIBLE` actions that carry no
    approval (`RISK-001`), tokens minted for a different action (`RISK-002`), unsigned tokens when
    signing is required (`RISK-003`), and expired tokens (`RISK-004`). Every refusal is appended
    to the ledger as `action.refused` with the deciding policy ID (`RISK-000`).
  - `CycleDispatcher` takes the **stricter** of the planner's declared risk and the adapter's, so
    a plan cannot relabel a delete as harmless to slip past the gate (`RISK-CLASS`).
  - `orrery/adapters/conformance.py` — the **Adapter Conformance Kit** (`ADP-001`…`ADP-012`),
    run in CI against every bundled adapter and offered to third-party adapter authors. It
    verifies that receipts echo the request, that unsupported actions fail rather than raise or
    falsely succeed, that failed receipts carry an error, and that no adapter stamps its own
    output as `simulated`.
  - `approval` settings block in `config/settings.yaml` (`require_for_irreversible`,
    `require_for_compensable`, `require_signed`, `ttl_seconds`).
  - 43 new tests. Coverage is now 90% of `orrery/` (1380 statements, 156 tests).

### Fixed

- **The three simulated adapters reported success for actions they do not implement.** The
  conformance kit caught this on its first run: `OpenClawAdapter`, `HermesAdapter`, and
  `WindowsOSAdapter` returned `success=True` for *any* `action_name`, including nonsense. A
  simulation that fabricates success for unimplemented work is indistinguishable from a broken
  integration, and is exactly what Law 7 forbids. All three now publish an action vocabulary and
  return a failed receipt for anything outside it.

### Changed

- **Governance headline: 5 of the 10 Laws without runtime control → 3.** Laws 1 and 2 moved from
  `NOT_ENFORCED` to `PARTIAL`, and Law 4 to `ENFORCED`. Read this narrowly. Orrery still has no
  harm model and cannot judge whether an action is *good*; what it can now do is refuse to perform
  an action it cannot undo unless a human authorized that exact action. That bounds the class of
  what happens without consent, not the content of what is consented to.

### Security

- **An unsigned `ApprovalToken` is an assertion, not a proof.** Without `ORRERY_APPROVAL_KEY` set
  and `approval.require_signed` enabled, any code running in the same process can mint a token.
  Unsigned approval is a record for the audit trail, not a security control. Even with signing on,
  a shared symmetric key proves custody, not authorship.

### Added

- **Gate 2 — governance stops being a document.**
  - `GOVERNANCE.md` maps all 10 Laws to policy IDs, runtime predicates, mechanisms, and tests.
    It is checked against `orrery/core/governance.py` by `tests/test_governance.py` in CI, so the
    document cannot claim an enforcement the code does not implement, and a policy marked
    `ENFORCED` without a test fails the build. It states plainly how many of the 10 Laws have
    no runtime control.
  - `orrery/core/ledger.py` — an append-only, hash-linked `EventLedger` (Law 9). Phase
    transitions, action outcomes, critiques, rollbacks, adapter registrations, and delegation
    decisions are recorded as JSONL. It lives outside the rewindable `StateContext` and exposes
    no delete, update, or truncate operation, so backtracking rewinds state while the record of
    the erased attempts survives.
  - `orrery/core/delegation.py` — delegation is authorized before it runs (Law 10), against
    depth (`DEL-001`), per-parent fan-out (`DEL-002`), tree population (`DEL-003`), ancestry
    loops (`DEL-004`), and tier ordering (`DEL-005`). A refusal produces a failed receipt rather
    than an exception, so the parent's own reflection handles it. Subclass `DelegationPolicy`
    for site rules; `spawn_child` propagates it so governance is not reset one tier down.
  - `orrery/core/integrity.py` — checkpoints are SHA-256 hash-linked and verified on load; an
    edited checkpoint file is refused rather than restored. Optional HMAC-SHA256 signing via
    `ORRERY_CHECKPOINT_KEY`, and `integrity.require_signature` to refuse unsigned checkpoints.
  - `CheckpointManager.verify_chain()`, `EventLedger.verify()`, and `purge_cycle()`.
  - `.github/workflows/ci.yml` — tests on Linux and Windows across Python 3.10–3.12, plus a
    separate governance conformance gate.

### Fixed

- **Unbounded checkpoint growth (H-5).** In-memory eviction previously dropped the oldest entry
  regardless of whether a cycle still needed it, and never touched `_cycle_history` or disk.
  Eviction now protects each cycle's chain head, disk retention is bounded per cycle by
  `max_checkpoints_on_disk_per_cycle`, and pruning truncates the chain without rewriting a link,
  so the surviving chain still verifies and reports itself as truncated.

### Changed

- **Gate 1 — the core is now honest.** Execution no longer fabricates results.
  - Every hardcoded `success=True` was removed from the dispatcher and from all four tiers.
  - `CycleDispatcher` gained an adapter registry. Actions route to `action.target_adapter`;
    an unregistered target or a raising adapter produces a **failed** receipt with an explicit
    error. An unwired framework now reports `FAILED` instead of silent success. This is a
    **behavioural break**: callers must register an adapter to get a passing cycle.
  - Backtracking learns. `StateContext` gained rollback-immune `lessons` and `attempt_log`;
    `backtrack()` carries them forward and keeps `step_count` monotonic (Law 9). The default
    planner consumes lessons and emits a distinct plan per attempt, replacing the previous
    behaviour of retrying an identical plan three times.
  - `config/settings.yaml` is loaded for the first time, by the new `orrery.core.config`.
    `max_cycle_iterations`, per-tier timeouts, the critique threshold, and checkpoint storage
    settings are now applied rather than decorative. `ORRERY_SETTINGS` overrides the path.
  - `run_full_cycle` is bounded by a step budget and an `asyncio.wait_for` wall-clock budget.
  - `delegate_to_child` shares one checkpoint manager, critique engine, and adapter set across
    the cycle tree, making cross-tier rewind possible; a failed child now appends a failed
    `delegate_to_<tier>` receipt so it fails the parent's reflection instead of being swallowed.
  - Bundled adapters declare `is_simulation`. Registering one logs a warning and tags its
    receipts with `simulated: True`.
- **BREAKING — Project renamed** from *Cognition Cycles* to **Orrery**. The distribution is now
  `orrery` and the import root moved from `src` to `orrery`. Update all imports:
  `from src.core.types import ...` → `from orrery.core.types import ...`.
- Documentation, configuration (`config/settings.yaml`), and repository URLs rebranded. Dated
  analysis documents are annotated rather than rewritten.

### Security

- **Path traversal in checkpoint persistence (CRITICAL)**. `cycle_id` and `checkpoint_id` were
  interpolated into filesystem paths without validation, allowing writes outside the storage
  directory. Fixed at two layers: strict UUID validation at the model boundary (with
  `validate_assignment=True`, so mutation is also covered) and path containment in
  `CheckpointManager`. Checkpoint files are now written with `0o600` permissions.

### Added

- `LICENSE` (MIT) and OSI license metadata.
- `tests/test_security.py` — 37 regression cases covering traversal, absolute paths, and
  malformed-identifier rejection on both construction and assignment.

### Fixed

- Missing `Optional` import in the adapter base class — a latent `ImportError` on the declared
  Python 3.10 target, masked by the workspace's Python 3.14 deferred annotations.

## [0.1.0] - 2026-07-31

> **Correction.** This entry was originally published as `1.0.0`. The package has always
> declared `0.1.0` in `pyproject.toml` and `orrery.__version__`, and a release whose core
> execution path reported unconditional success was not a 1.0. The heading is corrected to
> match the code; the content below is unchanged.

### Added

- **Cycle Dispatcher State Machine**: 4-phase state machine driving `PERCEPTION`, `PLANNING`, `EXECUTION`, and `REFLECTION`.
- **4-Tier Abstraction Hierarchy**: `MetaCycle`, `MacroCycle`, `MesoCycle`, and `MicroCycle` implementations with parent-child delegation.
- **State Checkpointing & Disk Persistence**: In-memory and disk-backed `.checkpoints/` snapshot serialization and rewind logic in `CheckpointManager`.
- **Agent Self-Critique Engine**: `SelfCritiqueEngine` with configurable evaluation gates and reflection threshold ($\theta = 0.70$).
- **Automated Backtracking**: State rewind mechanism returning execution to `PLANNING` upon reflection gate failures.
- **Platform Adapters**:
  - `OpenClawAdapter`: Prism Refraction routing core task dispatcher.
  - `HermesAdapter`: Console and LLM backend reasoning harness interface.
  - `WindowsOSAdapter`: Desktop UI automation and screen state verification controller.
- **Antigravity v2 Integration**: Environment rules (`.antigravity/rules.md`) and workflow orchestration (`.antigravity/workflows/cognition_cycle.yaml`).
- **Comprehensive Documentation**: PRD (`docs/PRD.md`), Architecture Specification (`docs/architecture.md`), Setup Guide (`docs/setup_guide.md`), and Market Research Audit (`docs/market_research_audit.md`).
- **End-to-End Executable Demo**: `examples/demo_cycle.py` demonstrating multi-tier cognitive delegation and failover recovery.
- **Complete Test Suite**: Pytest unit test coverage across dispatcher, tiers, meta-skills, and platform adapters.
