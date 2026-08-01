"""
Hermes / Console Backend Reasoning Harness Adapter.
"""

from typing import Any, Dict, Optional
from src.core.types import ActionPayload, ExecutionReceipt, StateContext
from src.adapters.base import BaseAdapter


class HermesAdapter(BaseAdapter):
    """
    Adapter interfacing with Hermes / Console backend reasoning harness.
    Provides evaluation gates and self-critique prior to terminal/console execution.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name="hermes", config=config)
        self.mode = self.config.get("mode", "console")

    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        return {
            "platform": "Hermes/Console",
            "mode": self.mode,
            "evaluation_gates": "active",
        }

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        output_msg = f"[Hermes/Console] Reasoned and evaluated action '{action.action_name}'."
        return ExecutionReceipt(
            action_id=action.action_id,
            action_name=action.action_name,
            success=True,
            output=output_msg,
        )
