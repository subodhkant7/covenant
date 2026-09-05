"""Generic model provider abstraction (LLM / Model agnostic)."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from agent_runtime.core.contracts.tool import ToolSpec


class ModelMessage(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str


class ModelToolCall(BaseModel):
    call_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ModelRequest(BaseModel):
    messages: List[ModelMessage]
    available_tools: List[ToolSpec] = Field(default_factory=list)
    temperature: float = 0.1
    response_schema: Optional[Dict[str, Any]] = None


class ModelResponse(BaseModel):
    content: Optional[str] = None
    tool_calls: List[ModelToolCall] = Field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = Field(default_factory=dict)


class IModelProvider(ABC):
    """Pluggable model provider interface."""

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        pass
