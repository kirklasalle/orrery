# Cognition Cycles Setup & Integration Guide

> **Target Repository:** `https://github.com/kirklasalle/cognition-cycles`

---

## 1. Installation

### Requirements
- Python 3.10+
- Pytest (for unit test verification)

### Environment Setup

```bash
# Clone repository
git clone https://github.com/kirklasalle/cognition-cycles.git
cd cognition-cycles

# Create and activate virtual environment
python -m venv .venv
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install in editable mode with development dependencies
pip install -e .[dev]
```

---

## 2. Running Unit Tests

Run the full pytest suite:

```bash
pytest tests/ -v
```

---

## 3. Running the End-to-End Demonstration Script

Execute the multi-tier nested cycle and failover backtracking demonstration:

```bash
python examples/demo_cycle.py
```

---

## 4. Programmatic Usage Example

```python
import asyncio
from src.core.types import StateContext, CycleTier
from src.cycles.meta import MetaCycle

async def main():
    # Initialize state context
    context = StateContext(
        goal="Process complex document ingestion and audit trail",
        tier=CycleTier.META,
    )
    
    # Initialize Meta-Cycle (automatically delegates down to Macro -> Meso -> Micro)
    meta = MetaCycle(context=context)
    
    # Run full cognitive cycle
    result = await meta.run_cycle()
    print(f"Cycle completed with status: {result.status}")
    print(f"Total steps executed across tiers: {result.step_count}")

if __name__ == "__main__":
    asyncio.run(main())
```
