"""ModelDrivenAgent: Generic agent reasoning worker powered by any IModelProvider with strict turn discipline."""

from typing import Any, Dict, Optional
from agent_runtime.core.contracts.agent import (
    AgentDefinition,
    AgentRunHistory,
    AgentStepComplete,
    AgentStepFailure,
    AgentStepResult,
    AgentStepToolRequest,
)
from agent_runtime.core.contracts.context import TaskContext
from agent_runtime.core.contracts.tool import ToolRequest
from agent_runtime.core.interfaces.agent import IAgent
from agent_runtime.core.interfaces.model import (
    IModelProvider,
    ModelMessage,
    ModelRequest,
)


class ModelDrivenAgent(IAgent):
    """
    Standard agent implementation powered by an IModelProvider.
    Enforces strict turn discipline: fails closed if model attempts multiple concurrent calls.
    """

    def __init__(
        self,
        agent_definition: AgentDefinition,
        model_provider: IModelProvider,
        system_prompt: Optional[str] = None,
    ):
        self.definition = agent_definition
        self.provider = model_provider
        self.system_prompt = system_prompt or (
            f"You are {agent_definition.name}. Solve the user's task using the available tools."
        )

    async def step(self, context: TaskContext, history: AgentRunHistory) -> AgentStepResult:
        messages = [ModelMessage(role="system", content=self.system_prompt)]

        # Add initial user request from TaskContext
        user_prompt = f"Task Intent: {context.intent}\nInput Payload: {context.input_data}"
        messages.append(ModelMessage(role="user", content=user_prompt))

        # Add prior reasoning turns
        for turn in history.turns:
            if turn.thought or turn.request:
                assistant_msg = turn.thought or ""
                if turn.request:
                    assistant_msg += f"\nRequesting tool '{turn.request.tool_name}' with args {turn.request.arguments}"
                messages.append(ModelMessage(role="assistant", content=assistant_msg))
            if turn.observation:
                obs_msg = f"Observation from {turn.observation.tool_name} (success={turn.observation.success}): {turn.observation.data}"
                messages.append(ModelMessage(role="user", content=obs_msg))

        req = ModelRequest(
            messages=messages,
            available_tools=context.available_tools,
            temperature=0.1,
        )

        try:
            resp = await self.provider.generate(req)
        except Exception as e:
            return AgentStepFailure(error_message=f"Model provider call failed: {str(e)}")

        # Enforce single tool per turn constraint (fail closed on multiple calls)
        if len(resp.tool_calls) > 1:
            return AgentStepFailure(
                error_message=f"Model produced multiple conflicting tool calls ({len(resp.tool_calls)}). V1 runtime requires exactly one tool call per turn."
            )

        # Single valid tool request
        if len(resp.tool_calls) == 1:
            call = resp.tool_calls[0]
            return AgentStepToolRequest(
                thought=resp.content,
                request=ToolRequest(
                    tool_name=call.tool_name,
                    arguments=call.arguments,
                    rationale=resp.content or f"Invoking {call.tool_name}",
                ),
            )

        # Otherwise model concluded reasoning
        return AgentStepComplete(
            thought="Reasoning concluded.",
            summary=resp.content or "Completed without message.",
            output_payload={"response": resp.content},
        )
