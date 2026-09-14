"""FastAPI REST API Routes for Covenant."""

import asyncio
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from agent_runtime.core.contracts.agent import AgentRun
from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.tool import ToolRequest
from agent_runtime.core.state.enums import ApprovalState
from covenant.agents.base import AgentContext
from covenant.agents.supervisor import SupervisorAgent
from covenant.domain.enums import (
    ActionStatus,
    ActionType,
    CommitmentStatus,
    ObligationDirection,
    RiskLevel,
)
from covenant.domain.models import AgentEvent, Commitment, utc_now
from covenant.llm.factory import get_model_provider
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.state_machine.machine import CommitmentStateMachine
from covenant.synthetic_data.store import workspace_store
from covenant.tools import initialize_tools
from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap, CovenantRuntimeEnvironment

router = APIRouter(prefix="/api")

# Repository, runtime environment, and agent singletons for local runtime
repo = SQLiteCommitmentRepository()
runtime_env: CovenantRuntimeEnvironment = CovenantRuntimeBootstrap.assemble()
tools = initialize_tools()
llm = get_model_provider()
supervisor = SupervisorAgent(llm=llm, tools=tools, commitment_repo=repo, event_repo=repo, runtime_env=runtime_env)


class DecisionActionRequest(BaseModel):
    notes: Optional[str] = None
    edited_payload: Optional[Dict[str, Any]] = None


class VerifyRequest(BaseModel):
    simulated_params: Optional[Dict[str, Any]] = None


class SimulateReplyRequest(BaseModel):
    fulfilled: bool = True


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "covenant", "version": "0.1.0"}


@router.get("/health/model")
async def health_model_check():
    """Safe model provider health and diagnostics check without credential disclosure."""
    from covenant.config import settings
    provider = settings.model_provider
    status: Dict[str, Any] = {
        "provider": provider,
        "configured_model": settings.ollama_model if provider == "ollama" else (settings.bedrock_model_id or "deterministic"),
        "fallback_model": settings.ollama_fallback_model if provider == "ollama" else None,
        "secondary_fallback_model": settings.ollama_secondary_fallback_model if provider == "ollama" else None,
        "connectivity": "unknown",
        "tool_calling_supported": True,
        "details": {},
    }

    if hasattr(llm, "get_diagnostics"):
        diag = await llm.get_diagnostics()
        status["connectivity"] = "connected" if diag.get("reachable") else "offline"
        status["details"] = {
            "installed_models": [m.get("name") for m in diag.get("installed_models", [])],
            "fallback_count": diag.get("fallback_count", 0),
            "recent_fallbacks": diag.get("recent_fallbacks", []),
        }
    elif hasattr(llm, "is_available"):
        avail = await llm.is_available()
        status["connectivity"] = "connected" if avail else "offline"
    else:
        status["connectivity"] = "ready"

    return status


@router.get("/stats")
async def get_stats():
    """Return dashboard operational metrics."""
    all_comms = await repo.list_all(limit=500)
    they_owe = [c for c in all_comms if c.obligation_direction == ObligationDirection.THEY_OWE_US]
    we_owe = [c for c in all_comms if c.obligation_direction == ObligationDirection.WE_OWE_THEM]
    overdue = [c for c in all_comms if c.is_overdue or c.status == CommitmentStatus.OVERDUE]
    awaiting_approval = [c for c in all_comms if c.status == CommitmentStatus.AWAITING_APPROVAL]
    resolved = [c for c in all_comms if c.status == CommitmentStatus.RESOLVED]

    return {
        "total_commitments": len(all_comms),
        "they_owe_count": len(they_owe),
        "we_owe_count": len(we_owe),
        "overdue_count": len(overdue),
        "awaiting_approval_count": len(awaiting_approval),
        "resolved_count": len(resolved),
    }


@router.get("/commitments", response_model=List[Commitment])
async def list_commitments(
    status: Optional[CommitmentStatus] = None,
    direction: Optional[ObligationDirection] = None,
    risk: Optional[RiskLevel] = None,
    q: Optional[str] = Query(None, description="Search term"),
):
    """List commitments with optional filtering."""
    return await repo.list_all(status=status, direction=direction, risk=risk, search_query=q)


@router.get("/commitments/{commitment_id}", response_model=Commitment)
async def get_commitment(commitment_id: str):
    """Get single commitment by ID."""
    com = await repo.get_by_id(commitment_id)
    if not com:
        raise HTTPException(status_code=404, detail="Commitment not found")
    return com


