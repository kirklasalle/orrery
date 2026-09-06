# Orrery Developer Guide

> **Target Audience:** Core Contributors, System Engineers, and Framework Integrators  
> **Version:** 1.0.0  
> **Status:** Active Reference  

---

## 1. Introduction & Core Philosophy

**Orrery** is a cognitive-governance framework designed to supersede fragile single-step ReAct loops ($\text{Prompt} \rightarrow \text{Tool Call} \rightarrow \text{Observation}$) with deterministic, stateful cognitive execution loops and defense-in-depth safety gates.

### Core Architectural Principles
1. **Deterministic Execution Pipeline**: Every agent action passes through an immutable five-stage verification pipeline before OS or network contact.
2. **Cryptographic Provenance**: Every execution envelope, ledger entry, and state transition is cryptographically signed using Ed25519 digital signatures and linked into an immutable hash chain.
3. **Fail-Closed Safety**: In any edge case (missing capability, signature mismatch, budget depletion, rate limit exhaustion, or malformed payload), the pipeline denies execution.
4. **Hierarchical Cognition**: Long-horizon agency is structured into four distinct abstraction tiers:
   - **Meta-Cycles**: High-level strategy, governance, and cross-agent alignment.
   - **Macro-Cycles**: Multi-step workflow milestone orchestration.
   - **Meso-Cycles**: Context-bound execution loops and tool management.
   - **Micro-Cycles**: Atomic tool execution, shell interaction, or UI verification.
5. **Stateful Self-Correction (Backtracking)**: Failed actions do not crash the agent; the state machine rewinds work to the last validated checkpoint while retaining attempt logs and failure lessons.

---

## 2. Repository Layout & Module Architecture

```
orrery/
├── orrery/
│   ├── __init__.py                # Package root & exports
│   ├── config.py                  # Thread-safe configuration singleton
│   ├── core/                      # Engine primitives & governance
│   │   ├── charter.py             # Permanent active directives & inviolate rules
│   │   ├── dispatcher.py          # State machine loop (Perceive -> Plan -> Execute -> Reflect)
│   │   ├── envelope.py            # Signed execution envelopes & action payloads
│   │   ├── governance.py          # 5-Gate defense-in-depth stack & verdicts
│   │   ├── hindsight.py           # Self-critique engine & threshold checks
│   │   ├── ledger.py              # Tamper-evident hash-chained audit ledger
│   │   ├── quarantine.py          # Process & state isolation for rogue runs
│   │   ├── signing.py             # Ed25519 cryptographic signing & keyring
│   │   └── state.py               # StateContext, checkpoints, & rolling backtrack
│   ├── cycles/                    # Hierarchical cognitive tiers
│   │   ├── meta.py                # MetaCycle implementation
│   │   ├── macro.py               # MacroCycle implementation
│   │   ├── meso.py                # MesoCycle implementation
│   │   └── micro.py               # MicroCycle implementation
│   ├── adapters/                  # External system execution harnesses
│   │   ├── base.py                # BaseAdapter abstract class (with hoisted _receipt)
│   │   ├── filesystem.py          # Path-confined, permission-controlled file I/O
│   │   ├── process.py             # Sandboxed subprocess runner with process tree kill
│   │   ├── openclaw.py            # OpenClaw routing harness
│   │   ├── hermes.py              # Hermes reasoning harness
│   │   └── windows_os.py          # Windows OS UI interaction harness
│   └── tools/                     # High-level tool wrappers
│       ├── base.py                # BaseTool definition
│       ├── registry.py            # Tool discovery & registration
│       └── builtin.py             # Built-in execution tools
├── tests/                         # Full test suite (400+ tests, 93%+ coverage)
├── docs/                          # Architecture, PRD, and operational guides
└── pyproject.toml                 # Packaging & tool configurations
```

---

## 3. Development Setup & Workflow

### Prerequisites
- **Python 3.10+** (Tested on Python 3.10, 3.11, 3.12)
- **Git**
- Optional: OpenSSL / libsodium for hardware crypto acceleration

