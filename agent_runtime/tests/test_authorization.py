"""Tests for ToolPermissionMatrix and organization isolation."""

import pytest

from agent_runtime.core.authorization.exceptions import PermissionDeniedError
from agent_runtime.core.authorization.matrix import ToolPermissionMatrix


def test_permission_matrix_grants_and_denials():
    matrix = ToolPermissionMatrix()
    matrix.grant("org_alpha", "agent_1", ["search_email", "read_email"])

    assert matrix.is_authorized("org_alpha", "agent_1", "search_email")
    assert matrix.is_authorized("org_alpha", "agent_1", "read_email")
    assert not matrix.is_authorized("org_alpha", "agent_1", "send_email")
    assert not matrix.is_authorized("org_alpha", "agent_2", "search_email")

    with pytest.raises(PermissionDeniedError):
        matrix.authorize("org_alpha", "agent_1", "send_email")


def test_organization_isolation():
    matrix = ToolPermissionMatrix()
    # Org A has agent_1 with tool restart_service
    matrix.grant("org_a", "agent_1", ["restart_service"])
    # Org B has agent_2 with tool restart_service
    matrix.grant("org_b", "agent_2", ["restart_service"])

    # Agent 1 in Org B must be denied
    assert not matrix.is_authorized("org_b", "agent_1", "restart_service")

    # Agent 2 in Org A must be denied
    assert not matrix.is_authorized("org_a", "agent_2", "restart_service")


def test_explicit_system_tool_grant():
    matrix = ToolPermissionMatrix()
    matrix.register_system_tool("clock")

    # System tool is authorized for any agent in any org
    assert matrix.is_authorized("org_any", "agent_any", "clock")
    assert not matrix.is_authorized("org_any", "agent_any", "unknown_tool")