def build_commitment_decision_trace(com: Commitment, events: List[AgentEvent]) -> Dict[str, Any]:
    """
    Assemble the authoritative Commitment Decision Trace from persisted domain state
    and real audit trail telemetry. Exposes no hidden chain-of-thought or credentials.
    """
    sorted_events = sorted(events, key=lambda e: e.timestamp)

    # 1. Commitment core metadata
    com_data = {
        "id": com.id,
        "title": com.title,
        "description": com.description,
        "category": com.category.value if hasattr(com.category, "value") else str(com.category),
        "promisor": com.promisor.model_dump(mode="json"),
        "promisee": com.promisee.model_dump(mode="json"),
        "obligation_direction": com.obligation_direction.value,
        "due_date": com.due_date.isoformat() if com.due_date else None,
        "promised_at": com.promised_at.isoformat() if com.promised_at else None,
        "created_at": com.created_at.isoformat() if com.created_at else None,
        "status": com.status.value,
        "risk": com.risk.value,
        "confidence": com.confidence,
        "health": com.health.value,
        "is_overdue": com.is_overdue,
        "days_overdue": com.days_overdue,
        "hours_overdue": com.hours_overdue,
        "source_references": com.source_references,
        "resolution_timestamp": com.resolution_timestamp.isoformat() if com.resolution_timestamp else None,
    }

    # 2. Corroborating Evidence
    evidence_items = []
    for ev in com.evidence_references:
        evidence_items.append({
            "id": ev.id,
            "source_type": ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type),
            "source_id": ev.source_id,
            "title": ev.title,
            "snippet": ev.snippet,
            "confidence": ev.confidence,
            "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
            "url_or_path": ev.url_or_path,
        })

    # Evidence Assessment (Synthesized Multi-Source Intelligence & Conflict Detection)
    evidence_assessment = None
    if com.evidence_assessment:
        evidence_assessment = com.evidence_assessment.model_dump(mode="json")
    elif com.metadata and "evidence_assessment" in com.metadata:
        evidence_assessment = com.metadata["evidence_assessment"]

    # 3. Risk Assessment

    risk_event = next(
        (e for e in sorted_events if e.action_name in ("CALCULATE_RISK", "EVALUATE_RISK") or e.event_type in ("RISK", "EVALUATION")),
        None,
    )
    risk_rationale = (
        risk_event.rationale or risk_event.summary
        if risk_event and (risk_event.rationale or risk_event.summary)
        else (
            f"Overdue by {com.days_overdue:.1f} days against deadline {com.due_date.isoformat()}."
            if com.is_overdue and com.due_date
            else f"Evaluated at {com.risk.value} risk with {int(com.confidence * 100)}% confidence."
        )
    )
    if com.evidence_assessment and com.evidence_assessment.is_blocking_downstream:
        blocking_impact = "Phase 3 engineering kickoff blocked on client approval"
    elif com.dependencies:
        blocking_impact = f"Blocks {len(com.dependencies)} downstream commitment(s)"
    else:
        blocking_impact = "No downstream dependencies blocked"

    risk_info = {
        "risk_level": com.risk.value,
        "confidence": com.confidence,
        "is_overdue": com.is_overdue,
        "days_overdue": com.days_overdue,
        "hours_overdue": com.hours_overdue,
        "overdue_duration": com.overdue_duration(),
        "rationale": risk_rationale,
        "blocking_impact": blocking_impact,
    }

    # 4. Action Details
    action_info = None
    if com.next_action:
        act = com.next_action
        action_info = {
            "id": act.id,
            "action_type": act.action_type.value if hasattr(act.action_type, "value") else str(act.action_type),
            "description": act.description,
            "status": act.status.value if hasattr(act.status, "value") else str(act.status),
            "risk": act.risk.value if hasattr(act.risk, "value") else str(act.risk),
            "requires_human_approval": act.requires_human_approval,
            "approval_reason": act.approval_reason,
            "recipient": act.recipient,
            "subject": act.subject,
            "created_at": act.created_at.isoformat() if act.created_at else None,
            "decided_at": act.decided_at.isoformat() if act.decided_at else None,
            "executed_at": act.executed_at.isoformat() if act.executed_at else None,
        }

    # 5. Policy Decision
    policy_event = next(
        (e for e in sorted_events if e.action_name == "EVALUATE_POLICY" or e.event_type == "POLICY"),
        None,
    )
    policy_rules = []
    if policy_event and policy_event.metadata and "rules" in policy_event.metadata:
        policy_rules = policy_event.metadata["rules"]
    elif com.next_action and com.next_action.approval_reason:
        policy_rules = [com.next_action.approval_reason]

    requires_approval = (
        policy_event.metadata.get("requires_human_approval")
        if (policy_event and policy_event.metadata and "requires_human_approval" in policy_event.metadata)
        else (com.next_action.requires_human_approval if com.next_action else False)
    )

    policy_info = {
        "decision": "HUMAN_APPROVAL_REQUIRED" if requires_approval else "AUTONOMOUS_PERMITTED",
        "rules_triggered": policy_rules,
        "requires_human_approval": requires_approval,
        "rationale": (
            (policy_event.rationale if policy_event else None)
            or (com.next_action.approval_reason if com.next_action else None)
            or ("Mandatory approval required by policy" if requires_approval else "Autonomous execution permitted")
        ),
        "evaluated_at": policy_event.timestamp.isoformat() if policy_event else (com.next_action.created_at.isoformat() if com.next_action else None),
        "authority": "PolicyAgent",
    }

    # 6. Human Approval
    dispatch_event = next(
        (e for e in sorted_events if e.action_name == "DISPATCH_ACTION" or e.event_type == "DISPATCH_ACTION"),
        None,
    )
    approval_status = "NOT_STARTED"
    reviewer = None
    decided_at = None
    approval_notes = None

    if com.next_action:
        decided_at = com.next_action.decided_at.isoformat() if com.next_action.decided_at else None
        approval_notes = com.next_action.decision_notes

    if com.status == CommitmentStatus.AWAITING_APPROVAL or (com.next_action and com.next_action.status == ActionStatus.AWAITING_APPROVAL):
        approval_status = "PENDING"
    elif (com.next_action and com.next_action.status == ActionStatus.APPROVED) or dispatch_event or com.status in (CommitmentStatus.EXECUTING, CommitmentStatus.VERIFYING, CommitmentStatus.RESOLVED):
        approval_status = "APPROVED"
        reviewer = "User"
    elif com.status == CommitmentStatus.REJECTED or (com.next_action and com.next_action.status == ActionStatus.REJECTED):
        approval_status = "REJECTED"
        reviewer = "User"
    elif com.next_action and not com.next_action.requires_human_approval:
        approval_status = "NOT_REQUIRED"

    approval_info = {
        "status": approval_status,
        "reviewer": reviewer,
        "decision_timestamp": decided_at or (dispatch_event.timestamp.isoformat() if dispatch_event else None),
        "notes": approval_notes or ("Authorized via Decision Surface" if approval_status == "APPROVED" else None),
        "authority": "Human Operator" if reviewer else None,
    }

    # 7. Action Execution
    execution_status = "NOT_STARTED"
    execution_timestamp = None
    execution_id = None
    tool_executed = None
    result_summary = "Awaiting authorization prior to dispatch."

    if dispatch_event:
        execution_status = "COMPLETED"
        execution_timestamp = dispatch_event.timestamp.isoformat()
        tool_executed = dispatch_event.tool or dispatch_event.tool_name
        execution_id = dispatch_event.metadata.get("execution_id") if dispatch_event.metadata else None
        result_summary = dispatch_event.summary
    elif com.status in (CommitmentStatus.VERIFYING, CommitmentStatus.RESOLVED):
        execution_status = "COMPLETED"
        execution_timestamp = com.next_action.executed_at.isoformat() if com.next_action and com.next_action.executed_at else None
        tool_executed = com.next_action.payload.get("tool") if com.next_action and com.next_action.payload else "send_followup"
        result_summary = "Action dispatched through runtime execution engine into communication stream."
    elif com.status == CommitmentStatus.EXECUTING:
        execution_status = "IN_PROGRESS"
        result_summary = "Runtime engine currently dispatching action."

    execution_info = {
        "status": execution_status,
        "timestamp": execution_timestamp,
        "tool_name": tool_executed,
        "execution_id": execution_id,
        "result_summary": result_summary,
        "authority": "ExecutionEngine",
    }

    # 8. Post-Dispatch Verification
    verification_event = next(
        (e for e in reversed(sorted_events) if e.action_name == "VERIFY_RESOLUTION" or e.event_type == "VERIFICATION"),
        None,
    )
    verification_status = "NOT_STARTED"
    verified_at = None
    gate_result = "NOT_RUN"
    verif_rationale = "Verification not initiated."
    evidence_ids = []
    fresh_evidence = []

    if com.verification_result:
        vr = com.verification_result
        gate_result = "PASSED" if vr.is_verified else ("FAILED" if com.status == CommitmentStatus.FAILED else "PENDING_PROOF")
        verification_status = "VERIFIED" if vr.is_verified else ("FAILED" if com.status == CommitmentStatus.FAILED else "IN_PROGRESS")
        verified_at = vr.verified_at.isoformat() if hasattr(vr, "verified_at") and vr.verified_at else (verification_event.timestamp.isoformat() if verification_event else None)
        verif_rationale = vr.rationale
        evidence_ids = vr.evidence_ids or []
        for ev in com.evidence_references:
            if ev.source_id in evidence_ids or "REPLY" in ev.source_id:
                fresh_evidence.append({
                    "id": ev.id,
                    "source_id": ev.source_id,
                    "source_type": ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type),
                    "title": ev.title,
                    "snippet": ev.snippet,
                    "confidence": ev.confidence,
                })
    elif com.status == CommitmentStatus.VERIFYING:
        verification_status = "IN_PROGRESS"
        gate_result = "AWAITING_COUNTERPARTY_RESPONSE"
        verif_rationale = "Action executed. Covenant VerificationGate actively monitoring for independent fulfillment proof."
    elif com.status == CommitmentStatus.FAILED:
        verification_status = "FAILED"
        gate_result = "FAILED"
        verif_rationale = verification_event.rationale if verification_event else "Counterparty verification failed."

    verification_info = {
        "status": verification_status,
        "timestamp": verified_at,
        "gate_result": gate_result,
        "rationale": verif_rationale,
        "evidence_ids": evidence_ids,
        "fresh_evidence": fresh_evidence,
        "authority": "VerificationGate (Authoritative Verifier)",
    }

    # 9. Final Outcome
    outcome_summary = ""
    if com.status == CommitmentStatus.RESOLVED:
        outcome_summary = f"Commitment successfully fulfilled and independently verified at {com.resolution_timestamp.isoformat() if com.resolution_timestamp else 'N/A'}."
    elif com.status == CommitmentStatus.FAILED:
        outcome_summary = "Commitment failed independent verification by VerificationGate."
    elif com.status == CommitmentStatus.VERIFYING:
        outcome_summary = "Remedy action dispatched; waiting for external corroborating proof."
    elif com.status == CommitmentStatus.AWAITING_APPROVAL:
        outcome_summary = "Action formulated; awaiting human authorization on decision surface."
    else:
        outcome_summary = f"Commitment in {com.status.value} state."

    final_outcome = {
        "status": com.status.value,
        "is_resolved": com.status == CommitmentStatus.RESOLVED,
        "resolved_at": com.resolution_timestamp.isoformat() if com.resolution_timestamp else None,
        "summary": outcome_summary,
        "authority": "CovenantStateMachine",
    }

    # 10. Chronological Stages Stepper Contract (10 stages)
    # Commitment detected -> Evidence gathered -> Risk calculated -> Action proposed -> Policy decision
    # -> Human approval -> Action executed -> Verification started -> Verification evidence -> Final outcome
    stages = [
        {
            "step": 1,
            "name": "Commitment detected",
            "status": "COMPLETED",
            "actor": "CommitmentAgent",
            "summary": f"Detected commitment: {com.title}",
            "timestamp": com.created_at.isoformat() if com.created_at else None,
        },
        {
            "step": 2,
            "name": "Evidence gathered",
            "status": "COMPLETED" if evidence_items else "PENDING",
            "actor": "EvidenceAgent",
            "summary": f"Corroborated {len(evidence_items)} evidence artifact(s) from workspace",
            "timestamp": evidence_items[0]["timestamp"] if evidence_items and evidence_items[0]["timestamp"] else None,
        },
        {
            "step": 3,
            "name": "Risk calculated",
            "status": "COMPLETED",
            "actor": "RiskAgent",
            "summary": f"Risk assessed as {com.risk.value} ({'Overdue' if com.is_overdue else 'Active'})",
            "timestamp": risk_event.timestamp.isoformat() if risk_event else (com.created_at.isoformat() if com.created_at else None),
        },
        {
            "step": 4,
            "name": "Action proposed",
            "status": "COMPLETED" if action_info else "PENDING",
            "actor": "ResolutionAgent",
            "summary": action_info["description"] if action_info else "No operational remedy proposed yet",
            "timestamp": action_info["created_at"] if action_info else None,
        },
        {
            "step": 5,
            "name": "Policy decision",
            "status": "COMPLETED" if policy_info["rules_triggered"] or action_info else "PENDING",
            "actor": "PolicyAgent",
            "summary": f"Policy: {policy_info['decision']} ({', '.join(policy_info['rules_triggered']) if policy_info['rules_triggered'] else 'Autonomous allowed'})",
            "timestamp": policy_info["evaluated_at"],
        },
        {
            "step": 6,
            "name": "Human approval",
            "status": (
                "COMPLETED" if approval_info["status"] in ("APPROVED", "NOT_REQUIRED")
                else ("FAILED" if approval_info["status"] == "REJECTED"
                else ("ACTIVE" if approval_info["status"] == "PENDING" else "PENDING"))
            ),
            "actor": approval_info["authority"] or "Human Operator",
            "summary": (
                f"Approved by {approval_info['reviewer']}" if approval_info["status"] == "APPROVED"
                else ("Approval rejected" if approval_info["status"] == "REJECTED"
                else ("Pending review on Decision Surface" if approval_info["status"] == "PENDING" else "Not required"))
            ),
            "timestamp": approval_info["decision_timestamp"],
        },
        {
            "step": 7,
            "name": "Action executed",
            "status": (
                "COMPLETED" if execution_info["status"] == "COMPLETED"
                else ("ACTIVE" if execution_info["status"] == "IN_PROGRESS" else "PENDING")
            ),
            "actor": "ExecutionEngine",
            "summary": execution_info["result_summary"],
            "timestamp": execution_info["timestamp"],
        },
        {
            "step": 8,
            "name": "Verification started",
            "status": (
                "COMPLETED" if com.status in (CommitmentStatus.VERIFYING, CommitmentStatus.RESOLVED, CommitmentStatus.FAILED)
                else "PENDING"
            ),
            "actor": "VerificationAgent",
            "summary": "Independent VerificationGate loop initiated",
            "timestamp": execution_info["timestamp"],
        },
        {
            "step": 9,
            "name": "Verification evidence",
            "status": (
                "COMPLETED" if verification_info["fresh_evidence"] or (com.verification_result and com.verification_result.is_verified)
                else ("ACTIVE" if com.status == CommitmentStatus.VERIFYING else "PENDING")
            ),
            "actor": "VerificationGate",
            "summary": (
                f"Obtained fresh corroborating evidence: {len(verification_info['fresh_evidence'])} item(s)"
                if verification_info["fresh_evidence"]
                else "Awaiting fresh counterparty evidence"
            ),
            "timestamp": verification_info["timestamp"],
        },
        {
            "step": 10,
            "name": "Final outcome",
            "status": (
                "COMPLETED" if com.status == CommitmentStatus.RESOLVED
                else ("FAILED" if com.status == CommitmentStatus.FAILED
                else ("ACTIVE" if com.status == CommitmentStatus.VERIFYING else "PENDING"))
            ),
            "actor": "CommitmentStateMachine",
            "summary": final_outcome["summary"],
            "timestamp": final_outcome["resolved_at"],
        },
    ]

    # 11. Timeline: Build strictly from persisted audit records
    timeline_items = []
    for evt in sorted_events:
        timeline_items.append({
            "id": evt.id or evt.event_id,
            "timestamp": evt.timestamp.isoformat(),
            "event_type": evt.event_type or evt.action_name,
            "actor": evt.agent or evt.agent_name,
            "summary": evt.summary,
            "evidence_reference": evt.metadata.get("evidence_ids") or (f"[{evt.tool}]" if evt.tool else None),
            "result_status": evt.result_status,
            "rationale": evt.rationale,
            "state_after": evt.state_after.value if evt.state_after else (evt.new_state.value if evt.new_state else None),
        })

    # Merge in action_history if any distinct transition is not present in events
    for h in com.action_history:
        h_ts = h.timestamp.isoformat()
        if not any(t["summary"] == h.summary for t in timeline_items):
            timeline_items.append({
                "id": h.id,
                "timestamp": h_ts,
                "event_type": h.action_type.value if h.action_type else "STATE_TRANSITION",
                "actor": h.agent_name,
                "summary": h.summary,
                "evidence_reference": None,
                "result_status": "SUCCESS",
                "rationale": h.details.get("reason") if h.details else None,
                "state_after": h.state_after.value if h.state_after else None,
            })

    timeline_items.sort(key=lambda x: x["timestamp"])

    return {
        "commitment_id": com.id,
        "title": com.title,
        "current_state": com.status.value,
        "current_risk": com.risk.value,
        "health": com.health.value,
        "commitment": com_data,
        "stages": stages,
        "evidence": evidence_items,
        "evidence_assessment": evidence_assessment,
        "risk": risk_info,

        "action": action_info,
        "policy_decision": policy_info,
        "approval": approval_info,
        "execution": execution_info,
        "verification": verification_info,
        "final_outcome": final_outcome,
        "timeline": timeline_items,
        "timeline_source": "persisted_sqlite_audit_events" if timeline_items else "none_recorded",
    }


