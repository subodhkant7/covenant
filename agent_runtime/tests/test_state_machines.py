"""Tests for Task, AgentRun, ToolExecution, and Approval state machines."""

import pytest

from agent_runtime.core.state.enums import (
    ApprovalState,
    AgentRunState,
    TaskState,
    ToolExecutionState,
)
from agent_runtime.core.state.exceptions import InvalidStateTransitionError
from agent_runtime.core.state.machine import (
    approval_validator,
    agent_run_validator,
    task_validator,
    tool_execution_validator,
)


def test_task_state_machine_valid_lifecycle():
    # PENDING -> ROUTED -> RUNNING -> COMPLETED
    assert task_validator.can_transition(TaskState.PENDING, TaskState.ROUTED)
    assert task_validator.can_transition(TaskState.ROUTED, TaskState.RUNNING)
    assert task_validator.can_transition(TaskState.RUNNING, TaskState.COMPLETED)

    # RUNNING -> BLOCKED -> RUNNING
    assert task_validator.can_transition(TaskState.RUNNING, TaskState.BLOCKED)
    assert task_validator.can_transition(TaskState.BLOCKED, TaskState.RUNNING)

    # RUNNING -> VERIFYING -> COMPLETED
    assert task_validator.can_transition(TaskState.RUNNING, TaskState.VERIFYING)
    assert task_validator.can_transition(TaskState.VERIFYING, TaskState.COMPLETED)


def test_task_state_machine_invalid_transitions():
    # Cannot jump directly from PENDING to COMPLETED
    with pytest.raises(InvalidStateTransitionError):
        task_validator.validate_transition(TaskState.PENDING, TaskState.COMPLETED)

    # Cannot transition out of terminal COMPLETED
    with pytest.raises(InvalidStateTransitionError):
        task_validator.validate_transition(TaskState.COMPLETED, TaskState.RUNNING)


def test_agent_run_state_machine():
    assert agent_run_validator.can_transition(AgentRunState.INITIALIZING, AgentRunState.EXECUTING)
    assert agent_run_validator.can_transition(AgentRunState.EXECUTING, AgentRunState.AWAITING_TOOL)
    assert agent_run_validator.can_transition(AgentRunState.AWAITING_TOOL, AgentRunState.EXECUTING)
    assert agent_run_validator.can_transition(AgentRunState.EXECUTING, AgentRunState.AWAITING_APPROVAL)
    assert agent_run_validator.can_transition(AgentRunState.AWAITING_APPROVAL, AgentRunState.EXECUTING)
    assert agent_run_validator.can_transition(AgentRunState.EXECUTING, AgentRunState.COMPLETED)

    # Terminal state cannot transition
    with pytest.raises(InvalidStateTransitionError):
        agent_run_validator.validate_transition(AgentRunState.COMPLETED, AgentRunState.EXECUTING)


def test_tool_execution_state_machine():
    assert tool_execution_validator.can_transition(ToolExecutionState.QUEUED, ToolExecutionState.RUNNING)
    assert tool_execution_validator.can_transition(ToolExecutionState.RUNNING, ToolExecutionState.SUCCEEDED)
    assert tool_execution_validator.can_transition(ToolExecutionState.RUNNING, ToolExecutionState.FAILED)

    with pytest.raises(InvalidStateTransitionError):
        tool_execution_validator.validate_transition(ToolExecutionState.SUCCEEDED, ToolExecutionState.RUNNING)


def test_approval_state_machine():
    assert approval_validator.can_transition(ApprovalState.PENDING, ApprovalState.APPROVED)
    assert approval_validator.can_transition(ApprovalState.APPROVED, ApprovalState.EXECUTED)
    assert approval_validator.can_transition(ApprovalState.PENDING, ApprovalState.REJECTED)
    assert approval_validator.can_transition(ApprovalState.PENDING, ApprovalState.EXPIRED)

    # Executed approval is a single-use token and cannot be re-approved
    with pytest.raises(InvalidStateTransitionError):
        approval_validator.validate_transition(ApprovalState.EXECUTED, ApprovalState.APPROVED)
