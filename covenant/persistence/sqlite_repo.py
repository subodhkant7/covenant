"""SQLite Repository Implementation for Covenant."""

import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from covenant.config import DEFAULT_DB_PATH
from covenant.domain.enums import CommitmentStatus, ObligationDirection, RiskLevel
from covenant.domain.models import (
    AgentEvent,
    Commitment,
    utc_now,
)
from covenant.persistence.repository import (
    AbstractCommitmentRepository,
    AbstractEventRepository,
)


class SQLiteCommitmentRepository(AbstractCommitmentRepository, AbstractEventRepository):
    """
    SQLite implementation of Commitment and Event repositories.
    Uses asyncio.to_thread with sqlite3 standard library for cross-platform stability.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)

    def _get_connection(self) -> sqlite3.Connection:
        """Create a standard sqlite3 connection with Row factory."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    async def initialize(self) -> None:
        """Apply the DDL schema to the database and run migrations."""
        schema_path = Path(__file__).parent / "schema.sql"
        schema_sql = schema_path.read_text(encoding="utf-8")

        def _init():
            with self._get_connection() as conn:
                conn.executescript(schema_sql)
                
                # Safe migrations for agent_events table
                cursor = conn.execute("PRAGMA table_info(agent_events)")
                columns = [row["name"] for row in cursor.fetchall()]
                new_cols = [
                    ("event_id", "TEXT DEFAULT ''"),
                    ("workflow_id", "TEXT"),
                    ("event_type", "TEXT DEFAULT 'ACTION'"),
                    ("result_status", "TEXT DEFAULT 'SUCCESS'"),
                    ("confidence", "REAL"),
                    ("risk", "TEXT"),
                    ("human_required", "INTEGER DEFAULT 0"),
                    ("correlation_id", "TEXT"),
                ]
                for col_name, col_type in new_cols:
                    if col_name not in columns:
                        try:
                            conn.execute(f"ALTER TABLE agent_events ADD COLUMN {col_name} {col_type}")
                        except Exception:
                            pass

                conn.commit()

        await asyncio.to_thread(_init)

    def _serialize_commitment(self, c: Commitment) -> Dict[str, Any]:
        """Convert Commitment Pydantic model to database record parameters."""
        return {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "category": c.category.value,
            "promisor_json": c.promisor.model_dump_json(),
            "promisee_json": c.promisee.model_dump_json(),
            "source_references_json": json.dumps(c.source_references),
            "evidence_references_json": json.dumps([e.model_dump(mode="json") for e in c.evidence_references]),
            "created_at": c.created_at.isoformat(),
            "promised_at": c.promised_at.isoformat() if c.promised_at else None,
            "due_date": c.due_date.isoformat() if c.due_date else None,
            "resolution_timestamp": c.resolution_timestamp.isoformat() if c.resolution_timestamp else None,
            "status": c.status.value,
            "risk": c.risk.value,
            "confidence": float(c.confidence),
            "dependencies_json": json.dumps(c.dependencies),
            "next_action_json": c.next_action.model_dump_json() if c.next_action else None,
            "required_human_approval": 1 if c.required_human_approval else 0,
            "action_history_json": json.dumps([h.model_dump(mode="json") for h in c.action_history]),
            "verification_requirements_json": json.dumps([v.model_dump(mode="json") for v in c.verification_requirements]),
            "verification_result_json": c.verification_result.model_dump_json() if c.verification_result else None,
            "tags_json": json.dumps(c.tags),
            "metadata_json": json.dumps(c.metadata),
            "obligation_direction": c.obligation_direction.value,
            "updated_at": utc_now().isoformat(),
        }

    def _deserialize_commitment(self, row: sqlite3.Row) -> Commitment:
        """Construct Commitment Pydantic model from SQLite row."""
        data = {
            "id": row["id"],
            "title": row["title"],
            "description": row["description"],
            "category": row["category"],
            "promisor": json.loads(row["promisor_json"]),
            "promisee": json.loads(row["promisee_json"]),
            "source_references": json.loads(row["source_references_json"]),
            "evidence_references": json.loads(row["evidence_references_json"]),
            "created_at": datetime.fromisoformat(row["created_at"]),
            "promised_at": datetime.fromisoformat(row["promised_at"]) if row["promised_at"] else None,
            "due_date": datetime.fromisoformat(row["due_date"]) if row["due_date"] else None,
            "resolution_timestamp": datetime.fromisoformat(row["resolution_timestamp"]) if row["resolution_timestamp"] else None,
            "status": row["status"],
            "risk": row["risk"],
            "confidence": float(row["confidence"]),
            "dependencies": json.loads(row["dependencies_json"]),
            "next_action": json.loads(row["next_action_json"]) if row["next_action_json"] else None,
            "required_human_approval": bool(row["required_human_approval"]),
            "action_history": json.loads(row["action_history_json"]),
            "verification_requirements": json.loads(row["verification_requirements_json"]),
            "verification_result": json.loads(row["verification_result_json"]) if row["verification_result_json"] else None,
            "tags": json.loads(row["tags_json"]),
            "metadata": json.loads(row["metadata_json"]),
        }
        return Commitment.model_validate(data)

    async def save(self, commitment: Commitment) -> Commitment:
        """Upsert a commitment into SQLite."""
        params = self._serialize_commitment(commitment)

        query = """
        INSERT INTO commitments (
            id, title, description, category, promisor_json, promisee_json,
            source_references_json, evidence_references_json, created_at, promised_at,
            due_date, resolution_timestamp, status, risk, confidence, dependencies_json,
            next_action_json, required_human_approval, action_history_json,
            verification_requirements_json, verification_result_json, tags_json,
            metadata_json, obligation_direction, updated_at
        ) VALUES (
            :id, :title, :description, :category, :promisor_json, :promisee_json,
            :source_references_json, :evidence_references_json, :created_at, :promised_at,
            :due_date, :resolution_timestamp, :status, :risk, :confidence, :dependencies_json,
            :next_action_json, :required_human_approval, :action_history_json,
            :verification_requirements_json, :verification_result_json, :tags_json,
            :metadata_json, :obligation_direction, :updated_at
        )
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            description=excluded.description,
            category=excluded.category,
            promisor_json=excluded.promisor_json,
            promisee_json=excluded.promisee_json,
            source_references_json=excluded.source_references_json,
            evidence_references_json=excluded.evidence_references_json,
            promised_at=excluded.promised_at,
            due_date=excluded.due_date,
            resolution_timestamp=excluded.resolution_timestamp,
            status=excluded.status,
            risk=excluded.risk,
            confidence=excluded.confidence,
            dependencies_json=excluded.dependencies_json,
            next_action_json=excluded.next_action_json,
            required_human_approval=excluded.required_human_approval,
            action_history_json=excluded.action_history_json,
            verification_requirements_json=excluded.verification_requirements_json,
            verification_result_json=excluded.verification_result_json,
            tags_json=excluded.tags_json,
            metadata_json=excluded.metadata_json,
            obligation_direction=excluded.obligation_direction,
            updated_at=excluded.updated_at
        """

        def _execute_save():
            with self._get_connection() as conn:
                conn.execute(query, params)
                conn.commit()

        await asyncio.to_thread(_execute_save)
        return commitment

    async def get_by_id(self, commitment_id: str) -> Optional[Commitment]:
        """Retrieve commitment by ID."""
        def _get():
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,))
                row = cursor.fetchone()
                return self._deserialize_commitment(row) if row else None

        return await asyncio.to_thread(_get)

    async def list_all(
        self,
        status: Optional[CommitmentStatus] = None,
        direction: Optional[ObligationDirection] = None,
        risk: Optional[RiskLevel] = None,
        search_query: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Commitment]:
        """Query commitments with filters."""
        query = "SELECT * FROM commitments WHERE 1=1"
        params: List[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status.value)
        if direction:
            query += " AND obligation_direction = ?"
            params.append(direction.value)
        if risk:
            query += " AND risk = ?"
            params.append(risk.value)
        if search_query:
            query += " AND (title LIKE ? OR description LIKE ?)"
            term = f"%{search_query}%"
            params.extend([term, term])

        query += " ORDER BY due_date ASC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        def _list():
            with self._get_connection() as conn:
                cursor = conn.execute(query, params)
                return [self._deserialize_commitment(row) for row in cursor.fetchall()]

        return await asyncio.to_thread(_list)

    async def delete(self, commitment_id: str) -> bool:
        """Delete commitment by ID."""
        def _delete():
            with self._get_connection() as conn:
                cursor = conn.execute("DELETE FROM commitments WHERE id = ?", (commitment_id,))
                conn.commit()
                return cursor.rowcount > 0

        return await asyncio.to_thread(_delete)

    async def count(
        self,
        status: Optional[CommitmentStatus] = None,
        direction: Optional[ObligationDirection] = None,
    ) -> int:
        """Count commitments."""
        query = "SELECT COUNT(*) as cnt FROM commitments WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status.value)
        if direction:
            query += " AND obligation_direction = ?"
            params.append(direction.value)

        def _count():
            with self._get_connection() as conn:
                cursor = conn.execute(query, params)
                row = cursor.fetchone()
                return row["cnt"] if row else 0

        return await asyncio.to_thread(_count)

    async def record_event(self, event: AgentEvent) -> AgentEvent:
        """Persist an agent event for observability."""
        evt_id = event.event_id or event.id
        params = {
            "id": evt_id,
            "event_id": evt_id,
            "timestamp": event.timestamp.isoformat(),
            "workflow_id": event.workflow_id,
            "commitment_id": event.commitment_id,
            "agent_name": event.agent or event.agent_name,
            "event_type": event.event_type or event.action_name or "ACTION",
            "tool_name": event.tool or event.tool_name,
            "action_name": event.action_name or event.event_type or "ACTION",
            "summary": event.summary,
            "result_status": event.result_status or "SUCCESS",
            "inputs_summary": event.inputs_summary,
            "result_summary": event.result_summary,
            "previous_state": event.state_before.value if event.state_before else (event.previous_state.value if event.previous_state else None),
            "new_state": event.state_after.value if event.state_after else (event.new_state.value if event.new_state else None),
            "confidence": event.confidence,
            "risk": event.risk.value if event.risk else None,
            "human_required": 1 if event.human_required else 0,
            "correlation_id": event.correlation_id,
            "rationale": event.rationale,
            "metadata_json": json.dumps(event.metadata),
        }

        query = """
        INSERT OR REPLACE INTO agent_events (
            id, event_id, timestamp, workflow_id, commitment_id, agent_name,
            event_type, tool_name, action_name, summary, result_status,
            inputs_summary, result_summary, previous_state, new_state,
            confidence, risk, human_required, correlation_id, rationale, metadata_json
        ) VALUES (
            :id, :event_id, :timestamp, :workflow_id, :commitment_id, :agent_name,
            :event_type, :tool_name, :action_name, :summary, :result_status,
            :inputs_summary, :result_summary, :previous_state, :new_state,
            :confidence, :risk, :human_required, :correlation_id, :rationale, :metadata_json
        )
        """

        def _record():
            with self._get_connection() as conn:
                conn.execute(query, params)
                conn.commit()

        await asyncio.to_thread(_record)
        return event

    async def list_events(
        self,
        commitment_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        workflow_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AgentEvent]:
        """Fetch audit trail events."""
        query = "SELECT * FROM agent_events WHERE 1=1"
        params: List[Any] = []

        if commitment_id:
            query += " AND commitment_id = ?"
            params.append(commitment_id)
        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)
        if workflow_id:
            query += " AND workflow_id = ?"
            params.append(workflow_id)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        def _list_events():
            with self._get_connection() as conn:
                cursor = conn.execute(query, params)
                events = []
                for row in cursor.fetchall():
                    events.append(
                        AgentEvent(
                            id=row["id"],
                            event_id=row["event_id"] if "event_id" in row.keys() else row["id"],
                            timestamp=datetime.fromisoformat(row["timestamp"]),
                            workflow_id=row["workflow_id"] if "workflow_id" in row.keys() else None,
                            commitment_id=row["commitment_id"],
                            agent=row["agent_name"],
                            agent_name=row["agent_name"],
                            event_type=row["event_type"] if "event_type" in row.keys() else "ACTION",
                            action_name=row["action_name"],
                            tool=row["tool_name"],
                            tool_name=row["tool_name"],
                            summary=row["summary"],
                            result_status=row["result_status"] if "result_status" in row.keys() else "SUCCESS",
                            inputs_summary=row["inputs_summary"],
                            result_summary=row["result_summary"],
                            state_before=CommitmentStatus(row["previous_state"]) if row["previous_state"] else None,
                            previous_state=CommitmentStatus(row["previous_state"]) if row["previous_state"] else None,
                            state_after=CommitmentStatus(row["new_state"]) if row["new_state"] else None,
                            new_state=CommitmentStatus(row["new_state"]) if row["new_state"] else None,
                            confidence=row["confidence"] if "confidence" in row.keys() else None,
                            risk=RiskLevel(row["risk"]) if ("risk" in row.keys() and row["risk"]) else None,
                            human_required=bool(row["human_required"]) if "human_required" in row.keys() else False,
                            correlation_id=row["correlation_id"] if "correlation_id" in row.keys() else None,
                            rationale=row["rationale"],
                            metadata=json.loads(row["metadata_json"]),
                        )
                    )
                return events

        return await asyncio.to_thread(_list_events)
