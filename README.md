# Cognition Cycles: Architecture & Agentic Framework

> *"Outgrowing the basic loop"*

**Cognition Cycles** is an agentic framework and orchestration paradigm designed to replace single-step ReAct loops ($\text{Prompt} \rightarrow \text{Tool Call} \rightarrow \text{Observation} \rightarrow \text{Answer}$) with stateful, multi-tier cognitive state loops operating across perception, planning, execution, and reflection.

---

## 🏗️ Project Architecture Overview

```text
cognition-cycles/
├── .antigravity/
│   ├── rules.md                  # Agent behavior rules (System 1/2 roles, Classic IDE layout)
│   └── workflows/
│       └── cognition_cycle.yaml  # Antigravity v2 orchestration workflow (Perception -> Deliberation -> Synthesis)
├── src/
│   ├── core/                     # Execution engine runtime (Dispatcher, State, Critique, Types)
│   ├── cycles/                   # Hierarchical abstraction tiers (Meta, Macro, Meso, Micro)
│   └── adapters/                 # Platform adapters (OpenClaw, Hermes, Windows OS Agent)
├── config/                       # YAML project settings & thresholds
├── docs/                         # Architecture documentation & setup guides
├── tests/                        # Comprehensive Pytest suite
├── .gitignore                    # Exclusion rules
├── pyproject.toml                # Build system & dependency specification
└── README.md                     # Project overview & jumpstart entry point
```

---

## ⚡ Key Features

1. **Cycle Dispatcher State Machine**: 4-phase state transition engine (Perception $\rightarrow$ Planning $\rightarrow$ Execution $\rightarrow$ Reflection).
2. **4 Hierarchical Abstraction Tiers**:
   - **Meta-Cycles**: High-level system strategy and agent goal alignment.
   - **Macro-Cycles**: Multi-step workflow orchestration and milestone tracking.
   - **Meso-Cycles**: Context-bound execution loops and tool sequence management.
   - **Micro-Cycles**: Fine-grained atomic actions and visual/text observation verification.
3. **Built-in Meta-Skills**:
   - **Agent Self-Critique**: Quantitative evaluation gates ($0.0 - 1.0$) checking invariants prior to completion.
   - **State Checkpointing**: Immutable point-in-time state snapshots (`StateContext`).
   - **Backtracking**: Automated recovery mechanism rewinding state on reflection failure.
4. **Target Platform Adapters**:
   - **Prism Refraction / OpenClaw**: Routing core and state engine task dispatching.
   - **Hermes / Console**: Reasoning harness and console evaluation gates.
   - **Windows OS Agent**: Executive controller for desktop UI state verification.
5. **Antigravity v2 Rules & Workflow Integration**: Configured for System 1 (Perception), System 2 (Deliberation), and Synthesis Aggregator roles.

---

## 🚀 Quickstart & Testing

```bash
# Install package in editable mode with dev dependencies
pip install -e .[dev]

# Run full unit test suite
pytest tests/ -v
```

---

## 🔗 Connecting to GitHub

To link your local project folder to a GitHub repository:

1. **Create an Empty GitHub Repository**:
   - Go to [GitHub New Repository](https://github.com/new) and name it `cognition-cycles`.
   - Leave options to add README, `.gitignore`, or license unchecked.

2. **Initialize Git & Commit**:
   ```bash
   git init
   git branch -M main
   git add .
   git commit -m "Initial commit: Cognition Cycles structure with Antigravity v2 setup"
   ```

3. **Link Remote and Push**:
   ```bash
   git remote add origin https://github.com/<your-username>/cognition-cycles.git
   git push -u origin main
   ```
