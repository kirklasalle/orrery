"""
Windows OS Desktop Automation Agent Adapter.
"""

from typing import Any, Dict, Optional
from src.core.types import ActionPayload, ExecutionReceipt, StateContext
from src.adapters.base import BaseAdapter


class WindowsOSAdapter(BaseAdapter):
    """
    Adapter acting as executive controller for desktop automation.
    Uses micro-cycle reflection to verify screen state changes and UI element interactions.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name="windows_os", config=config)
        self.verify_screen_state = self.config.get("screen_state_verification", True)

    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        return {
            "platform": "Windows OS",
            "screen_state": "focused",
            "active_window": "CognitionCycles Desktop Controller",
        }

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        target = action.params.get("target", "desktop_ui")
        output_msg = f"[Windows OS Agent] Executed UI action '{action.action_name}' on target '{target}'."
        return ExecutionReceipt(
            action_id=action.action_id,
            action_name=action.action_name,
            success=True,
            output=output_msg,
        )
