"""Persistence module exports."""

from agent_runtime.core.persistence.agent_run_repo import SQLiteAgentRunRepository
from agent_runtime.core.persistence.approval_repo import SQLiteApprovalRepository
from agent_runtime.core.persistence.connection import CURRENT_SCHEMA_VERSION, DatabaseManager
from agent_runtime.core.persistence.idempotency_store import SQLiteIdempotencyStore
from agent_runtime.core.persistence.interfaces import (
    IApprovalRepository,
    IAgentRunRepository,
    IIdempotencyStore,
    ITaskRepository,
    IToolExecutionRepository,
)
from agent_runtime.core.persistence.recovery import RecoveryReport, RuntimeCrashRecoveryService
from agent_runtime.core.persistence.task_repo import SQLiteTaskRepository
from agent_runtime.core.persistence.tool_exec_repo import SQLiteToolExecutionRepository

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "DatabaseManager",
    "IApprovalRepository",
    "IAgentRunRepository",
    "IIdempotencyStore",
    "ITaskRepository",
    "IToolExecutionRepository",
    "RecoveryReport",
    "RuntimeCrashRecoveryService",
    "SQLiteAgentRunRepository",
    "SQLiteApprovalRepository",
    "SQLiteIdempotencyStore",
    "SQLiteTaskRepository",
    "SQLiteToolExecutionRepository",
]
