"""Prompts package — centralized agent prompts and prompt registry.

Importing this package registers every prompt module with the registry,
so any entry point (CLI, gateway, tests) gets the full set.  If a prompt
is missing here, it silently KeyErrors at runtime for entry points that
don't import it explicitly — keep this list in sync with prompts/*.py.
"""

from __future__ import annotations

from ninurta.prompts.registry import prompt_registry, prompt, PromptRegistry
from ninurta.prompts import job_extractor
from ninurta.prompts import resume_validator
from ninurta.prompts import matcher

__all__ = [
    "prompt_registry",
    "prompt",
    "PromptRegistry",
    "job_extractor",
    "resume_validator",
    "matcher",
]
