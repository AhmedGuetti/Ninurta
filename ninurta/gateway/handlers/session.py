"""Session JSON-RPC handlers."""

import logging
import threading
import time
from typing import Any

from ninurta.config import load_config
from ninurta.interface.resume_loader import load_resume_from_db, load_resume_from_disk
from ninurta.graph import extract_graph, match_graph
from ninurta.gateway.utils import _format_cost_table

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Resume loading (DB → disk fallback — shared with the CLI via resume_loader)
# ---------------------------------------------------------------------------

def _get_resume(transport) -> tuple[dict | None, str | None]:
    """Load resume data: DB first, then disk fallback."""
    transport.send_event("pipeline.progress", {"step": "loading_resume"})
    transport.send_event("turn.delta", {"text": "▸ looking up resume…\n"})

    parsed, raw = load_resume_from_db()
    if parsed or raw:
        name = (parsed or {}).get("name", "unknown")
        sections_n = len((parsed or {}).get("sections", {}))
        transport.send_event(
            "turn.delta",
            {"text": f"  ✓ using resume from DB: {name} ({sections_n} sections) — /db resume 1 to inspect\n"}
        )
        # Also check if a disk copy exists and is newer
        from ninurta.interface.resume_loader import RESUME_FILES
        disk_text = None
        for path in RESUME_FILES:
            if path.exists():
                try:
                    from ninurta.interface.documents import extract_text
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
    parsed, raw = load_resume_from_disk()
    if parsed or raw:
        name = (parsed or {}).get("name", "unknown")
        sections_n = len((parsed or {}).get("sections", {}))
        # Persist the disk parse so match reports can link a real resume row.
        if parsed is not None:
            try:
                from ninurta.db.operations import save_resume

                save_resume(parsed, raw or "")
            except Exception as exc:  # noqa: BLE001 — persistence must not block scoring
                logger.warning("could not persist resume from disk: %s", exc)
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
        {"step": "extractor", "message": "extracting job description…"},
    )
    transport.send_event(
        "turn.delta",
        {"text": f"▸ extracting job description ({len(jd_text)} chars) with {model_id}…\n"},
    )

    state: dict[str, Any] = {"jd_text": jd_text}
    # Register the LLM-status sink so the TUI's status line shows live
    # "reasoning…" messages while the extractor calls the model.
    from ninurta.nodes._llm_helpers import set_llm_status_sink

    set_llm_status_sink(
        lambda msg: transport.send_event("pipeline.progress", {"step": "llm", "message": msg})
    )
    try:
        result = {}
        for event in extract_graph.stream(state):
            for node_name, state_update in event.items():
                if node_name == "extractor":
                    transport.send_event("turn.delta", {"text": "  ⚡ extracted constraints... checking DB for duplicates...\n"})
                elif node_name == "job_dedup":
                    transport.send_event("turn.delta", {"text": "  ✓ extraction complete.\n"})
                
                # Check for dedup embedded within updates
                dedup = state_update.get("dedup_result")
                if dedup:
                    verdict = dedup.get("verdict")
                    if verdict == "duplicate":
                        transport.send_event("turn.delta", {"text": "  [✓] found similar (duplicate)\n"})
                    elif verdict == "similar":
                        transport.send_event("turn.delta", {"text": "  [⚠] found similar\n"})
                    else:
                        transport.send_event("turn.delta", {"text": "  [✓] new listing\n"})

                result.update(state_update)
    finally:
        set_llm_status_sink(None)

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

    # ── JD dedup: heuristic similarity against stored jobs ──────────────
    # The extract graph now runs job_dedup_node after the extractor; its
    # verdict (duplicate/similar/new + top matches) lands in dedup_result.
    dedup = result.get("dedup_result") or {}
    verdict = dedup.get("verdict", "new")
    matches = dedup.get("matches") or []

    if verdict == "duplicate" and matches:
        m = matches[0]
        tag = "✓applied" if m.get("already_applied") else "seen before"
        transport.send_event(
            "turn.delta",
            {"text": f"  ⚡ already in DB (id={m['id']}, {m['score']:.0%} match, {tag})\n"},
        )
        if len(matches) > 1:
            others = ", ".join(f"id={x['id']} ({x['score']:.0%})" for x in matches[1:])
            transport.send_event("turn.delta", {"text": f"    └ similar too: {others}\n"})
    elif verdict == "similar" and matches:
        m = matches[0]
        transport.send_event(
            "turn.delta",
            {"text": f"  ⚠ similar listing (id={m['id']}, {m['score']:.0%} match) — check before applying\n"},
        )
    else:
        transport.send_event("turn.delta", {"text": "  · new listing (not in DB)\n"})

    # ── Persist the JP in the DB ─────────────────────────────────────────
    # Re-extraction of a known listing does NOT mark it applied — that flag
    # is reserved for actual applications (mark_applied=False).
    from ninurta.db.operations import save_job

    job_save = save_job(parsed_job, jd_text, mark_applied=False)
    if job_save["status"] == "created":
        transport.send_event(
            "turn.delta",
            {"text": f"  💾 job saved to DB (id={job_save['job_id']})\n"},
        )
    # status 'exists' — already persisted, nothing to do.

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

    transport.send_event("pipeline.progress", {"step": "matcher", "message": "scoring resume vs JD…"})

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
    set_llm_status_sink(
        lambda msg: transport.send_event("pipeline.progress", {"step": "llm", "message": msg})
    )
    try:
        match_result = {}
        transport.send_event("turn.delta", {"text": "\n  🧠 starting analysis of score...\n"})
        for event in match_graph.stream(match_state):
            for node_name, state_update in event.items():
                if node_name == "matcher":
                    transport.send_event("turn.delta", {"text": "  ✓ analysis complete\n"})
                match_result.update(state_update)
    finally:
        set_llm_status_sink(None)

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
        edu = match_data.get("education_score", 0)
        resp = match_data.get("responsibilities_score", 0)
        
        overall_pct = int(overall * 100)

        # NOTE: no ANSI SGR codes here. The TUI renders this via Ink's <Text>,
        # which does NOT interpret raw escape sequences — they corrupt the
        # string-width math and make lines overlap/mangle (compounding every
        # turn). Emoji + markdown markers carry the hierarchy instead.
        md_lines = [
            f"## 🎯 Match Analysis: {overall_pct}%",
            "",
            "### 📊 Breakdown",
            f"- Skills: {int(skills * 100)}%",
            f"- Experience: {int(exp * 100)}%"
        ]

        if edu is not None:
            md_lines.append(f"- Education: {int(edu * 100)}%")
        if resp is not None:
            md_lines.append(f"- Responsibilities: {int(resp * 100)}%")

        summary = match_data.get("summary")
        if summary:
            md_lines.extend(["", "### 📋 Summary", summary])

        strengths = match_data.get("strengths") or []
        if strengths:
            md_lines.extend(["", "### ✅ Strengths"])
            for s in strengths[:5]:
                md_lines.append(f"- {s}")

        gaps = match_data.get("gaps") or []
        if gaps:
            md_lines.extend(["", "### ⚠ Gaps"])
            for g in gaps[:5]:
                md_lines.append(f"- {g}")

        action_items = match_data.get("action_items") or []
        if action_items:
            md_lines.extend(["", "### 🔧 Action Items"])
            for a in action_items[:5]:
                md_lines.append(f"- {a}")

        # Stream the report ONE LINE at a time (with a tiny inter-line delay).
        # Sending the whole multi-line report as a single turn.delta makes the
        # frontend append ~30 lines in one React update, which the inline diff
        # renderer can't lay out correctly — rows end up overlapping/mangled.
        # Small deltas let each line render incrementally (same as the progress
        # messages above, which arrive one-by-one).
        transport.send_event("turn.delta", {"text": "\n"})
        for line in md_lines:
            transport.send_event("turn.delta", {"text": f"{line}\n"})
            time.sleep(0.005)

        # ── Persist the structured report (job × resume × score) ────────
        from ninurta.db.operations import save_match_report

        try:
            report_save = save_match_report(job_save["job_id"], match_data)
            transport.send_event(
                "turn.delta",
                {"text": f"\n💾 report saved (id={report_save['report_id']}) — /db report {report_save['report_id']}\n"},
            )
        except Exception as exc:  # noqa: BLE001 — persistence must not kill the turn
            logger.warning("failed to save match report: %s", exc)

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