@router.get("/commitments/{commitment_id}/trace")
async def get_commitment_decision_trace(commitment_id: str):
    """
    Retrieve the full, auditable Decision Trace for a commitment.
    Composes real persisted domain state and telemetry audit events.
    Read-only, non-mutating, zero model private reasoning exposed.
    """
    com = await repo.get_by_id(commitment_id)
    if not com:
        raise HTTPException(status_code=404, detail=f"Commitment '{commitment_id}' not found.")

    events = await repo.list_events(commitment_id=commitment_id, limit=200)
    return build_commitment_decision_trace(com, events)


@router.get("/map")
async def get_commitment_map():
    """
    Generate graph payload for the visual Commitment Map.
    Nodes represent Parties, Commitments, Evidence, and Actions.
    Edges represent causal obligations, proofs, and remedies.
    """
    commitments = await repo.list_all(limit=200)
    nodes = []
    edges = []
    seen_parties = set()

    for c in commitments:
        # Commitment Node
        com_node_id = f"com_{c.id}"
        nodes.append({
            "id": com_node_id,
            "type": "commitment",
            "title": c.title,
            "status": c.status.value,
            "risk": c.risk.value,
            "confidence": c.confidence,
            "due_date": c.due_date.isoformat() if c.due_date else None,
            "direction": c.obligation_direction.value,
            "is_overdue": c.is_overdue,
            "data": c.model_dump(mode="json"),
        })

        # Promisor Party Node
        promisor_id = f"party_{c.promisor.name.replace(' ', '_')}"
        if promisor_id not in seen_parties:
            seen_parties.add(promisor_id)
            nodes.append({
                "id": promisor_id,
                "type": "party",
                "name": c.promisor.name,
                "organization": c.promisor.organization,
                "role": "PROMISOR",
            })

        # Edge: Promisor -> Commitment
        edges.append({
            "id": f"edge_prom_{promisor_id}_{c.id}",
            "source": promisor_id,
            "target": com_node_id,
            "label": "PROMISED",
            "relationship": "promisor_to_commitment",
        })

        # Promisee Party Node
        promisee_id = f"party_{c.promisee.name.replace(' ', '_')}"
        if promisee_id not in seen_parties:
            seen_parties.add(promisee_id)
            nodes.append({
                "id": promisee_id,
                "type": "party",
                "name": c.promisee.name,
                "organization": c.promisee.organization,
                "role": "PROMISEE",
            })

        # Edge: Commitment -> Promisee
        edges.append({
            "id": f"edge_pree_{c.id}_{promisee_id}",
            "source": com_node_id,
            "target": promisee_id,
            "label": "OWED_TO",
            "relationship": "commitment_to_promisee",
        })

        # Evidence Nodes & Edges
        for ev in c.evidence_references:
            ev_node_id = f"ev_{ev.id}"
            nodes.append({
                "id": ev_node_id,
                "type": "evidence",
                "source_type": ev.source_type.value,
                "title": ev.title,
                "snippet": ev.snippet,
                "source_id": ev.source_id,
            })
            edges.append({
                "id": f"edge_ev_{c.id}_{ev.id}",
                "source": ev_node_id,
                "target": com_node_id,
                "label": "CORROBORATES",
                "relationship": "evidence_to_commitment",
            })

        # Next Action Node & Edge
        if c.next_action:
            act_node_id = f"act_{c.next_action.id}"
            nodes.append({
                "id": act_node_id,
                "type": "action",
                "action_type": c.next_action.action_type.value,
                "description": c.next_action.description,
                "status": c.next_action.status.value,
                "requires_approval": c.next_action.requires_human_approval,
            })
            edges.append({
                "id": f"edge_act_{c.id}_{c.next_action.id}",
                "source": com_node_id,
                "target": act_node_id,
                "label": "REMEDY",
                "relationship": "commitment_to_action",
            })

    return {"nodes": nodes, "edges": edges, "total_commitments": len(commitments)}


