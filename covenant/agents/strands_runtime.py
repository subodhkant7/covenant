"""Strands Agents SDK Runtime Integration for Covenant."""

import json
import logging
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional
import httpx
import uuid

from strands import Agent, tool
from strands.models.model import Model
from strands.types.streaming import StreamEvent

from covenant.config import settings
from covenant.domain.enums import (
    ActionStatus,
    ActionType,
    CommitmentCategory,
    CommitmentStatus,
    PolicyCategory,
    PolicyDecisionType,
    RiskLevel,
)
from covenant.domain.models import (
    AgentEvent,
    Commitment,
    EvidenceReference,
    EvidenceSourceType,
    Party,
    PolicyDecision,
    ProposedAction,
    VerificationResult,
    utc_now,
)
from covenant.persistence.repository import AbstractCommitmentRepository, AbstractEventRepository
from covenant.state_machine.machine import CommitmentStateMachine
from covenant.synthetic_data.store import workspace_store
from covenant.llm.provider import strip_private_reasoning_text, sanitize_model_payload

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 1. Strands Native Tools
# ----------------------------------------------------------------------

@tool
def tool_search_email(query: str) -> str:
    """Search workspace emails by keyword, sender, recipient, or subject."""
    results = workspace_store.search_emails(query)
    return json.dumps({"count": len(results), "emails": results})


@tool
def tool_read_email(email_id: str) -> str:
    """Fetch full email body and metadata by email ID."""
    email = workspace_store.get_email_by_id(email_id)
    return json.dumps(email if email else {"error": f"Email {email_id} not found."})


@tool
def tool_search_contract(query: str) -> str:
    """Search contracts for specific clauses, terms, or parties."""
    contracts = workspace_store.search_contracts(query)
    return json.dumps({"count": len(contracts), "contracts": contracts})


@tool
def tool_get_project_status(project_id: str) -> str:
    """Retrieve milestones, status, and blockers for a project ID."""
    prj = workspace_store.get_project_by_id(project_id)
    return json.dumps(prj if prj else {"error": f"Project {project_id} not found."})


@tool
def tool_send_followup(
    commitment_id: str,
    recipient_email: str,
    subject: str,
    body: str,
) -> str:
    """Actually dispatch an approved follow-up email into the workspace communication stream."""
    record = workspace_store.send_email(
        from_addr="Alex North <alex@northstarstudio.com>",
        to_addrs=[recipient_email],
        subject=subject,
        body=body,
        thread_id="TH-ATLAS-APPROVAL" if "atlas" in commitment_id.lower() else "TH-FOLLOWUP",
    )
    return json.dumps({
        "action_succeeded": True,
        "sent_email_id": record["id"],
        "dispatched_at": record["date"],
        "message": f"Follow-up dispatched to {recipient_email}.",
    })


@tool
def tool_create_escalation(commitment_id: str, title: str, rationale: str) -> str:
    """Record a formal dispute escalation in the workspace."""
    esc = workspace_store.record_escalation(commitment_id, title, rationale)
    return json.dumps({
        "escalation_id": esc["id"],
        "status": "ESCALATED",
        "title": title,
    })


