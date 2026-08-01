# Cognition Cycles Setup Guide

## Quickstart Guide

### 1. Requirements
- Python 3.10+
- Pytest (for running unit tests)
- Pydantic v2 & PyYAML

### 2. Installation
Initialize virtual environment and install dependencies:

```bash
python -m venv .venv
# Activate on Windows PowerShell:
.venv\Scripts\Activate.ps1
# Activate on Linux/macOS:
source .venv/bin/activate

pip install -e .
```

### 3. Running Unit Tests

To run the complete test suite:

```bash
pytest tests/ -v
```

### 4. Basic Framework Usage

```python
import asyncio
from src.core.dispatcher import CycleDispatcher
from src.core.types import StateContext, CycleTier
from src.cycles.meta import MetaCycle

async def main():
    # Initialize initial state context
    initial_state = StateContext(
        goal="Demonstrate cognitive cycle transition",
        variables={"env": "dev"}
    )
    
    # Instantiate MetaCycle dispatcher
    meta = MetaCycle(context=initial_state)
    
    # Run full cognitive loop (Perception -> Planning -> Execution -> Reflection)
    final_context = await meta.run_cycle()
    print(f"Cycle completed with status: {final_context.status}")

if __name__ == "__main__":
    asyncio.run(main())
```
