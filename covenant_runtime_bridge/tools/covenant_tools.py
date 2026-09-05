"""Catalog of adapted Covenant tools with explicit delivery guarantees and risk profiles."""

from agent_runtime.core.engine.registry import ToolRegistry
from agent_runtime.core.state.enums import ExecutionSafety
from covenant.tools.action_tools import (
    CreateEscalationTool,
    DraftFollowupTool,
    RequestHumanApprovalTool,
    SendFollowupTool,
    VerifyCommitmentTool,
)
from covenant.tools.commitment_tools import (
    CalculateRiskTool,
    CreateCommitmentTool,
    FindEvidenceTool,
)
from covenant.tools.workspace_tools import (
    GetInvoiceStatusTool,
    GetProjectStatusTool,
    ReadEmailTool,
    SearchCalendarTool,
    SearchContractTool,
    SearchEmailTool,
)
from covenant_runtime_bridge.tools.tool_adapter import CovenantToolAdapter


def create_covenant_tool_registry() -> ToolRegistry:
    """Instantiates and registers all Covenant tools wrapped in runtime adapters."""
    registry = ToolRegistry()

    # 1. READ_ONLY Inspection & Calculation Tools
    registry.register(CovenantToolAdapter(SearchEmailTool(), ExecutionSafety.READ_ONLY, risk_level="LOW"))
    registry.register(CovenantToolAdapter(ReadEmailTool(), ExecutionSafety.READ_ONLY, risk_level="LOW"))
    registry.register(CovenantToolAdapter(SearchContractTool(), ExecutionSafety.READ_ONLY, risk_level="LOW"))
    registry.register(CovenantToolAdapter(GetProjectStatusTool(), ExecutionSafety.READ_ONLY, risk_level="LOW"))
    registry.register(CovenantToolAdapter(GetInvoiceStatusTool(), ExecutionSafety.READ_ONLY, risk_level="LOW"))
    registry.register(CovenantToolAdapter(SearchCalendarTool(), ExecutionSafety.READ_ONLY, risk_level="LOW"))
    registry.register(CovenantToolAdapter(CalculateRiskTool(), ExecutionSafety.READ_ONLY, risk_level="LOW"))
    registry.register(CovenantToolAdapter(FindEvidenceTool(), ExecutionSafety.READ_ONLY, risk_level="LOW"))
    registry.register(CovenantToolAdapter(VerifyCommitmentTool(), ExecutionSafety.READ_ONLY, risk_level="LOW"))

    # 2. IDEMPOTENT Preparation & Staging Tools
    registry.register(CovenantToolAdapter(CreateCommitmentTool(), ExecutionSafety.IDEMPOTENT, risk_level="LOW"))
    registry.register(CovenantToolAdapter(DraftFollowupTool(), ExecutionSafety.IDEMPOTENT, risk_level="LOW"))
    registry.register(CovenantToolAdapter(RequestHumanApprovalTool(), ExecutionSafety.IDEMPOTENT, risk_level="LOW"))

    # 3. NON_IDEMPOTENT Side-Effecting Tools (Require governance and safe recovery)
    registry.register(CovenantToolAdapter(SendFollowupTool(), ExecutionSafety.NON_IDEMPOTENT, risk_level="HIGH"))
    registry.register(CovenantToolAdapter(CreateEscalationTool(), ExecutionSafety.NON_IDEMPOTENT, risk_level="HIGH"))

    return registry