@router.get("/decisions")
async def list_pending_decisions():
    """Retrieve all pending actions that require human decision."""
    all_comms = await repo.list_all(status=CommitmentStatus.AWAITING_APPROVAL)
    decisions = []
    for c in all_comms:
        if c.next_action and c.next_action.status == ActionStatus.AWAITING_APPROVAL:
            decisions.append({
                "commitment_id": c.id,
                "commitment_title": c.title,
                "promisor": c.promisor.model_dump(mode="json"),
                "promisee": c.promisee.model_dump(mode="json"),
                "due_date": c.due_date.isoformat() if c.due_date else None,
                "risk": c.risk.value,
                "confidence": c.confidence,
                "evidence": [e.model_dump(mode="json") for e in c.evidence_references],
                "action": c.next_action.model_dump(mode="json"),
                "evidence_assessment": (
                    c.evidence_assessment.model_dump(mode="json")
                    if c.evidence_assessment
                    else (c.metadata.get("evidence_assessment") if c.metadata else None)
                ),
            })
    return decisions


@router.post("/decisions/{action_id}/approve")
async def approve_decision(action_id: str, req: DecisionActionRequest):
    """Execute human approval on a pending action and dispatch it to the environment via the authoritative runtime."""
    all_comms = await repo.list_all()
    target_com: Optional[Commitment] = None

    for c in all_comms:
        if c.next_action and c.next_action.id == action_id:
            target_com = c
            break

    if not target_com or not target_com.next_action:
        raise HTTPException(status_code=404, detail=f"Pending decision for action '{action_id}' not found.")

    action = target_com.next_action

    if target_com.status in [CommitmentStatus.REJECTED, CommitmentStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail=f"Action '{action_id}' cannot be approved: commitment is {target_com.status.value}.")

    # Resolve tool name from action payload or action type
    tool_name = action.payload.get("tool") or action.payload.get("tool_name")
    if not tool_name:
        if action.action_type == ActionType.FOLLOWUP_EMAIL:
            tool_name = "send_followup"
        elif action.action_type == ActionType.ESCALATE_DISPUTE:
            tool_name = "create_escalation"
        else:
            tool_name = "send_followup"

    recipient = action.recipient or (target_com.promisor.email if target_com.promisor else None) or "client@example.com"
    subject = action.subject or f"Follow-up: {target_com.title}"
    body = action.payload.get("body", action.description)

    # Compute effective arguments
    effective_args: Dict[str, Any] = {
        "commitment_id": target_com.id,
        "recipient_email": recipient,
        "subject": subject,
        "body": body,
    }
    if req.edited_payload:
        if "body" in req.edited_payload:
            body = req.edited_payload["body"]
            effective_args["body"] = body
        if "subject" in req.edited_payload:
            subject = req.edited_payload["subject"]
            effective_args["subject"] = subject
        if "recipient" in req.edited_payload:
            recipient = req.edited_payload["recipient"]
            effective_args["recipient_email"] = recipient

    for k, v in action.payload.items():
        if k not in effective_args and k not in ("tool", "tool_name"):
            effective_args[k] = v

    # 1. Handle Idempotent Replay for already dispatched actions
    if action.status == ActionStatus.COMPLETED or target_com.status == CommitmentStatus.VERIFYING:
        tool_spec = runtime_env.tools.get(tool_name)
        is_idemp = tool_spec.spec.is_idempotent if tool_spec else False
        idemp_key = runtime_env.engine.idempotency.compute_key(
            task_id=f"tsk_{target_com.id}",
            agent_run_id=f"run_{action.id}",
            tool_name=tool_name,
            arguments=effective_args,
            is_tool_idempotent=is_idemp,
        )
        cached_obs = None
        if hasattr(runtime_env.engine.idempotency, "reserve_or_get"):
            reservation = await runtime_env.engine.idempotency.reserve_or_get(
                key=idemp_key,
                tool_name=tool_name,
                execution_id=f"exec_{uuid4().hex[:8]}",
            )
            cached_obs = reservation.cached_observation
        else:
            cached_obs = runtime_env.engine.idempotency.get(idemp_key)

        dispatch_data = cached_obs.data if cached_obs and isinstance(cached_obs.data, dict) else ({"result": cached_obs.data} if cached_obs else {})
        return {
            "success": True,
            "message": f"Action '{action_id}' already approved and dispatched (idempotent replay).",
            "dispatch_details": dispatch_data,
            "commitment": target_com.model_dump(mode="json"),
        }

    # 2. Construct authoritative runtime task, run, and tool request
    task = Task(
        id=f"tsk_{target_com.id}",
        organization_id=runtime_env.organization_id,
        intent=f"Dispatch remedy for {target_com.title}",
        required_role="covenant.resolver",
    )
    run = AgentRun(
        id=f"run_{action.id}",
        task_id=task.id,
        agent_id="covenant.resolver_agent",
    )
    tool_req = ToolRequest(
        request_id=f"req_{action.id}",
        tool_name=tool_name,
        arguments=effective_args,
        rationale=action.approval_reason or "Human authorized recommended action on Decision Surface.",
    )

    approval_id = f"appr_{action.id}"
    approval: Optional[HumanApprovalRequest] = None

    # 3. Authoritative Runtime Approval Transition via RuntimeApprovalService
    if runtime_env.approval_repo:
        existing_appr = await runtime_env.approval_repo.get(approval_id)
        if not existing_appr:
            pending_appr = HumanApprovalRequest(
                approval_id=approval_id,
                organization_id=task.organization_id,
                task_id=task.id,
                agent_run_id=run.id,
                tool_request=tool_req,
                policy_decision_id=getattr(action, "policy_decision_id", None) or f"pol_{action.id}",
                status=ApprovalState.PENDING,
            )
            try:
                await runtime_env.approval_repo.create(pending_appr)
            except Exception:
                pass  # Concurrently created by racing request

        if runtime_env.approval_service:
            try:
                approval = await runtime_env.approval_service.approve_human_request(
                    approval_id=approval_id,
                    organization_id=task.organization_id,
                    task_id=task.id,
                    agent_run_id=run.id,
                    tool_name=tool_name,
                    reviewed_by="User",
                    modified_arguments=effective_args,
                    notes=req.notes or "Approved by user.",
                )
            except (ValueError, RuntimeError) as e:
                # Racing/duplicate approval attempt: inspect idempotency cache before failing
                err_text = str(e)
                tool_spec = runtime_env.tools.get(tool_name)
                is_idemp = tool_spec.spec.is_idempotent if tool_spec else False
                idemp_key = runtime_env.engine.idempotency.compute_key(
                    task_id=f"tsk_{target_com.id}",
                    agent_run_id=f"run_{action.id}",
                    tool_name=tool_name,
                    arguments=effective_args,
                    is_tool_idempotent=is_idemp,
                )
                cached_obs = None
                if hasattr(runtime_env.engine.idempotency, "reserve_or_get"):
                    reservation = await runtime_env.engine.idempotency.reserve_or_get(
                        key=idemp_key,
                        tool_name=tool_name,
                        execution_id=f"exec_{uuid4().hex[:8]}",
                    )
                    cached_obs = reservation.cached_observation
                else:
                    cached_obs = runtime_env.engine.idempotency.get(idemp_key)

                if cached_obs:
                    return {
                        "success": True,
                        "message": f"Action '{action_id}' already approved and dispatched (idempotent replay).",
                        "dispatch_details": cached_obs.data if isinstance(cached_obs.data, dict) else {"result": cached_obs.data},
                        "commitment": target_com.model_dump(mode="json"),
                    }

                raise HTTPException(
                    status_code=409,
                    detail=f"Approval rejected or already consumed (concurrent/duplicate request): {err_text}",
                )
        else:
            approval = await runtime_env.approval_repo.get(approval_id)
            if approval:
                approval.status = ApprovalState.APPROVED
                approval.reviewed_by = "User"
                approval.reviewer_notes = req.notes or "Approved by user."
                approval.modified_arguments = effective_args
    else:
        approval = HumanApprovalRequest(
            approval_id=approval_id,
            organization_id=task.organization_id,
            task_id=task.id,
            agent_run_id=run.id,
            tool_request=tool_req,
            policy_decision_id=getattr(action, "policy_decision_id", None) or f"pol_{action.id}",
            status=ApprovalState.APPROVED,
            reviewed_by="User",
            reviewer_notes=req.notes or "Approved by user.",
            modified_arguments=effective_args,
        )

    # 4. Authoritative Runtime Execution via ExecutionEngine
    # Governed by: ToolPermissionMatrix, DefaultPolicyEngine, Idempotency, and EventSink
    obs, _ = await runtime_env.engine.handle_tool_request(
        task=task,
        run=run,
        request=tool_req,
        approval=approval,
    )

    if not obs.success:
        err_msg = obs.error or "Tool execution denied by runtime governance."
        if "already consumed" in err_msg.lower() or "concurrent" in err_msg.lower():
            raise HTTPException(status_code=409, detail=f"Concurrent approval or execution conflict: {err_msg}")
        if "Permission denied" in err_msg or "Policy denied" in err_msg or "denied" in err_msg.lower():
            raise HTTPException(status_code=403, detail=f"Runtime execution denied: {err_msg}")
        raise HTTPException(status_code=500, detail=f"Runtime tool execution failed: {err_msg}")


    # 5. Runtime execution succeeded -> Authoritatively update Covenant domain state
    action.status = ActionStatus.APPROVED
    action.decided_at = utc_now()
    action.decision_notes = req.notes or "Approved by user."
    if req.edited_payload:
        action.payload.update(req.edited_payload)

    if CommitmentStateMachine.can_transition(target_com.status, CommitmentStatus.EXECUTING):
        CommitmentStateMachine.transition(
            commitment=target_com,
            target_state=CommitmentStatus.EXECUTING,
            agent_name="HumanUser",
            reason="Human authorized recommended action on Decision Surface.",
            approved_by="User",
        )

    action.status = ActionStatus.COMPLETED
    action.executed_at = utc_now()

    if CommitmentStateMachine.can_transition(target_com.status, CommitmentStatus.VERIFYING):
        CommitmentStateMachine.transition(
            commitment=target_com,
            target_state=CommitmentStatus.VERIFYING,
            agent_name="System",
            reason=f"Action dispatched through runtime engine into communication stream ({obs.execution_id}). Awaiting independent verification of client response.",
        )

    # 6. Record domain event in Covenant audit repository
    await repo.record_event(
        AgentEvent(
            agent="System",
            event_type="DISPATCH_ACTION",
            summary=f"Dispatched approved action to {recipient} via runtime execution engine",
            commitment_id=target_com.id,
            tool=tool_name,
            state_before=CommitmentStatus.EXECUTING,
            state_after=CommitmentStatus.VERIFYING,
            result_status="SUCCESS",
            rationale="Action authorized, policy verified, and executed through runtime engine. Lifecycle entered VERIFYING stage.",
            metadata={"execution_id": obs.execution_id},
        )
    )

    await repo.save(target_com)

    dispatch_data = obs.data if isinstance(obs.data, dict) else {"result": obs.data, "execution_id": obs.execution_id}

    return {
        "success": True,
        "message": f"Action '{action_id}' approved and dispatched through runtime engine. Commitment entered VERIFYING stage.",
        "dispatch_details": dispatch_data,
        "commitment": target_com.model_dump(mode="json"),
    }



