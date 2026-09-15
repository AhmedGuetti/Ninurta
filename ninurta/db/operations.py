"""Database operations/CRUD helpers for Ninurta."""

from __future__ import annotations

import json
from typing import Any
from ninurta.db.session import SessionLocal, init_db
from ninurta.db.models import Job, MatchReport, Resume
from ninurta.schemas.job_description import JobDescription


def save_resume(parsed: dict, raw_text: str) -> dict[str, Any]:
    """Upsert a parsed resume dict into the resumes table (keyed by name).

    The parsed dict is stored as JSON in ``Resume.parsed_json`` — the schema is
    deliberately flexible (sections may be str, list, or dict), so whatever the
    LLM decided (e.g. categorized skills) round-trips losslessly.

    Returns:
        dict: {"status": "created" | "updated", "resume_id": int}
    """
    init_db()

    session = SessionLocal()
    try:
        name = (parsed.get("name") or "Unknown Name").strip()
        parsed_json = json.dumps(parsed, ensure_ascii=False)

        existing = (
            session.query(Resume)
            .filter(Resume.name.collate("NOCASE") == name)
            .first()
        )

        if existing:
            existing.content = raw_text  # type: ignore[assignment]
            existing.parsed_json = parsed_json  # type: ignore[assignment]
            session.commit()
            return {"status": "updated", "resume_id": int(existing.id)}  # type: ignore[arg-type]

        db_resume = Resume(
            name=name,
            content=raw_text,
            parsed_json=parsed_json,
        )
        session.add(db_resume)
        session.commit()
        return {"status": "created", "resume_id": int(db_resume.id)}  # type: ignore[arg-type]
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def save_job(job_desc: JobDescription, raw_jd: str, mark_applied: bool = True) -> dict[str, Any]:
    """Save an extracted job and its raw job description to the SQLite database.

    Checks for existing job listings matching the same company and position title.
    If a match is found, it updates the existing listing's already_applied flag to True.
    Otherwise, a new job listing is added.

    Args:
        job_desc: The extracted job description.
        raw_jd:   The raw job description text.
        mark_applied: When True (default), an existing listing is flagged as
            already_applied.  Pass False when the pipeline merely re-scored a
            known listing (e.g. report generation) — re-extraction is not an
            application.

    Returns:
        dict: A dictionary indicating the result ('status': 'created' or
        'already_applied').
    """
    # Ensure tables are initialized
    init_db()
    
    session = SessionLocal()
    try:
        company = (job_desc.company_name or "Unknown Company").strip()
        position = (job_desc.position_title or "Unknown Position").strip()

        # Check for existing listing (case-insensitive)
        existing_job = (
            session.query(Job)
            .filter(
                Job.company_name.collate("NOCASE") == company,
                Job.position_title.collate("NOCASE") == position,
            )
            .first()
        )

        if existing_job:
            if mark_applied:
                existing_job.already_applied = True  # type: ignore[assignment]
                session.commit()
                return {"status": "already_applied", "job_id": int(existing_job.id)}  # type: ignore[arg-type]
            return {"status": "exists", "job_id": int(existing_job.id)}  # type: ignore[arg-type]

        # Otherwise, add a new listing
        extracted_dict = job_desc.model_dump() if hasattr(job_desc, "model_dump") else job_desc.__dict__
        extracted_json_str = json.dumps(extracted_dict)
        
        db_job = Job(
            company_name=company,
            position_title=position,
            raw_job_description=raw_jd,
            extracted_json=extracted_json_str,
            already_applied=False,
        )
        
        session.add(db_job)
        session.commit()
        return {"status": "created", "job_id": int(db_job.id)}  # type: ignore[arg-type]
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_latest_resume_id() -> int | None:
    """Return the id of the most recent resume row, or None if empty."""
    init_db()
    session = SessionLocal()
    try:
        resume = session.query(Resume).order_by(Resume.id.desc()).first()
        return int(resume.id) if resume else None  # type: ignore[arg-type]
    finally:
        session.close()


def save_match_report(job_id: int, match_data: dict, resume_id: int | None = None) -> dict[str, Any]:
    """Persist a structured match report linking job + resume + scores.

    Scores are stored as typed columns (queryable); keywords/strengths/gaps/
    action items/summary as JSON text.  When ``resume_id`` is omitted it
    resolves to the most recent resume — the one the matcher scored against.

    Returns:
        dict: {'status': 'created', 'report_id': int}
    """
    init_db()
    session = SessionLocal()
    try:
        if resume_id is None:
            resume_id = get_latest_resume_id()

        def _as_json(value: Any) -> str | None:
            if value in (None, "", []):
                return None
            return json.dumps(value, ensure_ascii=False)

        def _score(key: str) -> float:
            v = match_data.get(key)
            try:
                return float(v) if v is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        report = MatchReport(
            job_id=job_id,
            resume_id=resume_id,
            overall_score=_score("overall_score"),
            skills_score=_score("skills_score"),
            experience_score=_score("experience_score"),
            education_score=_score("education_score"),
            responsibilities_score=_score("responsibilities_score"),
            keyword_match=_as_json(match_data.get("keyword_match")),
            strengths=_as_json(match_data.get("strengths")),
            gaps=_as_json(match_data.get("gaps")),
            action_items=_as_json(match_data.get("action_items")),
            summary=(match_data.get("summary") or "")[:2000] or None,
        )
        session.add(report)
        session.commit()
        return {
            "status": "created",
            "report_id": int(report.id),  # type: ignore[arg-type]
            "resume_id": resume_id,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()