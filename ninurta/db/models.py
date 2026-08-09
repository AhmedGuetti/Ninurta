"""Database SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Boolean
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

    # A base resume can have many tailored versions
    tailored_versions = relationship("TailoredResume", back_populates="base_resume")


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

    # A job can have many tailored resumes (if we try different approaches)
    tailored_resumes = relationship("TailoredResume", back_populates="target_job")


class TailoredResume(Base):
    """The tuned resumes crafted for a specific Job by the LLM."""

    __tablename__ = "tailored_resumes"

    id = Column(Integer, primary_key=True)
    base_resume_id = Column(Integer, ForeignKey("resumes.id"))
    job_id = Column(Integer, ForeignKey("jobs.id"))
    
    content = Column(Text, nullable=False)       # The finalized tuned resume
    created_at = Column(DateTime, default=_utcnow)

    base_resume = relationship("Resume", back_populates="tailored_versions")
    target_job = relationship("Job", back_populates="tailored_resumes")
