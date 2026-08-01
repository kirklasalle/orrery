# Cognition Cycles: Multi-Tier Stateful Cognitive Framework

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub Repository](https://img.shields.io/badge/GitHub-kirklasalle%2Fcognition--cycles-blue?logo=github)](https://github.com/kirklasalle/cognition-cycles)
[![Architecture](https://img.shields.io/badge/Antigravity-v2-purple.svg)](.antigravity/rules.md)

> *"Outgrowing the basic loop"*

**Cognition Cycles** is an enterprise agentic framework and orchestration paradigm designed to replace single-step ReAct loops ($\text{Prompt} \rightarrow \text{Tool Call} \rightarrow \text{Observation} \rightarrow \text{Answer}$) with stateful, multi-tier cognitive state loops operating across perception, planning, execution, and reflection.

---

## 🏗️ Architecture Overview

```text
cognition-cycles/
├── .antigravity/
│   ├── rules.md                  # Agent behavior rules (System 1/2 roles, IDE interface constraints)
│   └── workflows/
│       └── cognition_cycle.yaml  # Antigravity v2 orchestration workflow (Perception -> Deliberation -> Synthesis)
├── config/
│   └── settings.yaml             # Project settings, thresholds, and storage paths
├── docs/
│   ├── PRD.md                    # Product Requirements Document
│   ├── CHANGELOG.md              # Semantic Versioning Release Log
│   ├── market_research_audit.md  # Market Research & Strategic Positioning Audit
│   ├── architecture.md           # Technical Architecture Specification
│   └── setup_guide.md            # Installation & Integration Guide
├── examples/
│   └── demo_cycle.py             # Executable End-to-End Demonstration Script
├── src/
│   ├── core/                     # State Machine Dispatcher, CheckpointManager, SelfCritiqueEngine
│   ├── cycles/                   # Hierarchical Tiers (MetaCycle, MacroCycle, MesoCycle, MicroCycle)
│   └── adapters/                 # Adapters (OpenClaw, Hermes, Windows OS Agent)
├── tests/                        # Comprehensive Pytest Suite
├── .gitignore
├── pyproject.toml
└── README.md
```

---

## ⚡ Key Architecture & Features

### 1. 4-Phase State Machine Dispatcher
Transitions deterministically through:
- **PERCEPTION**: Environmental sensing & hypothesis generation (System 1).
- **PLANNING**: Strategy formulation & constraint evaluation (System 2).
- **EXECUTION**: Adapter action dispatch & receipt collection.
- **REFLECTION**: Quantitative self-critique gate ($\theta_{\text{critique}} = 0.70$).

### 2. 4 Hierarchical Abstraction Tiers
- **Meta-Cycles**: High-level system strategy and agent goal alignment.
- **Macro-Cycles**: Multi-step workflow orchestration and milestone tracking.
- **Meso-Cycles**: Context-bound execution loops and tool sequence management.
- **Micro-Cycles**: Fine-grained atomic actions and visual/text observation verification.

### 3. Built-in Meta-Skills
- **Disk-Backed State Checkpointing**: Immutable point-in-time state snapshots (`StateContext`) persisted to `.checkpoints/`.
- **Automated Backtracking**: Rewinds execution state back to safe checkpoints upon reflection failure.
- **Agent Self-Critique**: Quantitative scoring ($0.0 - 1.0$) evaluating execution invariants.

### 4. Enterprise Integration Adapters
- **[OpenClawAdapter](file:///d:/Projects/cognition_cycles/src/adapters/openclaw.py)**: Prism Refraction routing core and state engine.
- **[HermesAdapter](file:///d:/Projects/cognition_cycles/src/adapters/hermes.py)**: Hermes / Console backend reasoning harness and evaluation gates.
- **[WindowsOSAdapter](file:///d:/Projects/cognition_cycles/src/adapters/windows_os.py)**: Windows OS Agent desktop UI state controller.

---

## 🚀 Quickstart & Testing

```bash
# Clone & install repository
git clone https://github.com/kirklasalle/cognition-cycles.git
cd cognition-cycles
pip install -e .[dev]

# Run unit test suite
pytest tests/ -v

# Run executable demonstration script
python examples/demo_cycle.py
```

---

## 📊 Market Research & Strategic Audit

For an in-depth competitive analysis comparing 1st-generation ReAct agent loops against Cognition Cycles multi-tier state machines, see [docs/market_research_audit.md](file:///d:/Projects/cognition_cycles/docs/market_research_audit.md).

---

## 🔗 Repository & Remote Integration

Remote repository target: `https://github.com/kirklasalle/cognition-cycles.git`

```powershell
git remote add origin https://github.com/kirklasalle/cognition-cycles.git
git push -u origin main
```
