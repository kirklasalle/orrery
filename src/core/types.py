"""
Data models and types for the Cognition Cycles framework.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class CyclePhase(str, Enum):
    PERCEPTION = "PERCEPTION"
    PLANNING = "PLANNING"
    EXECUTION = "EXECUTION"
    REFLECTION = "REFLECTION"


class CycleTier(str, Enum):
    META = "META"
    MACRO = "MACRO"
    MESO = "MESO"
    MICRO = "MICRO"


class CycleStatus(str, Enum):
    IDLE = "IDLE"
    IN_PROGRESS = "IN_PROGRESS"
    CHECKPOINTED = "CHECKPOINTED"
    COMPLETED = "COMPLETED"
    BACKTRACKING = "BACKTRACKING"
    FAILED = "FAILED"


class ActionPayload(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_name: str
    params: Dict[str, Any] = Field(default_factory=dict)
    tier: CycleTier = CycleTier.MICRO
    target_adapter: str = "default"


class ExecutionReceipt(BaseModel):
    action_id: str
    action_name: str
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CritiqueResult(BaseModel):
    score: float = 1.0  # 0.0 to 1.0
    passed: bool = True
    reasoning: str = "Plan execution satisfies invariants."
    recommendations: List[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Checkpoint(BaseModel):
    checkpoint_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cycle_id: str
    tier: CycleTier
    phase: CyclePhase
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    state_data: Dict[str, Any]
    step_number: int = 0


class StateContext(BaseModel):
    cycle_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tier: CycleTier = CycleTier.META
    current_phase: CyclePhase = CyclePhase.PERCEPTION
    status: CycleStatus = CycleStatus.IDLE
    goal: str = ""
    variables: Dict[str, Any] = Field(default_factory=dict)
    
    # Phase specific state buffers
    hypotheses: List[str] = Field(default_factory=list)
    planned_actions: List[ActionPayload] = Field(default_factory=list)
    execution_receipts: List[ExecutionReceipt] = Field(default_factory=list)
    critiques: List[CritiqueResult] = Field(default_factory=list)
    
    # Checkpointing and backtracking state
    active_checkpoint_id: Optional[str] = None
    step_count: int = 0
    backtrack_count: int = 0
    max_backtracks: int = 3
