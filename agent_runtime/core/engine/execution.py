"""ExecutionEngine: The single source of execution authority in the runtime."""

import datetime
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from agent_runtime.core.authorization.matrix import ToolPermissionMatrix
from agent_runtime.core.contracts.agent import AgentRun
from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.event import Event, EventType
from agent_runtime.core.contracts.policy import PolicyEvaluationContext
from agent_runtime.core.contracts.tool import Observation, ToolExecution, ToolRequest
from agent_runtime.core.engine.idempotency import IdempotencyStore
from agent_runtime.core.engine.registry import ToolRegistry
from agent_runtime.core.engine.sanitizer import ObservationSanitizer
from agent_runtime.core.interfaces.policy import IPolicyEngine
from agent_runtime.core.interfaces.telemetry import IEventSink
from agent_runtime.core.persistence.interfaces import (
    IApprovalRepository,
    IIdempotencyStore,
    IToolExecutionRepository,
)
from agent_runtime.core.state.enums import ApprovalState, IdempotencyStatus, PolicyDecisionType, ToolExecutionState
from agent_runtime.core.state.machine import approval_validator


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class ExecutionEngine:
    """
    Authoritative runtime execution engine.
    Ensures that an agent can NEVER invoke a tool directly or bypass policies.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        permissions: ToolPermissionMatrix,
        policy_engine: IPolicyEngine,
        event_sink: IEventSink,
        idempotency_store: Optional[Any] = None,
        sanitizer: Optional[ObservationSanitizer] = None,
        tool_execution_repo: Optional[IToolExecutionRepository] = None,
        approval_repo: Optional[IApprovalRepository] = None,
    ):
        self.tools = tool_registry
        self.permissions = permissions
        self.policy_engine = policy_engine
        self.event_sink = event_sink
        self.idempotency = idempotency_store or IdempotencyStore()
        self.sanitizer = sanitizer or ObservationSanitizer()
        self.tool_repo = tool_execution_repo
        self.approval_repo = approval_repo

    async def handle_tool_request(
        self,
        task: Task,
        run: AgentRun,
        request: ToolRequest,
        approval: Optional[HumanApprovalRequest] = None,
        trace_id: Optional[str] = None,
    ) -> Tuple[Observation, Optional[HumanApprovalRequest]]:
        """
        Executes the canonical runtime tool evaluation and execution protocol.
        Guarantees:
        1. Approval is NOT consumed until modified arguments, schema, policy, and permissions are validated.
        2. Atomic idempotency reservation prevents duplicate concurrent runs.
        3. All persisted arguments, results, and event payloads are sanitized.
        """
        tid = trace_id or task.workflow_run_id or f"trc_{task.id}"

        # 1. Sanitize request arguments for events and audit
        clean_args = self.sanitizer.sanitize_arguments(request.arguments)
        await self.event_sink.record(
            Event(
                trace_id=tid,
                organization_id=task.organization_id,
                task_id=task.id,
                agent_run_id=run.id,
                event_type=EventType.TOOL_REQUESTED,
                summary=f"Agent '{run.agent_id}' requested tool '{request.tool_name}'.",
                payload={"arguments": clean_args, "rationale": request.rationale},
            )
        )

        # 2. Resolve Tool
        tool = self.tools.get(request.tool_name)
        if not tool:
            obs = Observation(
                execution_id="none",
                tool_name=request.tool_name,
                success=False,
                data=None,
                error=f"Tool '{request.tool_name}' is not registered.",
            )
            return obs, None

        # 3. Handle Human Approval Flow vs Standard Flow
        effective_arguments = dict(request.arguments)
        schema = tool.spec.parameters_schema or {}
        required_props = schema.get("required", [])

        if approval:
            # Replay protection check
            if approval.status != ApprovalState.APPROVED:
                obs = Observation(
                    execution_id="none",
                    tool_name=request.tool_name,
                    success=False,
                    data=None,
                    error=f"Approval request '{approval.approval_id}' is in state '{approval.status}', not APPROVED.",
                )
                return obs, None

            # Apply human modifications
            if approval.modified_arguments:
                effective_arguments = dict(approval.modified_arguments)

            # Validate effective arguments against ToolSpec parameters_schema
            missing_mod = [p for p in required_props if p not in effective_arguments]
            if missing_mod:
                obs = Observation(
                    execution_id="none",
                    tool_name=request.tool_name,
                    success=False,
                    data=None,
                    error=f"Modified arguments invalid. Missing required fields: {missing_mod}",
                )
                return obs, None  # Approval remains APPROVED; NOT consumed

            # Re-evaluate Policy against modified arguments
            policy_ctx = PolicyEvaluationContext(
                organization_id=task.organization_id,
                task_id=task.id,
                agent_run_id=run.id,
                agent_id=run.agent_id,
                role_id=task.required_role,
                tool_spec=tool.spec,
                tool_request=ToolRequest(
                    request_id=request.request_id,
                    tool_name=request.tool_name,
                    arguments=effective_arguments,
                ),
                task_scope=task.scope,
            )
            re_decision = self.policy_engine.evaluate(policy_ctx)
            if re_decision.decision == PolicyDecisionType.DENY:
                obs = Observation(
                    execution_id="none",
                    tool_name=request.tool_name,
                    success=False,
                    data=None,
                    error=f"Policy denied modified arguments: {re_decision.rationale}",
                )
                return obs, None  # Approval remains APPROVED; NOT consumed

            # Verify permissions
            if not self.permissions.is_authorized(task.organization_id, run.agent_id, request.tool_name):
                obs = Observation(
                    execution_id="none",
                    tool_name=request.tool_name,
                    success=False,
                    data=None,
                    error=f"Permission denied: Agent '{run.agent_id}' is not authorized for '{request.tool_name}'.",
                )
                return obs, None  # Approval remains APPROVED; NOT consumed

            # ALL CHECKS PASSED: Atomically consume approval
            if self.approval_repo:
                consumed = await self.approval_repo.atomic_consume(approval.approval_id)
                if not consumed:
                    obs = Observation(
                        execution_id="none",
                        tool_name=request.tool_name,
                        success=False,
                        data=None,
                        error=f"Approval request '{approval.approval_id}' was already consumed by another worker.",
                    )
                    return obs, None
            else:
                approval_validator.validate_transition(approval.status, ApprovalState.EXECUTED, reason="Action dispatched")
            approval.status = ApprovalState.EXECUTED

            clean_mod = self.sanitizer.sanitize_arguments(approval.modified_arguments or {})
            await self.event_sink.record(
                Event(
                    trace_id=tid,
                    organization_id=task.organization_id,
                    task_id=task.id,
                    agent_run_id=run.id,
                    event_type=EventType.APPROVAL_DECIDED,
                    summary=f"Human approval executed by '{approval.reviewed_by}' for tool '{request.tool_name}'.",
                    payload={"modified_arguments": clean_mod},
                )
            )

        else:
            # Validate Schema for standard request
            missing = [p for p in required_props if p not in request.arguments]
            if missing:
                obs = Observation(
                    execution_id="none",
                    tool_name=request.tool_name,
                    success=False,
                    data=None,
                    error=f"Invalid arguments for tool '{request.tool_name}'. Missing required fields: {missing}",
                )
                return obs, None

            # Validate Permissions
            if not self.permissions.is_authorized(task.organization_id, run.agent_id, request.tool_name):
                await self.event_sink.record(
                    Event(
                        trace_id=tid,
                        organization_id=task.organization_id,
                        task_id=task.id,
                        agent_run_id=run.id,
                        event_type=EventType.SECURITY_VIOLATION,
                        summary=f"Unauthorized tool invocation attempted: '{request.tool_name}'.",
                        payload={"agent_id": run.agent_id, "tool_name": request.tool_name},
                    )
                )
                obs = Observation(
                    execution_id="none",
                    tool_name=request.tool_name,
                    success=False,
                    data=None,
                    error=f"Permission denied: Agent '{run.agent_id}' is not authorized to invoke '{request.tool_name}'.",
                )
                return obs, None

            # Evaluate Policy
            policy_ctx = PolicyEvaluationContext(
                organization_id=task.organization_id,
                task_id=task.id,
                agent_run_id=run.id,
                agent_id=run.agent_id,
                role_id=task.required_role,
                tool_spec=tool.spec,
                tool_request=request,
                task_scope=task.scope,
            )
            decision = self.policy_engine.evaluate(policy_ctx)
            await self.event_sink.record(
                Event(
                    trace_id=tid,
                    organization_id=task.organization_id,
                    task_id=task.id,
                    agent_run_id=run.id,
                    event_type=EventType.POLICY_EVALUATED,
                    summary=f"Policy decision for '{request.tool_name}': {decision.decision.value}.",
                    payload={"rationale": decision.rationale, "rules": decision.rules_triggered},
                )
            )

            if decision.decision == PolicyDecisionType.DENY:
                obs = Observation(
                    execution_id="none",
                    tool_name=request.tool_name,
                    success=False,
                    data=None,
                    error=f"Policy denied execution of '{request.tool_name}': {decision.rationale}",
                )
                return obs, None

            if decision.decision == PolicyDecisionType.REQUIRE_HUMAN_APPROVAL:
                # Sanitize arguments before creating approval record
                sanitized_req = ToolRequest(
                    request_id=request.request_id,
                    tool_name=request.tool_name,
                    arguments=self.sanitizer.sanitize_arguments(request.arguments),
                    rationale=request.rationale,
                )
                approval_req = HumanApprovalRequest(
                    organization_id=task.organization_id,
                    task_id=task.id,
                    agent_run_id=run.id,
                    tool_request=sanitized_req,
                    policy_decision_id=decision.decision_id,
                    status=ApprovalState.PENDING,
                )
                if self.approval_repo:
                    await self.approval_repo.create(approval_req)

                await self.event_sink.record(
                    Event(
                        trace_id=tid,
                        organization_id=task.organization_id,
                        task_id=task.id,
                        agent_run_id=run.id,
                        event_type=EventType.APPROVAL_REQUESTED,
                        summary=f"Human approval required for tool '{request.tool_name}'.",
                        payload={"approval_id": approval_req.approval_id, "rationale": decision.rationale},
                    )
                )
                pending_obs = Observation(
                    execution_id="pending_approval",
                    tool_name=request.tool_name,
                    success=False,
                    data=None,
                    error=f"Action requires human approval. Created request '{approval_req.approval_id}'.",
                )
                return pending_obs, approval_req

        # 4. Atomic Idempotency Reservation
        idemp_key = self.idempotency.compute_key(
            task_id=task.id,
            agent_run_id=run.id,
            tool_name=request.tool_name,
            arguments=effective_arguments,
            is_tool_idempotent=tool.spec.is_idempotent,
        )

        execution_id = f"exec_{uuid4().hex[:8]}"

        if hasattr(self.idempotency, "reserve_or_get"):
            reservation = await self.idempotency.reserve_or_get(
                key=idemp_key,
                tool_name=request.tool_name,
                execution_id=execution_id,
            )
            if reservation.status == IdempotencyStatus.CACHED and reservation.cached_observation:
                return reservation.cached_observation, None
            elif reservation.status == IdempotencyStatus.CONCURRENT_RUN:
                obs = Observation(
                    execution_id="none",
                    tool_name=request.tool_name,
                    success=False,
                    data=None,
                    error=reservation.error or "Concurrent execution in progress for this request.",
                )
                return obs, None
            elif reservation.status == IdempotencyStatus.UNKNOWN:
                obs = Observation(
                    execution_id="none",
                    tool_name=request.tool_name,
                    success=False,
                    data=None,
                    error=reservation.error or "Prior execution outcome was ambiguous. Replay blocked.",
                )
                return obs, None
        else:
            cached_obs = self.idempotency.get(idemp_key)
            if cached_obs:
                return cached_obs, None

        # 5. Persist ToolExecution in RUNNING state (with sanitized arguments)
        sanitized_exec_args = self.sanitizer.sanitize_arguments(effective_arguments)
        execution = ToolExecution(
            id=execution_id,
            agent_run_id=run.id,
            task_id=task.id,
            tool_name=request.tool_name,
            arguments=sanitized_exec_args,
            status=ToolExecutionState.RUNNING,
            idempotency_key=idemp_key,
        )
        if self.tool_repo:
            await self.tool_repo.create(execution)

        await self.event_sink.record(
            Event(
                trace_id=tid,
                organization_id=task.organization_id,
                task_id=task.id,
                agent_run_id=run.id,
                execution_id=execution.id,
                event_type=EventType.TOOL_EXECUTION_STARTED,
                summary=f"Executing tool '{request.tool_name}'.",
                payload={"execution_id": execution.id},
            )
        )

        # 6. Execute Real Tool Code
        try:
            raw_result = await tool.execute(**effective_arguments)
            execution.status = ToolExecutionState.SUCCEEDED
            # Store sanitized result in ToolExecution persistence
            execution.result = self.sanitizer.sanitize_payload(raw_result)
            execution.completed_at = utc_now()
            observation = self.sanitizer.sanitize(
                raw_result=raw_result,
                tool_name=request.tool_name,
                execution_id=execution.id,
            )

            # Record success in idempotency store
            if hasattr(self.idempotency, "mark_succeeded"):
                await self.idempotency.mark_succeeded(idemp_key, execution.id, observation)
            elif tool.spec.is_idempotent:
                self.idempotency.set(idemp_key, observation)

        except Exception as e:
            execution.status = ToolExecutionState.FAILED
            clean_err = self.sanitizer.redact_text(str(e))
            execution.error = clean_err
            execution.completed_at = utc_now()
            observation = self.sanitizer.sanitize(
                raw_result=None,
                tool_name=request.tool_name,
                execution_id=execution.id,
                is_error=True,
                error_message=clean_err,
            )
            if hasattr(self.idempotency, "mark_failed"):
                await self.idempotency.mark_failed(idemp_key, execution.id, observation)

        if self.tool_repo:
            await self.tool_repo.update(execution)

        await self.event_sink.record(
            Event(
                trace_id=tid,
                organization_id=task.organization_id,
                task_id=task.id,
                agent_run_id=run.id,
                execution_id=execution.id,
                event_type=EventType.TOOL_EXECUTION_COMPLETED,
                summary=f"Tool '{request.tool_name}' completed with status '{execution.status.value}'.",
                payload={"status": execution.status.value, "success": observation.success},
            )
        )
        await self.event_sink.record(
            Event(
                trace_id=tid,
                organization_id=task.organization_id,
                task_id=task.id,
                agent_run_id=run.id,
                execution_id=execution.id,
                event_type=EventType.OBSERVATION_EMITTED,
                summary=f"Delivered observation for '{request.tool_name}'.",
                payload={"truncated": observation.truncated},
            )
        )

        return observation, None
