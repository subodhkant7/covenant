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


class AbstractModelProvider(ABC):
    """Abstract interface for LLM backends (Ollama, Bedrock, etc.)."""

    @abstractmethod
    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Send chat messages and get response."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Healthcheck whether the provider is currently reachable."""
        pass
