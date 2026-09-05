"""OllamaModelProvider: Local LLM adapter using standard HTTP with dual schema & content parsing and connection resilience."""

import asyncio
import json
from typing import Any, Dict, List, Optional
import httpx

from agent_runtime.core.interfaces.model import (
    IModelProvider,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
)


class ModelProviderError(Exception):
    """Raised when an external model provider fails."""
    pass


class OllamaModelProvider(IModelProvider):
    """
    Adapter for locally-hosted Ollama server.
    Conforms strictly to IModelProvider without leaking Ollama specifics to runtime core.
    Supports native function-calling, single JSON content, line-delimited multi-tool parsing,
    and transient connection retry.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:3b-instruct-q4_K_M",
        timeout: float = 30.0,
        http_client: Optional[httpx.AsyncClient] = None,
        num_ctx: Optional[int] = None,
        think: Optional[bool] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._external_client = http_client
        self.num_ctx = num_ctx
        self.think = think

    async def is_available(self) -> bool:
        """Check if Ollama server is running, reachable, and has the configured model available."""
        client = self._external_client or httpx.AsyncClient(timeout=3.0)
        try:
            res = await client.get(f"{self.base_url}/api/tags")
            if res.status_code != 200:
                return False
            data = res.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            return any(self.model == m or self.model in m or m.startswith(self.model.split(":")[0]) for m in models)
        except Exception:
            return False
        finally:
            if not self._external_client:
                await client.aclose()

    async def generate(self, request: ModelRequest) -> ModelResponse:
        url = f"{self.base_url}/api/chat"

        # 1. Transform messages
        messages: List[Dict[str, Any]] = [
            {"role": m.role, "content": m.content}
            for m in request.messages
        ]

        # 2. Transform tool schemas
        tools: Optional[List[Dict[str, Any]]] = None
        if request.available_tools:
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters_schema,
                    },
                }
                for t in request.available_tools
            ]

        options: Dict[str, Any] = {
            "temperature": request.temperature,
            "num_predict": 128,
        }
        if self.num_ctx is not None:
            options["num_ctx"] = self.num_ctx

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if self.think is not None:
            payload["think"] = self.think
        if tools:
            payload["tools"] = tools
        if request.response_schema:
            payload["format"] = request.response_schema

        # 3. HTTP Request with single transient retry
        last_err: Optional[Exception] = None
        for attempt in range(2):
            client = self._external_client or httpx.AsyncClient(timeout=self.timeout)
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    raise ModelProviderError(f"Ollama API returned HTTP {resp.status_code}: {resp.text}")
                data = resp.json()
                break
            except (httpx.RequestError, httpx.RemoteProtocolError) as e:
                last_err = e
                if attempt == 0:
                    await asyncio.sleep(0.3)
                    continue
                raise ModelProviderError(f"Failed to connect to Ollama service at {self.base_url}: {str(e)}") from e
            finally:
                if not self._external_client:
                    await client.aclose()

        # 4. Map Response
        msg = data.get("message", {})
        raw_content = msg.get("content")
        raw_tool_calls = msg.get("tool_calls", [])

        # Extract thinking trace safely without exposing in reports or final answers
        has_thinking = bool(msg.get("thinking"))
        content = raw_content
        if content and ("<think>" in content or "</think>" in content):
            has_thinking = True
            if "</think>" in content:
                parts = content.split("</think>", 1)
                content = parts[1].strip()
            elif "<think>" in content:
                parts = content.split("<think>", 1)
                content = parts[0].strip()

        parsed_calls: List[ModelToolCall] = []
        for idx, call in enumerate(raw_tool_calls):
            fn = call.get("function", {})
            fn_name = fn.get("name", "")
            fn_args = fn.get("arguments", {})
            if isinstance(fn_args, str):
                try:
                    fn_args = json.loads(fn_args)
                except Exception:
                    fn_args = {}
            parsed_calls.append(
                ModelToolCall(
                    call_id=f"call_{idx}",
                    tool_name=fn_name,
                    arguments=fn_args,
                )
            )

        # Fallback: Parse structured tool call(s) from content if raw_tool_calls was empty
        if not parsed_calls and content:
            trimmed = content.strip()
            if "```json" in trimmed:
                parts = trimmed.split("```json")
                if len(parts) > 1:
                    trimmed = parts[1].split("```")[0].strip()
            elif "```" in trimmed:
                parts = trimmed.split("```")
                if len(parts) > 1:
                    trimmed = parts[1].split("```")[0].strip()

            # Attempt 1: Single JSON object
            if trimmed.startswith("{") and trimmed.endswith("}"):
                try:
                    data_obj = json.loads(trimmed)
                    if "name" in data_obj:
                        parsed_calls.append(
                            ModelToolCall(
                                call_id="call_content_0",
                                tool_name=data_obj["name"],
                                arguments=data_obj.get("arguments", {}),
                            )
                        )
                except Exception:
                    pass

            # Attempt 2: Line-by-line JSON objects (detects multiple tool calls)
            if not parsed_calls:
                lines = [l.strip() for l in trimmed.splitlines() if l.strip()]
                for idx, line in enumerate(lines):
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            obj = json.loads(line)
                            if "name" in obj:
                                parsed_calls.append(
                                    ModelToolCall(
                                        call_id=f"call_line_{idx}",
                                        tool_name=obj["name"],
                                        arguments=obj.get("arguments", {}),
                                    )
                                )
                        except Exception:
                            pass

        return ModelResponse(
            content=content,
            tool_calls=parsed_calls,
            finish_reason="stop" if not parsed_calls else "tool_calls",
            usage={
                "prompt_eval_count": data.get("prompt_eval_count", 0),
                "eval_count": data.get("eval_count", 0),
                "load_duration": data.get("load_duration", 0),
                "prompt_eval_duration": data.get("prompt_eval_duration", 0),
                "eval_duration": data.get("eval_duration", 0),
                "total_duration": data.get("total_duration", 0),
                "has_thinking": has_thinking,
            },
        )