@router.post("/simulate/reply/{commitment_id}")
async def simulate_external_reply(commitment_id: str, req: Optional[SimulateReplyRequest] = None):
    """
    'World Changes' Demo Mechanism:
    Simulates the external counterparty observing the follow-up and sending a reply.
    """
    fulfilled = req.fulfilled if req is not None else True
    reply = workspace_store.simulate_client_reply(commitment_id, fulfilled=fulfilled)
    if not reply:
        raise HTTPException(status_code=404, detail="No simulation rule found for this commitment.")

    # Record event that world changed
    await repo.record_event(
        AgentEvent(
            agent="ExternalActor",
            event_type="INCOMING_COMMUNICATION",
            summary=f"Received incoming reply: '{reply['subject']}' from {reply['from']}",
            commitment_id=commitment_id,
            result_status="SUCCESS",
            rationale=f"External environment updated with counterparty response (fulfilled={fulfilled}).",
        )
    )

    # Trigger verification pass to catch this change
    res = await supervisor.verify_commitment(commitment_id)
    updated = await repo.get_by_id(commitment_id)

    return {
        "success": True,
        "message": f"External client response simulated (fulfilled={fulfilled}) and evaluated through VerificationGate.",
        "incoming_email": reply,
        "commitment": updated.model_dump(mode="json") if updated else None,
        "verification": res.data,
    }


