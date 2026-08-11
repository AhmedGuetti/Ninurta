"""JSON-RPC method handlers for the Ninurta TUI gateway.

Each handler receives ``(params, transport)`` — the parsed request params and
the transport (used to push async SSE-style events such as ``turn.delta`` and
``pipeline.progress`` back to the Node frontend).
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from ninurta.config import load_config
from ninurta.db.session import SessionLocal, init_db
from ninurta.db.models import Job, Resume
from ninurta.graph import extract_graph, match_graph

# Ensure prompts are registered before the gateway tries to use them.
import ninurta.prompts.job_extractor  # noqa: F401 — registers @prompt("job_extractor")
import ninurta.prompts.matcher       # noqa: F401 — registers @prompt("matcher")

logger = logging.getLogger(__name__)

# EUR/USD rate (fixed reference)
_USD_TO_EUR = 0.926


def _format_cost_table(
    model_id: str,
    input_tok: int,
    output_tok: int,
    thinking_tok: int,
    cost_usd: float,
) -> str:
    """Build a unicode box-drawing cost table as a plain string."""
    cost_eur = cost_usd * _USD_TO_EUR
    rows = [
        ("Model",          model_id),
        ("Input tokens",   f"{input_tok:,}"),
        ("Output tokens",  f"{output_tok:,}"),
    ]
    if thinking_tok:
        rows.append(("Thinking tokens", f"{thinking_tok:,}"))
    rows += [
        ("Cost (USD)",     f"${cost_usd:.5f}"),
        ("Cost (EUR)",     f"\u20ac{cost_eur:.5f}"),
    ]
    col1_w = max(len(r[0]) for r in rows) + 2
    col2_w = max(len(r[1]) for r in rows) + 2
    total_w = col1_w + col2_w + 3
    title = " Run Cost Summary "
    top_pad = max(0, total_w - 2 - len(title))
    lines = ["\u250c" + title + "\u2500" * top_pad + "\u2510"]
    lines.append("\u251c" + "\u2500" * col1_w + "\u252c" + "\u2500" * col2_w + "\u2524")
    for label, value in rows:
        l = f" {label} ".ljust(col1_w)
        v = f" {value} ".ljust(col2_w)
        lines.append(f"\u2502{l}\u2502{v}\u2502")
    lines.append("\u2514" + "\u2500" * col1_w + "\u2534" + "\u2500" * col2_w + "\u2518")
    return "\n".join(lines)

# Disk resume paths (fallback when DB is empty)
_RESUME_DIR = Path(__file__).resolve().parent.parent.parent / "resume"
_RESUME_FILES = [
    _RESUME_DIR / "resume_en.docx",
    _RESUME_DIR / "resume_fr.docx",
]


def _mask_key(value: Any) -> Any:
    """Mask API keys so they never leak over the RPC wire."""
    if isinstance(value, str) and value:
        return f"{value[:4]}…{value[-4:]}"
    return value


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


# ---------------------------------------------------------------------------
# Handler: db.inspect — inspect database tables
# ---------------------------------------------------------------------------

def _db_summary(session) -> str:
    """Return a compact summary of all tables."""
    resumes = session.query(Resume).all()
    jobs = session.query(Job).all()
    lines = [
        f"resumes: {len(resumes)}",
        f"jobs: {len(jobs)}",
    ]
    if resumes:
        lines.append("─ resumes ─")
        for r in resumes[:5]:
            lines.append(f"  [{r.id}] {r.name}")
    if jobs:
        lines.append("─ jobs ─")
        for j in jobs[:5]:
            lines.append(
                f"  [{j.id}] {j.position_title} @ {j.company_name}"
                f"{' ✓applied' if j.already_applied else ''}"
            )
    return "\n".join(lines)


def _db_row(session, table: str, row_id: int) -> str:
    """Return a detailed view of a single row."""
    if table in ("resumes", "resume"):
        row = session.query(Resume).filter(Resume.id == row_id).first()
        if not row:
            return f"resume id={row_id} not found"
        created = row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else "?"
        lines = [
            f"Resume #{row.id}: {row.name}",
            f"created: {created}",
            "",
        ]
        if row.parsed_json:
            try:
                parsed = json.loads(row.parsed_json)
                body: list[str] = []

                # ── Contact ──────────────────────────────────────────
                contact = parsed.get("contact", {})
                n_before = len(body)
                for fld in ("email", "phone", "linkedin"):
                    v = contact.get(fld, "")
                    if v:
                        body.append(f"  {fld:22s} {v}")
                if len(body) > n_before:
                    body.insert(n_before, "  ── Contact " + "─" * 30)

                sections = parsed.get("sections", {})

                # ── Profile / Summary ────────────────────────────────
                for label in ("profile", "summary", "objective"):
                    if label in sections:
                        n_before = len(body)
                        txt = sections[label]
                        if isinstance(txt, str) and txt.strip():
                            preview = txt[:200].replace("\n", " ")
                            body.append(f"  {preview}")
                            if len(txt) > 200:
                                body.append(f"  … ({len(txt)} chars total)")
                        if len(body) > n_before:
                            body.insert(n_before, f"  ── {label.title()} " + "─" * 30)
                        break

                # ── Skills ───────────────────────────────────────────
                if "skills" in sections:
                    n_before = len(body)
                    sk = sections["skills"]
                    if isinstance(sk, dict):
                        for cat, items in sk.items():
                            if isinstance(items, list) and items:
                                body.append(f"  {cat:22s} {', '.join(items)}")
                    elif isinstance(sk, list):
                        if sk:
                            body.append(f"  {'skills':22s} {', '.join(str(s) for s in sk)}")
                    elif isinstance(sk, str) and sk.strip():
                        body.append(f"  {sk}")
                    if len(body) > n_before:
                        body.insert(n_before, "  ── Skills " + "─" * 30)

                # ── Experience ───────────────────────────────────────
                exp = sections.get("experience")
                if isinstance(exp, list) and exp:
                    n_before = len(body)
                    for i, e in enumerate(exp, 1):
                        title_parts = []
                        if e.get("position"):
                            title_parts.append(e["position"])
                        if e.get("company"):
                            title_parts.append(f"@ {e['company']}")
                        if e.get("period"):
                            title_parts.append(f"({e['period']})")
                        body.append(f"  [{i}] {' '.join(title_parts)}")
                        if e.get("location"):
                            body.append(f"      {e['location']}")
                        mission = e.get("mission", "")
                        if mission:
                            body.append(f"      {mission[:200]}")
                        for a in e.get("achievements", [])[:4]:
                            body.append(f"      • {a}")
                    if len(body) > n_before:
                        body.insert(n_before, f"  ── Experience ({len(exp)} entries) " + "─" * 30)

                # ── Education ────────────────────────────────────────
                edu = sections.get("education")
                if isinstance(edu, list) and edu:
                    n_before = len(body)
                    for i, e in enumerate(edu, 1):
                        parts = []
                        if e.get("degree"):
                            parts.append(e["degree"])
                        if e.get("institution"):
                            parts.append(f"@ {e['institution']}")
                        if e.get("period"):
                            parts.append(f"({e['period']})")
                        body.append(f"  [{i}] {' '.join(parts)}")
                        if e.get("location"):
                            body.append(f"      {e['location']}")
                        if e.get("details"):
                            body.append(f"      {e['details'][:200]}")
                    if len(body) > n_before:
                        body.insert(n_before, f"  ── Education ({len(edu)} entries) " + "─" * 30)

                # ── Projects ─────────────────────────────────────────
                proj = sections.get("projects")
                if isinstance(proj, list) and proj:
                    n_before = len(body)
                    for i, p in enumerate(proj, 1):
                        name = p.get("name", "")
                        desc = p.get("description", "")
                        link = p.get("link", "")
                        body.append(f"  [{i}] {name}")
                        if desc:
                            body.append(f"      {desc[:200]}")
                        if link:
                            body.append(f"      {link}")
                    if len(body) > n_before:
                        body.insert(n_before, f"  ── Projects ({len(proj)} entries) " + "─" * 30)

                # ── Achievements / Awards ────────────────────────────
                ach = sections.get("achievements")
                if isinstance(ach, list) and ach:
                    n_before = len(body)
                    for a in ach[:8]:
                        body.append(f"  • {a}")
                    if len(body) > n_before:
                        body.insert(n_before, f"  ── Achievements ({len(ach)} items) " + "─" * 30)

                # ── Other sections (catch-all: str or list) ──────────
                for sect_name, sect_data in sections.items():
                    if sect_name in ("profile", "summary", "objective",
                                     "skills", "experience", "education",
                                     "projects", "achievements"):
                        continue  # already handled above
                    n_before = len(body)
                    if isinstance(sect_data, str) and sect_data.strip():
                        body.append(f"  {sect_data[:300]}")
                    elif isinstance(sect_data, list) and sect_data:
                        for item in sect_data[:5]:
                            body.append(f"  • {item}")
                    elif isinstance(sect_data, dict):
                        for k, v in sect_data.items():
                            if isinstance(v, list):
                                body.append(f"  {k}: {', '.join(str(x) for x in v[:10])}")
                            else:
                                body.append(f"  {k}: {v}")
                    if len(body) > n_before:
                        body.insert(n_before, f"  ── {sect_name.title()} " + "─" * 30)

                lines.extend(body)

            except json.JSONDecodeError:
                lines.append("  (parsed_json is malformed)")
        lines.append("")
        lines.append(f"raw text: {len(row.content or '')} chars")
        return "\n".join(lines)

    if table in ("jobs", "job"):
        row = session.query(Job).filter(Job.id == row_id).first()
        if not row:
            return f"job id={row_id} not found"
        applied = "✓ yes" if row.already_applied else "no"
        created = row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else "?"
        lines = [
            f"Job #{row.id}: {row.position_title} @ {row.company_name}",
            f"applied: {applied} · created: {created}",
            "",
        ]
        if row.extracted_json:
            try:
                jd = json.loads(row.extracted_json)

                # Build sections lazily — only show headers when content exists.
                body: list[str] = []

                def _add_kv(label, key=None):
                    if key is None:
                        key = label
                    v = jd.get(key)
                    if v is not None and v != "" and v != []:
                        body.append(f"  {label:22s} {v}")
                        return True
                    return False

                def _add_list(key, label=None):
                    v = jd.get(key)
                    if isinstance(v, list) and v:
                        body.append(f"  {label or key:22s} {', '.join(v)}")
                        return True
                    return False

                def _section(title):
                    body.append(f"  ── {title} " + "─" * 30)

                # ── Role ──────────────────────────────────────────────
                n_before = len(body)
                _add_kv("position_title")
                _add_kv("employment_type")
                _add_kv("work_mode")
                _add_kv("experience_level")
                _add_kv("years_required")
                _add_kv("department")
                if len(body) > n_before:
                    body.insert(n_before, f"  ── Role " + "─" * 30)

                # ── Company ───────────────────────────────────────────
                n_before = len(body)
                _add_kv("company_name")
                _add_kv("company_description")
                _add_kv("industry")
                loc_parts = [p for p in [jd.get("city"), jd.get("region"), jd.get("country")] if p]
                if loc_parts:
                    body.append(f"  {'location':22s} {', '.join(loc_parts)}")
                if len(body) > n_before:
                    body.insert(n_before, f"  ── Company " + "─" * 30)

                # ── Compensation ─────────────────────────────────────
                n_before = len(body)
                sal_min = jd.get("salary_min")
                sal_max = jd.get("salary_max")
                sal_cur = jd.get("salary_currency", "")
                sal_per = jd.get("salary_period", "")
                if sal_min or sal_max:
                    rng = f"{sal_min or '?'} – {sal_max or '?'} {sal_cur} / {sal_per or 'yr'}"
                    body.append(f"  {'salary':22s} {rng}")
                _add_list("benefits")
                if len(body) > n_before:
                    body.insert(n_before, f"  ── Compensation " + "─" * 30)

                # ── Skills ───────────────────────────────────────────
                n_before = len(body)
                _add_list("skills_required", "required")
                _add_list("nice_to_have_skills", "nice to have")
                _add_list("languages_required", "languages")
                _add_list("certifications")
                if len(body) > n_before:
                    body.insert(n_before, f"  ── Skills " + "─" * 30)

                # ── Responsibilities ─────────────────────────────────
                n_before = len(body)
                resp = jd.get("responsibilities", [])
                if resp:
                    for r in resp[:8]:
                        body.append(f"  • {r}")
                if len(body) > n_before:
                    body.insert(n_before, f"  ── Responsibilities " + "─" * 30)

                # ── Application ──────────────────────────────────────
                n_before = len(body)
                _add_kv("contact")
                _add_kv("application_method")
                visa = jd.get("visa_sponsorship")
                if visa is not None:
                    body.append(f"  {'visa sponsorship':22s} {'yes' if visa else 'no'}")
                _add_kv("posted_date")
                _add_kv("application_deadline")
                _add_kv("source_url")
                if len(body) > n_before:
                    body.insert(n_before, f"  ── Application " + "─" * 30)

                lines.extend(body)

            except json.JSONDecodeError:
                lines.append("  (extracted_json is malformed)")
        lines.append("")
        lines.append(f"raw JD: {len(row.raw_job_description or '')} chars")
        return "\n".join(lines)

    return f"unknown table '{table}' — try 'resumes' or 'jobs'"


def handle_db_inspect(params: dict, transport) -> dict:
    """Inspect database: summary, list table, or view a specific row.

    Params:
        table: 'resumes' | 'jobs' (optional, omit for summary)
        id:    row ID (optional, requires table)
    """
    init_db()
    session = SessionLocal()
    try:
        table = (params.get("table") or "").strip().lower()
        row_id = params.get("id")

        if not table:
            text = _db_summary(session)
        elif row_id is not None:
            text = _db_row(session, table, int(row_id))
        else:
            # List all rows of a table
            if table in ("resumes", "resume"):
                rows = session.query(Resume).order_by(Resume.id).all()
                if not rows:
                    text = "no resumes in db"
                else:
                    text = "\n".join(f"[{r.id}] {r.name}" for r in rows)
            elif table in ("jobs", "job"):
                rows = session.query(Job).order_by(Job.id.desc()).all()
                if not rows:
                    text = "no jobs in db"
                else:
                    text = "\n".join(
                        f"[{j.id}] {j.position_title} @ {j.company_name}"
                        f"{' ✓' if j.already_applied else ''}"
                        for j in rows
                    )
            else:
                text = f"unknown table '{table}' — try 'resumes' or 'jobs'"
    finally:
        session.close()

    # Return text only — caller (useMainApp) handles display; no turn.end push
    # to avoid the double-append bug.
    return {"text": text}


# ---------------------------------------------------------------------------
# Config handlers
# ---------------------------------------------------------------------------

def handle_config_get(params: dict, transport) -> dict:
    """Inspect configuration — API keys masked."""
    cfg = load_config()
    safe: dict[str, Any] = {}
    llm = cfg.get("llm", {})
    if isinstance(llm, dict):
        safe["llm"] = {
            k: (_mask_key(v) if "key" in k.lower() else v)
            for k, v in llm.items()
        }
    return {"config": safe}


def handle_config_set(params: dict, transport) -> dict:
    """Update non-secret config keys (keys are never settable over RPC)."""
    patch = params.get("config") or {}
    cfg = load_config()
    llm = cfg.setdefault("llm", {})
    if isinstance(patch, dict) and isinstance(llm, dict):
        for k, v in patch.items():
            if "key" in k.lower():
                continue  # never allow API keys over the wire
            llm[k] = v
    from ninurta.config import save_config

    save_config(cfg)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Handler: model.get / model.set — switch LLM model at runtime
# ---------------------------------------------------------------------------

def handle_model_get(params: dict, transport) -> dict:
    """Return the current model ID and provider."""
    cfg = load_config()
    llm = cfg.get("llm", {})
    provider = llm.get("provider", "gemini")
    model = llm.get("model", "gemini-3.6-flash")
    return {"provider": provider, "model": model, "full": f"{provider}:{model}"}


def handle_model_set(params: dict, transport) -> dict:
    """Change the default LLM model and clear the LLM cache.

    Accepts a ``model_id`` in ``provider:model`` format (e.g. ``gemini:gemini-3.6-flash``).
    If no provider prefix is given, keeps the current provider and only updates the model name.
    """
    model_id = (params.get("model_id") or "").strip()
    if not model_id:
        raise ValueError("model_id is required (e.g. 'gemini:gemini-3.6-flash')")

    cfg = load_config()
    llm = cfg.setdefault("llm", {})

    provider, sep, model = model_id.partition(":")
    if sep:
        llm["provider"] = provider
        llm["model"] = model
    else:
        # No provider prefix → only change the model, keep current provider
        llm["model"] = model_id

    from ninurta.config import save_config
    from ninurta.llm.factory import clear_llm_cache

    save_config(cfg)
    clear_llm_cache()

    new_id = f"{llm.get('provider', 'gemini')}:{llm.get('model', '?')}"
    logger.info("model switched to %s", new_id)
    return {"status": "ok", "model": new_id}


# ---------------------------------------------------------------------------
# Dispatch map
# ---------------------------------------------------------------------------

def get_dispatch_map() -> dict:
    """Route RPC method names to handlers."""
    return {
        "session.send": handle_session_send,
        "pipeline.cancel": handle_pipeline_cancel,
        "db.inspect": handle_db_inspect,
        "model.get": handle_model_get,
        "model.set": handle_model_set,
        "config.get": handle_config_get,
        "config.set": handle_config_set,
    }
