"""Database SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.orm import relationship

from ninurta.db.session import Base


def _utcnow() -> datetime:
    """Return the current UTC datetime with timezone info."""
    return datetime.now(timezone.utc)


class Resume(Base):
    """The user's base/standard resumes."""

    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)        # e.g., "Software Engineer 2026"
    content = Column(Text, nullable=False)       # Full markdown/text of the resume

    # Full parsed resume dict stored as JSON — deliberately schema-flexible
    # (sections may be str, list, or dict depending on what the LLM decided).
    parsed_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=_utcnow)

    # Match reports scored against this resume
    reports = relationship("MatchReport", back_populates="resume")


class Job(Base):
    """Target job descriptions we want to apply for."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    company_name = Column(String, nullable=False)
    position_title = Column(String, nullable=False)
    raw_job_description = Column(Text, nullable=False)
    
    # Store the 28-field JSON extracted earlier natively as text/json
    extracted_json = Column(Text, nullable=True) 

    already_applied = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=_utcnow)

    # Match reports scored against this job
    reports = relationship("MatchReport", back_populates="job")


class MatchReport(Base):
    """A structured match report linking a job, a resume, and the scores.

    One row per scoring run — re-scoring the same job+resume creates a new
    report row (history of how the score evolved over time).
    """

    __tablename__ = "match_reports"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=True)

    # ── Scores (0.0–1.0) ───────────────────────────────────────────────
    overall_score = Column(Float, nullable=False, default=0.0)
    skills_score = Column(Float, nullable=False, default=0.0)
    experience_score = Column(Float, nullable=False, default=0.0)
    education_score = Column(Float, nullable=False, default=0.0)
    responsibilities_score = Column(Float, nullable=False, default=0.0)

    # ── Structured payloads (JSON text) ────────────────────────────────
    keyword_match = Column(Text, nullable=True)    # {"matched": [...], "missing": [...]}
    strengths = Column(Text, nullable=True)        # list[str]
    gaps = Column(Text, nullable=True)             # list[str]
    action_items = Column(Text, nullable=True)     # list[str]
    summary = Column(Text, nullable=True)          # one-line narrative

    created_at = Column(DateTime, default=_utcnow)

    job = relationship("Job", back_populates="reports")
    resume = relationship("Resume", back_populates="reports")
