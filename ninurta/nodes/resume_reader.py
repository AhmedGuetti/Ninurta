"""Resume reader node — parse raw resume text into a structured dict.

Parsing is intentionally simple (no LLM):

* name            → first non-empty line
* contact         → email / phone / LinkedIn via regex
* sections        → split on known headers
* experience      → list of entries: {company, position, period, mission, achievements[]}
* projects        → list of entries: {name, description, link}
* achievements    → list of strings

The parsed dict is validated/corrected by the LLM in :mod:`resume_validator`
and reviewed by the user in :mod:`resume_reviewer` before summarization.
"""

from __future__ import annotations

import re

from ninurta.state import State
from ninurta.utils.logger import get_logger

log = get_logger(__name__)

# ── Common resume section headers (matched case-insensitively) ──────────────
_SECTION_HEADERS = [
    "summary", "objective", "profile", "experience", "work experience",
    "employment", "professional experience", "education", "skills",
    "technical skills", "projects", "personal projects", "certifications",
    "languages", "interests", "awards", "achievements", "accomplishments",
    "publications", "volunteer", "leadership", "references",
    # Multi-word / localized variants
    "awards & achievements", "awards and achievements",
    "prizes & distinctions", "prizes and distinctions", "honors & awards",
    "prix & distinctions", "prix et distinctions", "distinctions",
    "profil", "formation", "compétences", "expérience", "langues",
]

# Headers that mean the same thing → canonical section key
_HEADER_ALIASES = {
    "work experience": "experience",
    "employment": "experience",
    "professional experience": "experience",
    "technical skills": "skills",
    "personal projects": "projects",
    "accomplishments": "achievements",
    "awards & achievements": "achievements",
    "awards and achievements": "achievements",
    "prizes & distinctions": "achievements",
    "prizes and distinctions": "achievements",
    "honors & awards": "achievements",
    "prix & distinctions": "achievements",
    "prix et distinctions": "achievements",
    "distinctions": "achievements",
    "profil": "profile",
    "formation": "education",
    "compétences": "skills",
    "expérience": "experience",
    "langues": "languages",
}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
_LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w-]+", re.IGNORECASE)

# A date token: "2024", "10/2025", "01.2025"
_DATE = r"(?:\d{1,2}[/.]\d{4}|\d{4})"
# "(2024 – 2026)", "(2020–Present)", "10/2025 – Present", "01/2025 – 08/2025",
# and accented French "Présent"
_PERIOD_RE = re.compile(
    r"\(([^()]*" + _DATE + r"[^()]*)\)"
    r"|" + _DATE + r"\s*[-–—to]+\s*(?:present|présent|now|current|" + _DATE + r")",
    re.IGNORECASE,
)

