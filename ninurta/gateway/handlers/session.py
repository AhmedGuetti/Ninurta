"""Session JSON-RPC handlers."""

import logging
import threading
from typing import Any
from pathlib import Path
import json

from ninurta.config import load_config
from ninurta.db.session import SessionLocal, init_db
from ninurta.db.models import Job, Resume
from ninurta.graph import extract_graph, match_graph
from ninurta.gateway.utils import _format_cost_table

logger = logging.getLogger(__name__)

# Disk resume paths (fallback when DB is empty)
_RESUME_DIR = Path(__file__).resolve().parent.parent.parent.parent / "resume"
_RESUME_FILES = [
    _RESUME_DIR / "resume_en.docx",
    _RESUME_DIR / "resume_fr.docx",
]

# ---------------------------------------------------------------------------
# Resume loading (DB → disk fallback)
# ---------------------------------------------------------------------------

def _load_resume_from_db() -> tuple[dict | None, str | None]:
    """Return the first resume record from the DB: (parsed_json, raw_content)."""
    init_db()
    session = SessionLocal()
    try:
        resume = session.query(Resume).order_by(Resume.id.desc()).first()
        if not resume:
            return None, None
        parsed = None
        if resume.parsed_json:  # type: ignore[truthy-function]
            try:
                parsed = json.loads(resume.parsed_json)  # type: ignore[arg-type]
            except json.JSONDecodeError:
                logger.warning("resume %d has invalid parsed_json", resume.id)
        return parsed, resume.content  # type: ignore[return-value]
    finally:
        session.close()


def _load_resume_from_disk() -> tuple[dict | None, str | None]:
    """Parse the first available .docx resume from disk.

    Returns (parsed_dict, raw_text) using the resume_reader_node's parser,
    without going through the full resume graph (no LLM validation needed
    for matching — the raw parse is sufficient).
    """
    from ninurta.interface.documents import extract_text
    from ninurta.nodes.resume_reader import parse_resume

    for path in _RESUME_FILES:
        if path.exists():
            try:
                text = extract_text(path)
                if not text.strip():
                    continue
                parsed = parse_resume(text)
                logger.info("loaded resume from disk: %s", path.name)
                return parsed, text
            except Exception as exc:
                logger.warning("failed to read %s: %s", path.name, exc)
                continue
    return None, None


def _get_resume(transport) -> tuple[dict | None, str | None]:
    """Load resume data: DB first, then disk fallback."""
    transport.send_event("pipeline.progress", {"step": "loading_resume"})
    transport.send_event("turn.delta", {"text": "▸ looking up resume…\n"})

    parsed, raw = _load_resume_from_db()
    if parsed or raw:
        name = (parsed or {}).get("name", "unknown")
        sections_n = len((parsed or {}).get("sections", {}))
        transport.send_event(
            "turn.delta",
            {"text": f"  ✓ using resume from DB: {name} ({sections_n} sections) — /db resume 1 to inspect\n"}
        )
        # Also check if a disk copy exists and is newer
        from ninurta.interface.documents import extract_text
        disk_text = None
        for path in _RESUME_FILES:
            if path.exists():
                try:
                    disk_text = extract_text(path)
                    break
                except Exception:
                    continue
        if disk_text:
            transport.send_event(
                "turn.delta",
                {"text": "  💡 disk copy also available — re-parse with: ninurta resume\n"},
            )
        return parsed, raw

    transport.send_event(
        "turn.delta", {"text": "  · no resume in DB, parsing from disk…\n"}
    )
    parsed, raw = _load_resume_from_disk()
    if parsed or raw:
        name = (parsed or {}).get("name", "unknown")
        sections_n = len((parsed or {}).get("sections", {}))
        transport.send_event(
            "turn.delta", {"text": f"  ✓ parsed resume from disk: {name} ({sections_n} sections, {len(raw or '')} chars)\n"}
        )
        return parsed, raw

    transport.send_event(
        "turn.delta",
        {"text": "  ✗ no resume found in DB or on disk — scoring skipped\n"},
    )
    return None, None


# ---------------------------------------------------------------------------
# Pipeline cancellation — thread-safe flag checked between phases.
# When Ctrl+C is pressed in the TUI, ``pipeline.cancel`` sets this flag.
# The running ``session.send`` handler checks it after each blocking call
# and aborts gracefully (the old pipeline thread completes but its output
# is suppressed, and a fresh ``turn.end`` with a cancellation message is
# sent immediately).
# ---------------------------------------------------------------------------
_pipeline_cancel = threading.Event()