### Initializing the Environment

```bash
# Clone the repository
git clone https://github.com/kirklasalle/orrery.git
cd orrery

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install editable package with dev dependencies
pip install -e ".[dev]"
```

### Running the Test Suite

```bash
# Run all unit tests
pytest

# Run tests with coverage summary
pytest --cov=orrery --cov-report=term-missing

# Run a specific test file
pytest tests/test_governance.py -v
```

### Linting and Formatting

```bash
# Run code formatter and linter
ruff check orrery/ tests/
ruff format --check orrery/ tests/

# Type checking
mypy orrery/
```

---

## 4. Developing Custom Adapters

All tool and action executions terminate at an **Adapter**. Every adapter must inherit from `orrery.adapters.base.BaseAdapter`.

### Key Requirements for Adapters:
1. **Declare Capabilities**: The adapter must declare explicit capability tokens (e.g., `["exec:run", "exec:kill"]`).
2. **Enforce Isolation**: Operations must respect safety roots (e.g., directory confinement or process group isolation).
3. **Use Hoisted `_receipt()`**: Use `self._receipt(...)` from `BaseAdapter` to generate standardized, cryptographically bindable receipts.
4. **Clean Resource Deallocation**: Processes, file descriptors, or sockets must be guaranteed cleanup via `try...finally` or context managers.

### Adapter Implementation Template

```python
from typing import Any, Dict, List, Optional
from pathlib import Path
from orrery.adapters.base import BaseAdapter, ExecutionReceipt

class CustomDatabaseAdapter(BaseAdapter):
    """
    Adapter providing governed read-only access to SQLite databases.
    """

    def __init__(self, db_path: Path, allowed_tables: List[str]):
        super().__init__(name="sqlite_adapter")
        self.db_path = Path(db_path).resolve()
        self.allowed_tables = set(allowed_tables)

    @property
    def capabilities(self) -> List[str]:
        return ["db:query", "db:schema"]

    async def execute(self, action: str, parameters: Dict[str, Any]) -> ExecutionReceipt:
        """
        Executes a database query with strict capability checks.
        """
        if action not in self.capabilities:
            return self._receipt(
                action=action,
                success=False,
                output=None,
                error=f"Unsupported database action: {action}"
            )

        if action == "db:schema":
            return self._receipt(
                action=action,
                success=True,
                output={"tables": list(self.allowed_tables)}
            )

        if action == "db:query":
            query = parameters.get("sql", "").strip()
            # Enforce read-only constraint
            if not query.upper().startswith("SELECT"):
                return self._receipt(
                    action=action,
                    success=False,
                    output=None,
                    error="Non-SELECT queries are forbidden under the safety policy."
                )
            
            # Execute query safely...
            result = self._run_query(query)
            return self._receipt(
                action=action,
                success=True,
                output=result
            )

        return self._receipt(action=action, success=False, error="Unhandled path")

    def _run_query(self, query: str) -> List[Dict[str, Any]]:
        # Database query execution logic
        return []
```

---

## 5. Extending the Governance Gate Stack

The `GovernanceEngine` evaluates actions through a chain of safety gates. When designing new gates (e.g., rate limiting, DLP / data-loss prevention, or LLM-as-a-judge):

### Gate Contract
- Gate evaluation must return a `GateVerdict` with `allowed: bool`, `gate_name: str`, and `reason: str`.
- **Fail-Closed Rule**: If a gate encounters an unhandled exception or ambiguous state, it MUST reject the action (`allowed=False`).

### Implementing a Custom Gate

