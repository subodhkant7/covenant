"""Resolver Agent Adapter: Adapts ResolutionAgent into runtime IAgent."""

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
from covenant_runtime_bridge.mapping.entity_mapping import extract_commitment_id_from_scope


class AdaptedResolutionAgent(IAgent):
    """
    Adapts Covenant's resolution behavior into a generic turn-based agent.
    Fulfills the 'covenant.resolver' role.
    """
    definition = AgentDefinition(
        id="covenant.resolver_agent",
        name="Covenant Resolution Specialist",
        description="Formulates and dispatches resolution actions.",
        supported_roles=["covenant.resolver"],
    )

    async def step(self, context: TaskContext, history: AgentRunHistory) -> AgentStepResult:
        turn = history.turn_count
        cid = context.input_data.get("commitment_id") or extract_commitment_id_from_scope(context.scope) or "com_atlas_approval"

        if turn == 0:
            # Turn 0: Draft the follow-up reminder
            return AgentStepToolRequest(
                thought="Drafting polite follow-up citing contractual agreement.",
                request=ToolRequest(
                    tool_name="draft_followup",
                    arguments={
                        "commitment_id": cid,
                        "recipient_name": "Sarah Jenkins",
                        "recipient_email": "sjenkins@meridianglobal.com",
                        "subject": "Follow-up: Project Atlas Phase 2 Formal Approval",
                        "promise_summary": "Formal written sign-off for Phase 2 deliverables",
                        "original_due_date": "September 5, 2026",
                        "evidence_notes": "Phase 2 deliverables submitted Sep 3 per MSA Section 4.2.",
                    },
                    rationale="Prepare formal follow-up text for review.",
                ),
            )
        elif turn == 1:
            # Turn 1: Propose actual outbound dispatch (Gated by runtime policy)
            return AgentStepToolRequest(
                thought="Proposing outbound follow-up email dispatch.",
                request=ToolRequest(
                    tool_name="send_followup",
                    arguments={
                        "commitment_id": cid,
                        "recipient_email": "sjenkins@meridianglobal.com",
                        "subject": "Follow-up: Project Atlas Phase 2 Formal Approval",
                        "body": "Dear Sarah,\nFollowing up on Phase 2 deliverables.\nBest regards,\nAlex North",
                    },
                    rationale="Dispatch approved follow-up email.",
                ),
            )
        else:
            # Turn 2: Conclude resolution action
            return AgentStepComplete(
                thought="Outbound action successfully dispatched.",
                summary="Follow-up reminder dispatched to client. Ready for independent verification.",
                output_payload={
                    "commitment_id": cid,
                    "action_executed": True,
                    "recipient": "sjenkins@meridianglobal.com",
                },
            )
