# Cognition Cycles Architecture Specification

> **Version:** 1.0.0  
> **Status:** Production Architecture

---

## 1. Executive System Overview

**Cognition Cycles** ("outgrowing the basic loop") is an enterprise agentic framework designed to replace single-step ReAct loops ($\text{Prompt} \rightarrow \text{Tool Call} \rightarrow \text{Observation} \rightarrow \text{Answer}$) with stateful, multi-tier cognitive state loops.

---

## 2. Multi-Stage State Machine Dispatcher

The `CycleDispatcher` manages state transitions across four core phases:

```
┌─────────────────────────┐         ┌─────────────────────────┐
│       PERCEPTION        │ ──────> │        PLANNING         │
│  (System 1 / Temp 0.7)  │         │  (System 2 / Temp 0.1)  │
└─────────────────────────┘         └─────────────────────────┘
             ▲                                   │
             │ (Automated Backtrack Rewind)      ▼
┌─────────────────────────┐         ┌─────────────────────────┐
│       REFLECTION        │ <────── │        EXECUTION        │
│  (Critique Gate >= 0.7) │         │    (Adapter Actions)    │
└─────────────────────────┘         └─────────────────────────┘
```

1. **Perception**: sensing environmental state, parsing inputs, extracting context signals, and generating candidate hypotheses (System 1).
2. **Planning**: formulating strategic goal paths, evaluating constraints against truth tables, and constructing `ActionPayload` objects (System 2).
3. **Execution**: dispatching payloads to target adapters and gathering `ExecutionReceipt` objects.
4. **Reflection**: evaluating execution results via `SelfCritiqueEngine`. If score $\ge \theta_{\text{critique}} = 0.70$, cycle advances to completion. If score $< \theta_{\text{critique}}$, state rewinds to the active checkpoint and triggers backtracking.

---

## 3. Hierarchical Abstraction Tiers & Nested Delegation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ META-CYCLES (High-Level Strategy, Goal Alignment & Cross-Agent Governance)   │
├─────────────────────────────────────────────────────────────────────────────┤
│  └─> MACRO-CYCLES (Multi-Step Milestone Orchestration & Sub-Task Sequences)│
├─────────────────────────────────────────────────────────────────────────────┤
│       └─> MESO-CYCLES (Context-Bound Execution Loops & Tool Management)     │
├─────────────────────────────────────────────────────────────────────────────┤
│            └─> MICRO-CYCLES (Fine-Grained Atomic UI Actions & Turn Gates)  │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Meta-Cycles**: Manage high-level strategy and agent goal alignment. Invokes child `MacroCycle` instances via `delegate_to_child()`.
- **Macro-Cycles**: Manage multi-step workflow orchestration. Invokes child `MesoCycle` instances.
- **Meso-Cycles**: Manage operational tool execution loops. Invokes child `MicroCycle` instances.
- **Micro-Cycles**: Perform atomic tool interactions, shell execution, or screen state verification.

---

## 4. Built-in Meta-Skills

### 4.1 Disk-Backed State Checkpointing
- Snapshots immutable `StateContext` objects before phase transitions.
- Persists JSON metadata to `.checkpoints/<cycle_id>/<checkpoint_id>.json` for cross-process session restores.

### 4.2 Automated Backtracking
- Rewinds execution back to the `PLANNING` phase of the safe checkpoint when reflection fails.
- Increments `backtrack_count` and modifies strategy context to guarantee convergence.

### 4.3 Agent Self-Critique
- Computes numerical scores ($0.0 - 1.0$) based on action success ratios and policy invariants.
- Emits actionable recommendations for plan revision upon failure.

---

## 5. Integration Adapters

- **[OpenClawAdapter](file:///d:/Projects/cognition_cycles/src/adapters/openclaw.py)**: Interoperates with Prism Refraction routing core and OpenClaw state engine.
- **[HermesAdapter](file:///d:/Projects/cognition_cycles/src/adapters/hermes.py)**: Interoperates with Hermes reasoning harness and console evaluation gates.
- **[WindowsOSAdapter](file:///d:/Projects/cognition_cycles/src/adapters/windows_os.py)**: Interoperates with Windows OS Agent for desktop UI state verification.