```python
from orrery.core.governance import GateVerdict
from orrery.core.envelope import ActionPayload

class RateLimitGate:
    """
    Limits the number of sensitive operations per cycle tier.
    """
    def __init__(self, max_calls_per_minute: int = 60):
        self.max_calls = max_calls_per_minute
        self.call_history: list[float] = []

    def evaluate(self, payload: ActionPayload) -> GateVerdict:
        current_time = payload.timestamp
        # Clean expired timestamps
        self.call_history = [t for t in self.call_history if current_time - t < 60]

        if len(self.call_history) >= self.max_calls:
            return GateVerdict(
                allowed=False,
                gate_name="RateLimitGate",
                reason=f"Exceeded quota of {self.max_calls} calls/min."
            )

        self.call_history.append(current_time)
        return GateVerdict(
            allowed=True,
            gate_name="RateLimitGate",
            reason="Within rate limit budget."
        )
```

---

## 6. Implementing Cycle Tiers & Phase Handlers

The `CycleDispatcher` executes four discrete phases for each cycle:

```python
async def run_cycle(self, context: StateContext) -> StateContext:
    context = await self.perceive(context)
    context = await self.plan(context)
    context = await self.execute(context)
    context = await self.reflect(context)
    return context
```

### Phase Responsibilities:
1. **`perceive(context)`**:
   - Parses observations from prior actions.
   - Generates candidate hypotheses (`context.hypotheses.append(...)`).
   - Checks environmental cues.
2. **`plan(context)`**:
   - Formulates concrete `ActionPayload` items.
   - Evaluates constraints and pre-conditions.
   - Enqueues planned actions in `context.planned_actions`.
3. **`execute(context)`**:
   - Iterates through `context.planned_actions`.
   - Dispatches each action through `GovernanceEngine.evaluate()`.
   - Dispatches approved actions to the registered `BaseAdapter`.
   - Records `ExecutionReceipt` into `context.execution_history`.
4. **`reflect(context)`**:
   - Computes empirical critique score via `SelfCritiqueEngine`.
   - If $\text{score} \ge \theta_{\text{critique}}$ ($0.70$): Advances status to `CycleStatus.COMPLETED`.
   - If $\text{score} < \theta_{\text{critique}}$: Triggers `CheckpointManager.backtrack()`.

---

## 7. Cryptographic Signing & Key Management

Orrery enforces cryptographic non-repudiation using Ed25519 (EdDSA over Curve25519).

### Key Classes in `orrery.core.signing`:
- `Ed25519Signer`: Handles private-key signing of arbitrary payloads or canonical JSON representations.
- `Keyring`: Manages trusted public keys and verifies incoming signatures.
- `SignedEnvelope`: Wraps an `ActionPayload` or `ExecutionReceipt` with:
  - `key_id`: Identifier of the signing entity.
  - `signature_hex`: 64-byte Ed25519 signature encoded as hexadecimal.
  - `algorithm`: Default `"ed25519"`.

### Generating and Using Keys:

```python
from orrery.core.signing import Ed25519Signer, Keyring

# 1. Instantiate a signer with an existing private key or generate a new one
signer = Ed25519Signer.generate(key_id="agent-worker-01")

# 2. Export public key to register in Keyring
keyring = Keyring()
keyring.add(signer.key_id, signer.public_key_hex)

# 3. Sign an execution payload
data = {"action": "fs:read", "path": "/safe/workspace/data.txt"}
signature = signer.sign(data)

# 4. Verify signature on receiving end
is_valid = keyring.verify(signer.key_id, data, signature)
assert is_valid is True
```

---

## 8. State Context & Checkpoint Rolling Backtrack

`StateContext` is the state container for all cognitive cycles.

### Backtracking Semantics
When an action fails or reflection rejects a milestone:
- **`CheckpointManager.backtrack(context)`** restores state back to the most recent safe checkpoint.
- **Critical Invariant**: State variables and hypotheses revert to the safe checkpoint, but **step counts, attempt logs, and lessons persist**. This ensures the agent does not repeat identical flawed attempts.

