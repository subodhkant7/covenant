"""Tests for policy evaluation and human approval mechanics."""

from datetime import datetime, timezone
import pytest

from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.context import TaskScope
from agent_runtime.core.contracts.policy import PolicyDecision, PolicyEvaluationContext
from agent_runtime.core.contracts.tool import ToolRequest, ToolSpec
from agent_runtime.core.interfaces.policy import IPolicyRule
from agent_runtime.core.policy.engine import DefaultPolicyEngine
from agent_runtime.core.state.enums import ApprovalState, PolicyDecisionType


class RestrictiveFileRule(IPolicyRule):
    rule_id = "RESTRICT_SYS_FILES"
    description = "Denies file modifications in /etc or /system"

    def evaluate(self, context: PolicyEvaluationContext):
        if context.tool_request.tool_name == "modify_file":
            path = context.tool_request.arguments.get("path", "")
            if path.startswith("/etc") or path.startswith("/system"):
                return PolicyDecision(
                    tool_request_id=context.tool_request.request_id,
                    decision=PolicyDecisionType.DENY,
                    rationale="Protected system paths cannot be modified.",
                    rules_triggered=[self.rule_id],
                )
        return None


def test_default_policy_read_only_vs_side_effects():
    engine = DefaultPolicyEngine()

    read_tool = ToolSpec(name="read_file", description="reads file", has_side_effects=False)
    write_tool = ToolSpec(name="write_file", description="writes file", has_side_effects=True)

    ctx_read = PolicyEvaluationContext(
        organization_id="org_test",
        task_id="tsk_1",
        agent_run_id="run_1",
        agent_id="agent_1",
        role_id="role_1",
        tool_spec=read_tool,
        tool_request=ToolRequest(tool_name="read_file", arguments={"path": "/data.txt"}),
        task_scope=TaskScope(),
    )
    decision_read = engine.evaluate(ctx_read)
    assert decision_read.decision == PolicyDecisionType.ALLOW

    ctx_write = PolicyEvaluationContext(
        organization_id="org_test",
        task_id="tsk_1",
        agent_run_id="run_1",
        agent_id="agent_1",
        role_id="role_1",
        tool_spec=write_tool,
        tool_request=ToolRequest(tool_name="write_file", arguments={"path": "/data.txt"}),
        task_scope=TaskScope(),
    )
    decision_write = engine.evaluate(ctx_write)
    assert decision_write.decision == PolicyDecisionType.REQUIRE_HUMAN_APPROVAL


def test_custom_deny_policy_rule():
    engine = DefaultPolicyEngine(rules=[RestrictiveFileRule()])
    write_tool = ToolSpec(name="modify_file", description="modifies file", has_side_effects=True)

    ctx_deny = PolicyEvaluationContext(
        organization_id="org_test",
        task_id="tsk_1",
        agent_run_id="run_1",
        agent_id="agent_1",
        role_id="role_1",
        tool_spec=write_tool,
        tool_request=ToolRequest(tool_name="modify_file", arguments={"path": "/etc/passwd"}),
        task_scope=TaskScope(),
    )
    decision = engine.evaluate(ctx_deny)
    assert decision.decision == PolicyDecisionType.DENY
    assert "Protected system paths" in decision.rationale


def test_human_approval_request_lifecycle():
    appr = HumanApprovalRequest(
        organization_id="org_test",
        task_id="tsk_1",
        agent_run_id="run_1",
        tool_request=ToolRequest(tool_name="send_invoice", arguments={"amount": 5000}),
        policy_decision_id="pol_1",
    )
    assert appr.status == ApprovalState.PENDING

    # Reviewer approves with modified arguments
    appr.status = ApprovalState.APPROVED
    appr.reviewed_by = "LeadAdmin"
    appr.reviewed_at = datetime.now(timezone.utc)
    appr.modified_arguments = {"amount": 4500}

    assert appr.status == ApprovalState.APPROVED
    assert appr.modified_arguments["amount"] == 4500
