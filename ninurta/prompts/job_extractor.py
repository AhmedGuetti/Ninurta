"""Prompt templates for the Job Extractor agent."""

from __future__ import annotations

from datetime import date
from ninurta.prompts.registry import prompt

SYSTEM = """\
You are an expert recruitment data analyst. Your sole task is to extract \
structured information from job postings and return it as a single JSON object.

CRITICAL RULES — follow every one of them:
1. Output ONLY the raw JSON object. No markdown fences (```), no prose, \
no explanation before or after.
2. Every key in the schema must appear in your output. Use JSON null for \
missing information — never omit a key.
3. List fields (skills_required, nice_to_have_skills, languages_required, \
certifications, responsibilities, benefits) must always be JSON arrays. \
Use [] when empty, never null.
4. contact must be a single string (name, email, or phone). \
Set to null if no contact info exists.
5. employment_type: use one of full-time, part-time, contract, freelance, \
internship, apprenticeship, temporary — or null if unclear.
6. work_mode: use one of on-site, remote, hybrid — or null if unclear.
7. experience_level: use one of junior, mid, senior, lead, principal, \
director, executive — or null if unclear.
8. Dates should be "YYYY-MM-DD" strings or null.
9. Do NOT invent information absent from the posting.
"""

_TEMPLATE = """\
{
  "position_title": null,
  "employment_type": null,
  "work_mode": null,
  "experience_level": null,
  "years_required": null,
  "department": null,
  "company_name": null,
  "company_description": null,
  "industry": null,
  "city": null,
  "country": null,
  "region": null,
  "salary_min": null,
  "salary_max": null,
  "salary_currency": null,
  "salary_period": null,
  "benefits": [],
  "skills_required": [],
  "nice_to_have_skills": [],
  "languages_required": [],
  "certifications": [],
  "responsibilities": [],
  "contact": null,
  "application_method": null,
  "visa_sponsorship": null,
  "posted_date": null,
  "application_deadline": null,
  "source_url": null
}"""


@prompt("job_extractor")
def build_messages(jd_text: str) -> list[dict]:
    """Return the chat messages list to send to the model."""
    today = date.today().isoformat()

    user_content = f"""\
Today's date is {today}.

Extract every field you can find from the job posting below and return \
a completed version of the JSON template. Follow all rules from the system prompt.

JSON TEMPLATE TO COMPLETE:
{_TEMPLATE}

JOB POSTING:
\"\"\"
{jd_text.strip()}
\"\"\"

Return the completed JSON object now:"""

    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user",   "content": user_content},
    ]
