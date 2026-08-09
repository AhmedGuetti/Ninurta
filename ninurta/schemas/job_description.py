"""JobDescription — Pydantic schema for a parsed job posting.

All fields are optional (default None) so the model can leave them
blank when a posting doesn't mention them, without validation errors.
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, Field


def _coerce_str(v: object) -> str | None:
    """Coerce ints/floats to str so the model can return e.g. 3 instead of '3+'."""
    if v is None:
        return None
    return str(v)


class JobDescription(BaseModel):
    """Fully structured representation of a parsed job posting."""

    # ── Role ────────────────────────────────────────────────────────────
    position_title: Optional[str] = Field(
        None, description="Exact job title as written in the posting."
    )
    employment_type: Optional[str] = Field(
        None, description="full-time, part-time, contract, freelance, internship, etc."
    )
    work_mode: Optional[str] = Field(
        None, description="on-site, remote, or hybrid."
    )
    experience_level: Optional[str] = Field(
        None, description="junior, mid, senior, lead, principal, director, etc."
    )
    years_required: Annotated[Optional[str], BeforeValidator(_coerce_str)] = Field(
        None, description="Experience requirement, e.g. '3+ years'."
    )
    department: Optional[str] = Field(
        None, description="Business unit or team, e.g. 'Engineering'."
    )

    # ── Company ─────────────────────────────────────────────────────────
    company_name: Optional[str] = Field(None, description="Company name.")
    company_description: Optional[str] = Field(
        None, description="Brief description of the company."
    )
    industry: Optional[str] = Field(
        None, description="Industry sector, e.g. 'FinTech', 'Healthcare'."
    )

    # ── Location ────────────────────────────────────────────────────────
    city: Optional[str] = Field(None, description="City of the job location.")
    country: Optional[str] = Field(None, description="Country name or ISO code.")
    region: Optional[str] = Field(
        None, description="State, province, or region."
    )

    # ── Compensation ────────────────────────────────────────────────────
    salary_min: Annotated[Optional[str], BeforeValidator(_coerce_str)] = Field(
        None, description="Lower bound of salary range."
    )
    salary_max: Annotated[Optional[str], BeforeValidator(_coerce_str)] = Field(
        None, description="Upper bound of salary range."
    )
    salary_currency: Optional[str] = Field(
        None, description="ISO 4217 currency code, e.g. 'EUR', 'USD'."
    )
    salary_period: Optional[str] = Field(
        None, description="Pay period: annual, monthly, hourly, etc."
    )
    benefits: Optional[list[str]] = Field(
        default_factory=list,
        description="Other perks: health insurance, PTO, gym, etc.",
    )

    # ── Skills ──────────────────────────────────────────────────────────
    skills_required: Optional[list[str]] = Field(
        default_factory=list,
        description="Hard skills explicitly required, e.g. ['Python', 'Docker'].",
    )
    nice_to_have_skills: Optional[list[str]] = Field(
        default_factory=list,
        description="Skills listed as 'a plus' or 'preferred'.",
    )
    languages_required: Optional[list[str]] = Field(
        default_factory=list,
        description="Human languages required, e.g. ['English C1', 'Dutch B2'].",
    )
    certifications: Optional[list[str]] = Field(
        default_factory=list,
        description="Certifications mentioned, e.g. ['AWS SAA', 'PMP'].",
    )

    # ── Responsibilities ────────────────────────────────────────────────
    responsibilities: Optional[list[str]] = Field(
        default_factory=list,
        description="Main day-to-day duties as bullet points.",
    )

    # ── Contact & Application ──────────────────────────────────────────
    contact: Optional[str] = Field(
        None, description="Recruiter/HR contact info (name, email, or phone)."
    )
    application_method: Optional[str] = Field(
        None, description="How to apply: 'via LinkedIn', 'email CV to...', etc."
    )

    # ── Misc ────────────────────────────────────────────────────────────
    visa_sponsorship: Optional[bool] = Field(
        None, description="True if visa/work-permit sponsorship is offered."
    )
    posted_date: Optional[str] = Field(
        None, description="Date the job was posted (YYYY-MM-DD if available)."
    )
    application_deadline: Optional[str] = Field(
        None, description="Application closing date (YYYY-MM-DD if available)."
    )
    source_url: Optional[str] = Field(
        None, description="URL where the job posting was found."
    )

    # ── Pydantic config ────────────────────────────────────────────────
    model_config = {
        "str_strip_whitespace": True,
        "populate_by_name": True,
    }

    # ── Helpers ────────────────────────────────────────────────────────

    def summary(self) -> str:
        """One-line human-readable summary of the job posting."""
        parts = [
            self.position_title or "Unknown Role",
            f"@ {self.company_name}" if self.company_name else "",
            f"· {self.city}" if self.city else "",
            f"({self.country})" if self.country else "",
        ]
        return " ".join(p for p in parts if p)

    def to_csv_row(self) -> dict[str, str]:
        """Flat dict suitable for writing to a CSV file."""
        return {
            "position_title": self.position_title or "",
            "company_name": self.company_name or "",
            "employment_type": self.employment_type or "",
            "work_mode": self.work_mode or "",
            "experience_level": self.experience_level or "",
            "years_required": self.years_required or "",
            "department": self.department or "",
            "company_description": self.company_description or "",
            "industry": self.industry or "",
            "city": self.city or "",
            "country": self.country or "",
            "region": self.region or "",
            "salary_min": self.salary_min or "",
            "salary_max": self.salary_max or "",
            "salary_currency": self.salary_currency or "",
            "salary_period": self.salary_period or "",
            "benefits": ", ".join(self.benefits or []),
            "skills_required": ", ".join(self.skills_required or []),
            "nice_to_have_skills": ", ".join(self.nice_to_have_skills or []),
            "languages_required": ", ".join(self.languages_required or []),
            "certifications": ", ".join(self.certifications or []),
            "responsibilities": ", ".join(self.responsibilities or []),
            "contact": self.contact or "",
            "application_method": self.application_method or "",
            "visa_sponsorship": str(self.visa_sponsorship) if self.visa_sponsorship is not None else "",
            "posted_date": self.posted_date or "",
            "application_deadline": self.application_deadline or "",
            "source_url": self.source_url or "",
        }
