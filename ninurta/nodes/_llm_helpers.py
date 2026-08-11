"""Shared LLM helpers — safe LLM calls + robust JSON extraction.

All LLM-calling nodes (extractor, matcher, resume_validator) use these
helpers instead of calling ``llm.complete()`` directly, which bypasses
timeout protection and produces unhelpful error messages on failure.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from ninurta.llm.base import LLMResult
from ninurta.utils.logger import get_logger

log = get_logger(__name__)

# ── LLM call with timeout ────────────────────────────────────────────────


def _call_llm(llm, messages: list[dict], max_tokens: int = 8192, timeout: int = 120) -> LLMResult:
    """Call ``llm.complete()`` with a thread-pool timeout.

    Without this wrapper a hung API call freezes the TUI indefinitely.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(llm.complete, messages, max_tokens=max_tokens, thinking=False)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            raise TimeoutError(
                f"LLM call to {llm.model_id} timed out after {timeout}s — "
                "check your network or try again."
            ) from None


# ── Robust JSON extraction ───────────────────────────────────────────────


def _extract_json(raw: str, llm_model: str = "", phase: str = "") -> dict:
    """Extract a JSON object from an LLM response, handling common failure modes.

    Handles:
    * ``<think>...</think>`` blocks (DeepSeek-R1 style)
    * Markdown code fences (`` ```json ... ``` ``)
    * Stray leading/trailing characters (e.g. ``)...`` prefix)
    * Unicode curly-bracket lookalikes (U+FF5B / U+FF5D)
    * Empty / whitespace-only responses
    * JSON arrays (wrapped as ``{"items": [...]}``)
    * Truncated output (missing closing ``}``)

    Returns a ``dict`` on success.  Raises ``ValueError`` with a diagnostic
    message on failure.
    """
    raw_clean = raw

    # 1. Strip <think> blocks (DeepSeek-R1, QwQ, etc.)
    raw_clean = re.sub(r"<think>.*?</think>", "", raw_clean, flags=re.DOTALL)

    # 2. Strip markdown code fences
    raw_clean = re.sub(r"```(?:json)?\s*", "", raw_clean)
    raw_clean = raw_clean.replace("```", "")

    # 3. Normalise Unicode curly-bracket lookalikes
    raw_clean = raw_clean.replace("\uff5b", "{")  # ｛ → {
    raw_clean = raw_clean.replace("\uff5d", "}")  # ｝ → }

    raw_clean = raw_clean.strip()

    # 4. Empty check
    if not raw_clean:
        raise ValueError(
            f"[{phase}] {llm_model} returned an empty response — "
            "check your API key and quota."
        )

    # 5. Find JSON boundaries — first '{' and last '}'
    start = raw_clean.find("{")
    end = raw_clean.rfind("}")

    if start == -1 or end == -1 or start >= end:
        # 6. Handle truncated output (opening { but no closing })
        if start != -1 and end == -1:
            raise ValueError(
                f"[{phase}] {llm_model} response has an opening '{{' but no "
                f"closing '}}' — output may have been truncated by max_tokens. "
                f"First 100 chars: {raw[:100]!r}"
            )

        # Try array fallback
        arr_start = raw_clean.find("[")
        arr_end = raw_clean.rfind("]")
        if arr_start != -1 and arr_end != -1 and arr_start < arr_end:
            try:
                arr = json.loads(raw_clean[arr_start:arr_end + 1])
                return {"items": arr}
            except json.JSONDecodeError:
                pass
        raise ValueError(
            f"[{phase}] {llm_model} returned no JSON structure. "
            f"First 100 chars: {raw[:100]!r}"
        )

    json_str = raw_clean[start:end + 1]

    # 7. Parse
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"[{phase}] {llm_model} returned malformed JSON: {exc}. "
            f"First 300 chars: {raw[:300]!r}"
        ) from None

    if not isinstance(data, dict):
        raise ValueError(
            f"[{phase}] {llm_model} response is a JSON {type(data).__name__}, "
            f"not an object. First 100 chars: {raw[:100]!r}"
        )

    return data
