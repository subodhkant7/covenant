"""Tool capability interface."""

from abc import ABC, abstractmethod
from typing import Any
from agent_runtime.core.contracts.tool import ToolSpec


class ITool(ABC):
    """Abstract tool capability executable by the runtime."""
    spec: ToolSpec

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Executes tool code with validated arguments."""
        pass