_BULLET_RE = re.compile(r"^\s*[-•*–·›]\s+")
_URL_RE = re.compile(r"https?://\S+|github\.com/[\w./-]+", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

def _detect_header(line: str) -> str | None:
    """Return the canonical section name if *line* is a section header."""
    cleaned = line.strip().rstrip(":").strip().lower()
    if cleaned in _SECTION_HEADERS:
        return _HEADER_ALIASES.get(cleaned, cleaned)
    return None


# ---------------------------------------------------------------------------
# Structured section parsers
# ---------------------------------------------------------------------------

def _match_entry_header(line: str) -> dict | None:
    """Parse a line like ``Acme Corp — Senior Engineer (2020–Present)``.

    Also handles tab-separated entries such as ``AI Engineer, Apprenticeship\t10/2025 – Present``
    (position before the tab, period after) — in that case ``company`` is left
    empty because it lives on the following line.

    Returns ``{company, position, period}`` or None if the line has no
    recognizable date range (i.e. it's probably a description line).
    """
    m = _PERIOD_RE.search(line)
    if not m:
        return None
    period = (m.group(1) or m.group(0)).strip()
    rest = _PERIOD_RE.sub("", line)

    has_tab = "\t" in rest
    rest = rest.strip(" ,;|·—–\t")
    if has_tab:
        # Tab-separated: "Position, Type\tPeriod" — company is on the next line
        return {"company": "", "position": rest, "period": period}

    parts = re.split(r"\s*[—–|]\s*", rest)
    if len(parts) >= 2:
        company = parts[0].strip()
        position = " ".join(p.strip() for p in parts[1:])
    elif "," in rest:
        # "Position, Company" convention
        pos, _, comp = rest.rpartition(",")
        position, company = pos.strip(), comp.strip()
    else:
        company, position = rest, ""
    return {"company": company, "position": position, "period": period}


def _parse_company_line(line: str) -> tuple[str, str] | None:
    """Split a ``Company\tLocation`` line; return (company, location) or None."""
    if "\t" in line:
        company, _, location = line.partition("\t")
        return company.strip(), location.strip()
    return None


def parse_experience(text: str) -> list[dict]:
    """Split an experience section into structured job entries.

    Lines containing a date range start a new entry; bullet lines under an
    entry become ``achievements``; everything else becomes ``mission``.
    Tab-separated resumes (``Position\tPeriod`` / ``Company\tLocation``) are
    handled: the company/location line right after a header is consumed.
    """
    entries: list[dict] = []
    current: dict | None = None
    lines = text.splitlines()
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()
        i += 1
        if not line:
            continue

        header = _match_entry_header(line)
        if header:
            if current:
                entries.append(current)
            header["mission"] = ""
            header["achievements"] = []
            header["location"] = ""
            current = header

            # Tab-separated format: company/location line follows the header
            if not current["company"] and i < n:
                nxt = lines[i].strip()
                company_loc = _parse_company_line(nxt)
                if company_loc and not _match_entry_header(nxt):
                    current["company"], current["location"] = company_loc
                    i += 1
            continue

        if current is None:
            # Description text before any dated header — start an anonymous entry
            current = {"company": "", "position": "", "period": "",
                       "mission": "", "achievements": [], "location": ""}

        if _BULLET_RE.match(line):
            current["achievements"].append(_BULLET_RE.sub("", line).strip())
        else:
            current["mission"] = (current["mission"] + "\n" + line).strip()

    if current:
        entries.append(current)

    if not entries:
        entries = [{"company": "", "position": "", "period": "",
                    "mission": text.strip(), "achievements": [], "location": ""}]
    return entries


def parse_education(text: str) -> list[dict]:
    """Split an education section into structured entries.

    Each entry: {degree, institution, period, details}.
    Supports both ``Institution — Degree (Period)`` and tab-separated
    ``Degree\tPeriod`` / ``Institution\tLocation`` formats.
    """
    entries: list[dict] = []
    current: dict | None = None
    lines = text.splitlines()
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()
        i += 1
        if not line:
            continue

        header = _match_entry_header(line)
        if header:
            if current:
                entries.append(current)
            degree = header.get("position") or header.get("company", "")
            current = {
                "degree": degree,
                "institution": header.get("company", "") if header.get("position") else "",
                "period": header.get("period", ""),
                "details": "",
                "location": "",
            }
            # Tab-separated format: institution/location line follows the header
            if not current["institution"] and i < n:
                nxt = lines[i].strip()
                company_loc = _parse_company_line(nxt)
                if company_loc and not _match_entry_header(nxt):
                    current["institution"], current["location"] = company_loc
                    i += 1
            continue

        if current is None:
            continue  # stray text before any header — ignore

        if current["details"]:
            current["details"] += "\n" + line
        else:
            current["details"] = line

    if current:
        entries.append(current)

    if not entries:
        entries = [{"degree": "", "institution": "", "period": "",
                    "details": text.strip(), "location": ""}]
    return entries


def parse_projects(text: str) -> list[dict]:
    """Split a projects section into {name, description, link} entries."""
    projects: list[dict] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue

        # Extract the link first so it doesn't pollute name/description
        link = ""
        for ln in lines:
            m = _URL_RE.search(ln)
            if m:
                link = m.group(0)
                break
        clean_lines = [_URL_RE.sub("", ln).strip(" ,;") for ln in lines]
        clean_lines = [ln for ln in clean_lines if ln]

        # First line holds the name, optionally "Name — description"
        first = clean_lines[0] if clean_lines else ""
        name, description = first, ""
        if re.search(r"\s*[—–:]\s*", first):
            parts = re.split(r"\s*[—–:]\s*", first, maxsplit=1)
            name, description = parts[0], parts[1]

        desc_lines = [ln for ln in clean_lines[1:] if ln]
        if description:
            desc_lines.insert(0, description)
        desc_text = "\n".join(desc_lines).strip()

        projects.append({"name": name.strip(), "description": desc_text,
                         "link": link})
    return projects


def parse_achievements(text: str) -> list[str]:
    """Split an achievements section into a list of strings."""
    items: list[str] = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        items.append(_BULLET_RE.sub("", ln).strip() if _BULLET_RE.match(ln) else ln)
    return items


# ---------------------------------------------------------------------------
# Top-level parsing
# ---------------------------------------------------------------------------

def parse_resume(text: str) -> dict:
    """Parse raw resume text into a plain Python dict.

    Shape:
        {
          "name": str,
          "contact": {"email": str, "phone": str, "linkedin": str},
          "sections": {
            "experience":   [{"company", "position", "period", "mission", "achievements[]", "location"}],
            "education":    [{"degree", "institution", "period", "details", "location"}],
            "projects":     [{"name", "description", "link"}],
            "achievements": [str, ...],
            ...             # any other section stays a plain string
          },
        }
    """
    lines = text.splitlines()

    # Name = first non-empty line (most resumes lead with the name)
    name = next((ln.strip() for ln in lines if ln.strip()), "")

    # Contact details from the whole text
    email = _EMAIL_RE.search(text)
    phone = _PHONE_RE.search(text)
    linkedin = _LINKEDIN_RE.search(text)

    # Split the body into sections by known headers
    sections: dict[str, str | list] = {}
    current: str | None = None
    buf: list[str] = []

    for line in lines:
        header = _detect_header(line)
        if header:
            if current and buf:
                sections[current] = "\n".join(buf).strip()
            current = header
            buf = []
        else:
            buf.append(line)
    if current and buf:
        sections[current] = "\n".join(buf).strip()

    # Structure the special sections
    if "experience" in sections:
        sections["experience"] = parse_experience(str(sections["experience"]))
    if "education" in sections:
        sections["education"] = parse_education(str(sections["education"]))
    if "projects" in sections:
        sections["projects"] = parse_projects(str(sections["projects"]))
    if "achievements" in sections:
        sections["achievements"] = parse_achievements(str(sections["achievements"]))

    return {
        "name": name,
        "contact": {
            "email": email.group(0) if email else "",
            "phone": phone.group(0) if phone else "",
            "linkedin": linkedin.group(0) if linkedin else "",
        },
        "sections": sections,
    }


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def resume_reader_node(state: State) -> dict:
    """First resume node: parse resume text into a structured dict."""
    text = state.get("resume_text", "")
    if not text:
        return {"error": "No resume text provided."}

    parsed = parse_resume(text)
    n_entries = len(parsed["sections"].get("experience", []))
    log.info("Resume parsed: %d experience entries, %d sections",
             n_entries, len(parsed["sections"]))

    return {"parsed_resume": parsed, "error": None}

