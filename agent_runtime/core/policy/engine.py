"""Policy engine implementation."""

from typing import List, Optional
from agent_runtime.core.contracts.policy import PolicyDecision, PolicyEvaluationContext
from agent_runtime.core.interfaces.policy import IPolicyEngine, IPolicyRule
from agent_runtime.core.state.enums import PolicyDecisionType


class DefaultPolicyEngine(IPolicyEngine):
    """
    Deterministic policy engine.
    Evaluates registered rules in priority order:
    1. If any rule returns DENY -> DENY.
    2. If any rule returns REQUIRE_HUMAN_APPROVAL -> REQUIRE_HUMAN_APPROVAL.
    3. If any rule explicitly returns ALLOW -> ALLOW.
    4. If no rule evaluated or matched:
       - if tool has_side_effects -> default to REQUIRE_HUMAN_APPROVAL
       - else -> ALLOW
    """

    def __init__(self, rules: Optional[List[IPolicyRule]] = None):
        self.rules: List[IPolicyRule] = rules or []

    def register_rule(self, rule: IPolicyRule) -> None:
        self.rules.append(rule)

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyDecision:
        triggered_rules: List[str] = []
        requires_approval = False
        explicit_allow: Optional[PolicyDecision] = None

        for rule in self.rules:
            decision = rule.evaluate(context)
            if decision:
                triggered_rules.append(rule.rule_id)
                if decision.decision == PolicyDecisionType.DENY:
                    return PolicyDecision(
                        tool_request_id=context.tool_request.request_id,
                        decision=PolicyDecisionType.DENY,
                        rationale=decision.rationale or f"Denied by policy rule '{rule.rule_id}'.",
                        rules_triggered=triggered_rules,
                    )
                elif decision.decision == PolicyDecisionType.REQUIRE_HUMAN_APPROVAL:
                    requires_approval = True
                elif decision.decision == PolicyDecisionType.ALLOW:
                    if not explicit_allow:
                        explicit_allow = decision

        if requires_approval:
            return PolicyDecision(
                tool_request_id=context.tool_request.request_id,
                decision=PolicyDecisionType.REQUIRE_HUMAN_APPROVAL,
                rationale=f"Human approval required by policy rules: {', '.join(triggered_rules)}.",
                rules_triggered=triggered_rules,
            )

        if explicit_allow:
            return explicit_allow

        # Baseline fallback when no explicit rule matched:
        if context.tool_spec.has_side_effects:
            return PolicyDecision(
                tool_request_id=context.tool_request.request_id,
                decision=PolicyDecisionType.REQUIRE_HUMAN_APPROVAL,
                rationale="Tool has side effects and default policy requires human authorization.",
                rules_triggered=["DEFAULT_SIDE_EFFECT_GUARD"],
            )

        return PolicyDecision(
            tool_request_id=context.tool_request.request_id,
            decision=PolicyDecisionType.ALLOW,
            rationale="Read-only tool allowed by default policy.",
            rules_triggered=[],
        )
