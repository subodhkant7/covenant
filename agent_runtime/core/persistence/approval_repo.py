"""SQLiteApprovalRepository: Durable single-use human approvals."""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import sqlite3

from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.tool import ToolRequest
from agent_runtime.core.persistence.connection import DatabaseManager
from agent_runtime.core.persistence.interfaces import IApprovalRepository
from agent_runtime.core.state.enums import ApprovalState


def _serialize_approval(approval: HumanApprovalRequest) -> Dict[str, Any]:
    return {
        "approval_id": approval.approval_id,
        "organization_id": approval.organization_id,
        "task_id": approval.task_id,
        "agent_run_id": approval.agent_run_id,
        "tool_request_json": json.dumps(approval.tool_request.model_dump(mode="json")),
        "policy_decision_id": approval.policy_decision_id,
        "status": approval.status.value,
        "requested_at": approval.requested_at.isoformat(),
        "timeout_at": approval.timeout_at.isoformat() if approval.timeout_at else None,
        "modified_arguments_json": json.dumps(approval.modified_arguments) if approval.modified_arguments else None,
        "reviewed_by": approval.reviewed_by,
        "reviewed_at": approval.reviewed_at.isoformat() if approval.reviewed_at else None,
        "reviewer_notes": approval.reviewer_notes,
    }


def _deserialize_approval(row: sqlite3.Row) -> HumanApprovalRequest:
    tool_req_dict = json.loads(row["tool_request_json"])
    return HumanApprovalRequest(
        approval_id=row["approval_id"],
        organization_id=row["organization_id"],
        task_id=row["task_id"],
        agent_run_id=row["agent_run_id"],
        tool_request=ToolRequest(**tool_req_dict),
        policy_decision_id=row["policy_decision_id"],
        status=ApprovalState(row["status"]),
        requested_at=datetime.fromisoformat(row["requested_at"]),
        timeout_at=datetime.fromisoformat(row["timeout_at"]) if row["timeout_at"] else None,
        modified_arguments=json.loads(row["modified_arguments_json"]) if row["modified_arguments_json"] else None,
        reviewed_by=row["reviewed_by"],
        reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] else None,
        reviewer_notes=row["reviewer_notes"],
    )


class SQLiteApprovalRepository(IApprovalRepository):
    """SQLite implementation of HumanApproval persistence."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def create(self, approval: HumanApprovalRequest) -> HumanApprovalRequest:
        def _insert():
            data = _serialize_approval(approval)
            query = """
            INSERT INTO human_approvals (
                approval_id, organization_id, task_id, agent_run_id, tool_request_json,
                policy_decision_id, status, requested_at, timeout_at, modified_arguments_json,
                reviewed_by, reviewed_at, reviewer_notes
            ) VALUES (
                :approval_id, :organization_id, :task_id, :agent_run_id, :tool_request_json,
                :policy_decision_id, :status, :requested_at, :timeout_at, :modified_arguments_json,
                :reviewed_by, :reviewed_at, :reviewer_notes
            )
            """
            with self.db.get_connection() as conn:
                conn.execute(query, data)
                conn.commit()
            return approval

        return await self.db.run_async(_insert)

    async def get(self, approval_id: str) -> Optional[HumanApprovalRequest]:
        def _get():
            with self.db.get_connection() as conn:
                cursor = conn.execute("SELECT * FROM human_approvals WHERE approval_id = ?", (approval_id,))
                row = cursor.fetchone()
                return _deserialize_approval(row) if row else None

        return await self.db.run_async(_get)

    async def get_by_task(self, task_id: str) -> Optional[HumanApprovalRequest]:
        def _get():
            with self.db.get_connection() as conn:
                cursor = conn.execute("SELECT * FROM human_approvals WHERE task_id = ? ORDER BY requested_at DESC LIMIT 1", (task_id,))
                row = cursor.fetchone()
                return _deserialize_approval(row) if row else None

        return await self.db.run_async(_get)

    async def atomic_approve(
        self,
        approval_id: str,
        reviewed_by: str,
        modified_arguments: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        mod_json = json.dumps(modified_arguments) if modified_arguments else None

        def _approve():
            query = """
            UPDATE human_approvals
            SET status = 'APPROVED', reviewed_by = ?, reviewed_at = ?,
                modified_arguments_json = ?, reviewer_notes = ?
            WHERE approval_id = ? AND status = 'PENDING'
            """
            with self.db.get_connection() as conn:
                cursor = conn.execute(query, (reviewed_by, now, mod_json, notes, approval_id))
                conn.commit()
                return cursor.rowcount == 1

        return await self.db.run_async(_approve)

    async def atomic_consume(self, approval_id: str) -> bool:
        """
        Single-use execution token. Transitions APPROVED -> EXECUTED.
        Fails if already EXECUTED or not APPROVED.
        """
        def _consume():
            query = """
            UPDATE human_approvals
            SET status = 'EXECUTED'
            WHERE approval_id = ? AND status = 'APPROVED'
            """
            with self.db.get_connection() as conn:
                cursor = conn.execute(query, (approval_id,))
                conn.commit()
                return cursor.rowcount == 1

        return await self.db.run_async(_consume)

    async def atomic_reject(
        self,
        approval_id: str,
        reviewed_by: str,
        notes: Optional[str] = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()

        def _reject():
            query = """
            UPDATE human_approvals
            SET status = 'REJECTED', reviewed_by = ?, reviewed_at = ?, reviewer_notes = ?
            WHERE approval_id = ? AND status = 'PENDING'
            """
            with self.db.get_connection() as conn:
                cursor = conn.execute(query, (reviewed_by, now, notes, approval_id))
                conn.commit()
                return cursor.rowcount == 1

        return await self.db.run_async(_reject)

    async def list_pending(self, organization_id: Optional[str] = None) -> List[HumanApprovalRequest]:
        def _list():
            query = "SELECT * FROM human_approvals WHERE status = 'PENDING'"
            params: List[Any] = []
            if organization_id:
                query += " AND organization_id = ?"
                params.append(organization_id)
            query += " ORDER BY requested_at ASC"

            with self.db.get_connection() as conn:
                cursor = conn.execute(query, params)
                return [_deserialize_approval(r) for r in cursor.fetchall()]

        return await self.db.run_async(_list)
