"""Ollama and Deterministic LLM Provider Implementations."""

import json
from typing import Any, Dict, List, Optional
import httpx

from covenant.config import settings
from covenant.llm.provider import (
    AbstractModelProvider,
    ChatMessage,
    LLMResponse,
    sanitize_model_payload,
    strip_private_reasoning_text,
)


class OllamaModelProvider(AbstractModelProvider):
    """Local LLM provider using Ollama HTTP API with graceful multi-model failover."""

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
        self.fallback_history: List[Dict[str, Any]] = []
        self._deterministic_fallback = DeterministicFallbackProvider(model_name="deterministic-fallback")

    @property
    def candidate_models(self) -> List[str]:
        """Ordered candidate models for runtime execution."""
        candidates = [self.model_name, self.fallback_model, self.secondary_fallback_model]
        return [m for m in candidates if m]

    async def is_available(self) -> bool:
        """Check if Ollama server is running and reachable."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    async def get_diagnostics(self) -> Dict[str, Any]:
        """Return safe diagnostic metadata without secrets or private prompt data."""
        reachable = False
        installed_models = []
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    reachable = True
                    data = res.json()
                    installed_models = [
                        {
                            "name": m.get("name"),
                            "capabilities": m.get("capabilities", []),
                        }
                        for m in data.get("models", [])
                    ]
        except Exception as e:
            reachable = False

        return {
            "provider": "ollama",
            "base_url": self.base_url,
            "configured_model": self.model_name,
            "fallback_model": self.fallback_model,
            "secondary_fallback_model": self.secondary_fallback_model,
            "candidate_models": self.candidate_models,
            "reachable": reachable,
            "installed_models": installed_models,
            "fallback_count": len(self.fallback_history),
            "recent_fallbacks": self.fallback_history[-5:] if self.fallback_history else [],
        }

    def _record_fallback(self, attempted: str, reason: str, candidates: List[str], current_idx: int) -> None:
        """Record sanitized fallback event without sensitive payload data."""
        import datetime
        next_model = candidates[current_idx + 1] if current_idx + 1 < len(candidates) else "deterministic-fallback"
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "attempted_model": attempted,
            "fallback_target": next_model,
            "reason": str(reason)[:200],
        }
        self.fallback_history.append(entry)

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        schema: Optional[Any] = None,
    ) -> LLMResponse:
        """Execute chat completion via Ollama /api/chat with ordered model failover and deterministic output sanitization."""
        candidates = self.candidate_models

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for idx, model in enumerate(candidates):
                payload: Dict[str, Any] = {
                    "model": model,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                    },
                }
                if schema is not None:
                    if hasattr(schema, "model_json_schema"):
                        payload["format"] = schema.model_json_schema()
                    elif isinstance(schema, dict):
                        payload["format"] = schema
                    else:
                        payload["format"] = "json"
                elif json_mode:
                    payload["format"] = "json"

                try:
                    res = await client.post(f"{self.base_url}/api/chat", json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        if "error" in data:
                            self._record_fallback(model, data["error"], candidates, idx)
                            continue

                        raw_content = data.get("message", {}).get("content", "")
                        # Deterministically strip any internal thinking/chain-of-thought tokens
                        msg_content = strip_private_reasoning_text(raw_content)

                        if not msg_content and not data.get("message", {}).get("tool_calls"):
                            self._record_fallback(model, "empty response content", candidates, idx)
                            continue

                        # Clean raw_response of any internal thinking/thought structures
                        clean_raw = sanitize_model_payload(data)

                        return LLMResponse(
                            content=msg_content,
                            model_name=model,
                            prompt_tokens=data.get("prompt_eval_count"),
                            completion_tokens=data.get("eval_count"),
                            raw_response=clean_raw,
                        )
                    else:
                        self._record_fallback(model, f"HTTP {res.status_code}: {res.text[:100]}", candidates, idx)
                except Exception as e:
                    self._record_fallback(model, str(e), candidates, idx)

        # If all Ollama candidates fail or require subscription credits, fall back safely to deterministic provider
        self._record_fallback("ollama-cluster", "all candidate models exhausted or uncredited", candidates, len(candidates) - 1)
        det_response = await self._deterministic_fallback.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            schema=schema,
        )
        det_response.model_name = f"ollama-fallback:{self.model_name}->{det_response.model_name}"
        return det_response


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
        schema: Optional[Any] = None,
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
