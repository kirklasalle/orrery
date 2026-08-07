"""
Shared test doubles.
"""

from typing import Any, ClassVar, Dict, List, Mapping

from orrery.adapters.base import BaseAdapter
from orrery.core.types import ActionPayload, ActionRisk, ExecutionReceipt, StateContext

# The action names the default handlers and the four tiers actually plan. A test double that
# declares its vocabulary models a conformant adapter; one that declares nothing models a
# defect, and there is a separate double for that below.
_STUB_VOCABULARY = (
    "anything",
    "test_action",
    "default_execute_goal",
    "default_execute_goal_attempt_2",
    "default_execute_goal_attempt_3",
    "default_execute_goal_attempt_4",
    "default_execute_goal_attempt_5",
    "meta_strategy_alignment",
    "execute_macro_milestone",
    "dispatch_tool_sequence",
    "atomic_action",
    "delegate_to_macro",
    "delegate_to_meso",
    "delegate_to_micro",
)


class StubAdapter(BaseAdapter):
    """
    Adapter that records what it was asked to do and reports a configurable outcome.
    """

    is_simulation: ClassVar[bool] = False

    declared_risks: ClassVar[Mapping[str, ActionRisk]] = {
        name: ActionRisk.REVERSIBLE for name in _STUB_VOCABULARY
    }

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

        if action.action_name not in self.declared_risks:
            return ExecutionReceipt(
                action_id=action.action_id,
                action_name=action.action_name,
                success=False,
                error=f"stub adapter does not implement action {action.action_name!r}",
            )

        return ExecutionReceipt(
            action_id=action.action_id,
            action_name=action.action_name,
            success=self.succeed,
            output=f"stub executed {action.action_name}" if self.succeed else None,
            error=None if self.succeed else "stub adapter was told to fail",
        )


class UndeclaredAdapter(BaseAdapter):
    """
    An adapter publishing no action vocabulary at all. This is the defect the conformance
    kit exists to make visible, so the double exists on purpose.
    """

    is_simulation: ClassVar[bool] = False

    def __init__(self, name: str = "undeclared"):
        super().__init__(name=name)

    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        return {"platform": "undeclared"}

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        return ExecutionReceipt(
            action_id=action.action_id,
            action_name=action.action_name,
            success=True,
            output=f"undeclared adapter did {action.action_name}",
        )
