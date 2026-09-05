"""FastAPI REST API Routes for Covenant."""

from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from covenant.agents.base import AgentContext
from covenant.agents.supervisor import SupervisorAgent
from covenant.domain.enums import (
    ActionStatus,
    CommitmentStatus,
    ObligationDirection,
    RiskLevel,
)
from covenant.domain.models import AgentEvent, Commitment, utc_now
from covenant.llm.ollama_provider import DeterministicFallbackProvider
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.state_machine.machine import CommitmentStateMachine
from covenant.synthetic_data.store import workspace_store
from covenant.tools import initialize_tools

router = APIRouter(prefix="/api")

# Repository and agent singletons for local runtime
repo = SQLiteCommitmentRepository()
tools = initialize_tools()
llm = DeterministicFallbackProvider()
supervisor = SupervisorAgent(llm=llm, tools=tools, commitment_repo=repo, event_repo=repo)


class DecisionActionRequest(BaseModel):
    notes: Optional[str] = None
    edited_payload: Optional[Dict[str, Any]] = None


class VerifyRequest(BaseModel):
    simulated_params: Optional[Dict[str, Any]] = None


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "covenant", "version": "0.1.0"}


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
            })
    return decisions


@router.post("/decisions/{action_id}/approve")
async def approve_decision(action_id: str, req: DecisionActionRequest):
    """Execute human approval on a pending action and dispatch it to the environment."""
    all_comms = await repo.list_all(status=CommitmentStatus.AWAITING_APPROVAL)
    target_com: Optional[Commitment] = None

    for c in all_comms:
        if c.next_action and c.next_action.id == action_id:
            target_com = c
            break

    if not target_com or not target_com.next_action:
        raise HTTPException(status_code=404, detail=f"Pending decision for action '{action_id}' not found.")

    action = target_com.next_action
    action.status = ActionStatus.APPROVED
    action.decided_at = utc_now()
    action.decision_notes = req.notes or "Approved by user."
    if req.edited_payload:
        action.payload.update(req.edited_payload)

    # 1. Transition state machine to EXECUTING
    CommitmentStateMachine.transition(
        commitment=target_com,
        target_state=CommitmentStatus.EXECUTING,
        agent_name="HumanUser",
        reason="Human authorized recommended action on Decision Surface.",
        approved_by="User",
    )
    await repo.save(target_com)

    # 2. Actually execute the action in the workspace environment
    send_tool = tools.get("send_followup")
    recipient = action.recipient or target_com.promisor.email or "client@example.com"
    subject = action.subject or f"Follow-up: {target_com.title}"
    body = action.payload.get("body", action.description)

    dispatch_res = await send_tool.execute(
        commitment_id=target_com.id,
        recipient_email=recipient,
        subject=subject,
        body=body,
    )

    action.status = ActionStatus.COMPLETED
    action.executed_at = utc_now()

    # 3. Transition to VERIFYING (distinguishing action dispatched from outcome verified)
    CommitmentStateMachine.transition(
        commitment=target_com,
        target_state=CommitmentStatus.VERIFYING,
        agent_name="System",
        reason=f"Action dispatched into communication stream ({dispatch_res.data.get('sent_email_id')}). Awaiting independent verification of client response.",
    )

    # Record event
    await repo.record_event(
        AgentEvent(
            agent="System",
            event_type="DISPATCH_ACTION",
            summary=f"Dispatched approved action to {recipient}",
            commitment_id=target_com.id,
            tool="send_followup",
            state_before=CommitmentStatus.EXECUTING,
            state_after=CommitmentStatus.VERIFYING,
            result_status="SUCCESS",
            rationale="Action authorized and sent. Lifecycle entered VERIFYING stage.",
        )
    )

    await repo.save(target_com)

    return {
        "success": True,
        "message": f"Action '{action_id}' approved and dispatched. Commitment entered VERIFYING stage.",
        "dispatch_details": dispatch_res.data,
        "commitment": target_com.model_dump(mode="json"),
    }


@router.post("/simulate/reply/{commitment_id}")
async def simulate_external_reply(commitment_id: str):
    """
    'World Changes' Demo Mechanism:
    Simulates the external counterparty observing the follow-up and sending a reply.
    """
    reply = workspace_store.simulate_client_reply(commitment_id)
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
            rationale="External environment updated with counterparty response.",
        )
    )

    # Trigger verification pass to catch this change
    res = await supervisor.verify_commitment(commitment_id)
    updated = await repo.get_by_id(commitment_id)

    return {
        "success": True,
        "message": "External client response simulated and verified.",
        "incoming_email": reply,
        "commitment": updated.model_dump(mode="json") if updated else None,
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
async def trigger_verification(commitment_id: str, req: VerifyRequest):
    """Trigger the VerificationAgent on a commitment."""
    com = await repo.get_by_id(commitment_id)
    if not com:
        raise HTTPException(status_code=404, detail="Commitment not found.")

    res = await supervisor.verify_commitment(commitment_id, req.simulated_params or {"simulated_signed_approval": True, "simulated_repair_complete": True, "simulated_delivery_complete": True})
    updated_com = await repo.get_by_id(commitment_id)
    return {
        "success": res.success,
        "summary": res.summary,
        "commitment": updated_com.model_dump(mode="json") if updated_com else None,
    }


@router.get("/events")
async def get_events(limit: int = 50, commitment_id: Optional[str] = None):
    """List agent activity events."""
    return await repo.list_events(commitment_id=commitment_id, limit=limit)


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
    await repo.initialize()
    ctx = AgentContext(session_id="seed_initialization")
    result = await supervisor.run(ctx)
    return {
        "success": True,
        "message": "Database successfully reseeded with Northstar Studio workspace data.",
        "scan_result": result.summary,
    }
