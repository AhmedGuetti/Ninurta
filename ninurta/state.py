"""State definition for the Ninurta LangGraph pipeline."""

from __future__ import annotations

from typing import TypedDict
from ninurta.schemas.job_description import JobDescription


class State(TypedDict):
    """The state dictionary shared by the extract and resume graphs."""

    # ── Extract graph ────────────────────────────────────────────────────
    jd_text: str
    parsed_job: JobDescription | None
    test_tool_result: str | None
    # Heuristic dedup verdict from job_dedup_node (against stored jobs).
    dedup_result: dict | None

    # ── Resume graph ─────────────────────────────────────────────────────
    resume_text: str
    parsed_resume: dict | None

    # ── Match graph ──────────────────────────────────────────────────────
    match_result: dict | None

    # ── Shared ───────────────────────────────────────────────────────────
    error: str | None
