"""Bootstrap: Deterministic assembly of the Covenant runtime bridge environment."""

from dataclasses import dataclass
from typing import Any, Optional

from agent_runtime.core.approval.service import InMemoryApprovalRepository, RuntimeApprovalService
from agent_runtime.core.authorization.matrix import ToolPermissionMatrix
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.idempotency import IdempotencyStore
from agent_runtime.core.engine.registry import AgentRegistry, ToolRegistry
from agent_runtime.core.engine.router import DeterministicTaskRouter
from agent_runtime.core.interfaces.telemetry import IEventSink
from agent_runtime.core.persistence.interfaces import IApprovalRepository, IToolExecutionRepository
from agent_runtime.core.policy.engine import DefaultPolicyEngine
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from covenant_runtime_bridge.agents.discovery_agent import AdaptedCommitmentAgent
from covenant_runtime_bridge.agents.investigator_agent import AdaptedEvidenceAgent
from covenant_runtime_bridge.agents.resolver_agent import AdaptedResolutionAgent
from covenant_runtime_bridge.policies.policy_adapter import CovenantActionPolicyRule
from covenant_runtime_bridge.tools.covenant_tools import create_covenant_tool_registry
from covenant_runtime_bridge.verification.verification_adapter import CovenantVerificationAdapter


@dataclass
class CovenantRuntimeEnvironment:
    organization_id: str
    tools: ToolRegistry
    agents: AgentRegistry
    permissions: ToolPermissionMatrix
    policy: DefaultPolicyEngine
    verifier: CovenantVerificationAdapter
    router: DeterministicTaskRouter
    engine: Optional[ExecutionEngine] = None
    event_sink: Optional[IEventSink] = None
    idempotency: Optional[Any] = None
    approval_service: Optional[RuntimeApprovalService] = None
    tool_repo: Optional[IToolExecutionRepository] = None
    approval_repo: Optional[IApprovalRepository] = None


class CovenantRuntimeBootstrap:
    """
    Assembles and wires the complete Covenant domain bridge onto the generic runtime.
    Deterministic, opt-in, and side-effect-free upon instantiation.
    """
    ORGANIZATION_ID = "org_covenant_northstar"

    @classmethod
    def assemble(
        cls,
        organization_id: str = None,
        event_sink: Optional[IEventSink] = None,
        idempotency_store: Optional[Any] = None,
        tool_execution_repo: Optional[IToolExecutionRepository] = None,
        approval_repo: Optional[IApprovalRepository] = None,
    ) -> CovenantRuntimeEnvironment:
        org_id = organization_id or cls.ORGANIZATION_ID

        # 1. Tools
        tools = create_covenant_tool_registry()

        # 2. Agents
        agents = AgentRegistry()
        disc_agent = AdaptedCommitmentAgent()
        inv_agent = AdaptedEvidenceAgent()
        res_agent = AdaptedResolutionAgent()
        agents.register(disc_agent)
        agents.register(inv_agent)
        agents.register(res_agent)

        # 3. Router
        router = DeterministicTaskRouter()

        # 4. Authorizations
        permissions = ToolPermissionMatrix()
        # Discovery Agent Permissions
        permissions.grant(
            org_id,
            disc_agent.definition.id,
            ["search_email", "read_email", "search_contract", "create_commitment"],
        )
        # Investigator Agent Permissions
        permissions.grant(
            org_id,
            inv_agent.definition.id,
            [
                "search_email",
                "read_email",
                "get_project_status",
                "get_invoice_status",
                "search_calendar",
                "calculate_risk",
                "find_evidence",
            ],
        )
        # Resolver Agent Permissions
        permissions.grant(
            org_id,
            res_agent.definition.id,
            ["draft_followup", "send_followup", "create_escalation", "request_human_approval"],
        )

        # 5. Policy Engine
        policy = DefaultPolicyEngine(rules=[CovenantActionPolicyRule()])

        # 6. Verifier
        verifier = CovenantVerificationAdapter()

        # 7. Authoritative Execution Engine & Services
        sink = event_sink or InMemoryEventSink()
        idemp = idempotency_store or IdempotencyStore()
        app_repo = approval_repo or InMemoryApprovalRepository()

        engine = ExecutionEngine(
            tool_registry=tools,
            permissions=permissions,
            policy_engine=policy,
            event_sink=sink,
            idempotency_store=idemp,
            tool_execution_repo=tool_execution_repo,
            approval_repo=app_repo,
        )

        approval_service = RuntimeApprovalService(
            approval_repository=app_repo,
            event_sink=sink,
        )

        return CovenantRuntimeEnvironment(
            organization_id=org_id,
            tools=tools,
            agents=agents,
            permissions=permissions,
            policy=policy,
            verifier=verifier,
            router=router,
            engine=engine,
            event_sink=sink,
            idempotency=idemp,
            approval_service=approval_service,
            tool_repo=tool_execution_repo,
            approval_repo=app_repo,
        )
