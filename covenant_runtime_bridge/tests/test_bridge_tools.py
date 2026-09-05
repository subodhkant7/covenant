"""Tests for Covenant tool adapters and ExecutionSafety classifications."""

import pytest
from agent_runtime.core.state.enums import ExecutionSafety
from covenant_runtime_bridge.tools.covenant_tools import create_covenant_tool_registry


def test_tool_registry_and_delivery_guarantees():
    registry = create_covenant_tool_registry()

    # Verify READ_ONLY tools
    read_tools = [
        "search_email",
        "read_email",
        "search_contract",
        "get_project_status",
        "get_invoice_status",
        "search_calendar",
        "calculate_risk",
        "find_evidence",
        "verify_commitment",
    ]
    for name in read_tools:
        tool = registry.get(name)
        assert tool is not None, f"Tool '{name}' missing"
        assert tool.spec.execution_safety == ExecutionSafety.READ_ONLY, f"Tool '{name}' should be READ_ONLY"
        assert tool.spec.has_side_effects is False

    # Verify IDEMPOTENT tools
    idemp_tools = [
        "create_commitment",
        "draft_followup",
        "request_human_approval",
    ]
    for name in idemp_tools:
        tool = registry.get(name)
        assert tool is not None, f"Tool '{name}' missing"
        assert tool.spec.execution_safety == ExecutionSafety.IDEMPOTENT, f"Tool '{name}' should be IDEMPOTENT"
        assert tool.spec.is_idempotent is True

    # Verify NON_IDEMPOTENT tools
    non_idemp_tools = [
        "send_followup",
        "create_escalation",
    ]
    for name in non_idemp_tools:
        tool = registry.get(name)
        assert tool is not None, f"Tool '{name}' missing"
        assert tool.spec.execution_safety == ExecutionSafety.NON_IDEMPOTENT, f"Tool '{name}' should be NON_IDEMPOTENT"
        assert tool.spec.has_side_effects is True
        assert tool.spec.is_idempotent is False
        assert tool.spec.default_risk_level == "HIGH"


@pytest.mark.asyncio
async def test_tool_execution_via_adapter():
    registry = create_covenant_tool_registry()
    search_tool = registry.get("search_email")

    # Call search_email via runtime ITool interface
    res = await search_tool.execute(query="Meridian")
    assert isinstance(res, dict)
    assert "emails" in res
    assert res["count"] >= 1
