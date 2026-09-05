"""Ollama and Deterministic LLM Provider Implementations."""

import json
from typing import Any, Dict, List, Optional
import httpx

from covenant.config import settings
from covenant.llm.provider import AbstractModelProvider, ChatMessage, LLMResponse


class OllamaModelProvider(AbstractModelProvider):
    """Local LLM provider using Ollama HTTP API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model_name = model_name or settings.ollama_model
        self.timeout = timeout

    async def is_available(self) -> bool:
        """Check if Ollama server is running and reachable."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Execute chat completion via Ollama /api/chat."""
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/api/chat", json=payload)
            res.raise_for_status()
            data = res.json()

            return LLMResponse(
                content=data.get("message", {}).get("content", ""),
                model_name=self.model_name,
                prompt_tokens=data.get("prompt_eval_count"),
                completion_tokens=data.get("eval_count"),
                raw_response=data,
            )


class DeterministicFallbackProvider(AbstractModelProvider):
    """
    Deterministic provider that parses prompts for structured extraction
    or returns pre-configured responses during local testing / offline mode.
    """

    def __init__(self, model_name: str = "deterministic-local"):
        self.model_name = model_name

    async def is_available(self) -> bool:
        return True

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        last_msg = messages[-1].content if messages else ""
        
        # Default structured JSON if json_mode requested
        content = "{}"
        lower_msg = last_msg.lower()
        if "extract commitment" in lower_msg or "classify statement" in lower_msg or "extract commitments" in lower_msg:
            if any(w in lower_msg for w in ["?", "could we", "can you", "would you", "is there", "please review and send"]):
                stmt_type = "QUESTION"
                is_com = False
                rationale = "Statement is an inquiry, review request, or question rather than a binding promise."
            elif any(w in lower_msg for w in ["maybe", "perhaps", "could consider", "might want to", "suggest"]):
                stmt_type = "SUGGESTION"
                is_com = False
                rationale = "Statement expresses a non-binding suggestion or exploratory idea."
            elif any(w in lower_msg for w in ["already finished", "delivered yesterday", "finalized all", "have finalized"]):
                stmt_type = "COMPLETED_ACTION"
                is_com = False
                rationale = "Statement describes a completed past action or submission without future obligation."
            elif any(w in lower_msg for w in ["promise", "guarantee", "will provide", "will deliver", "sign-off by"]):
                stmt_type = "COMMITMENT"
                is_com = True
                rationale = "Statement contains an explicit binding commitment with deliverable and timeline."
            else:
                stmt_type = "NON_BINDING_STATEMENT"
                is_com = False
                rationale = "Statement expresses non-binding opinion or general communication."

            content = json.dumps({
                "is_commitment": is_com,
                "statement_type": stmt_type,
                "confidence": 0.96 if is_com else 0.90,
                "promised_deliverable": "Formal deliverable or agreed obligation" if is_com else "",
                "rationale": rationale,
            })
        elif "synthesize evidence" in lower_msg or "evidence assessment" in lower_msg:
            is_blocking = "blocked" in lower_msg or "prj-atlas" in lower_msg or "atlas" in lower_msg
            claims = [
                {
                    "source_id": "PRJ-ATLAS" if "atlas" in lower_msg else "DOC-001",
                    "claim": "Deliverables submitted and awaiting formal sign-off; downstream work blocked." if is_blocking else "Deliverable records logged in project system.",
                    "is_fact": True,
                    "relevance": "HIGH",
                    "confidence": 0.98,
                },
                {
                    "source_id": "INBOX_SCAN",
                    "claim": "No counterparty confirmation received past the expected deadline.",
                    "is_fact": True,
                    "relevance": "HIGH",
                    "confidence": 0.95,
                },
                {
                    "source_id": "DERIVED_ANALYSIS",
                    "claim": "Counterparty response time has exceeded contractual turnaround expectations.",
                    "is_fact": False,
                    "relevance": "MEDIUM",
                    "confidence": 0.85,
                },
            ]
            conflicts = [
                {
                    "source_a": "PRJ-ATLAS" if "atlas" in lower_msg else "DOC-001",
                    "source_b": "INBOX_SCAN",
                    "description": "Milestone submitted awaiting client approval, but deadline passed without formal sign-off.",
                    "conflict_type": "STATUS_CONTRADICTION",
                    "severity": "HIGH",
                }
            ] if is_blocking else []

            content = json.dumps({
                "finding": "Counterparty formal sign-off is overdue; downstream development is blocked." if is_blocking else "Evidence gathered across workspace records.",
                "factual_claims": claims,
                "conflicts": conflicts,
                "confidence": 0.96 if is_blocking else 0.88,
                "is_blocking_downstream": is_blocking,
                "recommended_risk": "MEDIUM" if is_blocking else "LOW",
                "rationale": "Cross-source corroboration confirmed submission is waiting while deadline has elapsed without response.",
            })
        elif "verify" in lower_msg:
            content = json.dumps({
                "is_verified": True,
                "rationale": "Evidence successfully corroborates requirement completion.",
            })

        return LLMResponse(
            content=content,
            model_name=self.model_name,
            prompt_tokens=len(last_msg.split()),
            completion_tokens=len(content.split()),
        )
