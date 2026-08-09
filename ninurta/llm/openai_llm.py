"""OpenAILLM — OpenAI API backend."""

from __future__ import annotations

import json
import os

from ninurta.llm.base import BaseLLM, LLMResult, ToolCall


class OpenAILLM(BaseLLM):
    """Call OpenAI-compatible APIs (OpenAI, Azure, etc.).

    Requires:
        pip install openai
        OPENAI_API_KEY env var (or OPENAI_BASE_URL for compatible endpoints)
    """

    def __init__(self, model_id: str = "gpt-4o-mini") -> None:
        self.model_id = model_id

    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        thinking: bool = False,
        tools: list[dict] | None = None,
    ) -> LLMResult:
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError:
            raise ImportError(
                "openai package not installed. Run: pip install ninurta[openai]"
            ) from None

        client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL"),  # None = default
        )

        kwargs: dict = dict(
            model=self.model_id,
            messages=messages,
            max_completion_tokens=max_tokens,
        )

        # o-series reasoning models support reasoning_effort
        if thinking and self.model_id.startswith(("o1", "o3", "o4")):
            kwargs["reasoning_effort"] = "high"

        if tools:
            kwargs["tools"] = tools

        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message
        content = msg.content or ""

        tool_calls: list[ToolCall] = []
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {"raw": tc.function.arguments}
                tool_calls.append(ToolCall(name=tc.function.name, arguments=args))

        if hasattr(response, "usage") and response.usage:
            input_tok = response.usage.prompt_tokens or 0
            output_tok = response.usage.completion_tokens or 0
            self.usage.record(input_tok, output_tok)

        return LLMResult(text=content.strip(), tool_calls=tool_calls)
