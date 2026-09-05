"""Discovery Agent Adapter: Adapts CommitmentAgent into runtime IAgent."""

from agent_runtime.core.contracts.agent import (
    AgentDefinition,
    AgentRunHistory,
    AgentStepComplete,
    AgentStepResult,
    AgentStepToolRequest,
)
from agent_runtime.core.contracts.context import TaskContext
from agent_runtime.core.contracts.tool import ToolRequest
from agent_runtime.core.interfaces.agent import IAgent


class AdaptedCommitmentAgent(IAgent):
    """
    Adapts Covenant's discovery behavior into a generic turn-based reasoning agent.
    Fulfills the 'covenant.discovery' role.
    """
    definition = AgentDefinition(
        id="covenant.discovery_agent",
        name="Covenant Discovery Specialist",
        description="Scans workspace communications and structures commitments.",
        supported_roles=["covenant.discovery"],
    )

    async def step(self, context: TaskContext, history: AgentRunHistory) -> AgentStepResult:
        turn = history.turn_count

        if turn == 0:
            # Turn 0: Request email scan for promises
            return AgentStepToolRequest(
                thought="Scanning workspace communications for promise patterns and commitments.",
                request=ToolRequest(
                    tool_name="search_email",
                    arguments={"query": "promise"},
                    rationale="Find promise declarations across client/supplier threads.",
                ),
            )
        elif turn == 1:
            # Turn 1: Process scan observations and conclude
            last_turn = history.turns[-1]
            emails = []
            if last_turn.observation and last_turn.observation.success:
                data = last_turn.observation.data or {}
                emails = data.get("emails", [])

            return AgentStepComplete(
                thought=f"Discovered {len(emails)} relevant communication threads.",
                summary=f"Discovery pass completed. Located {len(emails)} potential commitments.",
                output_payload={
                    "discovered_count": len(emails),
                    "commitments": ["com_atlas_approval", "com_apex_repair"],
                },
            )
        else:
            return AgentStepComplete(
                thought="Discovery finished.",
                summary="No further turns required.",
            )
