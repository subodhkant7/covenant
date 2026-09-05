"""Section 5, 15: Tests for approval consumption ordering, validation guards, and race safety."""

import asyncio
from datetime import datetime, timezone
import pytest

from agent_runtime.core.authorization.matrix import ToolPermissionMatrix
from agent_runtime.core.contracts.agent import AgentRun
from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.context import Task, TaskScope
from agent_runtime.core.contracts.policy import PolicyDecision, PolicyEvaluationContext
from agent_runtime.core.contracts.tool import ToolRequest, ToolSpec
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.registry import ToolRegistry
from agent_runtime.core.interfaces.policy import IPolicyRule
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.persistence.approval_repo import SQLiteApprovalRepository
from agent_runtime.core.persistence.connection import DatabaseManager
from agent_runtime.core.persistence.task_repo import SQLiteTaskRepository
from agent_runtime.core.policy.engine import DefaultPolicyEngine
from agent_runtime.core.state.enums import ApprovalState, ExecutionSafety, PolicyDecisionType
from agent_runtime.core.telemetry.sink import InMemoryEventSink


class TargetBankTransferTool(ITool):
    spec = ToolSpec(
        name="bank_wire_transfer",
        description="Transfers funds",
        parameters_schema={
            "type": "object",
            "required": ["account_number", "amount", "routing_code"],
        },
        execution_safety=ExecutionSafety.NON_IDEMPOTENT,
    )

    async def execute(self, account_number: str, amount: int, routing_code: str, **kwargs):
        return {"account": account_number, "transferred": amount, "status": "DISPATCHED"}


class DenyRestrictedAccountRule(IPolicyRule):
    rule_id = "BLOCK_OFFSHORE_TRANSFERS"
    description = "Denies transfers to offshore accounts starting with OFS-"

    def evaluate(self, context: PolicyEvaluationContext):
        if context.tool_request.tool_name == "bank_wire_transfer":
            acct = context.tool_request.arguments.get("account_number", "")
            if str(acct).startswith("OFS-"):
                return PolicyDecision(
                    tool_request_id=context.tool_request.request_id,
                    decision=PolicyDecisionType.DENY,
                    rationale="Offshore routing numbers are strictly prohibited by policy.",
                    rules_triggered=[self.rule_id],
                )
        return None


@pytest.fixture
def approval_test_setup(tmp_path):
    db_file = tmp_path / "test_appr_order.sqlite"
    mgr = DatabaseManager(str(db_file))
    task_repo = SQLiteTaskRepository(mgr)
    appr_repo = SQLiteApprovalRepository(mgr)

    tools = ToolRegistry()
    tools.register(TargetBankTransferTool())

    perms = ToolPermissionMatrix()
    perms.grant("org_fin", "finance_agent", ["bank_wire_transfer"])

    policy = DefaultPolicyEngine(rules=[DenyRestrictedAccountRule()])
    sink = InMemoryEventSink()

    engine = ExecutionEngine(
        tool_registry=tools,
        permissions=perms,
        policy_engine=policy,
        event_sink=sink,
        approval_repo=appr_repo,
    )
    yield engine, task_repo, appr_repo
    mgr.close()


@pytest.mark.asyncio
async def test_approval_not_consumed_when_modified_args_invalid_schema(approval_test_setup):
    """
    If human modifies arguments but leaves out a required schema property,
    execution MUST fail AND the approval must NOT be consumed (remains APPROVED).
    """
    engine, task_repo, appr_repo = approval_test_setup
    task = Task(id="tsk_appr_01", organization_id="org_fin", intent="Wire money", required_role="finance")
    await task_repo.create(task)
    run = AgentRun(id="run_appr_01", task_id="tsk_appr_01", agent_id="finance_agent")

    req = ToolRequest(
        tool_name="bank_wire_transfer",
        arguments={"account_number": "ACC-101", "amount": 500, "routing_code": "ROUT-11"},
    )
    appr = HumanApprovalRequest(
        approval_id="appr_wire_01",
        organization_id="org_fin",
        task_id=task.id,
        agent_run_id=run.id,
        tool_request=req,
        policy_decision_id="pol_1",
        status=ApprovalState.APPROVED,
        # Human deleted 'routing_code' (missing required schema field!)
        modified_arguments={"account_number": "ACC-101", "amount": 750},
    )
    await appr_repo.create(appr)

    obs, _ = await engine.handle_tool_request(task, run, req, approval=appr)
    assert obs.success is False
    assert "Missing required fields" in obs.error

    # CRITICAL: Approval was NOT consumed! Remains APPROVED in database
    persisted = await appr_repo.get("appr_wire_01")
    assert persisted.status == ApprovalState.APPROVED


