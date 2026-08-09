"""Prompt Registry for managing agent prompt templates and builders."""

from __future__ import annotations

from typing import Callable, Any


class PromptRegistry:
    """Stores prompt templates or generator functions by name."""

    def __init__(self) -> None:
        self._prompts: dict[str, Callable[..., list[dict]]] = {}

    def register(self, prompt_name: str) -> Callable[[Callable[..., list[dict]]], Callable[..., list[dict]]]:
        """Decorator to register a prompt builder function."""
        def decorator(func: Callable[..., list[dict]]) -> Callable[..., list[dict]]:
            self._prompts[prompt_name] = func
            return func
        return decorator

    def get(self, prompt_name: str, *args: Any, **kwargs: Any) -> list[dict]:
        """Retrieve and evaluate a registered prompt by name."""
        if prompt_name not in self._prompts:
            raise KeyError(f"Prompt '{prompt_name}' is not registered.")
        return self._prompts[prompt_name](*args, **kwargs)

    def clear(self) -> None:
        """Clear all registered prompts."""
        self._prompts.clear()


# Global default prompt registry instance
prompt_registry = PromptRegistry()
prompt = prompt_registry.register
