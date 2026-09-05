"""Tests for Covenant policy translation and approval rules."""

import pytest
from agent_runtime.core.contracts.context import TaskScope
from agent_runtime.core.contracts.policy import PolicyEvaluationContext
from agent_runtime.core.contracts.tool import ToolRequest, ToolSpec
from agent_runtime.core.state.enums import ExecutionSafety, PolicyDecisionType
from covenant_runtime_bridge.policies.policy_adapter import CovenantActionPolicyRule


@pytest.fixture
def policy_rule():
    return CovenantActionPolicyRule()


def test_policy_requires_human_approval_for_outbound_messages(policy_rule):
    spec = ToolSpec(name="send_followup", description="Send email", execution_safety=ExecutionSafety.NON_IDEMPOTENT, default_risk_level="HIGH")
    req = ToolRequest(tool_name="send_followup", arguments={"to": "sarah@meridian.com", "body": "Please approve"})
    ctx = PolicyEvaluationContext(
        organization_id="org_covenant_northstar",
        task_id="tsk_1",
        agent_run_id="run_1",
        agent_id="resolver",
        role_id="covenant.resolver",
        tool_spec=spec,
        tool_request=req,
        task_scope=TaskScope(),
    )

    decision = policy_rule.evaluate(ctx)
    assert decision.decision == PolicyDecisionType.REQUIRE_HUMAN_APPROVAL
    assert "RULE-EXT-COMM" in decision.rules_triggered[0]


def test_policy_denies_prohibited_actions(policy_rule):
    spec = ToolSpec(name="prohibited_external_leak", description="Leak data", execution_safety=ExecutionSafety.NON_IDEMPOTENT)
    req = ToolRequest(tool_name="prohibited_external_leak", arguments={})
    ctx = PolicyEvaluationContext(
        organization_id="org_covenant_northstar",
        task_id="tsk_2",
        agent_run_id="run_2",
        agent_id="resolver",
        role_id="covenant.resolver",
        tool_spec=spec,
        tool_request=req,
        task_scope=TaskScope(),
    )

    decision = policy_rule.evaluate(ctx)
    assert decision.decision == PolicyDecisionType.DENY
    assert "RULE-PROHIBITED-ACTION" in decision.rules_triggered[0]


def test_policy_allows_internal_queries(policy_rule):
    spec = ToolSpec(name="search_email", description="Search email", execution_safety=ExecutionSafety.READ_ONLY)
    req = ToolRequest(tool_name="search_email", arguments={"query": "promise"})
    ctx = PolicyEvaluationContext(
        organization_id="org_covenant_northstar",
        task_id="tsk_3",
        agent_run_id="run_3",
        agent_id="discovery",
        role_id="covenant.discovery",
        tool_spec=spec,
        tool_request=req,
        task_scope=TaskScope(),
    )

    decision = policy_rule.evaluate(ctx)
    assert decision.decision == PolicyDecisionType.ALLOW
