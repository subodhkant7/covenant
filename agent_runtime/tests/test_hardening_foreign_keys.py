"""Section 9: Tests for database referential integrity and foreign key constraints."""

import pytest
import sqlite3

from agent_runtime.core.contracts.agent import AgentRun
from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.tool import ToolExecution, ToolRequest
from agent_runtime.core.persistence.agent_run_repo import SQLiteAgentRunRepository
from agent_runtime.core.persistence.approval_repo import SQLiteApprovalRepository
from agent_runtime.core.persistence.connection import DatabaseManager
from agent_runtime.core.persistence.task_repo import SQLiteTaskRepository
from agent_runtime.core.persistence.tool_exec_repo import SQLiteToolExecutionRepository
from agent_runtime.core.state.enums import ToolExecutionState


@pytest.fixture
def db_mgr(tmp_path):
    mgr = DatabaseManager(str(tmp_path / "test_fk.sqlite"))
    yield mgr
    mgr.close()


@pytest.mark.asyncio
async def test_tool_execution_rejects_invalid_task_or_agent_run_foreign_keys(db_mgr):
    task_repo = SQLiteTaskRepository(db_mgr)
    run_repo = SQLiteAgentRunRepository(db_mgr)
    tool_repo = SQLiteToolExecutionRepository(db_mgr)

    # Create valid parent Task
    task = Task(id="tsk_valid_01", organization_id="org_test", intent="test", required_role="test")
    await task_repo.create(task)

    # Create valid parent AgentRun
    run = AgentRun(id="run_valid_01", task_id="tsk_valid_01", agent_id="agent_1")
    await run_repo.create(run)

    # 1. Reject ToolExecution with invalid task_id
    with pytest.raises(sqlite3.IntegrityError):
        await tool_repo.create(
            ToolExecution(
                id="exec_inv_task",
                agent_run_id="run_valid_01",
                task_id="tsk_DOES_NOT_EXIST",
                tool_name="some_tool",
            )
        )

    # 2. Reject ToolExecution with invalid agent_run_id
    with pytest.raises(sqlite3.IntegrityError):
        await tool_repo.create(
            ToolExecution(
                id="exec_inv_run",
                agent_run_id="run_DOES_NOT_EXIST",
                task_id="tsk_valid_01",
                tool_name="some_tool",
            )
        )

    # 3. Accept ToolExecution with valid task_id and valid agent_run_id
    valid_exec = ToolExecution(
        id="exec_valid_01",
        agent_run_id="run_valid_01",
        task_id="tsk_valid_01",
        tool_name="some_tool",
        status=ToolExecutionState.RUNNING,
    )
    saved = await tool_repo.create(valid_exec)
    assert saved.id == "exec_valid_01"
