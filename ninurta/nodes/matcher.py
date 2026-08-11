"""Matcher node — score a resume against a parsed job description.

Runs the LLM to produce a structured match analysis, then returns it as
``match_result`` in the state dict.
"""

from __future__ import annotations

from ninurta.llm.factory import get_llm
from ninurta.nodes._llm_helpers import _call_llm, _extract_json
from ninurta.prompts.registry import prompt_registry
from ninurta.state import State
from ninurta.utils.logger import get_logger

log = get_logger(__name__)


def matcher_node(state: State) -> dict:
    """Score the parsed resume against the parsed job description."""
    parsed_job = state.get("parsed_job")
    parsed_resume = state.get("parsed_resume")
    resume_text = state.get("resume_text", "")

    if not parsed_job:
        return {"error": "No parsed job description in state."}
    if not parsed_resume and not resume_text:
        return {"error": "No resume data in state (neither parsed nor raw text)."}

    # Serialize the Pydantic model to a plain dict for the prompt
    job_dict = parsed_job.model_dump() if hasattr(parsed_job, "model_dump") else parsed_job

    try:
        llm = get_llm()
        messages = prompt_registry.get(
            "matcher",
            job_description=job_dict,
            parsed_resume=parsed_resume,
            resume_text=resume_text,
        )
        log.info("Scoring match with [bold]%s[/]...", llm.model_id)
        result = _call_llm(llm, messages, max_tokens=4096)
        data = _extract_json(result.text, llm.model_id, phase="Match scoring")

        log.info(
            "Match score: %.2f (skills=%.2f, experience=%.2f)",
            data.get("overall_score", 0),
            data.get("skills_score", 0),
            data.get("experience_score", 0),
        )
        return {"match_result": data, "error": None}

    except Exception as exc:
        log.error("Match scoring failed: %s", exc)
        return {
            "error": str(exc),
            "match_result": {"overall_score": 0, "error": str(exc)},
        }
