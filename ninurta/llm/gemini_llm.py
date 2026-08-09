"""GeminiLLM — Google AI Studio (Gemini) backend via the google-genai SDK."""

from __future__ import annotations

import json
import os

from ninurta.llm.base import BaseLLM, LLMResult, ToolCall
from ninurta.utils.logger import get_logger

log = get_logger(__name__)

_DEFAULT_MODEL = "gemini-3.6-flash"


class GeminiLLM(BaseLLM):
    """Call Google Gemini models via the google-genai SDK.

    Requires:
        pip install google-genai
        GEMINI_API_KEY env var  (or GOOGLE_API_KEY)

    Supports the full tool round-trip: assistant ``tool_calls`` and
    ``role: "tool"`` messages in *messages* are translated into Gemini
    ``function_call`` / ``function_response`` parts, so a LangGraph
    tool loop (llm → tool_node → llm) feeds results back correctly.
    """

    def __init__(self, model_id: str = _DEFAULT_MODEL) -> None:
        self.model_id = model_id.strip()

    # ------------------------------------------------------------------
    # Message translation:  Ninurta dicts  →  Gemini Contents
    # ------------------------------------------------------------------

    def _to_contents(self, messages: list[dict], types) -> tuple[str | None, list]:
        """Split system instruction out and build a list of Gemini Contents.

        Handles four message shapes:
          * system                        → returned separately
          * user / assistant plain text   → Content(role, [text part])
          * assistant with tool_calls     → Content("model", [function_call parts])
          * role == "tool" (tool result)  → Content("user", [function_response part])
        """
        system_instruction: str | None = None
        contents: list = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content") or ""

            if role == "system":
                # Concatenate if multiple system messages appear.
                system_instruction = (
                    f"{system_instruction}\n\n{content}" if system_instruction else content
                )
                continue

            # ── Tool result coming back from our tool_node ──────────────
            if role == "tool":
                fn_name = msg.get("name", "unknown_tool")
                response_obj = self._coerce_tool_response(content)
                contents.append(
                    types.Content(
                        role="user",  # Gemini expects function responses as user turn
                        parts=[
                            types.Part.from_function_response(
                                name=fn_name,
                                response=response_obj,
                            )
                        ],
                    )
                )
                continue

            # ── Assistant turn that requested tool calls ────────────────
            tool_calls = msg.get("tool_calls")
            if role == "assistant" and tool_calls:
                parts = []
                if content:  # optional preamble text alongside the calls
                    parts.append(types.Part.from_text(text=content))
                for call in tool_calls:
                    parts.append(
                        types.Part.from_function_call(
                            name=call["name"],
                            args=call.get("arguments", {}),
                        )
                    )
                contents.append(types.Content(role="model", parts=parts))
                continue

            # ── Plain user / assistant text ─────────────────────────────
            gemini_role = "model" if role == "assistant" else "user"
            contents.append(
                types.Content(
                    role=gemini_role,
                    parts=[types.Part.from_text(text=content)],
                )
            )

        return system_instruction, contents

    @staticmethod
    def _coerce_tool_response(content: str) -> dict:
        """Gemini function_response.response must be a dict. Wrap non-dicts.

        Our tool_node JSON-encodes tool output, so try to decode it first;
        fall back to wrapping the raw string under a ``result`` key.
        """
        try:
            decoded = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {"result": content}
        return decoded if isinstance(decoded, dict) else {"result": decoded}

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        thinking: bool = False,
        tools: list[dict] | None = None,
    ) -> LLMResult:
        try:
            from google import genai  # noqa: PLC0415
            from google.genai import types  # noqa: PLC0415
        except ImportError:
            raise ImportError(
                "google-genai package not installed. Run: pip install ninurta[gemini]"
            ) from None

        from ninurta.config import get_gemini_api_key  # noqa: PLC0415
        api_key = get_gemini_api_key()
        if not api_key:
            raise EnvironmentError(
                "Gemini API key is not set. Set GEMINI_API_KEY / GOOGLE_API_KEY environment variables, or configure 'gemini_api_key' in config.yaml."
            )

        client = genai.Client(api_key=api_key)

        # ── Build contents + config ────────────────────────────────────
        system_instruction, contents = self._to_contents(messages, types)

        config_kwargs: dict = {"max_output_tokens": max_tokens}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        # Map OpenAI-style JSON schemas → Gemini tools
        if tools:
            func_decls = [
                types.FunctionDeclaration(
                    name=t["function"]["name"],
                    description=t["function"].get("description", ""),
                    parameters=t["function"].get("parameters"),
                )
                for t in tools
            ]
            config_kwargs["tools"] = [types.Tool(function_declarations=func_decls)]

        config = types.GenerateContentConfig(**config_kwargs)

        # ── Call the API ───────────────────────────────────────────────
        response = client.models.generate_content(
            model=self.model_id,
            contents=contents,
            config=config,
        )

        # ── Extract output ─────────────────────────────────────────────
        thinking_text = ""
        reply_text = ""
        tool_calls: list[ToolCall] = []

        for part in response.candidates[0].content.parts:
            if getattr(part, "thought", False):
                thinking_text += part.text or ""
            elif getattr(part, "function_call", None):
                fc = part.function_call
                args = fc.args
                args_dict = args if isinstance(args, dict) else dict(args)
                tool_calls.append(ToolCall(name=fc.name, arguments=args_dict))
            elif getattr(part, "text", None):
                reply_text += part.text

        if thinking_text:
            log.debug(
                "[bold yellow]🧠 GEMINI THINKING[/bold yellow]\n%s",
                thinking_text.strip(),
            )

        # ── Track token usage ──────────────────────────────────────────
        meta = response.usage_metadata
        if meta:
            input_tok = meta.prompt_token_count or 0
            output_tok = meta.candidates_token_count or 0
            thinking_tok = getattr(meta, "thoughts_token_count", 0) or 0
            self.usage.record(input_tok, output_tok, thinking_tok)
            log.info(
                "[dim]tokens → in: %d  out: %d  think: %d[/dim]",
                input_tok, output_tok, thinking_tok,
            )

        return LLMResult(text=reply_text.strip(), tool_calls=tool_calls)