def handle_pipeline_cancel(params: dict, transport) -> dict:
    """Cancel the currently running pipeline (if any).

    Sends an immediate ``turn.end`` with a cancellation message so the TUI
    resets.  The running ``session.send`` thread continues to completion in
    the background but its subsequent events are harmless — the frontend
    already ended the turn.
    """
    _pipeline_cancel.set()
    transport.send_event("turn.delta", {"text": "\n⏹  cancelled\n"})
    transport.send_event("turn.end", {})
    logger.info("pipeline cancelled by user")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Handler: session.send — full pipeline (extract → resume → score)
# ---------------------------------------------------------------------------

def handle_session_send(params: dict, transport) -> dict:
    """Run the full pipeline: extract JD, load resume, score match.

    Flow:
    1. Extract structured fields from the JD text (extract_graph)
    2. Look up resume from DB (or fall back to disk)
    3. Score the resume against the JD (match_graph)
    4. Stream events back to the TUI
    """
    _pipeline_cancel.clear()  # reset cancellation state for this run

    jd_text = (params.get("message") or "").strip()
    if not jd_text:
        raise ValueError("message is required")

    # ── Phase 1: Extract JD ───────────────────────────────────────────
    cfg = load_config()
    llm_cfg = cfg.get("llm", {})
    model_id = f"{llm_cfg.get('provider', 'gemini')}:{llm_cfg.get('model', '?')}"

    # Snapshot token usage before the run so we can compute per-run delta
    from ninurta.llm.factory import get_llm
    from ninurta.llm.base import get_pricing
    _llm = get_llm()
    _before_in    = _llm.usage.total_input_tokens
    _before_out   = _llm.usage.total_output_tokens
    _before_think = _llm.usage.total_thinking_tokens

    transport.send_event(
        "pipeline.progress",
        {"step": "extractor"},
    )
    transport.send_event(
        "turn.delta",
        {"text": f"▸ extracting job description ({len(jd_text)} chars) with {model_id}…\n"},
    )

    state: dict[str, Any] = {"jd_text": jd_text}
    result = extract_graph.invoke(state)  # type: ignore[arg-type]

    if _pipeline_cancel.is_set():
        return {"status": "cancelled"}

    parsed_job = result.get("parsed_job")
    error = result.get("error")
    if error:
        transport.send_event("turn.delta", {"text": f"  ✗ extraction error: {error}\n"})
        transport.send_event("turn.end", {"text": "", "error": error})
        return {"status": "error", "error": error}

    if not parsed_job:
        transport.send_event("turn.delta", {"text": "  ✗ no parseable job found\n"})
        transport.send_event("turn.end", {"text": "(no parseable job)"})
        return {"status": "ok", "summary": "(no parseable job)"}

    job_summary = (
        f"{parsed_job.position_title} @ {parsed_job.company_name}"
    )

    # Show extraction stats so the user knows it worked
    field_count = sum(
        1 for k, v in parsed_job.model_dump().items()
        if v and v != [] and k not in ("position_title", "company_name")
    )
    skills_n = len(parsed_job.skills_required or [])
    resp_n = len(parsed_job.responsibilities or [])
    transport.send_event(
        "turn.delta",
        {"text": f"  ✓ extracted: {job_summary} ({field_count} fields, {skills_n} skills, {resp_n} responsibilities)\n"},
    )

    # ── JD dedup: check if this listing already exists in DB ──────────
    init_db()
    session = SessionLocal()
    try:
        existing = (
            session.query(Job)
            .filter(
                Job.company_name.collate("NOCASE") == (parsed_job.company_name or "").strip(),  # type: ignore[union-attr]
                Job.position_title.collate("NOCASE") == (parsed_job.position_title or "").strip(),  # type: ignore[union-attr]
            )
            .first()
        )
        if existing:
            tag = "✓applied" if existing.already_applied else "seen before"  # type: ignore[union-attr]
            transport.send_event(
                "turn.delta",
                {"text": f"  ⚡ already in DB (id={existing.id}, {tag})\n"}
            )
        else:
            transport.send_event(
                "turn.delta", {"text": "  · new listing (not in DB)\n"}
            )
    finally:
        session.close()

    # ── Phase 2: Load resume ──────────────────────────────────────────
    parsed_resume, resume_text = _get_resume(transport)

    if not parsed_resume and not resume_text:
        # No resume at all — return extraction only
        transport.send_event(
            "turn.end",
            {"text": f"extracted: {job_summary} (no resume to score against)"},
        )
        return {"status": "ok", "summary": f"extracted: {job_summary}"}

    # ── Phase 3: Score match ──────────────────────────────────────────
    if _pipeline_cancel.is_set():
        return {"status": "cancelled"}

    transport.send_event("pipeline.progress", {"step": "matcher"})

    name = (parsed_resume or {}).get("name", "resume")
    transport.send_event(
        "turn.delta",
        {"text": f"▸ scoring match ({name} vs {parsed_job.position_title}) with {model_id}…\n"}
    )

    match_state: dict[str, Any] = {
        "jd_text": jd_text,
        "parsed_job": parsed_job,
        "parsed_resume": parsed_resume,
        "resume_text": resume_text,
    }
    match_result = match_graph.invoke(match_state)  # type: ignore[arg-type]

    if _pipeline_cancel.is_set():
        return {"status": "cancelled"}

    match_data = match_result.get("match_result")
    match_error = match_result.get("error")

    if match_error:
        transport.send_event(
            "turn.delta", {"text": f"  ✗ scoring error: {match_error}\n"}
        )

    # ── Phase 4: Format and stream results ────────────────────────────
    if match_data and isinstance(match_data, dict):
        overall = match_data.get("overall_score", 0)
        skills = match_data.get("skills_score", 0)
        exp = match_data.get("experience_score", 0)
        summary = match_data.get("summary", "")

        score_str = (
            f"overall: {overall:.0%} | "
            f"skills: {skills:.0%} | "
            f"experience: {exp:.0%}"
        )

        transport.send_event("turn.delta", {"text": f"\n📊 {score_str}\n"})

        if summary:
            transport.send_event("turn.delta", {"text": f"\n{summary}\n"})

        # Strengths & gaps
        strengths = match_data.get("strengths", [])
        gaps = match_data.get("gaps", [])
        actions = match_data.get("action_items", [])

        if strengths:
            transport.send_event("turn.delta", {"text": "\n✅ Strengths:\n"})
            for s in strengths[:5]:
                transport.send_event("turn.delta", {"text": f"  • {s}\n"})

        if gaps:
            transport.send_event("turn.delta", {"text": "\n⚠ Gaps:\n"})
            for g in gaps[:5]:
                transport.send_event("turn.delta", {"text": f"  • {g}\n"})

        if actions:
            transport.send_event("turn.delta", {"text": "\n🔧 Action items:\n"})
            for a in actions[:5]:
                transport.send_event("turn.delta", {"text": f"  • {a}\n"})

        # Keyword match summary
        kw = match_data.get("keyword_match", {})
        matched = kw.get("matched", [])
        missing = kw.get("missing", [])
        if matched:
            transport.send_event(
                "turn.delta",
                {"text": f"\n🔑 Matched keywords ({len(matched)}): {', '.join(matched[:10])}\n"},
            )
        if missing:
            transport.send_event(
                "turn.delta",
                {"text": f"❌ Missing keywords ({len(missing)}): {', '.join(missing[:10])}\n"},
            )

        transport.send_event(
            "pipeline.progress", {"step": "completed"}
        )

        # ── Cost table ────────────────────────────────────────────────
        _delta_in    = _llm.usage.total_input_tokens    - _before_in
        _delta_out   = _llm.usage.total_output_tokens   - _before_out
        _delta_think = _llm.usage.total_thinking_tokens - _before_think
        if _delta_in > 0 or _delta_out > 0:
            _p = get_pricing(_llm.model_id)
            _cost_usd = (
                _delta_in    * _p["input"]   / 1_000_000
                + _delta_out   * _p["output"]  / 1_000_000
                + _delta_think * _p["thinking"] / 1_000_000
            )
            _table = _format_cost_table(
                _llm.model_id, _delta_in, _delta_out, _delta_think, _cost_usd
            )
            transport.send_event("turn.delta", {"text": f"\n{_table}\n"})

        transport.send_event("turn.end", {})  # let endTurn use accumulated streaming
        return {"status": "ok", "match": match_data}

    # No match data path — still emit cost table
    _delta_in    = _llm.usage.total_input_tokens    - _before_in
    _delta_out   = _llm.usage.total_output_tokens   - _before_out
    _delta_think = _llm.usage.total_thinking_tokens - _before_think
    if _delta_in > 0 or _delta_out > 0:
        _p = get_pricing(_llm.model_id)
        _cost_usd = (
            _delta_in    * _p["input"]   / 1_000_000
            + _delta_out   * _p["output"]  / 1_000_000
            + _delta_think * _p["thinking"] / 1_000_000
        )
        _table = _format_cost_table(
            _llm.model_id, _delta_in, _delta_out, _delta_think, _cost_usd
        )
        transport.send_event("turn.delta", {"text": f"\n{_table}\n"})

    transport.send_event("pipeline.progress", {"step": "completed"})
    transport.send_event("turn.end", {})  # let endTurn use accumulated streaming
    return {"status": "ok", "summary": job_summary}
