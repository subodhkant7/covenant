"""External Agent Adapter & Transport-Neutral Protocol (Hardened).

Provides an authoritative, fail-closed boundary between untrusted external reasoning engines
(e.g., Antigravity subagents, Claude, OpenAI, custom reasoning workers)
and the Agent Organization Runtime.

Guarantees:
1. Multi-layer recursive secret redaction for task facts, observations, and tool arguments.
2. Unsafe execution handles (callables, DB connections, open files, runtime engines) fail closed.
3. Private chain-of-thought (thought) is stripped from the protocol in favor of rationale.
4. Attempted privilege escalations (forged approval, verification bypass) record SECURITY_VIOLATION.
5. Strict output schema validation under ConfigDict(extra="forbid").
"""

import asyncio
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_runtime.core.contracts.agent import (
    AgentDefinition,
    AgentRunHistory,
    AgentStepComplete,
    AgentStepFailure,
    AgentStepResult,
    AgentStepToolRequest,
)
from agent_runtime.core.contracts.context import TaskContext
from agent_runtime.core.contracts.event import Event, EventType
from agent_runtime.core.contracts.tool import ToolRequest
from agent_runtime.core.interfaces.agent import IAgent
from agent_runtime.core.interfaces.telemetry import IEventSink
from agent_runtime.security.external_agent_sanitizer import ExternalAgentSanitizer, UnsafeContextError


class ExternalAgentResponseType(str, Enum):
    """Allowed response categories from an external reasoning agent."""
    TOOL_PROPOSAL = "TOOL_PROPOSAL"
    COMPLETE = "COMPLETE"
    FAILURE = "FAILURE"


class ExternalAgentToolProposal(BaseModel):
    """An untrusted proposal from an external agent to invoke a tool."""
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    rationale: Optional[str] = ""

    @field_validator("tool_name")
    @classmethod
    def validate_tool_name(cls, v: str) -> str:
        if not v or not isinstance(v, str) or not v.strip():
            raise ValueError("tool_name must be a non-empty string")
        return v.strip()

    @field_validator("arguments")
    @classmethod
    def validate_arguments(cls, v: Any) -> Dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("arguments must be a dictionary")
        # Ensure arguments contains no python callables or execution handles
        sanitizer = ExternalAgentSanitizer()
        return sanitizer.sanitize_payload(v, fail_on_unsafe=True)


class ExternalAgentResponse(BaseModel):
    """Normalized, transport-neutral response parcel from an external agent.
    Strictly forbids private thought and arbitrary execution fields.
    """
    model_config = ConfigDict(extra="forbid")

    response_type: ExternalAgentResponseType
    tool_proposal: Optional[ExternalAgentToolProposal] = None
    completion_summary: Optional[str] = None
    output_payload: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    rationale: Optional[str] = None


class ExternalAgentObservation(BaseModel):
    """Sanitized, read-only projection of a past tool execution delivered to external agent."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str
    tool_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None


class ExternalAgentTurn(BaseModel):
    """Historical turn passed to external agent for conversational context.
    Excludes private chain-of-thought in favor of rationale.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    turn_index: int
    tool_name: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    observation: Optional[ExternalAgentObservation] = None
    rationale: Optional[str] = None


class ExternalAgentToolDescription(BaseModel):
    """Public specification of an available tool capability."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str
    parameters_schema: Dict[str, Any] = Field(default_factory=dict)
    has_side_effects: bool = False
    execution_safety: str = "READ_ONLY"


class ExternalAgentTaskFacts(BaseModel):
    """Immutable factual context describing the unit of work. Contains ZERO execution handles."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    organization_id: str
    intent: str
    required_role: str
    scope: Dict[str, Any] = Field(default_factory=dict)
    input_data: Dict[str, Any] = Field(default_factory=dict)


