"""
Prism Refraction & OpenClaw Platform Adapter.
"""

from typing import Any, Dict, Optional
from src.core.types import ActionPayload, ExecutionReceipt, StateContext
from src.adapters.base import BaseAdapter


class OpenClawAdapter(BaseAdapter):
    """
    Adapter interfacing with Prism Refraction routing core and OpenClaw state engine.
    Dispatches tasks from Meta-Cycles to Micro-Cycles with full checkpointing.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name="openclaw", config=config)
        self.routing_core = self.config.get("routing_core", "prism_refraction")

    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        return {
            "platform": "OpenClaw",
            "routing_core": self.routing_core,
            "active_cycle_tier": context.tier,
            "status": "ready",
        }

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        # Simulate Prism Refraction dispatching
        output_msg = f"[OpenClaw/{self.routing_core}] Dispatched action '{action.action_name}' successfully."
        return ExecutionReceipt(
            action_id=action.action_id,
            action_name=action.action_name,
            success=True,
            output=output_msg,
        )
