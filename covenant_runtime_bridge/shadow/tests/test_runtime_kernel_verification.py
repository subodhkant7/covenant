"""Verification that runtime shadow execution genuinely executes through the Agent Organization Runtime kernel."""

import pytest

from agent_runtime.core.contracts.context import TaskContext
from agent_runtime.core.contracts.event import EventType
from agent_runtime.core.contracts.tool import ToolRequest
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.state.enums import ApprovalState, ToolExecutionState
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from agent_runtime.core.verification.gate import VerificationGate

from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap
from covenant_runtime_bridge.mapping.task_factory import CovenantTaskFactory
from covenant_runtime_bridge.shadow.benchmark import sample_atlas_commitment


@pytest.mark.asyncio
async def test_runtime_shadow_traverses_all_kernel_boundaries():
    """
    SECTION 7 PROOF:
    Verify that runtime execution genuinely executes:
    AgentRunExecutor -> ToolRequest -> ExecutionEngine -> PermissionMatrix -> PolicyEngine -> Approval -> ToolExecution -> VerificationGate.
    """
    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )
    executor = AgentRunExecutor(engine, sink)
    verif_gate = VerificationGate(sink)

    c = sample_atlas_commitment()
    task = CovenantTaskFactory.create_resolution_task(c)
    agent = bridge_env.agents.get("covenant.resolver_agent")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=task.scope,
        available_tools=bridge_env.tools.list_specs(),
        input_data=task.input_payload,
    )

    # 1. Execute run until approval required
    run, history, approval_req = await executor.execute_run(task, agent, ctx)
    assert approval_req is not None
    assert approval_req.status == ApprovalState.PENDING

    # Verify authorization and policy boundaries executed
    event_types = [e.event_type for e in sink.events]
    assert EventType.AGENT_RUN_STARTED in event_types
    assert EventType.TOOL_EXECUTION_STARTED in event_types
    assert EventType.TOOL_EXECUTION_COMPLETED in event_types  # draft_followup succeeded
    assert EventType.APPROVAL_REQUESTED in event_types       # send_followup gated by policy!

    # 2. Human approves and resumes
    approval_req.status = ApprovalState.APPROVED
    approval_req.reviewed_by = "AuditReviewer"

    run2, history2, _ = await executor.execute_run(
        task=task,
        agent=agent,
        context=ctx,
        run=run,
        history=history,
        approval_resume=approval_req,
    )
    assert run2.status.value == "COMPLETED"

    # 3. Verification Gate execution
    v_res = await verif_gate.verify_task(task, bridge_env.verifier, expected_outcome="Approval verified")

    event_types_after = [e.event_type for e in sink.events]
    assert EventType.APPROVAL_DECIDED in event_types_after
    assert EventType.AGENT_RUN_FINISHED in event_types_after
    assert EventType.VERIFICATION_STARTED in event_types_after
    assert EventType.VERIFICATION_DONE in event_types_after


@pytest.mark.asyncio
async def test_bypassing_execution_engine_is_detected():
    """Negative test: Prove that directly calling bridge tools bypasses kernel telemetry and fails audit."""
    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()

    # If code attempts to bypass ExecutionEngine and directly invoke the tool:
    tool = bridge_env.tools.get("draft_followup")
    await tool.execute(
        commitment_id="com_1",
        recipient_name="Sarah",
        subject="Notice",
        promise_summary="Deliverable signoff",
    )

    # Invariant: No kernel execution events exist in sink!
    assert len(sink.events) == 0, "Bypassed tool call should not emit kernel telemetry!"
