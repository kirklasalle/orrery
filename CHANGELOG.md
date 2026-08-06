# Changelog

All notable changes to the **Orrery** framework (formerly *Cognition Cycles*) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

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

## [1.0.0] - 2026-07-31

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
