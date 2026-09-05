"""Exploration and calibration script for Qwen3 8B context window and thinking mode."""

import asyncio
import json
import os
import subprocess
import time
from typing import Any, Dict, List, Optional
import httpx

from agent_runtime.adapters.model_agent import ModelDrivenAgent
from agent_runtime.adapters.ollama_model import OllamaModelProvider
from agent_runtime.core.contracts.agent import AgentDefinition
from agent_runtime.core.contracts.context import Task, TaskContext
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from covenant.synthetic_data.store import workspace_store
from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap
from covenant_runtime_bridge.shadow.isolation import (
    ExternalSideEffectGuard,
    clone_workspace_store,
    scoped_workspace_store,
)


def get_memory_stats() -> Dict[str, Any]:
    try:
        res = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=5)
        for line in res.stdout.splitlines():
            if "System-wide memory free percentage:" in line:
                return {"free_pct": line.split(":")[-1].strip(), "raw": line.strip()}
    except Exception as e:
        return {"error": str(e)}
    return {"free_pct": "unknown"}


async def inspect_model_metadata(model_name: str = "qwen3:8b") -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post("http://localhost:11434/api/show", json={"model": model_name})
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text}"}
        data = resp.json()
        details = data.get("details", {})
        model_info = data.get("model_info", {})
        params = data.get("parameters", "")
        template = data.get("template", "")
        capabilities = data.get("capabilities", [])
        return {
            "family": details.get("family"),
            "parameter_size": details.get("parameter_size"),
            "quantization_level": details.get("quantization_level"),
            "capabilities": capabilities,
            "context_length": model_info.get("general.context_length") or details.get("context_length"),
            "parameters": params,
            "has_think_in_template": ("<think>" in template or "think" in template),
        }


async def test_raw_provider(model_name: str = "qwen3:8b", think: Optional[bool] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": "What is the status of project PRJ-ATLAS? Call get_project_status."}
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_project_status",
                    "description": "Get status for a project",
                    "parameters": {
                        "type": "object",
                        "properties": {"project_id": {"type": "string"}},
                        "required": ["project_id"],
                    },
                },
            }
        ],
        "stream": False,
        "options": {"num_ctx": 4096, "temperature": 0.1},
    }
    if think is not None:
        payload["think"] = think
        payload["options"]["think"] = think

    async with httpx.AsyncClient(timeout=60.0) as client:
        t0 = time.perf_counter()
        resp = await client.post("http://localhost:11434/api/chat", json=payload)
        dt_ms = (time.perf_counter() - t0) * 1000.0

    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text}", "status_code": resp.status_code}

    data = resp.json()
    msg = data.get("message", {})
    content = msg.get("content", "")
    tool_calls = msg.get("tool_calls", [])
    thinking_field = msg.get("thinking")
    has_think_tags = ("<think>" in content or "</think>" in content)

    # Sanitize content for output: truncate if excessively long
    sanitized_content = content[:150] + "..." if len(content) > 150 else content

    return {
        "status_code": 200,
        "latency_ms": dt_ms,
        "load_duration_ms": (data.get("load_duration", 0) or 0) / 1e6,
        "prompt_eval_duration_ms": (data.get("prompt_eval_duration", 0) or 0) / 1e6,
        "eval_duration_ms": (data.get("eval_duration", 0) or 0) / 1e6,
        "eval_count": data.get("eval_count", 0),
        "prompt_eval_count": data.get("prompt_eval_count", 0),
        "has_tool_calls_field": len(tool_calls) > 0,
        "tool_calls_count": len(tool_calls),
        "tool_names": [tc.get("function", {}).get("name") for tc in tool_calls],
        "has_thinking_field": bool(thinking_field),
        "has_think_tags": has_think_tags,
        "sanitized_content_sample": sanitized_content.replace("\n", " "),
    }


async def test_runtime_context_calibration(
    model_name: str,
    num_ctx: int,
    think: Optional[bool] = None,
) -> Dict[str, Any]:
    mem_before = get_memory_stats()
    t0 = time.perf_counter()

    provider = OllamaModelProvider(
        base_url="http://localhost:11434",
        model=model_name,
        timeout=60.0,
        num_ctx=num_ctx,
        think=think,
    )

    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(bridge_env.tools, bridge_env.permissions, bridge_env.policy, sink)
    executor = AgentRunExecutor(engine, sink)

    agent_id = f"cov.calib_agent_{num_ctx}"
    agent_def = AgentDefinition(id=agent_id, name="Calib Agent", supported_roles=["covenant.resolver"])
    bridge_env.permissions.grant("org_covenant_northstar", agent_id, ["get_project_status", "search_email"])

    system_prompt = (
        "You are an operations agent. Given an inquiry, call get_project_status with project_id='PRJ-ATLAS'."
    )
    agent = ModelDrivenAgent(agent_def, provider, system_prompt=system_prompt)

    task = Task(
        id=f"tsk_calib_{num_ctx}",
        organization_id="org_covenant_northstar",
        intent="Check project PRJ-ATLAS",
        required_role="covenant.resolver",
    )
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=task.scope,
        available_tools=bridge_env.tools.list_specs(),
        input_data={"project_id": "PRJ-ATLAS"},
        max_turns=2,
    )

    store = clone_workspace_store(workspace_store)
    run, history = None, None
    err = None
    try:
        with ExternalSideEffectGuard(), scoped_workspace_store(store):
            run, history, _ = await executor.execute_run(task, agent, ctx)
    except Exception as e:
        err = str(e)

    dt_ms = (time.perf_counter() - t0) * 1000.0
    mem_after = get_memory_stats()

    tool_called = None
    success = False
    if history and history.turns and history.turns[0].request:
        tool_called = history.turns[0].request.tool_name
        obs = history.turns[0].observation
        success = bool(obs and obs.success)

    return {
        "num_ctx": num_ctx,
        "think": think,
        "latency_ms": dt_ms,
        "tool_called": tool_called,
        "success": success,
        "error": err,
        "mem_before": mem_before.get("free_pct"),
        "mem_after": mem_after.get("free_pct"),
    }


async def main():
    print("==================================================")
    print("1. MODEL METADATA INSPECTION")
    print("==================================================")
    meta = await inspect_model_metadata("qwen3:8b")
    print(json.dumps(meta, indent=2))

    print("\n==================================================")
    print("2. RAW PROVIDER & THINKING MODE TEST")
    print("==================================================")
    print("A. Testing Default Mode (no explicit think param)...")
    res_def = await test_raw_provider("qwen3:8b", think=None)
    print(json.dumps(res_def, indent=2))

    print("\nB. Testing Thinking Disabled (think=False)...")
    res_no_think = await test_raw_provider("qwen3:8b", think=False)
    print(json.dumps(res_no_think, indent=2))

    print("\nC. Testing Thinking Enabled (think=True)...")
    res_think = await test_raw_provider("qwen3:8b", think=True)
    print(json.dumps(res_think, indent=2))

    print("\n==================================================")
    print("3. CONTEXT WINDOW CALIBRATION (4K, 8K, 16K)")
    print("==================================================")
    for ctx in [4096, 8192, 16384]:
        print(f"Testing num_ctx={ctx} (think=False)... ", end="", flush=True)
        r = await test_runtime_context_calibration("qwen3:8b", num_ctx=ctx, think=False)
        print(f"Latency: {r['latency_ms']:.1f}ms, Tool: {r['tool_called']}, Success: {r['success']}, MemFree: {r['mem_before']} -> {r['mem_after']}")


if __name__ == "__main__":
    asyncio.run(main())
