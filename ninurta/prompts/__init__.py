"""Prompts package — centralized agent prompts and prompt registry."""

from __future__ import annotations

from ninurta.prompts.registry import prompt_registry, prompt, PromptRegistry
from ninurta.prompts import job_extractor
from ninurta.prompts import resume_validator

__all__ = ["prompt_registry", "prompt", "PromptRegistry", "job_extractor", "resume_validator"]
