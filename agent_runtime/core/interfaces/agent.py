"""Agent worker interface."""

from abc import ABC, abstractmethod
from agent_runtime.core.contracts.agent import AgentDefinition, AgentRunHistory, AgentStepResult
from agent_runtime.core.contracts.context import TaskContext


class IAgent(ABC):
    """Abstract agent reasoning worker."""
    definition: AgentDefinition

    @abstractmethod
    async def step(self, context: TaskContext, history: AgentRunHistory) -> AgentStepResult:
        """Executes one turn of reasoning on the task context and history."""
        pass
