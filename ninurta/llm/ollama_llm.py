"""OllamaLLM — Ollama local server backend."""

from __future__ import annotations

import os

from ninurta.llm.base import BaseLLM, LLMResult

_DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaLLM(BaseLLM):
    """Call a locally-running Ollama server.

    Requires:
        pip install ninurta[ollama]   (pulls in httpx)
        An Ollama server running at OLLAMA_BASE_URL (default: http://localhost:11434)

    Pull a model first:
        ollama pull llama3.1
    """

    def __init__(self, model_id: str = "llama3.1") -> None:
        self.model_id = model_id
        self._base_url = os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")

    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        thinking: bool = False,
        tools: list[dict] | None = None,
    ) -> LLMResult:
        try:
            import httpx  # noqa: PLC0415
        except ImportError:
            raise ImportError(
                "httpx package not installed. Run: pip install ninurta[ollama]"
            ) from None

        payload = {
            "model": self.model_id,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
            },
        }

        if thinking:
            payload["think"] = True   # supported by some Ollama model variants

        if tools:
            payload["tools"] = tools

        response = httpx.post(
            f"{self._base_url}/api/chat",
            json=payload,
            timeout=300.0,   # local models can be slow
        )
        response.raise_for_status()
        data = response.json()
        content = data["message"]["content"]
        return LLMResult(text=content.strip())
