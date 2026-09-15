"""Shared resume loading: DB first, disk fallback.

Used by both the TUI gateway (``session.py``) and the CLI ``pipeline``
command so the two entry points never drift.  DB records win; when the
resumes table is empty the first ``resume/*.docx`` on disk is parsed
heuristic-style (no LLM) via :func:`parse_resume`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ninurta.db.models import Resume
from ninurta.db.session import SessionLocal, init_db

logger = logging.getLogger(__name__)

# Disk resume paths (fallback when DB is empty).
# resume_loader.py lives at ninurta/interface/ → 3 parents = project root.
RESUME_DIR = Path(__file__).resolve().parent.parent.parent / "resume"
RESUME_FILES = [
    RESUME_DIR / "resume_en.docx",
    RESUME_DIR / "resume_fr.docx",
]


def load_resume_from_db() -> tuple[dict | None, str | None]:
    """Return the most recent resume record: (parsed_json, raw_content)."""
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


def load_resume_from_disk() -> tuple[dict | None, str | None]:
    """Parse the first available resume file from disk (no LLM)."""
    from ninurta.interface.documents import extract_text  # noqa: PLC0415
    from ninurta.nodes.resume_reader import parse_resume  # noqa: PLC0415

    for path in RESUME_FILES:
        if path.exists():
            try:
                text = extract_text(path)
                if not text.strip():
                    continue
                parsed = parse_resume(text)
                logger.info("loaded resume from disk: %s", path.name)
                return parsed, text
            except Exception as exc:  # noqa: BLE001 — best-effort per file
                logger.warning("failed to read %s: %s", path.name, exc)
                continue
    return None, None