@router.post("/decisions/{action_id}/reject")
async def reject_decision(action_id: str, req: DecisionActionRequest):
    """Reject a proposed action."""
    all_comms = await repo.list_all(status=CommitmentStatus.AWAITING_APPROVAL)
    target_com: Optional[Commitment] = None

    for c in all_comms:
        if c.next_action and c.next_action.id == action_id:
            target_com = c
            break

    if not target_com or not target_com.next_action:
        raise HTTPException(status_code=404, detail=f"Pending decision for action '{action_id}' not found.")

    target_com.next_action.status = ActionStatus.REJECTED
    target_com.next_action.decided_at = utc_now()
    target_com.next_action.decision_notes = req.notes or "Rejected by user."

    CommitmentStateMachine.transition(
        commitment=target_com,
        target_state=CommitmentStatus.REJECTED,
        agent_name="HumanUser",
        reason=f"Action rejected by human: {req.notes or 'User override'}",
        approved_by="User",
    )
    await repo.save(target_com)

    return {
        "success": True,
        "message": f"Action '{action_id}' rejected.",
        "commitment": target_com.model_dump(mode="json"),
    }


@router.post("/commitments/{commitment_id}/verify")
async def trigger_verification(commitment_id: str, req: Optional[VerifyRequest] = None):
    """Trigger the VerificationAgent on a commitment."""
    com = await repo.get_by_id(commitment_id)
    if not com:
        raise HTTPException(status_code=404, detail="Commitment not found.")

    params = req.simulated_params if req else None
    res = await supervisor.verify_commitment(commitment_id, params)
    updated_com = await repo.get_by_id(commitment_id)
    return {
        "success": res.success,
        "summary": res.summary,
        "commitment": updated_com.model_dump(mode="json") if updated_com else None,
        "verification": res.data,
    }


