"""Authoritative Runtime Approval Service.

Sole authority over human approval transitions. The external agent has ZERO
access to this service and cannot invoke approve_human_request().
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import asyncio

from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.event import Event, EventType
from agent_runtime.core.interfaces.telemetry import IEventSink
from agent_runtime.core.persistence.interfaces import IApprovalRepository
from agent_runtime.core.state.enums import ApprovalState


class InMemoryApprovalRepository(IApprovalRepository):
    """In-memory thread-safe implementation of IApprovalRepository for tests and standalone runs."""

    def __init__(self):
        self._approvals: Dict[str, HumanApprovalRequest] = {}
        self._lock = asyncio.Lock()

    async def create(self, approval: HumanApprovalRequest) -> HumanApprovalRequest:
        async with self._lock:
            self._approvals[approval.approval_id] = approval.model_copy(deep=True)
            return approval

    async def get(self, approval_id: str) -> Optional[HumanApprovalRequest]:
        async with self._lock:
            appr = self._approvals.get(approval_id)
            return appr.model_copy(deep=True) if appr else None

    async def get_by_task(self, task_id: str) -> Optional[HumanApprovalRequest]:
        async with self._lock:
            for appr in reversed(list(self._approvals.values())):
                if appr.task_id == task_id:
                    return appr.model_copy(deep=True)
            return None

    async def atomic_approve(
        self,
        approval_id: str,
        reviewed_by: str,
        modified_arguments: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> bool:
        async with self._lock:
            appr = self._approvals.get(approval_id)
            if not appr or appr.status != ApprovalState.PENDING:
                return False
            appr.status = ApprovalState.APPROVED
            appr.reviewed_by = reviewed_by
            appr.reviewed_at = datetime.now(timezone.utc)
            if modified_arguments:
                appr.modified_arguments = dict(modified_arguments)
            if notes:
                appr.reviewer_notes = notes
            return True

    async def atomic_consume(self, approval_id: str) -> bool:
        async with self._lock:
            appr = self._approvals.get(approval_id)
            if not appr or appr.status != ApprovalState.APPROVED:
                return False
            appr.status = ApprovalState.EXECUTED
            return True

    async def atomic_reject(
        self,
        approval_id: str,
        reviewed_by: str,
        notes: Optional[str] = None,
    ) -> bool:
        async with self._lock:
            appr = self._approvals.get(approval_id)
            if not appr or appr.status != ApprovalState.PENDING:
                return False
            appr.status = ApprovalState.REJECTED
            appr.reviewed_by = reviewed_by
            appr.reviewed_at = datetime.now(timezone.utc)
            if notes:
                appr.reviewer_notes = notes
            return True

    async def list_pending(self, organization_id: Optional[str] = None) -> List[HumanApprovalRequest]:
        async with self._lock:
            results = []
            for appr in self._approvals.values():
                if appr.status == ApprovalState.PENDING:
                    if not organization_id or appr.organization_id == organization_id:
                        results.append(appr.model_copy(deep=True))
            return results


class RuntimeApprovalService:
    """Sole runtime authority governing the lifecycle of HumanApprovalRequests."""

    def __init__(
        self,
        approval_repository: Optional[IApprovalRepository] = None,
        event_sink: Optional[IEventSink] = None,
    ):
        self.repo = approval_repository or InMemoryApprovalRepository()
        self.sink = event_sink

    async def approve_human_request(
        self,
        approval_id: str,
        organization_id: str,
        task_id: str,
        agent_run_id: str,
        tool_name: str,
        reviewed_by: str,
        modified_arguments: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> HumanApprovalRequest:
        """Authoritative human authorization transition.

        Validates all 9 boundary conditions before transitioning PENDING -> APPROVED:
        1. Reviewer identity supplied.
        2. Approval exists in repository.
        3. Not already executed.
        4. In PENDING state.
        5. Request has not expired.
        6. Organization ID matches.
        7. Task ID matches.
        8. Agent Run ID matches.
        9. Tool name matches.
        """
        # 1. Reviewer identity supplied
        if not reviewed_by or not isinstance(reviewed_by, str) or not reviewed_by.strip():
            raise ValueError("Reviewer identity must be a non-empty string.")

        # 2. Approval exists
        approval = await self.repo.get(approval_id)
        if not approval:
            raise KeyError(f"Approval request '{approval_id}' was not found in runtime repository.")

        # 3. Not already executed
        if approval.status == ApprovalState.EXECUTED:
            raise ValueError(f"Approval request '{approval_id}' has already been executed.")

        # 4. In PENDING state
        if approval.status != ApprovalState.PENDING:
            raise ValueError(
                f"Approval request '{approval_id}' cannot be approved: current state is {approval.status.value}, expected PENDING."
            )

        # 5. Expiration check
        if approval.timeout_at and datetime.now(timezone.utc) > approval.timeout_at:
            raise TimeoutError(f"Approval request '{approval_id}' expired at {approval.timeout_at.isoformat()}.")

        # 6. Organization match
        if approval.organization_id != organization_id:
            raise PermissionError(
                f"Organization mismatch: request belongs to '{approval.organization_id}', not '{organization_id}'."
            )

        # 7. Task match
        if approval.task_id != task_id:
            raise ValueError(
                f"Task ID mismatch: request belongs to task '{approval.task_id}', not '{task_id}'."
            )

        # 8. Agent run match
        if approval.agent_run_id != agent_run_id:
            raise ValueError(
                f"Agent run mismatch: request belongs to run '{approval.agent_run_id}', not '{agent_run_id}'."
            )

        # 9. Tool name match
        if approval.tool_request.tool_name != tool_name:
            raise ValueError(
                f"Tool name mismatch: request was for '{approval.tool_request.tool_name}', not '{tool_name}'."
            )

        # Execute atomic transition
        success = await self.repo.atomic_approve(
            approval_id=approval_id,
            reviewed_by=reviewed_by.strip(),
            modified_arguments=modified_arguments,
            notes=notes,
        )
        if not success:
            raise RuntimeError(f"Atomic approval transition failed for approval '{approval_id}'.")

        updated = await self.repo.get(approval_id)

        if self.sink:
            await self.sink.record(
                Event(
                    trace_id=f"trc_{task_id}",
                    organization_id=organization_id,
                    task_id=task_id,
                    agent_run_id=agent_run_id,
                    event_type=EventType.APPROVAL_DECIDED,
                    summary=f"Approval '{approval_id}' authorized by reviewer '{reviewed_by.strip()}'.",
                    payload={
                        "approval_id": approval_id,
                        "status": ApprovalState.APPROVED.value,
                        "reviewed_by": reviewed_by.strip(),
                        "has_modified_arguments": modified_arguments is not None,
                    },
                )
            )

        return updated

    async def reject_human_request(
        self,
        approval_id: str,
        organization_id: str,
        task_id: str,
        agent_run_id: str,
        reviewed_by: str,
        notes: Optional[str] = None,
    ) -> HumanApprovalRequest:
        """Authoritative human rejection transition."""
        if not reviewed_by or not isinstance(reviewed_by, str) or not reviewed_by.strip():
            raise ValueError("Reviewer identity must be a non-empty string.")

        approval = await self.repo.get(approval_id)
        if not approval:
            raise KeyError(f"Approval request '{approval_id}' was not found in runtime repository.")

        if approval.status != ApprovalState.PENDING:
            raise ValueError(
                f"Approval request '{approval_id}' cannot be rejected: current state is {approval.status.value}, expected PENDING."
            )

        if approval.organization_id != organization_id or approval.task_id != task_id:
            raise PermissionError("Organization or task mismatch on rejection.")

        success = await self.repo.atomic_reject(
            approval_id=approval_id,
            reviewed_by=reviewed_by.strip(),
            notes=notes,
        )
        if not success:
            raise RuntimeError(f"Atomic rejection failed for approval '{approval_id}'.")

        return await self.repo.get(approval_id)
