"""Section 26 & 23: Full runtime-only persistent E2E integration test.

Exercises:
Task -> AgentRun -> ToolRequest -> Policy -> Approval -> ToolExecution ->
Observation -> Verification -> TaskCompleted.
Then:
1. Close the runtime.
2. Reopen against the exact same SQLite database.
3. Verify persisted state and audit trail.
4. Verify no duplicate side-effect occurred.
5. Verify completely independent of covenant.db.
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from agent_runtime.core.authorization.matrix import ToolPermissionMatrix
from agent_runtime.core.contracts.agent import (
    AgentDefinition,
    AgentRunHistory,
    AgentStepComplete,
    AgentStepToolRequest,
)
from agent_runtime.core.contracts.context import Task, TaskContext, TaskScope
from agent_runtime.core.contracts.event import Event, EventType
from agent_runtime.core.contracts.tool import ToolRequest, ToolSpec
from agent_runtime.core.contracts.verification import Evidence, VerificationRequest, VerificationResult
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.registry import AgentRegistry, ToolRegistry
from agent_runtime.core.engine.router import DeterministicTaskRouter
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.interfaces.agent import IAgent
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.interfaces.verification import IVerifier
from agent_runtime.core.persistence.agent_run_repo import SQLiteAgentRunRepository
from agent_runtime.core.persistence.approval_repo import SQLiteApprovalRepository
from agent_runtime.core.persistence.connection import DatabaseManager
from agent_runtime.core.persistence.idempotency_store import SQLiteIdempotencyStore
from agent_runtime.core.persistence.task_repo import SQLiteTaskRepository
from agent_runtime.core.persistence.tool_exec_repo import SQLiteToolExecutionRepository
from agent_runtime.core.policy.engine import DefaultPolicyEngine
from agent_runtime.core.state.enums import ApprovalState, TaskState
from agent_runtime.core.telemetry.sqlite_sink import SQLiteEventSink
from agent_runtime.core.verification.gate import VerificationGate


class PersistentReadTool(ITool):
    spec = ToolSpec(
        name="inspect_storage_quota",
        description="Reads current disk usage",
        parameters_schema={"type": "object", "required": ["volume"]},
        has_side_effects=False,
    )

    async def execute(self, volume: str, **kwargs):
        return {"volume": volume, "used_gb": 480, "total_gb": 500}


class PersistentMutatingTool(ITool):
    spec = ToolSpec(
        name="expand_volume_quota",
        description="Expands disk storage volume",
        parameters_schema={"type": "object", "required": ["volume", "additional_gb"]},
        has_side_effects=True,
        is_idempotent=True,
    )

    def __init__(self):
        self.invocation_count = 0

    async def execute(self, volume: str, additional_gb: int, **kwargs):
        self.invocation_count += 1
        return {"volume": volume, "new_total_gb": 500 + additional_gb, "invocation_count": self.invocation_count}


class PersistentLifecycleAgent(IAgent):
    definition = AgentDefinition(
        id="persistent_ops_agent",
        name="Persistent Ops Agent",
        supported_roles=["role_storage_admin"],
    )

    async def step(self, context: TaskContext, history: AgentRunHistory):
        # Turn 1: Read storage quota
        if history.turn_count == 0:
            return AgentStepToolRequest(
                thought="Checking current volume usage.",
                request=ToolRequest(tool_name="inspect_storage_quota", arguments={"volume": "data_vol_01"}),
            )
        # Turn 2: Expand volume quota (mutating)
        elif history.turn_count == 1:
            return AgentStepToolRequest(
                thought="Volume is 96% full. Requesting quota expansion.",
                request=ToolRequest(tool_name="expand_volume_quota", arguments={"volume": "data_vol_01", "additional_gb": 500}),
            )
        # Turn 3: Conclude reasoning
        else:
            return AgentStepComplete(
                thought="Storage expansion finished and verified.",
                summary="Expanded data_vol_01 by 500GB with admin sign-off.",
                output_payload={"status": "EXPANDED", "additional_gb": 500},
            )


class StorageHealthVerifier(IVerifier):
    async def verify(self, request: VerificationRequest, context):
        ev = Evidence(
            source_type="SYSTEM_DF",
            source_id="df -h /data",
            summary="Filesystem reports 1000GB available",
            collected_by="StorageVerifier",
        )
        return VerificationResult(
            task_id=request.task_id,
            verified=True,
            rationale="Filesystem size corroborated at 1000GB.",
            evidence=[ev],
            verified_by="StorageVerifier",
        )


@pytest.mark.asyncio
async def test_full_persistent_runtime_lifecycle_and_restart(tmp_path):
    """
    1. Runs full lifecycle with real SQLite file.
    2. Persists Task, AgentRun, ToolExecution, Approval, Idempotency, and Events.
    3. Closes runtime connection.
    4. Reopens against same SQLite file and verifies all data survived restart.
    5. Verifies covenant.db is not touched or needed.
    """
    db_path = str(tmp_path / "durable_agent_runtime.sqlite")

    # ========================== PHASE 1: INITIAL RUNTIME RUN ==========================
    db_mgr = DatabaseManager(db_path)
    task_repo = SQLiteTaskRepository(db_mgr)
    run_repo = SQLiteAgentRunRepository(db_mgr)
    tool_repo = SQLiteToolExecutionRepository(db_mgr)
    approval_repo = SQLiteApprovalRepository(db_mgr)
    idempotency = SQLiteIdempotencyStore(db_mgr)
    event_sink = SQLiteEventSink(db_mgr)

    read_tool = PersistentReadTool()
    mutating_tool = PersistentMutatingTool()

    tools = ToolRegistry()
    tools.register(read_tool)
    tools.register(mutating_tool)

    agent = PersistentLifecycleAgent()
    agents = AgentRegistry()
    agents.register(agent)

    perms = ToolPermissionMatrix()
    perms.grant("org_cloud", "persistent_ops_agent", ["inspect_storage_quota", "expand_volume_quota"])

    policy = DefaultPolicyEngine()
    router = DeterministicTaskRouter()
    engine = ExecutionEngine(
        tool_registry=tools,
        permissions=perms,
        policy_engine=policy,
        event_sink=event_sink,
        idempotency_store=idempotency,
        tool_execution_repo=tool_repo,
        approval_repo=approval_repo,
    )
    run_executor = AgentRunExecutor(engine, event_sink, agent_run_repo=run_repo)
    verif_gate = VerificationGate(event_sink)

    # 1. Create and Persist Task
    task = Task(
        id="tsk_persist_01",
        organization_id="org_cloud",
        intent="Remediate low storage on data_vol_01",
        required_role="role_storage_admin",
        requires_verification=True,
    )
    await task_repo.create(task)
    await event_sink.record(
        Event(
            trace_id=f"trc_{task.id}",
            organization_id=task.organization_id,
            task_id=task.id,
            event_type=EventType.TASK_CREATED,
            summary="Task created",
        )
    )

    # 2. Atomic Claim
    claimed = await task_repo.atomic_claim(task.id, "persistent_ops_agent")
    assert claimed is True
    task = await task_repo.get(task.id)
    assert task.status == TaskState.ROUTED

    # 3. Transition to RUNNING & Start Run
    await task_repo.atomic_transition(task.id, TaskState.ROUTED, TaskState.RUNNING)
    task = await task_repo.get(task.id)

    context = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=task.scope,
        available_tools=tools.list_specs(),
        max_turns=5,
    )

    # Phase 1: Executes until Approval Blocks
    run, history, approval_req = await run_executor.execute_run(task, agent, context)
    assert approval_req is not None
    assert approval_req.status == ApprovalState.PENDING

    # Verify task transitions to BLOCKED
    await task_repo.atomic_transition(task.id, TaskState.RUNNING, TaskState.BLOCKED)

    # Human approves via approval repo
    approved = await approval_repo.atomic_approve(
        approval_req.approval_id,
        reviewed_by="StorageDirector",
        modified_arguments={"volume": "data_vol_01", "additional_gb": 500},
        notes="Approved for production maintenance window.",
    )
    assert approved is True
    approval_req = await approval_repo.get(approval_req.approval_id)
    assert approval_req.status == ApprovalState.APPROVED

    # Resume turn loop
    await task_repo.atomic_transition(task.id, TaskState.BLOCKED, TaskState.RUNNING)
    task = await task_repo.get(task.id)

    run2, history2, _ = await run_executor.execute_run(
        task=task,
        agent=agent,
        context=context,
        run=run,
        history=history,
        approval_resume=approval_req,
    )
    assert run2.status.value == "COMPLETED"

    # Verification Gate
    await task_repo.atomic_transition(task.id, TaskState.RUNNING, TaskState.VERIFYING)
    task = await task_repo.get(task.id)

    v_res = await verif_gate.verify_task(
        task=task,
        verifier=StorageHealthVerifier(),
        expected_outcome="Storage confirmed expanded to 1000GB",
    )
    assert v_res.verified is True

    # Complete Task
    await task_repo.atomic_transition(task.id, TaskState.VERIFYING, TaskState.COMPLETED)
    await event_sink.record(
        Event(
            trace_id=f"trc_{task.id}",
            organization_id=task.organization_id,
            task_id=task.id,
            event_type=EventType.TASK_COMPLETED,
            summary="Task completed successfully",
        )
    )

    # Close the database manager (simulates process exit)
    db_mgr.close()

    # ========================== PHASE 2: RESTART & RE-INSPECTION ==========================
    # Process 2 opens the exact same SQLite database file
    db_mgr2 = DatabaseManager(db_path)
    task_repo2 = SQLiteTaskRepository(db_mgr2)
    run_repo2 = SQLiteAgentRunRepository(db_mgr2)
    tool_repo2 = SQLiteToolExecutionRepository(db_mgr2)
    approval_repo2 = SQLiteApprovalRepository(db_mgr2)
    idempotency2 = SQLiteIdempotencyStore(db_mgr2)
    event_sink2 = SQLiteEventSink(db_mgr2)

    # 1. Inspect Task state
    persisted_task = await task_repo2.get("tsk_persist_01")
    assert persisted_task is not None
    assert persisted_task.status == TaskState.COMPLETED
    assert persisted_task.assigned_agent_id == "persistent_ops_agent"

    # 2. Inspect AgentRun state
    persisted_runs = await run_repo2.list_by_task("tsk_persist_01")
    assert len(persisted_runs) == 1
    assert persisted_runs[0].status.value == "COMPLETED"
    assert persisted_runs[0].output_payload["status"] == "EXPANDED"

    # 3. Inspect ToolExecutions
    persisted_execs = await tool_repo2.list_by_task("tsk_persist_01")
    assert len(persisted_execs) == 2  # inspect_storage_quota and expand_volume_quota
    assert all(e.status.value == "SUCCEEDED" for e in persisted_execs)

    # 4. Inspect HumanApproval
    persisted_appr = await approval_repo2.get(approval_req.approval_id)
    assert persisted_appr is not None
    assert persisted_appr.status == ApprovalState.EXECUTED  # Single-use consumed!
    assert persisted_appr.reviewed_by == "StorageDirector"

    # 5. Inspect Idempotency Cache after restart
    idemp_key = idempotency2.compute_key(
        "tsk_persist_01",
        run.id,
        "expand_volume_quota",
        {"volume": "data_vol_01", "additional_gb": 500},
        is_tool_idempotent=True,
    )
    cached_obs = await idempotency2.get(idemp_key)
    assert cached_obs is not None
    assert cached_obs.data["new_total_gb"] == 1000

    # 6. Replay protection check: mutator tool invocation count must still be 1!
    assert mutating_tool.invocation_count == 1

    # 7. Inspect Event Audit Stream after restart
    persisted_events = await event_sink2.list_events(task_id="tsk_persist_01")
    assert len(persisted_events) >= 6
    evt_types = [e.event_type for e in persisted_events]
    assert EventType.TASK_CREATED in evt_types
    assert EventType.APPROVAL_REQUESTED in evt_types
    assert EventType.APPROVAL_DECIDED in evt_types
    assert EventType.TOOL_EXECUTION_COMPLETED in evt_types
    assert EventType.TASK_COMPLETED in evt_types

    # Section 25: Verify covenant.db was not created or touched in tmp_path
    assert not (tmp_path / "covenant.db").exists()
    assert Path(db_path).exists()

    db_mgr2.close()
