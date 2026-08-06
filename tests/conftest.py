"""
Shared test doubles.
"""

from typing import Any, ClassVar, Dict, List

from orrery.adapters.base import BaseAdapter
from orrery.core.types import ActionPayload, ExecutionReceipt, StateContext


class StubAdapter(BaseAdapter):
    """
    Adapter that records what it was asked to do and reports a configurable outcome.
    """

    is_simulation: ClassVar[bool] = False

    def __init__(self, name: str = "stub", succeed: bool = True, raises: bool = False):
        super().__init__(name=name)
        self.succeed = succeed
        self.raises = raises
        self.executed: List[ActionPayload] = []

    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        return {"platform": "stub", "goal": context.goal}

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        self.executed.append(action)
        if self.raises:
            raise RuntimeError("stub adapter blew up")
        return ExecutionReceipt(
            action_id=action.action_id,
            action_name=action.action_name,
            success=self.succeed,
            output=f"stub executed {action.action_name}" if self.succeed else None,
            error=None if self.succeed else "stub adapter was told to fail",
        )
