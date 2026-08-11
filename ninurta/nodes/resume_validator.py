"""Resume validator node — LLM validates/corrects the parsed dict against the resume text.

The heuristic parser can mis-split entries or misclassify text.  This node sends
the parsed JSON + the original resume text to the LLM and asks it to produce a
corrected, faithful JSON object.

A deterministic **grounding guard** runs after the LLM call as a safety net:
every value is checked against the resume text itself, so anything the model
hallucinated (not present in the resume) is removed regardless of the prompt.
"""

from __future__ import annotations

import json
import re

from rich.console import Console

from ninurta.llm.factory import get_llm
from ninurta.nodes._llm_helpers import _call_llm, _extract_json
from ninurta.prompts.registry import prompt_registry
from ninurta.state import State
from ninurta.utils.logger import get_logger

log = get_logger(__name__)
_console = Console()

_MAX_TOKENS = 8192

# Fields that must appear in the resume verbatim (normalized substring match)
_VERBATIM_FIELDS = ("name", "email", "phone", "linkedin", "company",
                    "position", "period", "name_proj", "link")
# Fields that may be lightly paraphrased — checked by word-overlap instead
_PARAPHRASE_FIELDS = ("mission", "description")

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'’\-]{2,}")


# ---------------------------------------------------------------------------
# JSON extraction from the model reply
# ---------------------------------------------------------------------------

def _extract_json_object(raw: str) -> dict:
    """Pull the first JSON object out of the model's reply."""
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    cleaned = re.sub(r"```(?:json)?", "", cleaned).strip()
    cleaned = cleaned.replace("```", "").strip()

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"Model returned no JSON object. Output: {raw[:100]}...")
    data = json.loads(match.group())
    if not isinstance(data, dict):
        raise ValueError("Validated JSON is not an object")
    return data


# ---------------------------------------------------------------------------
# Normalization — coerce whatever the LLM returned into our canonical shape
# ---------------------------------------------------------------------------

