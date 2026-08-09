"""ninurta.llm — unified LLM proxy package.

Usage:
    from ninurta.llm import get_llm

    llm = get_llm("gemini:gemini-3.6-flash")
    result = llm.complete([{"role": "user", "content": "Hello!"}])
"""

from ninurta.llm.base import BaseLLM, LLMResult, ToolCall, UsageStats, get_pricing
from ninurta.llm.factory import get_llm, clear_llm_cache

__all__ = [
    "BaseLLM",
    "LLMResult",
    "ToolCall",
    "UsageStats",
    "get_pricing",
    "get_llm",
    "clear_llm_cache",
]
