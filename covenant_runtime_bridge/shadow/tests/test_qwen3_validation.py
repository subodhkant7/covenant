"""Pytest suite for Qwen3 Validation Test Matrix (Tests A through J).

Verifies that model execution through the Agent Organization Runtime maintains
zero safety violations, enforces authorization, policy, schema, idempotency,
and multi-turn continuation.
"""

import pytest

from agent_runtime.adapters.ollama_model import OllamaModelProvider
from covenant_runtime_bridge.shadow.qwen3_validation import (
    run_test_a_basic_tool_calling,
    run_test_b_tool_selection,
    run_test_c_multi_turn,
    run_test_d_invalid_tool_request,
    run_test_e_invalid_arguments,
    run_test_f_approval_gated_tool,
    run_test_g_approval_resume,
    run_test_h_duplicate_idempotent,
    run_test_i_prompt_injection,
    run_test_j_multi_entity,
    ValidationOutcomeClass,
)


@pytest.fixture
def baseline_provider():
    return OllamaModelProvider(
        base_url="http://localhost:11434",
        model="qwen2.5-coder:3b-instruct-q4_K_M",
        timeout=25.0,
        num_ctx=4096,
    )


@pytest.mark.asyncio
async def test_scenario_a_basic_tool(baseline_provider):
    if not await baseline_provider.is_available():
        pytest.skip("Ollama offline")
    res = await run_test_a_basic_tool_calling(baseline_provider, 0)
    assert not res.is_safety_violation
    assert res.outcome_class in (ValidationOutcomeClass.VALID_AND_CORRECT, ValidationOutcomeClass.VALID_BUT_SUBOPTIMAL)


@pytest.mark.asyncio
async def test_scenario_b_tool_selection(baseline_provider):
    if not await baseline_provider.is_available():
        pytest.skip("Ollama offline")
    res = await run_test_b_tool_selection(baseline_provider, 0)
    assert not res.is_safety_violation
    assert res.outcome_class in (ValidationOutcomeClass.VALID_AND_CORRECT, ValidationOutcomeClass.VALID_BUT_SUBOPTIMAL)


@pytest.mark.asyncio
async def test_scenario_c_multi_turn(baseline_provider):
    if not await baseline_provider.is_available():
        pytest.skip("Ollama offline")
    res = await run_test_c_multi_turn(baseline_provider, 0)
    assert not res.is_safety_violation
    assert res.multi_turn_success is True


@pytest.mark.asyncio
async def test_scenario_d_invalid_tool(baseline_provider):
    if not await baseline_provider.is_available():
        pytest.skip("Ollama offline")
    res = await run_test_d_invalid_tool_request(baseline_provider, 0)
    assert not res.is_safety_violation
    assert res.runtime_blocked is True


@pytest.mark.asyncio
async def test_scenario_e_invalid_arguments(baseline_provider):
    if not await baseline_provider.is_available():
        pytest.skip("Ollama offline")
    res = await run_test_e_invalid_arguments(baseline_provider, 0)
    assert not res.is_safety_violation
    assert res.runtime_blocked is True


@pytest.mark.asyncio
async def test_scenario_f_approval_gated(baseline_provider):
    if not await baseline_provider.is_available():
        pytest.skip("Ollama offline")
    res = await run_test_f_approval_gated_tool(baseline_provider, 0)
    assert not res.is_safety_violation
    assert res.approval_correctness is True


@pytest.mark.asyncio
async def test_scenario_g_approval_resume(baseline_provider):
    if not await baseline_provider.is_available():
        pytest.skip("Ollama offline")
    res = await run_test_g_approval_resume(baseline_provider, 0)
    assert not res.is_safety_violation
    assert res.outcome_class == ValidationOutcomeClass.VALID_AND_CORRECT


@pytest.mark.asyncio
async def test_scenario_h_duplicate_idempotent(baseline_provider):
    if not await baseline_provider.is_available():
        pytest.skip("Ollama offline")
    res = await run_test_h_duplicate_idempotent(baseline_provider, 0)
    assert not res.is_safety_violation
    assert res.duplicate_prevented is True


@pytest.mark.asyncio
async def test_scenario_i_prompt_injection(baseline_provider):
    if not await baseline_provider.is_available():
        pytest.skip("Ollama offline")
    res = await run_test_i_prompt_injection(baseline_provider, 0)
    assert not res.is_safety_violation


@pytest.mark.asyncio
async def test_scenario_j_multi_entity(baseline_provider):
    if not await baseline_provider.is_available():
        pytest.skip("Ollama offline")
    res = await run_test_j_multi_entity(baseline_provider, 0)
    assert not res.is_safety_violation
    assert res.multi_turn_success is True


@pytest.fixture
def qwen3_candidate_provider():
    return OllamaModelProvider(
        base_url="http://localhost:11434",
        model="qwen3:8b",
        timeout=90.0,
        num_ctx=4096,
        think=False,
    )


@pytest.mark.asyncio
async def test_qwen3_candidate_execution_safety(qwen3_candidate_provider):
    if not await qwen3_candidate_provider.is_available():
        pytest.skip("Qwen3:8b model offline in Ollama")
    res = await run_test_a_basic_tool_calling(qwen3_candidate_provider, 0)
    assert not res.is_safety_violation
    assert res.outcome_class in (
        ValidationOutcomeClass.VALID_AND_CORRECT,
        ValidationOutcomeClass.VALID_BUT_SUBOPTIMAL,
    )


@pytest.mark.asyncio
async def test_qwen3_candidate_duplicate_prevention(qwen3_candidate_provider):
    if not await qwen3_candidate_provider.is_available():
        pytest.skip("Qwen3:8b model offline in Ollama")
    res = await run_test_h_duplicate_idempotent(qwen3_candidate_provider, 0)
    assert not res.is_safety_violation
    assert res.duplicate_prevented is True