def _as_str(value, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _as_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_experience(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    entries: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        entries.append({
            "company": _as_str(item.get("company")),
            "position": _as_str(item.get("position")),
            "period": _as_str(item.get("period")),
            "mission": _as_str(item.get("mission")),
            "achievements": _as_str_list(item.get("achievements")),
        })
    return entries


def _normalize_projects(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    projects: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        projects.append({
            "name": _as_str(item.get("name")),
            "description": _as_str(item.get("description")),
            "link": _as_str(item.get("link")),
        })
    return projects


def _normalize_education(value) -> list[dict]:
    """Coerce education entries into {degree, institution, period, details, location}."""
    if not isinstance(value, list):
        return []
    entries: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        entries.append({
            "degree": _as_str(item.get("degree")),
            "institution": _as_str(item.get("institution")),
            "period": _as_str(item.get("period")),
            "details": _as_str(item.get("details")),
            "location": _as_str(item.get("location")),
        })
    return entries


def normalize_parsed(parsed: dict) -> dict:
    """Coerce a validated dict into the canonical resume shape."""
    contact_raw = parsed.get("contact") or {}
    contact = {
        "email": _as_str(contact_raw.get("email")),
        "phone": _as_str(contact_raw.get("phone")),
        "linkedin": _as_str(contact_raw.get("linkedin")),
    }

    sections_raw = parsed.get("sections") or {}
    sections: dict[str, str | list | dict] = {}
    for title, content in sections_raw.items():
        if title == "experience":
            sections[title] = _normalize_experience(content)
        elif title == "education":
            sections[title] = _normalize_education(content)
        elif title == "projects":
            sections[title] = _normalize_projects(content)
        elif title == "achievements":
            sections[title] = _as_str_list(content)
        elif isinstance(content, str):
            sections[title] = content.strip()
        elif isinstance(content, list):
            sections[title] = _as_str_list(content)
        elif isinstance(content, dict):
            # Categorized section (e.g. skills → {category: [skills]})
            sections[title] = {
                str(category).strip(): _as_str_list(items)
                for category, items in content.items()
            }

    return {
        "name": _as_str(parsed.get("name")),
        "contact": contact,
        "sections": sections,
    }


# ---------------------------------------------------------------------------
# Grounding guard — remove anything not present in the resume text
# ---------------------------------------------------------------------------

def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _is_verbatim(value: str, resume_text: str) -> bool:
    """True if *value* appears in the resume text (normalized substring)."""
    if not value:
        return True  # empty is fine — nothing to ground
    return _normalized(value) in _normalized(resume_text)


def _word_overlap_ratio(value: str, resume_text: str) -> float:
    """Fraction of significant words in *value* that occur in the resume."""
    value_words = set(_WORD_RE.findall(value.lower()))
    if not value_words:
        return 1.0
    resume_words = set(_WORD_RE.findall(resume_text.lower()))
    if not resume_words:
        return 0.0
    return len(value_words & resume_words) / len(value_words)


def _split_items(value: str) -> list[str]:
    """Split a comma/semicolon/newline/" and "-separated list into items."""
    parts = re.split(r"[,;\n]+|\s+and\s+", value)
    return [item.strip() for item in parts if item.strip()]


def ground_against_resume(parsed: dict, resume_text: str) -> dict:
    """Remove any field value not supported by the resume text.

    Verbatim fields (name, contact, company, position, period, project
    name/link, achievements) must appear in the resume as a substring.
    Paraphrased prose fields (mission, description, summary) must share
    ≥ 60% of their significant words with the resume.  List-like string
    sections (e.g. "Python, LangGraph, SQL") are checked item by item so a
    single hallucinated item can't hide inside an otherwise-grounded list.
    Anything failing is blanked/removed — never kept.
    """
    # ── name & contact ────────────────────────────────────────────────────
    if not _is_verbatim(parsed.get("name", ""), resume_text):
        parsed["name"] = ""
    for key in ("email", "phone", "linkedin"):
        if not _is_verbatim(parsed["contact"].get(key, ""), resume_text):
            parsed["contact"][key] = ""

    # ── sections ─────────────────────────────────────────────────────────
    sections = parsed.get("sections", {})
    for title, content in sections.items():
        if title == "experience":
            for entry in content:
                for field in ("company", "position", "period"):
                    if not _is_verbatim(entry.get(field, ""), resume_text):
                        entry[field] = ""
                mission = _as_str(entry.get("mission"))
                if mission and _word_overlap_ratio(mission, resume_text) < 0.6:
                    entry["mission"] = ""
                entry["achievements"] = [
                    a for a in entry.get("achievements", [])
                    if _is_verbatim(a, resume_text)
                ]
        elif title == "projects":
            for project in content:
                for field in ("name", "link"):
                    if not _is_verbatim(project.get(field, ""), resume_text):
                        project[field] = ""
                desc = _as_str(project.get("description"))
                if desc and _word_overlap_ratio(desc, resume_text) < 0.6:
                    project["description"] = ""
        elif title == "education":
            for entry in content:
                for field in ("degree", "institution", "period", "location"):
                    if not _is_verbatim(entry.get(field, ""), resume_text):
                        entry[field] = ""
                details = _as_str(entry.get("details"))
                if details and _word_overlap_ratio(details, resume_text) < 0.6:
                    entry["details"] = ""
        elif title == "achievements":
            sections[title] = [
                a for a in _as_str_list(content) if _is_verbatim(a, resume_text)
            ]
        elif isinstance(content, str):
            sections[title] = _ground_string_section(content, resume_text)
        elif isinstance(content, list):
            sections[title] = [
                item for item in _as_str_list(content)
                if _is_verbatim(item, resume_text)
            ]
        elif isinstance(content, dict):
            # Categorized sections (e.g. skills → {category: [skills]})
            sections[title] = {
                category: [
                    item for item in _as_str_list(items)
                    if _is_verbatim(item, resume_text)
                ]
                for category, items in content.items()
            }

    return parsed


def _ground_string_section(content: str, resume_text: str) -> str:
    """Ground a plain string section, item-by-item when it's a list-like string."""
    items = _split_items(content)
    if len(items) >= 2:
        # List-like section (skills, certifications, ...): keep grounded items only
        kept = [
            item for item in items
            if _word_overlap_ratio(item, resume_text) >= 0.6
        ]
        if kept:
            return ", ".join(kept)
        # Nothing grounded individually → fall back to whole-section check
    if content and _word_overlap_ratio(content, resume_text) < 0.6:
        return ""
    return content


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def resume_validator_node(state: State) -> dict:
    """Second resume node: LLM-validate the parsed dict against the resume text."""
    parsed = state.get("parsed_resume")
    resume_text = state.get("resume_text", "")
    if not parsed:
        return {"error": "No parsed resume in state."}

    try:
        llm = get_llm()
        messages = prompt_registry.get(
            "resume_validator", resume_text=resume_text, parsed_json=parsed
        )
        log.info("Validating resume with [bold]%s[/]...", llm.model_id)
        result = _call_llm(llm, messages, max_tokens=_MAX_TOKENS)

        data = _extract_json(result.text, llm.model_id, phase="Resume validation")
        validated = normalize_parsed(data)
        validated = ground_against_resume(validated, resume_text)

        _console.print(
            "[bold green]✓[/] LLM validation complete — "
            "fields checked against resume text."
        )
        return {"parsed_resume": validated, "error": None}

    except Exception as exc:
        # Never fail the pipeline on validation issues — keep the parsed dict
        log.error("Resume validation failed (%s) — keeping parsed dict.", exc)
        _console.print(
            f"[bold yellow]⚠ LLM validation failed ({exc}) — "
            "using parsed dict as-is.[/]"
        )
        return {"parsed_resume": parsed, "error": None}
