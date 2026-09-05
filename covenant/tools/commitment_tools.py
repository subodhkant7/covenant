"""Commitment lifecycle and risk assessment tools."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from covenant.domain.enums import (
    CommitmentCategory,
    CommitmentStatus,
    ConfidenceLevel,
    EvidenceSourceType,
    RiskLevel,
)
from covenant.domain.models import (
    Commitment,
    EvidenceReference,
    Party,
    utc_now,
)
from covenant.tools.base import BaseTool, ToolResult, global_tool_registry


class CreateCommitmentTool(BaseTool):
    name = "create_commitment"
    description = "Create a structured commitment from discovered promise data."
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "category": {"type": "string"},
            "promisor_name": {"type": "string"},
            "promisor_org": {"type": "string"},
            "promisee_name": {"type": "string"},
            "promisee_org": {"type": "string"},
            "due_date": {"type": "string", "description": "ISO timestamp"},
            "source_reference_id": {"type": "string"},
        },
        "required": ["title", "description", "promisor_name", "promisee_name"],
    }

    async def execute(
        self,
        title: str,
        description: str,
        promisor_name: str,
        promisee_name: str,
        category: str = "OTHER",
        promisor_org: Optional[str] = None,
        promisee_org: Optional[str] = None,
        due_date: Optional[str] = None,
        source_reference_id: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            parsed_due = datetime.fromisoformat(due_date).replace(tzinfo=timezone.utc) if due_date else None
            cat = CommitmentCategory(category) if category in CommitmentCategory.__members__ else CommitmentCategory.OTHER
            
            commitment = Commitment(
                title=title,
                description=description,
                category=cat,
                promisor=Party(name=promisor_name, organization=promisor_org, role="PROMISOR"),
                promisee=Party(name=promisee_name, organization=promisee_org, role="PROMISEE"),
                due_date=parsed_due,
                source_references=[source_reference_id] if source_reference_id else [],
                status=CommitmentStatus.DISCOVERED,
            )
            return ToolResult(success=True, data=commitment.model_dump(mode="json"))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FindEvidenceTool(BaseTool):
    name = "find_evidence"
    description = "Create an evidence reference linking an artifact to a commitment."
    parameters_schema = {
        "type": "object",
        "properties": {
            "source_type": {"type": "string"},
            "source_id": {"type": "string"},
            "title": {"type": "string"},
            "snippet": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["source_type", "source_id", "title", "snippet"],
    }

    async def execute(
        self,
        source_type: str,
        source_id: str,
        title: str,
        snippet: str,
        confidence: float = 0.95,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            src_type = EvidenceSourceType(source_type.upper()) if source_type.upper() in EvidenceSourceType.__members__ else EvidenceSourceType.EMAIL
            evidence = EvidenceReference(
                source_type=src_type,
                source_id=source_id,
                title=title,
                snippet=snippet,
                confidence=confidence,
            )
            return ToolResult(success=True, data=evidence.model_dump(mode="json"))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class CalculateRiskTool(BaseTool):
    name = "calculate_risk"
    description = "Determine risk level based on overdue duration, blockers, and contract stakes."
    parameters_schema = {
        "type": "object",
        "properties": {
            "is_overdue": {"type": "boolean"},
            "days_overdue": {"type": "number"},
            "is_blocking_downstream": {"type": "boolean"},
            "financial_impact": {"type": "number"},
            "elapsed_seconds": {"type": "number"},
            "hours_overdue": {"type": "number"},
        },
        "required": ["is_overdue"],
    }

    async def execute(
        self,
        is_overdue: bool,
        days_overdue: float = 0.0,
        is_blocking_downstream: bool = False,
        financial_impact: float = 0.0,
        elapsed_seconds: Optional[float] = None,
        hours_overdue: Optional[float] = None,
        has_conflict: bool = False,
        has_evidence_gap: bool = False,
        recommended_risk: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        if elapsed_seconds is not None:
            if elapsed_seconds > 0:
                is_overdue = True
                if days_overdue == 0.0:
                    days_overdue = elapsed_seconds / 86400.0
            else:
                is_overdue = False
                days_overdue = 0.0

        if not is_overdue:
            return ToolResult(
                success=True,
                data={
                    "risk": RiskLevel.LOW.value,
                    "rationale": "Commitment is on track.",
                    "is_overdue": False,
                    "days_overdue": 0.0,
                },
            )

        if (
            recommended_risk == RiskLevel.HIGH.value
            or days_overdue >= 5.0
            or (is_blocking_downstream and (days_overdue >= 2.0 or has_conflict or has_evidence_gap))
            or financial_impact > 10000
        ):
            risk = RiskLevel.HIGH
            rationale = (
                f"Overdue by {days_overdue:.1f} days with downstream blocking impact on dependent deliverables."
                if is_blocking_downstream
                else f"Overdue by {days_overdue:.1f} days with high contract stakes or financial risk."
            )
        elif days_overdue >= 2.0 or is_blocking_downstream:
            risk = RiskLevel.MEDIUM
            rationale = f"Overdue by {days_overdue:.1f} days; attention required to prevent escalation."
        else:
            risk = RiskLevel.LOW
            rationale = "Recently overdue (under 48 hours), standard follow-up recommended."

        return ToolResult(
            success=True,
            data={
                "risk": risk.value,
                "rationale": rationale,
                "is_overdue": True,
                "days_overdue": days_overdue,
            },
        )


def register_commitment_tools():
    global_tool_registry.register(CreateCommitmentTool())
    global_tool_registry.register(FindEvidenceTool())
    global_tool_registry.register(CalculateRiskTool())
