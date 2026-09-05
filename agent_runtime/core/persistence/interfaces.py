"""Persistence repository interfaces for the Agent Organization Runtime."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from agent_runtime.core.contracts.agent import AgentRun
from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.tool import Observation, ToolExecution
from agent_runtime.core.state.enums import IdempotencyStatus, TaskState


@dataclass
class IdempotencyReservation:
    """Outcome of an atomic idempotency key reservation attempt."""
    status: IdempotencyStatus
    cached_observation: Optional[Observation] = None
    error: Optional[str] = None


class ITaskRepository(ABC):
    """Abstract repository for persisting and querying Tasks."""

    @abstractmethod
    async def create(self, task: Task) -> Task:
        """Persists a new Task. Raises error if task with same ID already exists."""
        pass

    @abstractmethod
    async def get(self, task_id: str) -> Optional[Task]:
        """Retrieves a Task by ID."""
        pass

    @abstractmethod
    async def update(self, task: Task) -> None:
        """Updates full task state."""
        pass

    @abstractmethod
    async def atomic_claim(self, task_id: str, agent_id: str) -> bool:
        """
        Atomically claims a PENDING task for an agent, transitioning it to ROUTED.
        Returns True if claim succeeded, False if already claimed or not PENDING.
        """
        pass

    @abstractmethod
    async def atomic_transition(
        self,
        task_id: str,
        expected_status: TaskState,
        new_status: TaskState,
    ) -> bool:
        """
        Atomically transitions task status only if current status matches expected_status.
        Returns True on success, False if current status did not match.
        """
        pass

    @abstractmethod
    async def list_by_status(
        self,
        status: TaskState,
        organization_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Task]:
        """Queries tasks by status and optional organization."""
        pass

    @abstractmethod
    async def list_interrupted(self) -> List[Task]:
        """Finds tasks left in non-terminal transient states (ROUTED, RUNNING, VERIFYING)."""
        pass


class IAgentRunRepository(ABC):
    """Abstract repository for persisting and querying AgentRuns."""

    @abstractmethod
    async def create(self, run: AgentRun) -> AgentRun:
        """Persists a new AgentRun."""
        pass

    @abstractmethod
    async def get(self, run_id: str) -> Optional[AgentRun]:
        """Retrieves an AgentRun by ID."""
        pass

    @abstractmethod
    async def update(self, run: AgentRun) -> None:
        """Updates an AgentRun status and outputs."""
        pass

    @abstractmethod
    async def list_by_task(self, task_id: str) -> List[AgentRun]:
        """Retrieves all runs for a task, ordered chronologically."""
        pass

    @abstractmethod
    async def list_active(self) -> List[AgentRun]:
        """Finds runs in non-terminal execution states."""
        pass


class IToolExecutionRepository(ABC):
    """Abstract repository for persisting and querying ToolExecutions."""

    @abstractmethod
    async def create(self, execution: ToolExecution) -> ToolExecution:
        """Persists a new ToolExecution in QUEUED or RUNNING state."""
        pass

    @abstractmethod
    async def get(self, execution_id: str) -> Optional[ToolExecution]:
        """Retrieves a ToolExecution by ID."""
        pass

    @abstractmethod
    async def update(self, execution: ToolExecution) -> None:
        """Updates ToolExecution completion status, result, or error."""
        pass

    @abstractmethod
    async def list_by_run(self, agent_run_id: str) -> List[ToolExecution]:
        """Retrieves all tool executions for an agent run."""
        pass

    @abstractmethod
    async def list_by_task(self, task_id: str) -> List[ToolExecution]:
        """Retrieves all tool executions for a task."""
        pass

    @abstractmethod
    async def list_active(self) -> List[ToolExecution]:
        """Finds executions left in QUEUED or RUNNING state."""
        pass


class IApprovalRepository(ABC):
    """Abstract repository for managing durable HumanApprovalRequests."""

    @abstractmethod
    async def create(self, approval: HumanApprovalRequest) -> HumanApprovalRequest:
        """Persists a new pending approval request."""
        pass

    @abstractmethod
    async def get(self, approval_id: str) -> Optional[HumanApprovalRequest]:
        """Retrieves an approval request by ID."""
        pass

    @abstractmethod
    async def get_by_task(self, task_id: str) -> Optional[HumanApprovalRequest]:
        """Retrieves active approval request for a task if one exists."""
        pass

    @abstractmethod
    async def atomic_approve(
        self,
        approval_id: str,
        reviewed_by: str,
        modified_arguments: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Atomically marks a PENDING approval as APPROVED.
        Returns True on success, False if not PENDING.
        """
        pass

    @abstractmethod
    async def atomic_consume(self, approval_id: str) -> bool:
        """
        Atomically marks an APPROVED request as EXECUTED (single-use token).
        Returns True on success, False if not APPROVED (e.g. already consumed or rejected).
        """
        pass

    @abstractmethod
    async def atomic_reject(
        self,
        approval_id: str,
        reviewed_by: str,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Atomically marks a PENDING approval as REJECTED.
        Returns True on success, False if not PENDING.
        """
        pass

    @abstractmethod
    async def list_pending(self, organization_id: Optional[str] = None) -> List[HumanApprovalRequest]:
        """Lists pending approvals waiting for human action."""
        pass


class IIdempotencyStore(ABC):
    """Abstract store for checking, reserving, and recording tool idempotency."""

    @abstractmethod
    def compute_key(
        self,
        task_id: str,
        agent_run_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        is_tool_idempotent: bool = False,
    ) -> str:
        """Computes deterministic hash key."""
        pass

    @abstractmethod
    async def reserve_or_get(
        self,
        key: str,
        tool_name: str,
        execution_id: str,
    ) -> IdempotencyReservation:
        """
        Atomically attempts to reserve the idempotency key for this execution.
        """
        pass

    @abstractmethod
    async def mark_succeeded(self, key: str, execution_id: str, observation: Observation) -> None:
        pass

    @abstractmethod
    async def mark_failed(self, key: str, execution_id: str, observation: Optional[Observation] = None) -> None:
        pass

    @abstractmethod
    async def mark_unknown(self, key: str, execution_id: str, error: str) -> None:
        pass
