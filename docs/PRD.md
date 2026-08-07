# Orrery: Product Requirements Document (PRD)

**Version:** 0.1.0  
**Status:** Draft — tracks an early-stage reference implementation  
**Author:** Kirk LaSalle  
**Target Repository:** `https://github.com/kirklasalle/orrery`

> **Correction (August 7, 2026):** this document previously declared itself version 1.0.0,
> "Approved / Active", and attributed to "Antigravity Engineering & System Architecture". No
> such approval took place and no such organization authored it. The version has been aligned
> with the package (0.1.0) and the CHANGELOG. Leaving the original header in place would have
> been the kind of unearned claim Law 7 forbids.

---

## 1. Executive Summary

Traditional AI agent frameworks operate on single-turn ReAct loops ($\text{Prompt} \rightarrow \text{Tool Call} \rightarrow \text{Observation} \rightarrow \text{Answer}$). While sufficient for basic Q&A or linear scripting, single-turn loops fail when executing complex, long-horizon tasks requiring multi-layered abstraction, self-correction, state isolation, and deterministic rollback.

**Orrery** introduces a multi-tier, stateful cognitive loop paradigm that decouples strategic planning from micro-execution. Operating across **Perception**, **Planning**, **Execution**, and **Reflection**, Orrery provides state checkpointing, automated backtracking, quantitative self-critique, and seamless platform adapters for popular agent harnesses, such as OpenClaw, Prism Refraction, Hermes, Frontier Console, and Windows OS Agent desktop automation.

---

## 2. Product Goals & Objectives

- **Replace Fragile ReAct Loops**: Establish a state-machine architecture that enforces structural reflection and verification gates prior to completing turns.
- **Hierarchical Abstraction**: Provide 4 explicit abstraction tiers (**Meta**, **Macro**, **Meso**, **Micro**) with clear delegation boundaries and parent-child state propagation.
- **Resilient Recovery**: Implement zero-data-loss state checkpointing and automatic backtracking when reflection scores fall below quality thresholds ($\theta_{\text{critique}} = 0.70$).
- **Platform Agnostic Execution**: Supply extensible adapter interfaces for cloud task routing, LLM reasoning harnesses, and desktop UI automation.
- **Engineering Baseline**: Typed Pydantic contracts, asynchronous execution, and a maintained test suite.

> **Implementation status (August 6, 2026).** This document describes the target design. As of Gate 1
> of the remediation plan, execution is honest: actions are routed to registered adapters, an action
> with no adapter yields a failed receipt, per-tier timeouts and step budgets are loaded from
> [../config/settings.yaml](../config/settings.yaml) and enforced, and backtracking carries lessons
> forward so retries differ from the attempt that failed. The bundled adapters remain **simulations**
> that perform no real I/O, and no governance Law is enforced at runtime. See
> [audit_2026-08-06.md](audit_2026-08-06.md) for the full gap analysis and remaining gates.

---

## 3. System Architecture & Component Specifications

### 3.1 Cognitive Cycle Phases

Each cycle step transitions deterministically through four phases:

1. **PERCEPTION (System 1)**: Environmental sensing, context extraction, and hypothesis generation at high temperature.
2. **PLANNING (System 2)**: Strategy formulation, constraint checking, and action payload construction at low temperature.
3. **EXECUTION (Action Dispatch)**: Dispatching payloads to target adapters and gathering execution receipts.
4. **REFLECTION (Self-Critique Gate)**: Evaluating receipts against system invariants and generating a quantitative score ($0.0 - 1.0$).

```
┌─────────────────────────┐         ┌─────────────────────────┐
│       PERCEPTION        │ ──────> │        PLANNING         │
│  (Hypotheses Buffer)    │         │   (Action Payloads)     │
└─────────────────────────┘         └─────────────────────────┘
             ▲                                   │
             │ (Backtrack Rewind)                ▼
┌─────────────────────────┐         ┌─────────────────────────┐
│       REFLECTION        │ <────── │        EXECUTION        │
│    (Critique Gate)      │         │   (Adapter Receipts)    │
└─────────────────────────┘         └─────────────────────────┘
```

---

## 4. Hierarchical Abstraction Tier Specifications

| Tier | Scope & Responsibility | Timeout (s) | Typical Action Payload |
| :--- | :--- | :--- | :--- |
| **Meta-Cycle** | High-level system strategy, long-term state evolution, agent goal alignment. | 300s | Strategic alignment, child Macro delegation. |
| **Macro-Cycle** | Multi-step workflow orchestration, milestone tracking, sub-task sequence planning. | 120s | Milestone execution, child Meso delegation. |
| **Meso-Cycle** | Context-bound execution loops, operational domain logic, tool chain management. | 60s | Tool sequence execution, child Micro delegation. |
| **Micro-Cycle** | Fine-grained atomic actions, turn-fixed evaluation gates, visual/UI observation verification. | 15s | Atomic UI click, shell command, tool API call. |

---

## 5. Built-in Meta-Skills

### 5.1 State Checkpointing & Disk Persistence

- Snapshots `StateContext` before entering critical phase transitions.
- Supports both in-memory caching and persistent disk storage in `.checkpoints/<cycle_id>/<checkpoint_id>.json`.

### 5.2 Automated Backtracking

- Triggered when `CritiqueResult.passed == False` (score $< 0.70$).
- Rewinds `StateContext` to the most recent safe checkpoint, increments `backtrack_count`, and re-routes execution back to **PLANNING**.
- Enforces `max_backtracks = 3` limit before failing gracefully.

### 5.3 Agent Self-Critique

- Quantitative scoring engine analyzing success ratio of execution receipts vs planned actions.
- Generates actionable feedback recommendations for plan adjustments upon failure.

---

## 6. Target Platform Adapters

1. **OpenClawAdapter**: Interoperates with Prism Refraction routing core and OpenClaw state engine.
2. **HermesAdapter**: Interoperates with Hermes reasoning harness and console evaluation gates.
3. **WindowsOSAdapter**: Executive desktop automation controller supporting screen state inspection and UI event dispatching.

---

## 7. Non-Functional & Quality Requirements

- **Python Compatibility**: Python 3.10+ (verified against 3.10 via the repository `.venv`).
- **Test Coverage**: **Measured 91% line coverage of `orrery/`** (2,993 statements, 331 tests, 1
  skipped) as of August 7, 2026.
- **Behavioural Evidence**: Line coverage measures which lines ran, not whether anything worked —
  this project has already shipped 85% coverage alongside a critique that certified goals it never
  checked. The load-bearing evidence is [`orrery/bench`](../orrery/bench), which runs real tasks
  against a real adapter, **grades every run by reading the disk afterwards**, and compares
  informed rollback against a control that can falsify the claim. Its `false success` count — runs
  reporting `COMPLETED` for a goal the filesystem says was not reached — is gated at zero in CI.
- **Async Execution**: Non-blocking `async/await` throughout all phase handlers and cycle runners.
- **Code Quality**: Strict type hint enforcement, Pydantic v2 validation, zero global state mutations.
- **Path Safety**: All checkpoint identifiers are validated as canonical UUIDs and all checkpoint I/O is confined to the configured storage root.