```python
# Create a checkpoint before executing speculative work
checkpoint = checkpoint_manager.create_checkpoint(context)

# If reflection score is low:
if critique_score < THETA_CRITIQUE:
    context.attempt_log.append(f"Attempt failed: {failure_reason}")
    context.lessons.append(f"Avoid parameter {bad_param}")
    context = checkpoint_manager.backtrack(context)
    # context is now back at CyclePhase.PLANNING with fresh lessons
```

---

## 9. Testing Standards & Coverage Rules

Orrery maintains an uncompromising standard for software verification.

### Core Testing Rules:
1. **Target Coverage**: Core modules (`core/`, `cycles/`, `adapters/`) must maintain **$\ge 90\%$ test coverage**.
2. **Deterministic Tests**: No non-deterministic sleep calls. Use asynchronous mocks or time fixtures.
3. **Process Isolation**: When testing adapters that launch processes, always use temporary working directories (`tmp_path`) and verify process tree cleanup.
4. **Hermetic Keyrings**: Never hardcode production cryptographic keys in tests; generate ephemeral in-memory signers.

### Running Test Verification Script:

```bash
# Verify entire suite with strict assertion
pytest tests/ -v --tb=short
```

---

## 10. OpenRouter Adapter & LLM-as-a-Judge (Law 7)

Orrery provides an air-gapped, zero-external-dependency adapter for OpenRouter's unified LLM API (`orrery/adapters/openrouter.py`), alongside an LLM-as-a-Judge goal verification engine (`orrery/core/judge.py`).

### Key Invariant (Law 7):
An LLM judge verdict is **strictly empirical evidence** passed to `SelfCritiqueEngine`; it can **never bypass** deterministic governance gates or overrule safety policies. If an LLM judge returns low confidence ($< 0.70$), times out, or fails, the verification **fails closed**.

```python
from orrery.adapters.openrouter import OpenRouterAdapter
from orrery.core.judge import create_openrouter_goal_check
from orrery.core.critique import SelfCritiqueEngine

# 1. Initialize adapter (uses OPENROUTER_API_KEY from env or runs in simulation mode)
adapter = OpenRouterAdapter(
    model="openai/gpt-4o-mini",
    allowed_models=["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"],
    max_tokens_limit=2048,
)

# 2. Wire LLM goal verification oracle into critique engine
goal_oracle = create_openrouter_goal_check(
    adapter=adapter,
    goal="Compile and verify binary output without memory leaks",
    min_confidence=0.75,
)

critique_engine = SelfCritiqueEngine(
    threshold=0.80,
    goal_check=goal_oracle,
)
```

---

## 11. Empirical $\theta_{\text{critique}}$ Calibration

Rather than guessing an arbitrary threshold for the reflection score, Orrery empirically derives $\theta_{\text{critique}}$ by sweeping candidate thresholds across execution traces:

```bash
python -m orrery.tools.calibrate_critique --objective fail_closed
```

- **Fail-Closed Objective**: Minimizes False Positives (passing a flawed plan), yielding an optimal default threshold of **$\theta = 0.80$** with 0.0% False Positive Rate.
- **Balanced Objective**: Optimizes the $F_1$ harmonic mean.

---

## 12. Automated Regulatory Compliance Engine

The `orrery.compliance` module maps all 10 Governance Laws, cryptographic receipts, and gates to leading U.S. and international AI governance frameworks:

- **NIST AI Risk Management Framework 1.0 (NIST AI 100-1)**: GOVERN, MAP, MEASURE, MANAGE
- **White House OMB M-24-10**: Federal Agency AI Governance
- **Colorado SB 24-205**: Artificial Intelligence Act (duty of care, impact assessments)
- **California AB 2013 / Safety Directives**: Transparency disclosures and emergency kill switch
- **EU AI Act Articles 12-15**: High-risk record-keeping, transparency, human oversight, robustness

### Running Compliance Audits:

```bash
# Run full audit and output GitHub-flavored Markdown
python -m orrery.tools.compliance --framework all --format markdown --output audit_report.md

# Run machine-readable JSON audit for CI / governance dashboard
python -m orrery.tools.compliance --framework nist --format json --strict
```

