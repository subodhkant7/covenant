"""Model Provider and Strands Model Factory for Covenant."""

import logging
from typing import Any, Optional

from strands.models.model import Model

from covenant.config import settings
from covenant.llm.bedrock_provider import BedrockModelProvider
from covenant.llm.ollama_provider import DeterministicFallbackProvider, OllamaModelProvider
from covenant.llm.provider import AbstractModelProvider

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ("deterministic", "ollama", "local", "bedrock", "gemini")


def get_model_provider(
    provider_name: Optional[str] = None,
    **overrides: Any,
) -> AbstractModelProvider:
    """
    Construct and return the configured Covenant LLM provider adapter.

    Args:
        provider_name: Explicit provider name ('deterministic', 'ollama', 'bedrock', 'gemini').
                       Defaults to settings.model_provider / COVENANT_MODEL_PROVIDER.
        **overrides: Constructor kwargs passed to the specific provider implementation.
    """
    import os
    env_provider = os.getenv("COVENANT_MODEL_PROVIDER")
    provider = (provider_name or env_provider or settings.model_provider).strip().lower()

    if provider in ("deterministic", "default"):
        return DeterministicFallbackProvider(**overrides)
    elif provider in ("ollama", "local"):
        return OllamaModelProvider(**overrides)
    elif provider == "bedrock":
        return BedrockModelProvider(**overrides)
    elif provider == "gemini":
        from covenant.llm.gemini_provider import GeminiModelProvider
        return GeminiModelProvider(**overrides)
    else:
        raise ValueError(
            f"Invalid model provider '{provider}'. "
            f"Supported providers: {', '.join(repr(p) for p in ('deterministic', 'ollama', 'bedrock', 'gemini'))}."
        )


def get_strands_model(
    provider_name: Optional[str] = None,
    **overrides: Any,
) -> Model:
    """
    Construct and return a native Strands Model instance matching the selected provider.

    Args:
        provider_name: Explicit provider name ('deterministic', 'ollama', 'bedrock').
                       Defaults to settings.model_provider / COVENANT_MODEL_PROVIDER.
        **overrides: Constructor kwargs passed to the underlying Strands model.
    """
    import os
    env_provider = os.getenv("COVENANT_MODEL_PROVIDER")
    provider = (provider_name or env_provider or settings.model_provider).strip().lower()

    if provider in ("deterministic", "default"):
        from covenant.agents.strands_runtime import LocalDeterministicStrandsModel
        return LocalDeterministicStrandsModel(**overrides)
    elif provider in ("ollama", "local"):
        from covenant.agents.strands_runtime import OllamaStrandsModel
        return OllamaStrandsModel(**overrides)
    elif provider == "bedrock":
        bedrock_provider = BedrockModelProvider(**overrides)
        return bedrock_provider.strands_model
    elif provider == "gemini":
        from covenant.agents.strands_runtime import GeminiStrandsModel
        return GeminiStrandsModel(**overrides)
    else:
        raise ValueError(
            f"Invalid model provider '{provider}'. "
            f"Supported providers: {', '.join(repr(p) for p in ('deterministic', 'ollama', 'bedrock', 'gemini'))}."
        )

