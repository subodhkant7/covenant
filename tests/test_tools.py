"""Tests for Tool Registry and Execution."""

import pytest
from covenant.tools import initialize_tools


@pytest.mark.asyncio
async def test_tool_registry_and_execution():
    registry = initialize_tools()
    
    # Check email search tool
    email_tool = registry.get("search_email")
    assert email_tool is not None
    res = await email_tool.execute(query="Meridian")
    assert res.success is True
    assert res.data["count"] >= 1

    # Check risk calculation tool
    risk_tool = registry.get("calculate_risk")
    assert risk_tool is not None
    res_risk = await risk_tool.execute(is_overdue=True, days_overdue=4.0, is_blocking_downstream=True)
    assert res_risk.success is True
    assert res_risk.data["risk"] in ["MEDIUM", "HIGH"]

    # Check draft followup tool
    draft_tool = registry.get("draft_followup")
    assert draft_tool is not None
    res_draft = await draft_tool.execute(
        commitment_id="com_01",
        recipient_name="Sarah",
        subject="Follow-up",
        promise_summary="Deliverable approval",
    )
    assert res_draft.success is True
    assert res_draft.data["requires_human_approval"] is True
