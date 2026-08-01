# Cognition Cycles Architecture Specification

## Overview

**Cognition Cycles** ("outgrowing the basic loop") is an agentic framework and orchestration paradigm designed to replace single-step ReAct loops ($\text{Prompt} \rightarrow \text{Tool Call} \rightarrow \text{Observation} \rightarrow \text{Answer}$) with stateful, multi-tier cognitive state loops.

---

## 1. Cycle Dispatcher (Multi-Stage State Machine)

The `CycleDispatcher` orchestrates structured transitions across four core phases:

```
┌─────────────────┐       ┌─────────────────┐
│   PERCEPTION    │ ────> │    PLANNING     │
└─────────────────┘       └─────────────────┘
         ▲                         │
         │                         ▼
┌─────────────────┐       ┌─────────────────┐
│   REFLECTION    │ <──── │    EXECUTION    │
└─────────────────┘       └─────────────────┘
```

1. **Perception**: Sensing the environment, parsing inputs, extracting context signals, and generating candidate hypotheses (System 1).
2. **Planning**: Decomposing goals into structured strategies, scoring candidate hypotheses, evaluating constraints, and building action steps (System 2).
3. **Execution**: Dispatching atomic tool calls, shell actions, or platform commands through specialized integration adapters.
4. **Reflection**: Evaluating outcome quality via `SelfCritiqueEngine`. If verification score $\ge \theta_{\text{critique}}$, the cycle completes or advances. If score $< \theta_{\text{critique}}$, state rolls back to the previous checkpoint via `CheckpointManager` and triggers backtracking.

---

## 2. Hierarchical Abstraction Tiers

```
┌─────────────────────────────────────────────────────────────┐
│ META-CYCLES (High-Level Strategy & Goal Alignment)          │
├─────────────────────────────────────────────────────────────┤
│  └─> MACRO-CYCLES (Multi-Step Workflow Orchestration)       │
├─────────────────────────────────────────────────────────────┤
│       └─> MESO-CYCLES (Context-Bound Tool Execution Loops)   │
├─────────────────────────────────────────────────────────────┤
│            └─> MICRO-CYCLES (Atomic Turn Evaluation Gates)  │
└─────────────────────────────────────────────────────────────┘
```

- **Meta-Cycles**: Long-term strategy, overall system goal alignment, cross-agent coordination, and meta-learning state evolution.
- **Macro-Cycles**: Multi-step workflow planning, major milestone tracking, sub-task breakdown, and component-level sequencing.
- **Meso-Cycles**: Operational domain logic, tool sequence management, stateful context isolation, and localized error handling.
- **Micro-Cycles**: Fine-grained atomic actions, turn-fixed evaluation gates, visual/text observation verification, and instant rewind capability.

---

## 3. Built-in Meta-Skills

### Agent Self-Critique
Automated evaluation gates evaluate plan quality and execution fidelity prior to completing cycles or producing terminal output. Outputs numerical scores ($0.0 - 1.0$) and actionable feedback.

### State Checkpointing
Full snapshotting of cycle state (`StateContext`), including memory parameters, open handles, phase indicators, and execution stack trace. Checkpoints can be committed at any phase boundary.

### Backtracking
Automatic recovery mechanism. When an execution phase fails reflection or hits an unrecoverable constraint error, the state machine unwinds to the most recent safe checkpoint, modifies the strategy context, and re-plans without losing high-level macro history.

---

## 4. Platform Adapters

- **OpenClaw Adapter**: Interfaces with OpenClaw and Prism Refraction routing core and state engine.
- **Hermes Adapter**: Interfaces with Hermes backend reasoning harness and console evaluation gates.
- **Windows OS Adapter**: Executive desktop automation adapter for screen state verification and UI element interactions.
