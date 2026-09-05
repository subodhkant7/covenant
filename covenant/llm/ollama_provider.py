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
        if "extract commitments" in last_msg.lower():
            content = json.dumps({
                "commitments_found": 1,
                "summary": "Extracted commitment from workspace evidence",
            })
        elif "verify" in last_msg.lower():
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
