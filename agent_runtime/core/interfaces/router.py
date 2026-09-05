"""Task router interface."""

from abc import ABC, abstractmethod
from typing import Any, Optional
from agent_runtime.core.contracts.agent import AgentDefinition
from agent_runtime.core.contracts.context import Task


class ITaskRouter(ABC):
    """Routes pending tasks to eligible registered agents."""

    @abstractmethod
    async def route(self, task: Task, registry: Any) -> Optional[AgentDefinition]:
        """Returns the best agent candidate matching the task's required role, or None."""
        pass
