"""Model Provider Abstraction Layer for Covenant."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Normalized chat message."""
    role: str = Field(..., description="'system', 'user', or 'assistant'")
    content: str


class LLMResponse(BaseModel):
    """Normalized response from LLM."""
    content: str
    model_name: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    raw_response: Optional[Dict[str, Any]] = None


import re

def strip_private_reasoning_text(text: str) -> str:
    """
    Deterministically strip internal chain-of-thought, <think>...</think>,
    <thought>...</thought>, and reasoning markers.
    """
    if not text:
        return ""
    # Strip multi-line thinking blocks
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<thought>.*?</thought>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    # Strip any dangling/unclosed tags
    cleaned = re.sub(r'</?(?:think|thought)>', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def sanitize_model_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministically strip internal reasoning fields ('thinking', 'thought', etc.)
    from raw model responses and dictionaries before storage or public exposure.
    """
    if not isinstance(data, dict):
        return {}
    clean = {}
    for k, v in data.items():
        if k in ("thinking", "thought", "reasoning", "chain_of_thought"):
            continue
        if isinstance(v, dict):
            clean[k] = sanitize_model_payload(v)
        elif isinstance(v, list):
            clean[k] = [sanitize_model_payload(x) if isinstance(x, dict) else x for x in v]
        elif isinstance(v, str) and k in ("content", "rationale", "summary"):
            clean[k] = strip_private_reasoning_text(v)
        else:
            clean[k] = v
    return clean

class AbstractModelProvider(ABC):
    """Abstract interface for LLM backends (Ollama, Bedrock, etc.)."""

    @abstractmethod
    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        schema: Optional[Any] = None,
    ) -> LLMResponse:
        """Send chat messages and get response."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Healthcheck whether the provider is currently reachable."""
        pass

