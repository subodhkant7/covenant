"""Gemini REST API Model Provider for Covenant."""

import json
import logging
import os
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

logger = logging.getLogger(__name__)


class GeminiModelProvider(AbstractModelProvider):
    """
    Direct Google Gemini API Model Provider using Google Generative Language REST API.
    Defaults to model: gemini-2.5-flash-lite
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or settings.gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = model_name or settings.gemini_model or os.getenv("COVENANT_GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.timeout = timeout

    @property
    def strands_model(self):
        """Return the corresponding Strands Model adapter for Gemini."""
        from covenant.agents.strands_runtime import GeminiStrandsModel
        return GeminiStrandsModel(api_key=self.api_key, model_name=self.model_name)

    async def is_available(self) -> bool:
        """Healthcheck whether Gemini API key is present and endpoint responds."""
        if not self.api_key:
            return False
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}?key={self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(url)
                return res.status_code == 200
        except Exception:
            return False

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        schema: Optional[Any] = None,
    ) -> LLMResponse:
        """Send chat messages to Gemini API and receive sanitized LLMResponse."""
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured on the server.")

        # Convert ChatMessage list into Gemini contents format
        contents = []
        for m in messages:
            role = "model" if m.role in ("assistant", "model") else "user"
            contents.append({
                "role": role,
                "parts": [{"text": m.content}],
            })

        gen_config: Dict[str, Any] = {
            "temperature": temperature,
        }
        if max_tokens:
            gen_config["maxOutputTokens"] = max_tokens
        if schema is not None:
            gen_config["responseMimeType"] = "application/json"
            if hasattr(schema, "model_json_schema"):
                gen_config["responseSchema"] = schema.model_json_schema()
            elif isinstance(schema, dict):
                gen_config["responseSchema"] = schema
        elif json_mode:
            gen_config["responseMimeType"] = "application/json"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        payload = {
            "contents": contents,
            "generationConfig": gen_config,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Gemini API error (HTTP {res.status_code}): {res.text[:200]}")
            data = res.json()

        candidates = data.get("candidates", [])
        raw_text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                raw_text = parts[0].get("text", "")

        clean_text = strip_private_reasoning_text(raw_text)
        clean_raw = sanitize_model_payload(data)

        usage = data.get("usageMetadata", {})
        prompt_tokens = usage.get("promptTokenCount")
        completion_tokens = usage.get("candidatesTokenCount")

        return LLMResponse(
            content=clean_text,
            model_name=self.model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            raw_response=clean_raw,
        )
