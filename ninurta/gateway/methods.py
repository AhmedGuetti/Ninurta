"""JSON-RPC method handlers for the Ninurta TUI gateway.

Each handler receives ``(params, transport)`` — the parsed request params and
the transport (used to push async SSE-style events such as ``turn.delta`` and
``pipeline.progress`` back to the Node frontend).
"""

from __future__ import annotations

import logging
from typing import Any

from ninurta.config import load_config
from ninurta.db.session import SessionLocal, init_db
from ninurta.db.models import Job, Resume
from ninurta.graph import extract_graph

logger = logging.getLogger(__name__)


def _mask_key(value: Any) -> Any:
    """Mask API keys so they never leak over the RPC wire."""
    if isinstance(value, str) and value:
        return f"{value[:4]}…{value[-4:]}"
    return value


def handle_session_send(params: dict, transport) -> dict:
    """Invoke the extract graph on raw text, streaming node progress."""
    message = (params.get("message") or "").strip()
    if not message:
        raise ValueError("message is required")

    transport.send_event("pipeline.progress", {"step": "started", "message": message[:80]})
    transport.send_event("turn.delta", {"text": f"you said: {message}\n"})
    transport.send_event("turn.delta", {"text": "running extract graph…\n"})

    # Run the LangGraph extraction pipeline on the message as raw JD text.
    transport.send_event("pipeline.progress", {"step": "extractor"})
    state: dict[str, Any] = {"jd_text": message}
    result = extract_graph.invoke(state)  # type: ignore[arg-type]
    parsed = result.get("parsed_job")
    error = result.get("error")

    if error:
        transport.send_event("turn.delta", {"text": f"extraction error: {error}\n"})
        transport.send_event("turn.end", {"text": "", "error": error})
        return {"status": "error", "error": error}

    summary = (
        f"extracted: {parsed.position_title} @ {parsed.company_name}"
        if parsed
        else "extracted: (no parseable job)"
    )
    transport.send_event("turn.delta", {"text": summary + "\n"})
    transport.send_event("pipeline.progress", {"step": "completed"})
    transport.send_event("turn.end", {"text": summary})
    return {"status": "ok", "summary": summary}


def handle_job_extract(params: dict, transport) -> dict:
    """Trigger job-description extraction for a URL (placeholder for fetch step)."""
    url = (params.get("url") or "").strip()
    if not url:
        raise ValueError("url is required")

    transport.send_event("pipeline.progress", {"step": "extracting_job", "url": url})
    transport.send_event("turn.delta", {"text": f"fetching job description from {url}\n"})
    # TODO: fetch page text from URL, then run extract_graph with it.
    transport.send_event("turn.end", {"text": f"job extract queued for {url}"})
    return {"status": "queued", "url": url}


def handle_resume_stats(params: dict, transport) -> dict:
    """Inspect parsed resume stats from SQLite."""
    init_db()
    session = SessionLocal()
    try:
        resumes = session.query(Resume).all()
        jobs = session.query(Job).all()
        lines = [
            f"resumes in db: {len(resumes)}",
            f"jobs in db: {len(jobs)}",
        ]
        for r in resumes[:5]:
            lines.append(f"  • {r.name} (id={r.id})")
        summary = "\n".join(lines)
    finally:
        session.close()

    transport.send_event("turn.end", {"text": summary})
    return {"status": "ok", "summary": summary}


def handle_search_run(params: dict, transport) -> dict:
    """Run the matching/scoring graph (stub — graph not yet wired)."""
    query = (params.get("query") or "").strip()
    transport.send_event("pipeline.progress", {"step": "search"})
    transport.send_event("turn.end", {"text": f"search for {query!r}: graph not implemented yet"})
    return {"status": "stub", "query": query}


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


def get_dispatch_map() -> dict:
    """Route RPC method names to handlers."""
    return {
        "session.send": handle_session_send,
        "job.extract": handle_job_extract,
        "resume.stats": handle_resume_stats,
        "search.run": handle_search_run,
        "config.get": handle_config_get,
        "config.set": handle_config_set,
    }
