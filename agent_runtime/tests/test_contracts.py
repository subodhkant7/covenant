"""Tests for contract validation, scopes, and immutable contexts."""

import pytest
from pydantic import ValidationError

from agent_runtime.core.contracts.context import (
    OrganizationContext,
    Role,
    Task,
    TaskContext,
    TaskScope,
)
from agent_runtime.core.contracts.tool import ToolSpec
from agent_runtime.core.state.enums import ScopeType, TaskState


def test_organization_context_validation():
    org = OrganizationContext(
        organization_id="org_test",
        name="Test Organization",
        settings={"default_timeout": 60},
    )
    assert org.organization_id == "org_test"
    assert org.settings["default_timeout"] == 60


def test_role_validation():
    role = Role(
        id="role_diagnostician",
        name="Diagnostician",
        description="Analyzes system telemetry",
        required_capabilities=["log_parsing", "metrics"],
    )
    assert role.id == "role_diagnostician"
    assert "log_parsing" in role.required_capabilities


def test_task_scope_variants():
    # Unscoped
    scope_unscoped = TaskScope(scope_type=ScopeType.UNSCOPED)
    assert scope_unscoped.scope_type == ScopeType.UNSCOPED
    assert scope_unscoped.entity_ids == []

    # Organization-wide
    scope_org = TaskScope(scope_type=ScopeType.ORGANIZATION)
    assert scope_org.scope_type == ScopeType.ORGANIZATION

    # Single entity
    scope_single = TaskScope(
        scope_type=ScopeType.ENTITY,
        entity_type="server",
        entity_ids=["srv-101"],
    )
    assert scope_single.entity_ids == ["srv-101"]

    # Multi entity
    scope_multi = TaskScope(
        scope_type=ScopeType.MULTI_ENTITY,
        entity_type="server",
        entity_ids=["srv-101", "srv-102", "srv-103"],
        filter_criteria={"region": "us-east"},
    )
    assert len(scope_multi.entity_ids) == 3


def test_task_creation_and_defaults():
    task = Task(
        organization_id="org_test",
        intent="Analyze error rates",
        required_role="role_diagnostician",
    )
    assert task.id.startswith("tsk_")
    assert task.status == TaskState.PENDING
    assert task.scope.scope_type == ScopeType.UNSCOPED
    assert task.attempt_count == 0


def test_task_context_immutability():
    tool_spec = ToolSpec(
        name="inspect_logs",
        description="Inspects logs",
        parameters_schema={"type": "object"},
    )
    ctx = TaskContext(
        task_id="tsk_101",
        organization_id="org_test",
        intent="Inspect logs",
        required_role="role_diagnostician",
        scope=TaskScope(scope_type=ScopeType.UNSCOPED),
        available_tools=[tool_spec],
    )

    # Immutability check: Pydantic frozen model raises ValidationError on assignment
    with pytest.raises(ValidationError):
        ctx.intent = "Modified Intent"

    with pytest.raises(ValidationError):
        ctx.task_id = "tsk_999"