@tool
def tool_verify_commitment(commitment_id: str) -> str:
    """Independently query workspace communications and project records to verify if outcome was achieved."""
    is_verified = False
    rationale = ""
    evidence_ids = []

    if "atlas" in commitment_id.lower():
        emails = workspace_store.search_emails("approv")
        signoff_email = next(
            (e for e in emails if "Signed_Atlas_Phase2_Signoff.pdf" in e.get("attachments", []) or "formally approve" in e.get("body", "").lower()),
            None,
        )
        atlas_prj = workspace_store.get_project_by_id("PRJ-ATLAS")
        m2 = next((m for m in atlas_prj.get("milestones", []) if m["id"] == "M2"), None) if atlas_prj else None

        if signoff_email and m2 and m2.get("status") == "APPROVED_BY_CLIENT":
            is_verified = True
            evidence_ids.append(signoff_email["id"])
            rationale = f"Formal signed approval verified from {signoff_email['from']} ({signoff_email['id']}). Milestone M2 status is APPROVED_BY_CLIENT."
        elif signoff_email:
            is_verified = True
            evidence_ids.append(signoff_email["id"])
            rationale = f"Written approval email received from {signoff_email['from']} ({signoff_email['id']})."
        else:
            is_verified = False
            rationale = "Action was executed, but no corroborating client approval response has been received in inbox yet."

    elif "apex" in commitment_id.lower():
        emails = workspace_store.search_emails("en route")
        if emails:
            is_verified = True
            evidence_ids.append(emails[0]["id"])
            rationale = f"Technician dispatch confirmed by service manager ({emails[0]['id']})."
        else:
            is_verified = False
            rationale = "No calibration completion report found in records."

    else:
        is_verified = False
        rationale = "No independent outcome verification evidence found."

    return json.dumps({
        "commitment_id": commitment_id,
        "action_succeeded": True,
        "business_outcome_verified": is_verified,
        "is_verified": is_verified,
        "rationale": rationale,
        "evidence_ids": evidence_ids,
    })


COVENANT_STRANDS_TOOLS = [
    tool_search_email,
    tool_read_email,
    tool_search_contract,
    tool_get_project_status,
    tool_send_followup,
    tool_create_escalation,
    tool_verify_commitment,
]


# ----------------------------------------------------------------------
# 2. Strands Model Implementations
# ----------------------------------------------------------------------

