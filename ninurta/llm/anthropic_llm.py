"""AnthropicLLM — Anthropic API backend."""

from __future__ import annotations

import os

from ninurta.llm.base import BaseLLM, LLMResult


class AnthropicLLM(BaseLLM):
    """Call the Anthropic API (Claude models).

    Requires:
        pip install ninurta[anthropic]
        ANTHROPIC_API_KEY env var
    """

    def __init__(self, model_id: str = "claude-3-5-haiku-20241022") -> None:
        self.model_id = model_id

    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        thinking: bool = False,
        tools: list[dict] | None = None,
    ) -> LLMResult:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Run: pip install ninurta[anthropic]"
            ) from None

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        chat_messages = [m for m in messages if m["role"] != "system"]
        system_text = "\n\n".join(system_parts) if system_parts else anthropic.NOT_GIVEN

        kwargs: dict = dict(
            model=self.model_id,
            max_tokens=max_tokens,
            system=system_text,
            messages=chat_messages,
        )

        if thinking:
            budget = min(max_tokens // 2, 4096)
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}

        response = client.messages.create(**kwargs)

        parts = [
            block.text
            for block in response.content
            if block.type == "text"
        ]
        text = "\n".join(parts)

        if hasattr(response, "usage") and response.usage:
            input_tok = response.usage.input_tokens or 0
            output_tok = response.usage.output_tokens or 0
            self.usage.record(input_tok, output_tok)

        return LLMResult(text=text.strip())