@router.get("/events")
async def get_events(limit: int = 50, commitment_id: Optional[str] = None):
    """List agent activity events."""
    return await repo.list_events(commitment_id=commitment_id, limit=limit)


@router.post("/monitoring/cycles")
async def trigger_monitoring_cycle():
    """
    Trigger a bounded autonomous monitoring cycle via the canonical SupervisorAgent.
    Enforces atomic cycle reservation (rejecting concurrent runs with 409 Conflict),
    persists cycle outcomes and operational counters, and records audit telemetry.
    """
    cycle_id = f"cycle_{uuid4().hex[:8]}"
    reserved, active_id = await repo.reserve_or_start_cycle(cycle_id)
    if not reserved:
        raise HTTPException(
            status_code=409,
            detail=f"A monitoring cycle is currently active: {active_id}",
        )

    ctx = AgentContext(session_id=f"monitor_{cycle_id}")
    try:
        result = await supervisor.run_monitoring_cycle(ctx, cycle_id=cycle_id)
        if not result.success or (result.data and result.data.get("status") == "FAILED"):
            errors = result.data.get("errors", [result.summary]) if result.data else [result.summary]
            raise HTTPException(
                status_code=500,
                detail={
                    "cycle_id": cycle_id,
                    "status": "FAILED",
                    "errors": errors,
                    "summary": result.summary,
                },
            )
        record = await repo.get_cycle_record(cycle_id)
        if record:
            return record
        return result.data
    except HTTPException:
        raise
    except Exception as exc:
        failed_record = {
            "cycle_id": cycle_id,
            "status": "FAILED",
            "started_at": utc_now().isoformat(),
            "completed_at": utc_now().isoformat(),
            "errors": [str(exc)],
            "summary": f"Monitoring cycle failed: {str(exc)}",
        }
        await repo.save_cycle_record(failed_record)
        raise HTTPException(
            status_code=500,
            detail={
                "cycle_id": cycle_id,
                "status": "FAILED",
                "errors": [str(exc)],
                "summary": str(exc),
            },
        )


