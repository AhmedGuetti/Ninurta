"""LLM factory — resolves a model ID string to the right backend.

Model ID format:
    provider:model_name

Examples:
    local:Qwen/Qwen3-4B          → LocalLLM("Qwen/Qwen3-4B")
    openai:gpt-4o-mini           → OpenAILLM("gpt-4o-mini")
    anthropic:claude-3-5-haiku-20241022 → AnthropicLLM("claude-3-5-haiku-20241022")
    gemini:gemini-3.6-flash      → GeminiLLM("gemini-3.6-flash")
    ollama:llama3.1              → OllamaLLM("llama3.1")
    Qwen/Qwen3-4B                → LocalLLM("Qwen/Qwen3-4B")  (no prefix = local)
"""

from __future__ import annotations

from ninurta.llm.base import BaseLLM
from ninurta.config import get_default_model_id

_llm_cache: dict[str, BaseLLM] = {}


def get_llm(model_id: str | None = None) -> BaseLLM:
    """Return a configured LLM backend for *model_id*.

    If model_id is None, falls back to the default configured in config.yaml.
    LLM instances are cached to accumulate usage stats across invocations.

    Raises:
        ValueError: if the provider prefix is unknown.
    """
    if not model_id:
        model_id = get_default_model_id()

    if model_id in _llm_cache:
        return _llm_cache[model_id]

    provider, sep, name = model_id.partition(":")

    if not sep:
        from ninurta.llm.local import LocalLLM  # noqa: PLC0415
        instance = LocalLLM(model_id)
        _llm_cache[model_id] = instance
        return instance

    match provider.lower():
        case "local":
            from ninurta.llm.local import LocalLLM  # noqa: PLC0415
            instance = LocalLLM(name)

        case "openai":
            from ninurta.llm.openai_llm import OpenAILLM  # noqa: PLC0415
            instance = OpenAILLM(name)

        case "anthropic":
            from ninurta.llm.anthropic_llm import AnthropicLLM  # noqa: PLC0415
            instance = AnthropicLLM(name)

        case "ollama":
            from ninurta.llm.ollama_llm import OllamaLLM  # noqa: PLC0415
            instance = OllamaLLM(name)

        case "gemini":
            from ninurta.llm.gemini_llm import GeminiLLM  # noqa: PLC0415
            instance = GeminiLLM(name)

        case _:
            raise ValueError(
                f"Unknown LLM provider '{provider}'. "
                "Valid prefixes: local, openai, anthropic, ollama, gemini"
            )

    _llm_cache[model_id] = instance
    return instance


def clear_llm_cache() -> None:
    """Clear all cached LLM instances."""
    _llm_cache.clear()
