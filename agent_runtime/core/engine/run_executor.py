"""AgentRunExecutor: Authoritative turn-taking reasoning loop coordinator."""

from typing import Optional, Tuple
from agent_runtime.core.contracts.agent import (
    AgentRun,
    AgentRunHistory,
    AgentStepComplete,
    AgentStepFailure,
    AgentStepToolRequest,
)
from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.context import Task, TaskContext
from agent_runtime.core.contracts.event import Event, EventType
from agent_runtime.core.engine.execution import ExecutionEngine, utc_now
from agent_runtime.core.interfaces.agent import IAgent
from agent_runtime.core.interfaces.telemetry import IEventSink
from agent_runtime.core.persistence.interfaces import IAgentRunRepository
from agent_runtime.core.state.enums import AgentRunState, TaskState
from agent_runtime.core.state.machine import agent_run_validator, task_validator


class AgentRunExecutor:
    """
    Coordinates an atomic AgentRun turn loop.
    The Agent NEVER owns this loop; the runtime kernel maintains complete control.
    """

    def __init__(
        self,
        execution_engine: ExecutionEngine,
        event_sink: IEventSink,
        agent_run_repo: Optional[IAgentRunRepository] = None,
    ):
        self.engine = execution_engine
        self.event_sink = event_sink
        self.run_repo = agent_run_repo

    async def execute_run(
        self,
        task: Task,
        agent: IAgent,
        context: TaskContext,
        run: Optional[AgentRun] = None,
        history: Optional[AgentRunHistory] = None,
        approval_resume: Optional[HumanApprovalRequest] = None,
    ) -> Tuple[AgentRun, AgentRunHistory, Optional[HumanApprovalRequest]]:
        """
        Executes an agent reasoning loop until completion, failure, timeout, or approval block.
        """
        trace_id = task.workflow_run_id or f"trc_{task.id}"

        # 1. Initialize Run and History if new
        if not run:
            run = AgentRun(
                task_id=task.id,
                agent_id=agent.definition.id,
                attempt_number=task.attempt_count + 1,
                status=AgentRunState.INITIALIZING,
            )
            agent_run_validator.validate_transition(run.status, AgentRunState.EXECUTING)
            run.status = AgentRunState.EXECUTING
            history = AgentRunHistory(run_id=run.id, task_id=task.id)

            # Persist AgentRun immediately so foreign keys can be referenced
            if self.run_repo:
                await self.run_repo.create(run)

            await self.event_sink.record(
                Event(
                    trace_id=trace_id,
                    organization_id=task.organization_id,
                    task_id=task.id,
                    agent_run_id=run.id,
                    event_type=EventType.AGENT_RUN_STARTED,
                    summary=f"Started AgentRun '{run.id}' for agent '{agent.definition.id}'.",
                    payload={"attempt": run.attempt_number},
                )
            )

        # 2. Handle Resume after Human Approval
        if approval_resume and run.status == AgentRunState.AWAITING_APPROVAL:
            run.status = AgentRunState.EXECUTING
            if self.run_repo:
                await self.run_repo.update(run)

            obs, _ = await self.engine.handle_tool_request(
                task=task,
                run=run,
                request=approval_resume.tool_request,
                approval=approval_resume,
                trace_id=trace_id,
            )
            history.append_turn(
                thought="Resumed after human authorization.",
                request=approval_resume.tool_request,
                observation=obs,
            )
            run.turn_count = history.turn_count

        # 3. Main Reasoning Turn Loop
        pending_approval: Optional[HumanApprovalRequest] = None

        while run.status == AgentRunState.EXECUTING:
            # Check turn limit
            if history.turn_count >= context.max_turns:
                agent_run_validator.validate_transition(run.status, AgentRunState.TIMED_OUT)
                run.status = AgentRunState.TIMED_OUT
                run.error = f"AgentRun exceeded max turns limit ({context.max_turns})."
                run.completed_at = utc_now()
                break

            # Check deadline
            if context.deadline and utc_now() > context.deadline:
                agent_run_validator.validate_transition(run.status, AgentRunState.TIMED_OUT)
                run.status = AgentRunState.TIMED_OUT
                run.error = "AgentRun exceeded task deadline."
                run.completed_at = utc_now()
                break

            # Invoke Agent turn
            try:
                step_result = await agent.step(context, history)
            except Exception as e:
                agent_run_validator.validate_transition(run.status, AgentRunState.FAILED)
                run.status = AgentRunState.FAILED
                run.error = f"Agent step crashed: {str(e)}"
                run.completed_at = utc_now()
                break

            # Process Step Result
            if isinstance(step_result, AgentStepToolRequest):
                obs, appr = await self.engine.handle_tool_request(
                    task=task,
                    run=run,
                    request=step_result.request,
                    trace_id=trace_id,
                )
                if appr:
                    # Record the pending tool turn in history and halt loop for approval
                    history.append_turn(
                        thought=step_result.thought,
                        request=step_result.request,
                        observation=obs,
                    )
                    run.turn_count = history.turn_count
                    agent_run_validator.validate_transition(run.status, AgentRunState.AWAITING_APPROVAL)
                    run.status = AgentRunState.AWAITING_APPROVAL
                    pending_approval = appr
                    if self.run_repo:
                        await self.run_repo.update(run)
                    break
                else:
                    history.append_turn(
                        thought=step_result.thought,
                        request=step_result.request,
                        observation=obs,
                    )
                    run.turn_count = history.turn_count
                    if obs.is_terminal_failure:
                        agent_run_validator.validate_transition(run.status, AgentRunState.FAILED)
                        run.status = AgentRunState.FAILED
                        run.error = obs.error
                        run.completed_at = utc_now()
                        break

            elif isinstance(step_result, AgentStepComplete):
                history.append_turn(thought=step_result.thought)
                agent_run_validator.validate_transition(run.status, AgentRunState.COMPLETED)
                run.status = AgentRunState.COMPLETED
                run.output_payload = step_result.output_payload
                run.completion_summary = step_result.summary
                run.completed_at = utc_now()
                run.turn_count = history.turn_count
                break

            elif isinstance(step_result, AgentStepFailure):
                history.append_turn(thought=step_result.thought)
                agent_run_validator.validate_transition(run.status, AgentRunState.FAILED)
                run.status = AgentRunState.FAILED
                run.error = step_result.error_message
                run.completed_at = utc_now()
                run.turn_count = history.turn_count
                break

            else:
                agent_run_validator.validate_transition(run.status, AgentRunState.FAILED)
                run.status = AgentRunState.FAILED
                run.error = f"Malformed AgentStepResult: {type(step_result)}"
                run.completed_at = utc_now()
                break

        if self.run_repo:
            await self.run_repo.update(run)

        await self.event_sink.record(
            Event(
                trace_id=trace_id,
                organization_id=task.organization_id,
                task_id=task.id,
                agent_run_id=run.id,
                event_type=EventType.AGENT_RUN_FINISHED,
                summary=f"AgentRun '{run.id}' finished with status '{run.status.value}'.",
                payload={"status": run.status.value, "turn_count": run.turn_count, "error": run.error},
            )
        )

        return run, history, pending_approval
