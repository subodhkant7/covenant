"""RuntimeCrashRecoveryService: Deterministic process restart recovery with UNKNOWN outcome safety."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.tool import ToolExecution, ToolSpec
from agent_runtime.core.engine.registry import ToolRegistry
from agent_runtime.core.persistence.interfaces import (
    IApprovalRepository,
    IAgentRunRepository,
    IIdempotencyStore,
    ITaskRepository,
    IToolExecutionRepository,
)
from agent_runtime.core.state.enums import (
    AgentRunState,
    ExecutionSafety,
    TaskState,
    ToolExecutionState,
)


@dataclass
class RecoveryReport:
    tasks_reset_to_pending: int
    tasks_blocked_for_unknown: int
    tasks_marked_failed: int
    runs_marked_interrupted: int
    tools_marked_unknown: int
    tools_marked_orphaned: int
    pending_approvals_preserved: int


class RuntimeCrashRecoveryService:
    """
    Scans persistent runtime state after an ungraceful shutdown or crash.
    Core Invariant:
    The runtime must never falsely assume that an interrupted external side effect definitely did not happen.
    """

    def __init__(
        self,
        task_repo: ITaskRepository,
        run_repo: IAgentRunRepository,
        tool_repo: IToolExecutionRepository,
        approval_repo: IApprovalRepository,
        idempotency_store: Optional[IIdempotencyStore] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        self.task_repo = task_repo
        self.run_repo = run_repo
        self.tool_repo = tool_repo
        self.approval_repo = approval_repo
        self.idempotency = idempotency_store
        self.tools = tool_registry

    async def recover(self) -> RecoveryReport:
        now = datetime.now(timezone.utc)
        report = RecoveryReport(
            tasks_reset_to_pending=0,
            tasks_blocked_for_unknown=0,
            tasks_marked_failed=0,
            runs_marked_interrupted=0,
            tools_marked_unknown=0,
            tools_marked_orphaned=0,
            pending_approvals_preserved=0,
        )

        tasks_with_unknown_tools: set[str] = set()

        # 1. Recover active ToolExecutions
        active_tools = await self.tool_repo.list_active()
        for tool_exec in active_tools:
            # Determine tool execution safety
            spec: Optional[ToolSpec] = None
            if self.tools:
                tool = self.tools.get(tool_exec.tool_name)
                spec = tool.spec if tool else None

            # Default to NON_IDEMPOTENT if spec unknown, to ensure safety
            is_non_idempotent = True
            if spec:
                is_non_idempotent = (spec.execution_safety == ExecutionSafety.NON_IDEMPOTENT)
            elif tool_exec.arguments.get("is_idempotent"):
                is_non_idempotent = False

            if is_non_idempotent:
                # Ambiguous external side effect: MUST NOT be marked failed or replayed blindly
                tool_exec.status = ToolExecutionState.UNKNOWN
                tool_exec.error = (
                    "AMBIGUOUS_EXTERNAL_EFFECT: Interrupted during non-idempotent execution. "
                    "Cannot verify whether external side effect occurred. Manual review or verification required."
                )
                tool_exec.completed_at = now
                await self.tool_repo.update(tool_exec)
                if self.idempotency and tool_exec.idempotency_key:
                    await self.idempotency.mark_unknown(tool_exec.idempotency_key, tool_exec.id, tool_exec.error)
                report.tools_marked_unknown += 1
                tasks_with_unknown_tools.add(tool_exec.task_id)
            else:
                # Read-only or idempotent tool: safe to mark interrupted
                tool_exec.status = ToolExecutionState.FAILED
                tool_exec.error = "ORPHANED_BY_PROCESS_CRASH: Safe to retry."
                tool_exec.completed_at = now
                await self.tool_repo.update(tool_exec)
                if self.idempotency and tool_exec.idempotency_key:
                    await self.idempotency.mark_failed(tool_exec.idempotency_key, tool_exec.id)
                report.tools_marked_orphaned += 1

        # 2. Recover active AgentRuns
        active_runs = await self.run_repo.list_active()
        for run in active_runs:
            run.status = AgentRunState.FAILED
            run.error = "INTERRUPTED_BY_PROCESS_CRASH: Agent reasoning loop terminated unexpectedly."
            run.completed_at = now
            await self.run_repo.update(run)
            report.runs_marked_interrupted += 1

        # 3. Recover transient Tasks (ROUTED, RUNNING, VERIFYING)
        interrupted_tasks = await self.task_repo.list_interrupted()
        for task in interrupted_tasks:
            if task.id in tasks_with_unknown_tools:
                # Ambiguous external effect occurred: Task is BLOCKED, not PENDING!
                task.status = TaskState.BLOCKED
                task.updated_at = now
                await self.task_repo.update(task)
                report.tasks_blocked_for_unknown += 1
            else:
                # Advance attempt counter to prevent infinite retry loops on recurring crash
                task.attempt_count += 1
                if task.attempt_count <= task.max_retries:
                    task.status = TaskState.PENDING
                    task.assigned_agent_id = None
                    task.updated_at = now
                    await self.task_repo.update(task)
                    report.tasks_reset_to_pending += 1
                else:
                    task.status = TaskState.FAILED
                    task.updated_at = now
                    await self.task_repo.update(task)
                    report.tasks_marked_failed += 1

        # 4. Check Pending Approvals
        pending_approvals = await self.approval_repo.list_pending()
        report.pending_approvals_preserved = len(pending_approvals)

        return report

    async def reconcile_unknown_execution(
        self,
        execution_id: str,
        verified_outcome: bool,
        rationale: str,
    ) -> ToolExecution:
        """
        Generic reconciliation mechanism for UNKNOWN tool executions.
        External verification or human intervention provides proof of whether
        the side-effect occurred.
        """
        now = datetime.now(timezone.utc)
        execution = await self.tool_repo.get(execution_id)
        if not execution:
            raise ValueError(f"Execution '{execution_id}' not found.")
        if execution.status != ToolExecutionState.UNKNOWN:
            raise ValueError(f"Execution '{execution_id}' is in status '{execution.status}', not UNKNOWN.")

        task = await self.task_repo.get(execution.task_id)

        if verified_outcome:
            # Corroborated: The external action did execute successfully!
            execution.status = ToolExecutionState.SUCCEEDED
            execution.result = {"reconciled": True, "rationale": rationale}
            execution.error = None
            execution.completed_at = now
            await self.tool_repo.update(execution)
            if task and task.status == TaskState.BLOCKED:
                task.status = TaskState.RUNNING
                await self.task_repo.update(task)
        else:
            # Corroborated: The external action did NOT execute
            execution.status = ToolExecutionState.FAILED
            execution.error = f"RECONCILED_AS_NOT_EXECUTED: {rationale}"
            execution.completed_at = now
            await self.tool_repo.update(execution)
            if task and task.status == TaskState.BLOCKED:
                task.status = TaskState.PENDING
                await self.task_repo.update(task)

        return execution