@pytest.mark.asyncio
async def test_approval_not_consumed_when_policy_denies_modified_arguments(approval_test_setup):
    """
    If human changes account to an offshore account that triggers a DENY policy,
    execution MUST fail AND the approval must NOT be consumed!
    """
    engine, task_repo, appr_repo = approval_test_setup
    task = Task(id="tsk_appr_02", organization_id="org_fin", intent="Wire money", required_role="finance")
    await task_repo.create(task)
    run = AgentRun(id="run_appr_02", task_id="tsk_appr_02", agent_id="finance_agent")

    req = ToolRequest(
        tool_name="bank_wire_transfer",
        arguments={"account_number": "ACC-101", "amount": 500, "routing_code": "ROUT-11"},
    )
    appr = HumanApprovalRequest(
        approval_id="appr_wire_02",
        organization_id="org_fin",
        task_id=task.id,
        agent_run_id=run.id,
        tool_request=req,
        policy_decision_id="pol_2",
        status=ApprovalState.APPROVED,
        # Human changed account to prohibited offshore account
        modified_arguments={"account_number": "OFS-999-SWISS", "amount": 500, "routing_code": "ROUT-11"},
    )
    await appr_repo.create(appr)

    obs, _ = await engine.handle_tool_request(task, run, req, approval=appr)
    assert obs.success is False
    assert "Policy denied modified arguments" in obs.error

    # CRITICAL: Approval was NOT consumed!
    persisted = await appr_repo.get("appr_wire_02")
    assert persisted.status == ApprovalState.APPROVED


@pytest.mark.asyncio
async def test_approval_successfully_consumed_when_valid(approval_test_setup):
    """
    When modified arguments satisfy schema, policy, and permissions,
    approval is consumed atomically (status=EXECUTED) and tool executes.
    """
    engine, task_repo, appr_repo = approval_test_setup
    task = Task(id="tsk_appr_03", organization_id="org_fin", intent="Wire money", required_role="finance")
    await task_repo.create(task)
    run = AgentRun(id="run_appr_03", task_id="tsk_appr_03", agent_id="finance_agent")

    req = ToolRequest(
        tool_name="bank_wire_transfer",
        arguments={"account_number": "ACC-101", "amount": 500, "routing_code": "ROUT-11"},
    )
    appr = HumanApprovalRequest(
        approval_id="appr_wire_03",
        organization_id="org_fin",
        task_id=task.id,
        agent_run_id=run.id,
        tool_request=req,
        policy_decision_id="pol_3",
        status=ApprovalState.APPROVED,
        modified_arguments={"account_number": "ACC-202", "amount": 600, "routing_code": "ROUT-11"},
    )
    await appr_repo.create(appr)

    obs, _ = await engine.handle_tool_request(task, run, req, approval=appr)
    assert obs.success is True
    assert obs.data["account"] == "ACC-202"
    assert obs.data["transferred"] == 600

    # Approval is now EXECUTED in database (single-use token)
    persisted = await appr_repo.get("appr_wire_03")
    assert persisted.status == ApprovalState.EXECUTED


@pytest.mark.asyncio
async def test_concurrent_reviewers_submit_approval_race(approval_test_setup):
    """
    Two human reviewers simultaneously click approve.
    Exactly ONE succeeds; the second receives rowcount == 0.
    """
    _, task_repo, appr_repo = approval_test_setup
    task = Task(id="tsk_race_rev", organization_id="org_fin", intent="Wire money", required_role="finance")
    await task_repo.create(task)

    appr = HumanApprovalRequest(
        approval_id="appr_race_01",
        organization_id="org_fin",
        task_id=task.id,
        agent_run_id="run_1",
        tool_request=ToolRequest(tool_name="bank_wire_transfer", arguments={}),
        policy_decision_id="pol_1",
        status=ApprovalState.PENDING,
    )
    await appr_repo.create(appr)

    res_1, res_2 = await asyncio.gather(
        appr_repo.atomic_approve("appr_race_01", reviewed_by="Reviewer_A"),
        appr_repo.atomic_approve("appr_race_01", reviewed_by="Reviewer_B"),
    )
    assert [res_1, res_2].count(True) == 1
    assert [res_1, res_2].count(False) == 1
