"""Tool and Agent registries for capability discovery."""

from typing import Dict, List, Optional
from agent_runtime.core.contracts.agent import AgentDefinition
from agent_runtime.core.contracts.tool import ToolSpec
from agent_runtime.core.interfaces.agent import IAgent
from agent_runtime.core.interfaces.tool import ITool


class ToolRegistry:
    """Registry answering 'What tools exist?'."""

    def __init__(self):
        self._tools: Dict[str, ITool] = {}

    def register(self, tool: ITool) -> None:
        self._tools[tool.spec.name] = tool

    def unregister(self, name: str) -> Optional[ITool]:
        return self._tools.pop(name, None)

    def get(self, name: str) -> Optional[ITool]:
        return self._tools.get(name)

    def list_specs(self) -> List[ToolSpec]:
        return [tool.spec for tool in self._tools.values()]


class AgentRegistry:
    """Registry answering 'What agents exist and what roles can they perform?'."""

    def __init__(self):
        self._agents: Dict[str, IAgent] = {}

    def register(self, agent: IAgent) -> None:
        self._agents[agent.definition.id] = agent

    def unregister(self, agent_id: str) -> Optional[IAgent]:
        return self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> Optional[IAgent]:
        return self._agents.get(agent_id)

    def find_by_role(self, role_id: str) -> List[IAgent]:
        return [
            agent for agent in self._agents.values()
            if role_id in agent.definition.supported_roles
        ]

    def list_definitions(self) -> List[AgentDefinition]:
        return [agent.definition for agent in self._agents.values()]
