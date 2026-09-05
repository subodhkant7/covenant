"""Tests for model provider adapters and Section 21 ModelDrivenAgent boundary test."""

import pytest
import httpx

from agent_runtime.adapters.mock_model import MockModelProvider
from agent_runtime.adapters.model_agent import ModelDrivenAgent
from agent_runtime.adapters.ollama_model import ModelProviderError, OllamaModelProvider
from agent_runtime.core.contracts.agent import (
    AgentDefinition,
    AgentRunHistory,
    AgentStepComplete,
    AgentStepToolRequest,
)
from agent_runtime.core.contracts.context import TaskContext, TaskScope
from agent_runtime.core.contracts.tool import ToolSpec
from agent_runtime.core.interfaces.model import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
)


@pytest.mark.asyncio
async def test_mock_model_provider_scripted_output():
    provider = MockModelProvider()
    provider.queue_response(
        ModelResponse(
            content="I will call the search tool.",
            tool_calls=[ModelToolCall(call_id="call_1", tool_name="search", arguments={"q": "status"})],
            finish_reason="tool_calls",
        )
    )
    provider.queue_response(
        ModelResponse(content="Search completed. Everything is good.", finish_reason="stop")
    )

    req1 = ModelRequest(messages=[ModelMessage(role="user", content="Check status")])
    res1 = await provider.generate(req1)
    assert len(res1.tool_calls) == 1
    assert res1.tool_calls[0].tool_name == "search"

    req2 = ModelRequest(messages=[ModelMessage(role="user", content="Next step")])
    res2 = await provider.generate(req2)
    assert res2.content == "Search completed. Everything is good."
    assert len(res2.tool_calls) == 0


@pytest.mark.asyncio
async def test_ollama_model_provider_with_mocked_http():
    """Tests Ollama adapter request/response mapping using an in-memory HTTP transport."""
    def handler(request: httpx.Request):
        assert request.url.path == "/api/chat"
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "Analyzing logs.",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "read_syslog",
                                "arguments": {"service": "nginx"},
                            }
                        }
                    ],
                },
                "prompt_eval_count": 42,
                "eval_count": 18,
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaModelProvider(base_url="http://mock-ollama:11434", http_client=mock_client)

    req = ModelRequest(
        messages=[ModelMessage(role="user", content="Diagnose nginx")],
        available_tools=[ToolSpec(name="read_syslog", description="reads syslog")],
    )
    res = await provider.generate(req)
    assert res.content == "Analyzing logs."
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].tool_name == "read_syslog"
    assert res.tool_calls[0].arguments["service"] == "nginx"
    assert res.usage["eval_count"] == 18

    await mock_client.aclose()


@pytest.mark.asyncio
async def test_ollama_model_provider_connection_failure():
    """Verifies that unreachable Ollama server produces clean ModelProviderError."""
    def failing_handler(request: httpx.Request):
        raise httpx.ConnectError("Connection refused by host")

    failing_client = httpx.AsyncClient(transport=httpx.MockTransport(failing_handler))
    provider = OllamaModelProvider(base_url="http://unreachable:11434", http_client=failing_client)

    with pytest.raises(ModelProviderError) as exc_info:
        await provider.generate(ModelRequest(messages=[ModelMessage(role="user", content="hello")]))

    assert "Failed to connect to Ollama service" in str(exc_info.value)
    await failing_client.aclose()


@pytest.mark.asyncio
async def test_section_21_agent_model_provider_boundary():
    """
    Section 21: Prove that the exact same Agent can run against MockModelProvider
    and OllamaModelProvider without changing the Agent contract.
    """
    agent_defn = AgentDefinition(
        id="generic_ops_agent",
        name="Generic Ops Agent",
        supported_roles=["role_ops"],
    )
    tool_spec = ToolSpec(name="ping", description="pings a host", parameters_schema={"type": "object"})

    context = TaskContext(
        task_id="tsk_boundary_01",
        organization_id="org_test",
        intent="Check network latency",
        required_role="role_ops",
        scope=TaskScope(),
        available_tools=[tool_spec],
    )
    history = AgentRunHistory(run_id="run_b_01", task_id="tsk_boundary_01")

    # 1. Run Agent against MockModelProvider
    mock_provider = MockModelProvider([
        ModelResponse(
            content="Pinging gateway.",
            tool_calls=[ModelToolCall(call_id="c1", tool_name="ping", arguments={"host": "gateway.local"})],
        )
    ])
    agent_with_mock = ModelDrivenAgent(agent_defn, mock_provider)
    step_result_mock = await agent_with_mock.step(context, history)

    assert isinstance(step_result_mock, AgentStepToolRequest)
    assert step_result_mock.request.tool_name == "ping"
    assert step_result_mock.request.arguments["host"] == "gateway.local"

    # 2. Run the EXACT SAME Agent class against OllamaModelProvider
    def ollama_handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "Pinging gateway via Ollama.",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "ping",
                                "arguments": {"host": "gateway.local"},
                            }
                        }
                    ],
                }
            },
        )

    ollama_client = httpx.AsyncClient(transport=httpx.MockTransport(ollama_handler))
    ollama_provider = OllamaModelProvider(http_client=ollama_client)
    agent_with_ollama = ModelDrivenAgent(agent_defn, ollama_provider)
    step_result_ollama = await agent_with_ollama.step(context, history)

    assert isinstance(step_result_ollama, AgentStepToolRequest)
    assert step_result_ollama.request.tool_name == "ping"
    assert step_result_ollama.request.arguments["host"] == "gateway.local"

    await ollama_client.aclose()
