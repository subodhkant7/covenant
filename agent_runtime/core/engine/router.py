"""Deterministic TaskRouter implementation."""

from typing import List, Optional
from agent_runtime.core.contracts.agent import AgentDefinition
from agent_runtime.core.contracts.context import Task
from agent_runtime.core.engine.registry import AgentRegistry
from agent_runtime.core.interfaces.router import ITaskRouter


class DeterministicTaskRouter(ITaskRouter):
    """
    Deterministic task router.
    Filters agents by required role and required capabilities.
    Sorts eligible agents by ID deterministically to ensure reproducible routing.
    """

    async def route(self, task: Task, registry: AgentRegistry) -> Optional[AgentDefinition]:
        candidates: List[AgentDefinition] = []
        for agent in registry.find_by_role(task.required_role):
            defn = agent.definition
            # Verify required capabilities
            has_all_caps = all(cap in defn.capabilities for cap in task.input_payload.get("required_capabilities", []))
            if has_all_caps:
                candidates.append(defn)

        if not candidates:
            return None

        # Sort deterministically by agent ID
        candidates.sort(key=lambda d: d.id)
        return candidates[0]