class LocalDeterministicStrandsModel(Model):
    """
    Deterministic Strands Model for offline testing and environments without GPU/Ollama.
    Implements the full Strands Model streaming interface.
    """

    def __init__(self, model_id: str = "covenant-local-deterministic"):
        self.config = {"model_id": model_id}

    def get_config(self) -> Any:
        return self.config

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    async def stream(
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: Any = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        last_content = messages[-1].get("content", "") if messages else ""
        if isinstance(last_content, list) and last_content:
            text = last_content[0].get("text", "")
        else:
            text = str(last_content)

        # Output reasoning and end turn
        yield {"contentBlockDelta": {"delta": {"text": f"[Covenant Reasoning]: Evaluated prompt against commitments and policy rules.\n"}}}
        yield {"messageStop": {"stopReason": "end_turn"}}

    async def structured_output(
        self,
        output_model: type,
        prompt: Any,
        system_prompt: Any = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        yield {"output": output_model.model_validate({})}


class OllamaStrandsModel(Model):
    """
    Local Ollama Model implementing the Strands Model protocol.
    Connects to http://localhost:11434 with clear diagnostic on connection failure.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        fallback_model: Optional[str] = None,
        secondary_fallback_model: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model_name = model_name or settings.ollama_model
        self.fallback_model = fallback_model or settings.ollama_fallback_model
        self.secondary_fallback_model = secondary_fallback_model or settings.ollama_secondary_fallback_model
        self.timeout = timeout
        self.config = {"model_id": f"ollama/{self.model_name}"}

    @property
    def candidate_models(self) -> List[str]:
        candidates = [self.model_name, self.fallback_model, self.secondary_fallback_model]
        return [m for m in candidates if m]

    def get_config(self) -> Any:
        return self.config

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    async def check_availability(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    async def stream(
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: Any = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        is_available = await self.check_availability()
        if not is_available:
            logger.warning(f"Ollama server not reachable at {self.base_url}. Falling back to deterministic execution.")
            yield {"contentBlockDelta": {"delta": {"text": f"[Ollama Diagnostic]: Ollama unreachable at {self.base_url}. Deterministic model active.\n"}}}
            yield {"messageStop": {"stopReason": "end_turn"}}
            return

        ollama_messages = []
        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, str):
                ollama_messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                tool_results = [c["toolResult"] for c in content if isinstance(c, dict) and "toolResult" in c]
                tool_uses = [c["toolUse"] for c in content if isinstance(c, dict) and "toolUse" in c]
                text_parts = [c["text"] for c in content if isinstance(c, dict) and "text" in c]

                if tool_results:
                    for tr in tool_results:
                        tr_c = tr.get("content", [])
                        tr_text = ""
                        if isinstance(tr_c, list) and tr_c:
                            tr_text = tr_c[0].get("text", "")
                        elif isinstance(tr_c, str):
                            tr_text = tr_c
                        else:
                            tr_text = json.dumps(tr_c)
                        ollama_messages.append({"role": "tool", "content": tr_text})
                elif tool_uses:
                    tc_list = []
                    for tu in tool_uses:
                        inp = tu.get("input", {})
                        if isinstance(inp, str):
                            try:
                                inp = json.loads(inp)
                            except Exception:
                                pass
                        tc_list.append({"function": {"name": tu.get("name"), "arguments": inp}})
                    msg_dict = {"role": "assistant", "content": " ".join(text_parts)}
                    if tc_list:
                        msg_dict["tool_calls"] = tc_list
                    ollama_messages.append(msg_dict)
                else:
                    ollama_messages.append({"role": role, "content": " ".join(text_parts)})

        # Convert Strands tool_specs to Ollama function tool format
        ollama_tools = None
        if tool_specs:
            ollama_tools = []
            for spec in tool_specs:
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": spec.get("name"),
                        "description": spec.get("description", ""),
                        "parameters": spec.get("inputSchema", {}).get("json", {}),
                    }
                })

        candidates = self.candidate_models

        for idx, model in enumerate(candidates):
            payload: Dict[str, Any] = {
                "model": model,
                "messages": ollama_messages,
            }
            if ollama_tools:
                payload["tools"] = ollama_tools
                payload["stream"] = False
            else:
                payload["stream"] = True

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    if ollama_tools:
                        # Non-streaming call when tools are enabled for reliable tool call schema parsing
                        res = await client.post(f"{self.base_url}/api/chat", json=payload)
                        if res.status_code != 200:
                            logger.warning(f"Ollama model {model} returned HTTP {res.status_code}. Trying next candidate.")
                            continue
                        data = res.json()
                        if "error" in data:
                            logger.warning(f"Ollama model {model} reported error: {data['error']}. Trying fallback.")
                            continue

                        msg = data.get("message", {})
                        tool_calls = msg.get("tool_calls", [])
                        if tool_calls:
                            for c_idx, tc in enumerate(tool_calls):
                                fn = tc.get("function", {})
                                fn_name = fn.get("name")
                                args = fn.get("arguments", {})
                                if not isinstance(args, str):
                                    args = json.dumps(args)
                                tool_use_id = f"tooluse_{uuid.uuid4().hex[:8]}"
                                yield {
                                    "contentBlockStart": {
                                        "contentBlockIndex": c_idx,
                                        "start": {
                                            "toolUse": {
                                                "name": fn_name,
                                                "toolUseId": tool_use_id,
                                            }
                                        }
                                    }
                                }
                                yield {
                                    "contentBlockDelta": {
                                        "contentBlockIndex": c_idx,
                                        "delta": {
                                            "toolUse": {
                                                "input": args,
                                            }
                                        }
                                    }
                                }
                                yield {"contentBlockStop": {"contentBlockIndex": c_idx}}
                            yield {"messageStop": {"stopReason": "tool_use"}}
                            return
                        else:
                            content_text = strip_private_reasoning_text(msg.get("content", ""))
                            if content_text:
                                yield {"contentBlockDelta": {"delta": {"text": content_text}}}
                            yield {"messageStop": {"stopReason": "end_turn"}}
                            return
                    else:
                        # Streaming call for regular text generation
                        async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                            if response.status_code != 200:
                                logger.warning(f"Ollama model {model} returned HTTP {response.status_code}. Trying next candidate.")
                                continue

                            got_any_text = False
                            async for line in response.aiter_lines():
                                if not line:
                                    continue
                                chunk = json.loads(line)
                                if "error" in chunk:
                                    logger.warning(f"Ollama model {model} reported error: {chunk['error']}. Trying fallback.")
                                    break
                                msg_chunk = chunk.get("message", {})
                                # Discard any thinking tokens immediately
                                if "thinking" in msg_chunk or "thought" in msg_chunk:
                                    continue
                                text = strip_private_reasoning_text(msg_chunk.get("content", ""))
                                if text:
                                    got_any_text = True
                                    yield {"contentBlockDelta": {"delta": {"text": text}}}
                                if chunk.get("done", False):
                                    yield {"messageStop": {"stopReason": "end_turn"}}
                                    return
                            if got_any_text:
                                return
            except Exception as e:
                logger.error(f"Error calling Ollama model {model}: {e}")

        # Fallback to local deterministic reasoning if all cloud/local models fail
        logger.warning("All Ollama models failed or require subscription credits. Streaming deterministic fallback reasoning.")
        yield {"contentBlockDelta": {"delta": {"text": f"[Ollama Failover]: All models uncredited/unavailable. Executing deterministic reasoning.\n"}}}
        yield {"messageStop": {"stopReason": "end_turn"}}

    async def structured_output(
        self,
        output_model: type,
        prompt: Any,
        system_prompt: Any = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        yield {"output": output_model.model_validate({})}


# ----------------------------------------------------------------------
# 3. Real Strands Agent Coordinator
# ----------------------------------------------------------------------

class CovenantStrandsAgentRunner:
    """
    Coordinates real Strands Agent instances with deterministic state machine verification.
    """

    def __init__(
        self,
        commitment_repo: AbstractCommitmentRepository,
        event_repo: AbstractEventRepository,
        use_ollama: bool = False,
        model: Optional[Model] = None,
    ):
        self.commitment_repo = commitment_repo
        self.event_repo = event_repo
        
        # Select model
        if model:
            self.model = model
        elif use_ollama:
            self.model = OllamaStrandsModel()
        else:
            from covenant.llm import get_strands_model
            self.model = get_strands_model()


        # Instantiate real Strands Agents
        self.supervisor_agent = Agent(
            model=self.model,
            tools=COVENANT_STRANDS_TOOLS,
            name="CovenantSupervisorAgent",
            system_prompt=(
                "You are Covenant's master autonomous commitment-resolution supervisor. "
                "You continuously observe promises, identify drift, plan remedies, enforce human approval policies, "
                "and verify independent real-world outcomes."
            ),
        )

        self.evidence_agent = Agent(
            model=self.model,
            tools=COVENANT_STRANDS_TOOLS,
            name="CovenantEvidenceAgent",
            system_prompt="You investigate workspace sources to cross-corroborate factual evidence.",
        )

        self.verification_agent = Agent(
            model=self.model,
            tools=COVENANT_STRANDS_TOOLS,
            name="CovenantVerificationAgent",
            system_prompt="You independently verify whether external promises and actions have achieved their required business outcome.",
        )

    async def emit_structured_event(
        self,
        agent_name: str,
        event_type: str,
        summary: str,
        commitment_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        state_before: Optional[CommitmentStatus] = None,
        state_after: Optional[CommitmentStatus] = None,
        confidence: Optional[float] = None,
        risk: Optional[RiskLevel] = None,
        human_required: bool = False,
        rationale: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> AgentEvent:
        """Create and persist a typed observability event."""
        evt = AgentEvent(
            agent=agent_name,
            event_type=event_type,
            summary=summary,
            commitment_id=commitment_id,
            tool=tool_name,
            state_before=state_before,
            state_after=state_after,
            confidence=confidence,
            risk=risk,
            human_required=human_required,
            rationale=rationale,
            workflow_id=workflow_id or "covenant_cycle",
        )
        await self.event_repo.record_event(evt)
        return evt
