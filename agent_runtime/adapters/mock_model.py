"""Mock model provider for testing without external API or LLM dependencies."""

from typing import List, Optional
from agent_runtime.core.interfaces.model import IModelProvider, ModelRequest, ModelResponse, ModelToolCall


class MockModelProvider(IModelProvider):
    """Deterministic mock provider returning scripted responses."""

    def __init__(self, scripted_responses: Optional[List[ModelResponse]] = None):
        self.responses = list(scripted_responses or [])
        self.recorded_requests: List[ModelRequest] = []

    def queue_response(self, response: ModelResponse) -> None:
        self.responses.append(response)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.recorded_requests.append(request)
        if self.responses:
            return self.responses.pop(0)
        return ModelResponse(content="Default mock response.", finish_reason="stop")
