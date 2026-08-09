"""Database operations/CRUD helpers for Ninurta."""

from __future__ import annotations

import json
from typing import Any
from ninurta.db.session import SessionLocal, init_db
from ninurta.db.models import Job, Resume
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


def save_job(job_desc: JobDescription, raw_jd: str) -> dict[str, Any]:
    """Save an extracted job and its raw job description to the SQLite database.

    Checks for existing job listings matching the same company and position title.
    If a match is found, it updates the existing listing's already_applied flag to True.
    Otherwise, a new job listing is added.

    Returns:
        dict: A dictionary indicating the result ("status": "created" or "already_applied").
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
            existing_job.already_applied = True  # type: ignore[assignment]
            session.commit()
            return {"status": "already_applied", "job_id": int(existing_job.id)}  # type: ignore[arg-type]

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