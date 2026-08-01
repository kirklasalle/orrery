"""
Base Adapter Abstract Interface.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict
from src.core.types import ActionPayload, ExecutionReceipt, StateContext


class BaseAdapter(ABC):
    """
    Abstract Base Class for external environment and platform adapters.
    """

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}

    @abstractmethod
    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        """
        Senses the platform state/environment and returns normalized observation signals.
        """
        pass

    @abstractmethod
    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        """
        Dispatches an action payload to the target platform engine and returns an execution receipt.
        """
        pass
