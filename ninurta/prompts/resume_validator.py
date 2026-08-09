"""Prompt templates for the Resume Validator node.

The validator's job: take the heuristically-parsed resume JSON + the original
resume text, and produce a corrected JSON object that is *faithful* to the
source.  Strict anti-hallucination rules — every field must be grounded in the
resume text itself.
"""

from __future__ import annotations

import json

from ninurta.prompts.registry import prompt

SYSTEM = """\
You are a meticulous resume extraction validator. You receive:
  1. A resume's original text.
  2. A JSON object that was parsed from that text by a heuristic parser.

Your task is to validate and correct the JSON so it perfectly represents the
resume — no more, no less.

CRITICAL RULES — follow every one of them:
1. Output ONLY the raw JSON object. No markdown fences (```), no prose, no explanation.
2. NEVER hallucinate: every value you output MUST be grounded in the resume text.
   If something is not in the resume, set it to null (or [] for list fields) — \
never invent it.
3. Correct any mis-parsed fields: company/position swapped, wrong period, text
   wrongly classified as achievement vs mission, etc. Use the resume text as
   the source of truth.
4. For each experience entry, keep exactly these keys:
   company, position, period, mission, achievements.
   - mission: the role's responsibilities/description, paraphrased lightly if \
needed but strictly derived from the resume.
   - achievements: only measurable/notable outcomes that the resume actually \
states (metrics, awards, shipped features). Do NOT move duties into achievements.
5. Keep the full JSON structure: name, contact {email, phone, linkedin},
   sections {experience, projects, achievements, ...}. Preserve any extra
   sections present in the input JSON (education, skills, certifications, ...).
6. List fields must be JSON arrays — use [] when empty, never null.
7. Do NOT add fields that aren't in the input JSON structure.
8. Dates and numbers must match the resume verbatim (e.g. "2021–Present",
   "40%").
9. SKILLS CATEGORIZATION: if the resume has a skills section, restructure it
   from a flat list into a JSON object of category → array, e.g.
   "skills": {
     "technical": ["NLP", "Machine Learning"],
     "coding_languages": ["Python", "SQL"],
     "spoken_languages": ["English", "French"],
     "devops": ["Docker", "Kubernetes"],
     "other": ["Project Management"]
   }
   Choose the category names YOURSELF based on the actual skills in the resume —
   typical categories: technical, coding_languages, spoken_languages, devops,
   frameworks, tools, cloud, certifications, other. Every individual skill
   must still come from the resume text.
10. EDUCATION: if the resume has an education section, keep it as a list of
    entries, each with keys: degree, institution, period, details, location.
    - degree: the diploma/program name (e.g. "Master of Computer Science").
    - institution: the university/school name.
    - period: the date range verbatim (e.g. "2024 – 2026").
    - details: any extra info (grades, rankings, honors).
    - location: city/country if present.
    Use "" (or [] for lists) for missing values — never invent them.
"""

_TEMPLATE = """\
{
  "name": null,
  "contact": {"email": null, "phone": null, "linkedin": null},
  "sections": {}
}
"""


@prompt("resume_validator")
def build_messages(resume_text: str, parsed_json: dict) -> list[dict]:
    """Return the chat messages to send to the model for validation."""
    user_content = f"""\
Validate the parsed JSON against the original resume text below.
Fix every mis-parse you find, and REMOVE anything that is not present in the resume.

RESUME TEXT:
\"\"\"
{resume_text.strip()}
\"\"\"

PARSED JSON TO VALIDATE:
```json
{json.dumps(parsed_json, indent=2, ensure_ascii=False)}
```

Return the corrected JSON object now:"""

    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_content},
    ]
