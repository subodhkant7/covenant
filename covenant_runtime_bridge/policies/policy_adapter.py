"""Policy Adapter: Enforces Covenant governance boundaries as a runtime IPolicyRule."""

from typing import Optional
from agent_runtime.core.contracts.policy import PolicyDecision, PolicyEvaluationContext
from agent_runtime.core.interfaces.policy import IPolicyRule
from agent_runtime.core.state.enums import PolicyDecisionType


class CovenantActionPolicyRule(IPolicyRule):
    """
    Translates Covenant's PolicyAgent rules into a deterministic runtime IPolicyRule.
    Rules:
    1. Prohibited tools -> DENY.
    2. Outbound external communications -> REQUIRE_HUMAN_APPROVAL.
    3. High or Critical risk tools -> REQUIRE_HUMAN_APPROVAL.
    4. Internal inspection / staging -> ALLOW.
    """
    rule_id = "COVENANT_GOVERNANCE_POLICY"
    description = "Enforces human approval on external communication and high-risk actions."

    def evaluate(self, context: PolicyEvaluationContext) -> Optional[PolicyDecision]:
        tool_name = context.tool_request.tool_name

        # 1. Prohibited Actions Check
        if tool_name in ["prohibited_external_leak", "unauthorized_payout", "delete_all_records"]:
            return PolicyDecision(
                tool_request_id=context.tool_request.request_id,
                decision=PolicyDecisionType.DENY,
                rationale=f"Tool '{tool_name}' is strictly prohibited by Covenant governance policy.",
                rules_triggered=["RULE-PROHIBITED-ACTION"],
            )

        # 2. Outbound Communication Rules
        if tool_name in ["send_followup", "create_escalation"]:
            return PolicyDecision(
                tool_request_id=context.tool_request.request_id,
                decision=PolicyDecisionType.REQUIRE_HUMAN_APPROVAL,
                rationale="RULE-EXT-COMM: Outbound messages to external clients/vendors require human authorization.",
                rules_triggered=["RULE-EXT-COMM"],
            )

        # 3. High / Critical Risk Check
        if context.tool_spec.default_risk_level in ["HIGH", "CRITICAL"]:
            return PolicyDecision(
                tool_request_id=context.tool_request.request_id,
                decision=PolicyDecisionType.REQUIRE_HUMAN_APPROVAL,
                rationale="RULE-HIGH-RISK: High or critical risk commitment actions require human sign-off.",
                rules_triggered=["RULE-HIGH-RISK"],
            )

        # 4. Standard autonomous non-disruptive actions
        return PolicyDecision(
            tool_request_id=context.tool_request.request_id,
            decision=PolicyDecisionType.ALLOW,
            rationale="Internal non-disruptive operation permitted autonomously.",
        )