@router.get("/monitoring/cycles/{cycle_id}")
async def get_monitoring_cycle(cycle_id: str):
    """Retrieve operational details and metrics for a specific monitoring cycle."""
    record = await repo.get_cycle_record(cycle_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Monitoring cycle '{cycle_id}' not found.")
    return {
        "cycle_id": record["cycle_id"],
        "status": record["status"],
        "started_at": record["started_at"],
        "completed_at": record["completed_at"],
        "commitments_scanned": record["commitments_scanned"],
        "commitments_changed": record["commitments_changed"],
        "actions_proposed": record["actions_proposed"],
        "approval_requests": record["approval_requests"],
        "executions": record["executions"],
        "verifications": record["verifications"],
        "resolved": record["resolved"],
        "failed": record["failed"],
        "errors": record.get("errors", []),
        "summary": record.get("summary", ""),
    }


@router.get("/monitoring/cycles")
async def list_monitoring_cycles(limit: int = 50):
    """List recent monitoring cycle records ordered by start time."""
    return await repo.list_cycle_records(limit=limit)


@router.post("/scan")
async def run_scan_cycle():
    """Trigger the full autonomous Supervisor scan cycle."""
    ctx = AgentContext(session_id=f"scan_{uuid4().hex[:6]}")
    result = await supervisor.run(ctx)
    return {
        "success": result.success,
        "summary": result.summary,
        "data": result.data,
        "events_count": len(result.events),
    }


@router.post("/seed")
async def reseed_database():
    """Reset database and re-seed with clean Northstar Studio workspace data."""
    def _clear():
        with repo._get_connection() as conn:
            conn.execute("DELETE FROM agent_events")
            conn.execute("DELETE FROM commitments")
            conn.execute("DELETE FROM monitoring_cycles")
    await asyncio.to_thread(_clear)
    workspace_store.reset()
    await repo.initialize()
    ctx = AgentContext(session_id="seed_initialization")
    result = await supervisor.run(ctx)
    return {
        "success": True,
        "message": "Database successfully reseeded with Northstar Studio workspace data.",
        "scan_result": result.summary,
    }

