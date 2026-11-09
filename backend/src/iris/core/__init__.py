"""Núcleo de infraestrutura e abstração de provedores de LLM da plataforma Íris."""
from iris.core.llm_client import (
    FRASE_SEM_RESPOSTA,
    BaseLLMProvider,
    ExtractiveFallbackLLMProvider,
    GroqLLMProvider,
    HybridLLMClient,
    LLMResponse,
    OllamaLLMProvider,
    get_llm_client,
    strip_thinking_tags,
)

__all__ = [
    "FRASE_SEM_RESPOSTA",
    "BaseLLMProvider",
    "ExtractiveFallbackLLMProvider",
    "GroqLLMProvider",
    "HybridLLMClient",
    "LLMResponse",
    "OllamaLLMProvider",
    "get_llm_client",
    "strip_thinking_tags",
]
