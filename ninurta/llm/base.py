"""BaseLLM — abstract contract for all LLM backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ── Per-model pricing ($ per 1M tokens) ────────────────────────────────────
# Add new models here as needed.
_PRICING: dict[str, dict[str, float]] = {
    # Gemini
    "gemini-2.5-flash":  {"input": 0.15, "output": 0.60, "thinking": 0.70},
    "gemini-2.5-pro":    {"input": 1.25, "output": 10.0, "thinking": 3.50},
    "gemini-2.0-flash":  {"input": 0.10, "output": 0.40, "thinking": 0.0},
    "gemini-3.6-flash":  {"input": 0.15, "output": 0.60, "thinking": 0.70},
    # OpenAI
    "gpt-4o":            {"input": 2.50, "output": 10.0, "thinking": 0.0},
    "gpt-4o-mini":       {"input": 0.15, "output": 0.60, "thinking": 0.0},
    # Fallback for unknown models
    "_default":          {"input": 0.0,  "output": 0.0,  "thinking": 0.0},
}


def get_pricing(model_id: str) -> dict[str, float]:
    """Get per-1M token pricing, falling back to substring matches."""
    # 1. Exact match
    if model_id in _PRICING:
        return _PRICING[model_id]

    # 2. Substring fallback (e.g. for "gemini-3.1-flash-live-preview")
    lower_id = model_id.lower()
    if "-flash-lite" in lower_id:
        return {"input": 0.075, "output": 0.30, "thinking": 0.0}
    elif "-flash" in lower_id:
        return {"input": 0.15, "output": 0.60, "thinking": 0.70}
    elif "-pro" in lower_id:
        return {"input": 1.25, "output": 10.0, "thinking": 3.50}

    # 3. Default (free / unknown)
    return _PRICING["_default"]


@dataclass
class UsageStats:
    """Cumulative token usage across all calls."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_thinking_tokens: int = 0
    total_calls: int = 0

    def record(self, input_tokens: int, output_tokens: int, thinking_tokens: int = 0) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_thinking_tokens += thinking_tokens
        self.total_calls += 1

    def estimate_cost(self, model_id: str) -> float:
        """Estimate cost in USD based on known pricing."""
        p = get_pricing(model_id)
        return (
            self.total_input_tokens * p["input"] / 1_000_000
            + self.total_output_tokens * p["output"] / 1_000_000
            + self.total_thinking_tokens * p["thinking"] / 1_000_000
        )


@dataclass
class ToolCall:
    """Represents a tool invocation requested by the model."""
    name: str                   # Name of the tool function
    arguments: dict[str, Any]   # Decoded JSON arguments


@dataclass
class LLMResult:
    """Unified return type for every backend's ``complete()``.

    A completion is *always* an ``LLMResult``. Plain text replies carry an
    empty ``tool_calls`` list; tool-calling replies may carry both text
    (the model's reasoning / preamble) and one or more ``ToolCall``s.

    This replaces the old ``str | tuple[str, list[ToolCall]]`` union so
    callers no longer have to ``isinstance``-check the return value.
    """
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)

    def __bool__(self) -> bool:
        """Truthy if there's any content — text or a tool call."""
        return bool(self.text or self.tool_calls)

    def __str__(self) -> str:
        """Convenience for callers that only care about the text."""
        return self.text


class BaseLLM(ABC):
    """Unified interface for any language model backend.

    Implementations handle authentication, SDK specifics, and transport.
    Agents and graph nodes only ever call ``.complete()``.
    """

    model_id: str   # e.g. "Qwen/Qwen3-4B", "gpt-4o", "gemini-3.6-flash"

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

    @property
    def usage(self) -> UsageStats:
        """Cumulative token usage for this LLM instance."""
        if not hasattr(self, "_usage"):
            self._usage = UsageStats()
        return self._usage

    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        thinking: bool = False,
        tools: list[dict] | None = None,
    ) -> LLMResult:
        """Given a list of message dicts, return an :class:`LLMResult`.

        Args:
            messages:   List of ``{"role": "...", "content": "..."}`` dicts.
                        May also carry ``tool_calls`` (assistant) or
                        ``role: "tool"`` (tool results) for tool loops.
            max_tokens: Max output tokens.
            thinking:   Enable chain-of-thought / reasoning output.
            tools:      Optional list of OpenAI-style tool JSON schemas.
                        Backends that don't support tool calling should
                        ignore this argument (optionally warning).

        Returns:
            LLMResult: ``.text`` holds the assistant's reply; ``.tool_calls``
            holds any tools the model asked to invoke (empty when none).
        """