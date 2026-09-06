"""
Orrery Gates SDK — Standalone Governance Pipeline.

Provides a decoupled, lightweight governance facade for embedding Orrery's 6-gate
defense-in-depth stack into external frameworks (LangGraph, CrewAI, FastAPI, CLI tools)
without requiring the full 4-tier cognitive state machine dispatcher.
"""

from orrery.gates.pipeline import GateVerdict, GovernancePipeline

__all__ = [
    "GovernancePipeline",
    "GateVerdict",
]
