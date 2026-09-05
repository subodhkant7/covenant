"""Policy Agent: Evaluates autonomy rules and enforces human-in-the-loop boundaries."""

from covenant.agents.base import AgentContext, AgentResult, BaseAgent
from covenant.domain.enums import (
    ActionStatus,
    ActionType,
    CommitmentStatus,
    PolicyDecisionType,
    RiskLevel,
)
from covenant.domain.models import PolicyDecision
from covenant.state_machine.machine import CommitmentStateMachine


class PolicyAgent(BaseAgent):
    name = "PolicyAgent"
    description = "Enforces deterministic action policies and identifies mandatory human approval boundaries."

    async def run(self, context: AgentContext) -> AgentResult:
        cid = context.target_commitment_id
        if not cid or not self.commitment_repo:
            return AgentResult(agent_name=self.name, success=False, summary="Missing commitment ID or repository.")

        commitment = await self.commitment_repo.get_by_id(cid)
        if not commitment or not commitment.next_action:
            return AgentResult(agent_name=self.name, success=False, summary=f"Commitment '{cid}' has no proposed action.")

        action = commitment.next_action
        events = []
        rules_triggered = []
        requires_approval = False

        # Rule 1: Outbound external communications to clients or suppliers require approval
        if action.action_type in [ActionType.FOLLOWUP_EMAIL, ActionType.ESCALATE_DISPUTE]:
            rules_triggered.append("RULE-EXT-COMM: Outbound messages to external clients/vendors require human approval.")
            requires_approval = True

        # Rule 2: High or critical risk actions require approval
        if action.risk in [RiskLevel.HIGH, RiskLevel.CRITICAL] or commitment.risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            rules_triggered.append("RULE-HIGH-RISK: High or critical risk commitment actions require human sign-off.")
            requires_approval = True

        # Rule 3: Financial or dispute escalations require approval
        if action.action_type in [ActionType.ISSUE_INVOICE, ActionType.ESCALATE_DISPUTE]:
            rules_triggered.append("RULE-FIN-DISP: Financial notices and formal dispute escalations require approval.")
            requires_approval = True

        decision_type = (
            PolicyDecisionType.HUMAN_APPROVAL_REQUIRED
            if requires_approval
            else PolicyDecisionType.AUTONOMOUS_PERMITTED
        )

        rationale = "; ".join(rules_triggered) if rules_triggered else "Internal non-disruptive state update permitted autonomously."

        policy_decision = PolicyDecision(
            action_id=action.id,
            decision=decision_type,
            rationale=rationale,
            risk_level=action.risk,
            requires_human_approval=requires_approval,
            rules_triggered=rules_triggered,
        )

        action.requires_human_approval = requires_approval
        action.approval_reason = rationale

        if requires_approval:
            action.status = ActionStatus.AWAITING_APPROVAL
            commitment.required_human_approval = True

            if CommitmentStateMachine.can_transition(commitment.status, CommitmentStatus.AWAITING_APPROVAL):
                CommitmentStateMachine.transition(
                    commitment=commitment,
                    target_state=CommitmentStatus.AWAITING_APPROVAL,
                    agent_name=self.name,
                    reason=f"Policy requirement: {rationale}",
                )
        else:
            action.status = ActionStatus.APPROVED

        await self.commitment_repo.save(commitment)

        evt = await self.emit_event(
            action_name="EVALUATE_POLICY",
            summary=f"Policy decision for {action.action_type.value}: {decision_type.value}",
            commitment_id=commitment.id,
            new_state=commitment.status,
            rationale=rationale,
            metadata={"rules": rules_triggered, "requires_human_approval": requires_approval},
        )
        events.append(evt)

        return AgentResult(
            agent_name=self.name,
            success=True,
            summary=f"Evaluated policy for action '{action.id}': {decision_type.value}.",
            data={"decision": policy_decision.model_dump(mode="json")},
            events=events,
        )
