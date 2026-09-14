"""Tests for Covenant Gemini REST API Model Provider and Strands Model integration."""

import pytest
from unittest.mock import AsyncMock, patch
import httpx

from covenant.llm.factory import get_model_provider, get_strands_model, SUPPORTED_PROVIDERS
from covenant.llm.gemini_provider import GeminiModelProvider
from covenant.agents.strands_runtime import GeminiStrandsModel
from covenant.llm.provider import ChatMessage


def test_gemini_provider_registration():
    """Verify gemini is registered in SUPPORTED_PROVIDERS."""
    assert "gemini" in SUPPORTED_PROVIDERS
    provider = get_model_provider("gemini", api_key="test-key")
    assert isinstance(provider, GeminiModelProvider)
    assert provider.model_name == "gemini-2.5-flash-lite"

    strands_model = get_strands_model("gemini", api_key="test-key")
    assert isinstance(strands_model, GeminiStrandsModel)
    assert strands_model.model_name == "gemini-2.5-flash-lite"


@pytest.mark.asyncio
async def test_gemini_provider_chat_and_private_reasoning_stripping():
    """Verify Gemini provider chat completion deterministically strips private reasoning."""
    provider = GeminiModelProvider(api_key="test-key", model_name="gemini-2.5-flash-lite")

    mock_gemini_resp = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": "<think>Private chain of thought</think>Actual output text."
                }]
            }
        }],
        "usageMetadata": {
            "promptTokenCount": 20,
            "candidatesTokenCount": 15,
        }
    }

    mock_response = httpx.Response(status_code=200, json=mock_gemini_resp, request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        res = await provider.chat([ChatMessage(role="user", content="Hello")])
        assert res.content == "Actual output text."
        assert "<think>" not in res.content
        assert res.prompt_tokens == 20
        assert res.completion_tokens == 15
        assert res.model_name == "gemini-2.5-flash-lite"


@pytest.mark.asyncio
async def test_gemini_strands_model_offline_diagnostic():
    """Verify GeminiStrandsModel safely yields diagnostic when GEMINI_API_KEY is missing."""
    model = GeminiStrandsModel(api_key="", model_name="gemini-2.5-flash-lite")
    events = []
    async for event in model.stream([{"role": "user", "content": "Hello"}]):
        events.append(event)

    assert len(events) == 2
    assert "GEMINI_API_KEY missing" in events[0]["contentBlockDelta"]["delta"]["text"]
    assert events[1]["messageStop"]["stopReason"] == "end_turn"
