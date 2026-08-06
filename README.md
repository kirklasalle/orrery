# Orrery: Multi-Tier Stateful Cognitive Framework

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub Repository](https://img.shields.io/badge/GitHub-kirklasalle%2Forrery-blue?logo=github)](https://github.com/kirklasalle/orrery)
[![Architecture](https://img.shields.io/badge/Antigravity-v2-purple.svg)](.antigravity/rules.md)

> *"Outgrowing the basic loop"*

**Orrery** is an agentic framework and orchestration paradigm designed to replace single-step ReAct loops ($\text{Prompt} \rightarrow \text{Tool Call} \rightarrow \text{Observation} \rightarrow \text{Answer}$) with stateful, multi-tier cognitive state loops operating across perception, planning, execution, and reflection.

An orrery is a clockwork model of nested orbits turning at different periods — the same relationship the **Meta**, **Macro**, **Meso**, and **Micro** tiers hold to one another.

> ### ⚠️ Project Status: Early-Stage Reference Implementation
>
> This repository is a **working architectural scaffold**, not a production system. Read this before evaluating:
>
> - The three integration adapters are **simulations**. They perform no network, LLM, or OS calls.
> - All execution handlers currently report unconditional success, so the reflection gate and
>   backtracking machinery are **not exercised by any production code path**.
> - Per-tier timeouts and iteration caps are declared in [config/settings.yaml](config/settings.yaml)
>   but are **not yet loaded or enforced**.
>
> A full technical and governance audit — including reproduced defects, severity ratings, and a
> sequenced remediation plan — is published at [docs/audit_2026-08-06.md](docs/audit_2026-08-06.md).
> Competitive and market positioning is at [docs/competitive_landscape_2026.md](docs/competitive_landscape_2026.md).

---

## 🏗️ Architecture Overview

```text
orrery/
├── .antigravity/
│   ├── rules.md                  # Agent behavior rules (System 1/2 roles, IDE interface constraints)
│   └── workflows/
│       └── cognition_cycle.yaml  # Antigravity v2 orchestration workflow (Perception -> Deliberation -> Synthesis)
├── config/
│   └── settings.yaml             # Project settings, thresholds, and storage paths
├── docs/
│   ├── PRD.md                    # Product Requirements Document
│   ├── audit_2026-08-06.md       # Full technical & governance audit
│   ├── competitive_landscape_2026.md  # Sourced competitive & market analysis
│   ├── architecture.md           # Technical Architecture Specification
│   └── setup_guide.md            # Installation & Integration Guide
├── examples/
│   └── demo_cycle.py             # Executable End-to-End Demonstration Script
├── orrery/
│   ├── core/                     # State Machine Dispatcher, CheckpointManager, SelfCritiqueEngine
│   ├── cycles/                   # Hierarchical Tiers (MetaCycle, MacroCycle, MesoCycle, MicroCycle)
│   └── adapters/                 # Adapters (OpenClaw, Hermes, Windows OS Agent)
├── tests/                        # Pytest Suite
├── CHANGELOG.md
├── LICENSE
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

> ⚠️ All three adapters are currently **simulated stubs** returning fixed responses. See the audit.

- **[OpenClawAdapter](orrery/adapters/openclaw.py)**: Prism Refraction routing core and state engine.
- **[HermesAdapter](orrery/adapters/hermes.py)**: Hermes / Console backend reasoning harness and evaluation gates.
- **[WindowsOSAdapter](orrery/adapters/windows_os.py)**: Windows OS Agent desktop UI state controller.

---

## 🚀 Quickstart & Testing

```bash
# Clone & install repository
git clone https://github.com/kirklasalle/orrery.git
cd orrery

# Create the canonical environment (Python 3.10)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -e ".[dev]"

# Run unit test suite
pytest tests/ -v

# Run executable demonstration script
python examples/demo_cycle.py
```

---

## 📊 Market Research & Strategic Audit

For an in-depth competitive analysis comparing 1st-generation ReAct agent loops against Orrery's multi-tier state machines, see [docs/market_research_audit.md](docs/market_research_audit.md).

> ⚠️ The market figures in that document are **unsourced and unverified**. Use
> [docs/competitive_landscape_2026.md](docs/competitive_landscape_2026.md) instead, which cites
> MarketsandMarkets and Precedence Research directly.

---

## 🔗 Repository & Remote Integration

Remote repository target: `https://github.com/kirklasalle/orrery.git`

```powershell
git remote add origin https://github.com/kirklasalle/orrery.git
git push -u origin main
```
