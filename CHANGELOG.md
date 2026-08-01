# Changelog

All notable changes to the **Cognition Cycles** framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