class ExternalAgentRequest(BaseModel):
    """Complete request context delivered to the external agent."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    task: ExternalAgentTaskFacts
    allowed_tools: List[ExternalAgentToolDescription] = Field(default_factory=list)
    history: List[ExternalAgentTurn] = Field(default_factory=list)
    current_turn: int
    max_turns: int
    run_state: str = "EXECUTING"


class IExternalAgent(ABC):
    """Contract for an external reasoning worker (model, subagent, script, or service)."""

    @abstractmethod
    async def decide(self, request: ExternalAgentRequest) -> ExternalAgentResponse:
        """Produces a tool proposal, completion, or failure."""
        pass


class IExternalAgentTransport(ABC):
    """Pluggable transport abstraction (in-process, IPC, HTTP, queue)."""

    @abstractmethod
    async def send_and_receive(self, request: ExternalAgentRequest) -> ExternalAgentResponse:
        """Transports request to the external agent and retrieves response."""
        pass


class InProcessExternalAgentTransport(IExternalAgentTransport):
    """Default zero-dependency in-process transport."""

    def __init__(self, external_agent: IExternalAgent):
        self.agent = external_agent

    async def send_and_receive(self, request: ExternalAgentRequest) -> ExternalAgentResponse:
        return await self.agent.decide(request)


# Set of keys indicating attempted privilege escalation in external responses
PRIVILEGE_ESCALATION_KEYS = {
    "approved",
    "approval",
    "approval_override",
    "verified",
    "verification",
    "skip_verification",
    "task_status",
    "execution_result",
    "policy_override",
}


class ExternalAgentAdapter(IAgent):
    """IAgent implementation wrapping an external reasoning entity.

    Enforces runtime authority:
    - Recursively sanitizes context data and tool observations using ExternalAgentSanitizer.
    - Fails closed on any raw execution handle or callable.
    - Rejects or strips forged authority claims, logging SECURITY_VIOLATION events.
    - Excludes private chain-of-thought from transport and telemetry.
    """

    def __init__(
        self,
        agent_definition: AgentDefinition,
        transport: Optional[IExternalAgentTransport] = None,
        external_agent: Optional[IExternalAgent] = None,
        event_sink: Optional[IEventSink] = None,
        timeout: float = 30.0,
        sanitizer: Optional[ExternalAgentSanitizer] = None,
    ):
        self.definition = agent_definition
        if transport is not None:
            self.transport = transport
        elif external_agent is not None:
            self.transport = InProcessExternalAgentTransport(external_agent)
        else:
            raise ValueError("Either transport or external_agent must be provided.")

        self.event_sink = event_sink
        self.timeout = timeout
        self.sanitizer = sanitizer or ExternalAgentSanitizer()

    async def step(self, context: TaskContext, history: AgentRunHistory) -> AgentStepResult:
        """Executes a single reasoning step via the external agent."""
        trace_id = f"trc_{context.task_id}"

        # 1. Sanitize TaskContext facts (Fail closed on unsafe execution handles)
        try:
            clean_input = self.sanitizer.sanitize_context_data(dict(context.input_data))
            scope_raw = {
                "scope_type": context.scope.scope_type.value if hasattr(context.scope.scope_type, "value") else str(context.scope.scope_type),
                "entity_type": context.scope.entity_type,
                "entity_ids": list(context.scope.entity_ids),
                "filter_criteria": dict(context.scope.filter_criteria),
            }
            clean_scope = self.sanitizer.sanitize_payload(scope_raw, fail_on_unsafe=True)
            task_facts = ExternalAgentTaskFacts(
                task_id=context.task_id,
                organization_id=context.organization_id,
                intent=self.sanitizer.redact_text(context.intent),
                required_role=context.required_role,
                scope=clean_scope,
                input_data=clean_input,
            )
        except UnsafeContextError as ue:
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=trace_id,
                        organization_id=context.organization_id,
                        task_id=context.task_id,
                        agent_run_id=history.run_id,
                        event_type=EventType.SECURITY_VIOLATION,
                        summary="Refused to expose raw execution handle to external agent.",
                        payload={"agent_id": self.definition.id, "violation": str(ue)},
                    )
                )
            return AgentStepFailure(
                error_message=f"Context security failure: {str(ue)}",
                recoverable=False,
            )

        # 2. Sanitize Allowed Tool Specifications
        allowed_tools = [
            ExternalAgentToolDescription(
                name=spec.name,
                description=self.sanitizer.redact_text(spec.description),
                parameters_schema=self.sanitizer.sanitize_payload(dict(spec.parameters_schema), fail_on_unsafe=True),
                has_side_effects=spec.has_side_effects,
                execution_safety=spec.execution_safety.value if hasattr(spec.execution_safety, "value") else str(spec.execution_safety),
            )
            for spec in context.available_tools
        ]

        # 3. Sanitize History Turns (Strip private thought, redact observation secrets)
        turns: List[ExternalAgentTurn] = []
        for turn in history.turns:
            obs = None
            if turn.observation:
                clean_obs_data = self.sanitizer.sanitize_observation_data(turn.observation.data)
                clean_obs_err = self.sanitizer.redact_text(turn.observation.error) if turn.observation.error else None
                obs = ExternalAgentObservation(
                    observation_id=turn.observation.observation_id,
                    tool_name=turn.observation.tool_name,
                    success=turn.observation.success,
                    data=clean_obs_data,
                    error=clean_obs_err,
                )
            clean_args = self.sanitizer.sanitize_payload(turn.request.arguments, fail_on_unsafe=True) if turn.request else None
            clean_rationale = self.sanitizer.redact_text(turn.request.rationale) if turn.request and turn.request.rationale else None

            turns.append(
                ExternalAgentTurn(
                    turn_index=turn.turn_index,
                    tool_name=turn.request.tool_name if turn.request else None,
                    arguments=clean_args,
                    observation=obs,
                    rationale=clean_rationale,
                )
            )

        # 4. Construct Request Parcel
        req = ExternalAgentRequest(
            task=task_facts,
            allowed_tools=allowed_tools,
            history=turns,
            current_turn=len(turns) + 1,
            max_turns=context.max_turns,
            run_state="EXECUTING",
        )

        # 5. Emit EXTERNAL_AGENT_REQUESTED Telemetry (Redacted, zero secrets, zero thought)
        if self.event_sink:
            await self.event_sink.record(
                Event(
                    trace_id=trace_id,
                    organization_id=context.organization_id,
                    task_id=context.task_id,
                    agent_run_id=history.run_id,
                    event_type=EventType.EXTERNAL_AGENT_REQUESTED,
                    summary=f"Dispatched reasoning turn {req.current_turn} to external agent '{self.definition.id}'.",
                    payload={
                        "agent_id": self.definition.id,
                        "turn_index": req.current_turn,
                        "allowed_tools_count": len(allowed_tools),
                    },
                )
            )

        # 6. Dispatch with Timeout and Exception Handling
        try:
            raw_response = await asyncio.wait_for(
                self.transport.send_and_receive(req),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=trace_id,
                        organization_id=context.organization_id,
                        task_id=context.task_id,
                        agent_run_id=history.run_id,
                        event_type=EventType.EXTERNAL_AGENT_TIMEOUT,
                        summary=f"External agent '{self.definition.id}' timed out after {self.timeout}s.",
                        payload={"agent_id": self.definition.id, "turn_index": req.current_turn},
                    )
                )
            return AgentStepFailure(
                error_message=f"External agent '{self.definition.id}' timed out after {self.timeout} seconds.",
                recoverable=True,
            )
        except Exception as exc:
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=trace_id,
                        organization_id=context.organization_id,
                        task_id=context.task_id,
                        agent_run_id=history.run_id,
                        event_type=EventType.EXTERNAL_AGENT_REJECTED,
                        summary=f"External agent '{self.definition.id}' threw an unhandled exception.",
                        payload={"agent_id": self.definition.id, "error": str(exc)},
                    )
                )
            return AgentStepFailure(
                error_message=f"External agent transport failure: {str(exc)}",
                recoverable=False,
            )

        # 7. Strict Fail-Closed Validation
        if raw_response is None:
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=trace_id,
                        organization_id=context.organization_id,
                        task_id=context.task_id,
                        agent_run_id=history.run_id,
                        event_type=EventType.EXTERNAL_AGENT_REJECTED,
                        summary="External agent returned null response.",
                        payload={"agent_id": self.definition.id},
                    )
                )
            return AgentStepFailure(
                error_message="External agent returned null response.",
                recoverable=False,
            )

        if not isinstance(raw_response, ExternalAgentResponse):
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=trace_id,
                        organization_id=context.organization_id,
                        task_id=context.task_id,
                        agent_run_id=history.run_id,
                        event_type=EventType.EXTERNAL_AGENT_REJECTED,
                        summary=f"Invalid response type from external agent: {type(raw_response).__name__}",
                        payload={"agent_id": self.definition.id},
                    )
                )
            return AgentStepFailure(
                error_message=f"Expected ExternalAgentResponse, received {type(raw_response).__name__}.",
                recoverable=False,
            )

        # 8. Detect Attempted Privilege Escalation
        payload_keys = set(raw_response.output_payload.keys()) if raw_response.output_payload else set()
        escalation_detected = payload_keys.intersection(PRIVILEGE_ESCALATION_KEYS)

        if escalation_detected:
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=trace_id,
                        organization_id=context.organization_id,
                        task_id=context.task_id,
                        agent_run_id=history.run_id,
                        event_type=EventType.SECURITY_VIOLATION,
                        summary="Attempted privilege escalation in external agent response: forged authority fields detected.",
                        payload={
                            "agent_id": self.definition.id,
                            "forged_fields": sorted(list(escalation_detected)),
                        },
                    )
                )
            # Strip authority fields from output_payload so they cannot leak into runtime state
            clean_output = {k: v for k, v in raw_response.output_payload.items() if k not in PRIVILEGE_ESCALATION_KEYS}
        else:
            clean_output = dict(raw_response.output_payload) if raw_response.output_payload else {}

        # 9. Record Successful Response Telemetry
        proposal_name = raw_response.tool_proposal.tool_name if raw_response.tool_proposal else None
        if self.event_sink:
            await self.event_sink.record(
                Event(
                    trace_id=trace_id,
                    organization_id=context.organization_id,
                    task_id=context.task_id,
                    agent_run_id=history.run_id,
                    event_type=EventType.EXTERNAL_AGENT_RESPONDED,
                    summary=f"External agent '{self.definition.id}' responded with {raw_response.response_type.value}.",
                    payload={
                        "agent_id": self.definition.id,
                        "turn_index": req.current_turn,
                        "response_type": raw_response.response_type.value,
                        "tool_proposal": proposal_name,
                    },
                )
            )

        # 10. Map Response Type to Runtime AgentStepResult
        if raw_response.response_type == ExternalAgentResponseType.TOOL_PROPOSAL:
            if not raw_response.tool_proposal:
                return AgentStepFailure(
                    error_message="Malformed response: response_type is TOOL_PROPOSAL but tool_proposal is missing.",
                    recoverable=False,
                )

            proposal = raw_response.tool_proposal
            return AgentStepToolRequest(
                thought=None,  # Do not emit private thought
                request=ToolRequest(
                    tool_name=proposal.tool_name,
                    arguments=proposal.arguments,
                    rationale=proposal.rationale or raw_response.rationale or f"External agent proposed {proposal.tool_name}",
                ),
            )

        elif raw_response.response_type == ExternalAgentResponseType.COMPLETE:
            return AgentStepComplete(
                thought=None,
                summary=raw_response.completion_summary or raw_response.rationale or "Task completed by external agent.",
                output_payload=clean_output,
            )

        elif raw_response.response_type == ExternalAgentResponseType.FAILURE:
            return AgentStepFailure(
                thought=None,
                error_message=raw_response.error_message or "External agent reported failure.",
                recoverable=False,
            )

        return AgentStepFailure(
            error_message=f"Unsupported external agent response type: {raw_response.response_type}",
            recoverable=False,
        )
