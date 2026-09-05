"""Section 34: Second-domain IT Helpdesk runtime integration test.

Validates that the SAME runtime kernel supports a completely different domain:
Diagnose server issue -> inspect logs -> restart daemon -> human approval ->
restart -> verify health -> completed.
"""

from datetime import datetime, timezone
import pytest

from agent_runtime.core.authorization.matrix import ToolPermissionMatrix
from agent_runtime.core.contracts.agent import (
    AgentDefinition,
    AgentRunHistory,
    AgentStepComplete,
    AgentStepToolRequest,
)
from agent_runtime.core.contracts.context import Task, TaskContext, TaskScope
from agent_runtime.core.contracts.tool import ToolRequest, ToolSpec
from agent_runtime.core.contracts.verification import Evidence, VerificationRequest, VerificationResult
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.registry import AgentRegistry, ToolRegistry
from agent_runtime.core.engine.router import DeterministicTaskRouter
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.interfaces.agent import IAgent
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.interfaces.verification import IVerifier
from agent_runtime.core.policy.engine import DefaultPolicyEngine
from agent_runtime.core.state.enums import ApprovalState, ScopeType, TaskState
from agent_runtime.core.state.machine import task_validator
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from agent_runtime.core.verification.gate import VerificationGate


# Domain Tools for IT Helpdesk
class InspectSyslogTool(ITool):
    spec = ToolSpec(
        name="inspect_syslog",
        description="Inspects system log lines",
        parameters_schema={"type": "object", "required": ["service"]},
        has_side_effects=False,
    )

    async def execute(self, service: str, **kwargs):
        return {"service": service, "errors_found": ["SIGSEGV in worker 4", "Out of memory"]}


class RestartDaemonTool(ITool):
    spec = ToolSpec(
        name="restart_daemon",
        description="Restarts a production daemon service",
        parameters_schema={"type": "object", "required": ["service", "force"]},
        has_side_effects=True,
        default_risk_level="HIGH",
    )

    async def execute(self, service: str, force: bool = False, **kwargs):
        return {"service": service, "restarted": True, "pid": 4819}


# Domain Agent for SRE Triage
class SREDiagnosticAgent(IAgent):
    definition = AgentDefinition(
        id="sre_triage_agent",
        name="SRE Triage Agent",
        supported_roles=["role_sre_diagnostician"],
    )

    async def step(self, context: TaskContext, history: AgentRunHistory):
        # Turn 1: Inspect logs
        if history.turn_count == 0:
            return AgentStepToolRequest(
                thought="Inspecting syslog for nginx failure reason.",
                request=ToolRequest(tool_name="inspect_syslog", arguments={"service": "nginx"}),
            )
        # Turn 2: Propose service restart
        elif history.turn_count == 1:
            return AgentStepToolRequest(
                thought="Memory leak detected in worker. Restart required.",
                request=ToolRequest(tool_name="restart_daemon", arguments={"service": "nginx", "force": True}),
            )
        # Turn 3: Complete reasoning
        else:
            return AgentStepComplete(
                thought="Nginx restarted successfully. Ready for health probe verification.",
                summary="Diagnosed OOM deadlock in nginx. Restarted service with SRE approval.",
                output_payload={"incident_status": "MITIGATED", "service": "nginx"},
            )


# Domain Verifier for Daemon Health Check
class DaemonHealthVerifier(IVerifier):
    async def verify(self, request: VerificationRequest, context):
        ev = Evidence(
            source_type="PROMETHEUS_METRICS",
            source_id="metric_http_probe_443",
            summary="HTTP 200 response with latency 24ms; 0 error rates over 30 seconds",
            collected_by="PrometheusProbe",
        )
        return VerificationResult(
            task_id=request.task_id,
            verified=True,
            rationale="Production payment daemon health check verified healthy.",
            evidence=[ev],
            verified_by="DaemonHealthVerifier",
        )


@pytest.mark.asyncio
async def test_it_helpdesk_domain_runtime_flow():
    """
    Demonstrates that the exact same runtime kernel manages an IT Helpdesk
    incident remediation workflow without any domain code inside the runtime.
    """
    tools = ToolRegistry()
    tools.register(InspectSyslogTool())
    tools.register(RestartDaemonTool())

    agents = AgentRegistry()
    agent = SREDiagnosticAgent()
    agents.register(agent)

    perms = ToolPermissionMatrix()
    perms.grant("org_enterprise", "sre_triage_agent", ["inspect_syslog", "restart_daemon"])

    policy = DefaultPolicyEngine()
    sink = InMemoryEventSink()
    router = DeterministicTaskRouter()
    engine = ExecutionEngine(tools, perms, policy, sink)
    run_executor = AgentRunExecutor(engine, sink)
    verif_gate = VerificationGate(sink)

    # 1. Incident Task Created
    task = Task(
        organization_id="org_enterprise",
        intent="Resolve 502 Bad Gateway on payment service",
        required_role="role_sre_diagnostician",
        scope=TaskScope(scope_type=ScopeType.ENTITY, entity_type="server_asset", entity_ids=["srv-pay-prod-01"]),
        requires_verification=True,
    )

    # 2. Route Task
    candidate = await router.route(task, agents)
    assert candidate.id == "sre_triage_agent"
    task_validator.validate_transition(task.status, TaskState.ROUTED)
    task.status = TaskState.ROUTED

    # 3. Agent Execution (Phase 1: Diagnosis & Approval Block)
    task_validator.validate_transition(task.status, TaskState.RUNNING)
    task.status = TaskState.RUNNING

    context = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=task.scope,
        available_tools=tools.list_specs(),
        max_turns=5,
    )

    run, history, approval_req = await run_executor.execute_run(task, agent, context)
    assert approval_req is not None
    assert approval_req.tool_request.tool_name == "restart_daemon"

    # Task transitions to BLOCKED
    task_validator.validate_transition(task.status, TaskState.BLOCKED)
    task.status = TaskState.BLOCKED

    # 4. On-Call Lead Approves
    approval_req.status = ApprovalState.APPROVED
    approval_req.reviewed_by = "OnCallLead"
    approval_req.reviewed_at = datetime.now(timezone.utc)

    # 5. Agent Execution (Phase 2: Execution & Complete)
    task_validator.validate_transition(task.status, TaskState.RUNNING)
    task.status = TaskState.RUNNING

    run2, history2, _ = await run_executor.execute_run(
        task=task,
        agent=agent,
        context=context,
        run=run,
        history=history,
        approval_resume=approval_req,
    )
    assert run2.status.value == "COMPLETED"
    assert run2.output_payload["incident_status"] == "MITIGATED"

    # 6. Verification Pass
    task_validator.validate_transition(task.status, TaskState.VERIFYING)
    task.status = TaskState.VERIFYING

    verifier = DaemonHealthVerifier()
    v_res = await verif_gate.verify_task(
        task=task,
        verifier=verifier,
        expected_outcome="Daemon latency under 50ms",
    )
    assert v_res.verified is True
    assert v_res.evidence[0].source_type == "PROMETHEUS_METRICS"

    # 7. Authoritative Task Closure
    task_validator.validate_transition(task.status, TaskState.COMPLETED)
    task.status = TaskState.COMPLETED
