"""Heuristic job-dedup node — no vector DB, no embeddings.

After extraction, compare the fresh ``JobDescription`` against every job
already stored in the DB using a weighted bag-of-words cosine similarity
over the structured ``extracted_json`` fields.  At single-user scale
(~1000 JDs/month, a few thousand rows), brute-force over the whole table
is milliseconds — no indexing or vector store needed.

How it works
------------
1. Each field of the parsed JD contributes tokens to a weighted vector:
   ``position_title`` 3.0, ``skills_required`` 2.0, ``responsibilities``
   1.5, ``company_name`` 1.5, etc. (see ``_FIELD_WEIGHTS``).  Tokens are
   lowercased alnum runs, stopwords and <3-char tokens dropped.
2. Cosine similarity between the new vector and each stored job's vector.
3. An exact company+title match (case-insensitive) pins the score to the
   duplicate threshold — preserving the legacy exact-match behaviour as a
   fast path while the heuristic covers reposts and near-duplicates.
4. Verdict: ``duplicate`` (top score ≥ duplicate_threshold), ``similar``
   (≥ similar_threshold), else ``new``.

Thresholds are configurable via an optional ``dedup:`` section in
config.yaml; code defaults apply when the section is absent::

    dedup:
      duplicate_threshold: 0.75
      similar_threshold: 0.45
      top_k: 3
"""

from __future__ import annotations

import json
import math
import re

from ninurta.config import load_config
from ninurta.db.models import Job
from ninurta.db.session import SessionLocal, init_db
from ninurta.state import State
from ninurta.utils.logger import get_logger

log = get_logger(__name__)

# Default verdict thresholds + result list size (overridable in config.yaml).
DEFAULT_DUPLICATE_THRESHOLD = 0.75
DEFAULT_SIMILAR_THRESHOLD = 0.45
DEFAULT_TOP_K = 3

# Fields whose tokens feed the similarity vector, with weights.  Title and
# skills dominate; company is deliberately moderate (same company posting a
# *different* role must not look like a duplicate); location stays low.
_FIELD_WEIGHTS: dict[str, float] = {
    "position_title": 3.0,
    "skills_required": 2.0,
    "responsibilities": 1.5,
    "company_name": 1.5,
    "nice_to_have_skills": 1.0,
    "languages_required": 1.0,
    "certifications": 1.0,
    "industry": 1.0,
    "department": 1.0,
    "company_description": 0.5,
    "employment_type": 0.5,
    "work_mode": 0.5,
    "experience_level": 0.5,
    "city": 0.5,
    "country": 0.5,
    "region": 0.5,
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Generic function words only — deliberately NOT domain words (experience,
# requirements, python...) which carry signal for JD-vs-JD comparison.
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "you", "will", "our", "your", "from",
    "that", "this", "are", "have", "has", "had", "was", "were", "can",
    "all", "any", "but", "not", "per", "via", "who", "which", "what",
    "when", "where", "how", "why", "its", "their", "them", "they", "we",
    "us", "or", "an", "of", "to", "in", "on", "at", "by", "as", "is",
    "it", "be", "been", "being", "may", "might", "must", "should",
    "would", "could", "than", "then", "there", "here", "into", "over",
    "under", "about", "between", "through", "during", "after", "before",
    "job", "jobs", "role", "roles", "team", "work", "working", "new",
    "one", "two", "years", "year", "day", "days", "hour", "hours",
})


def _tokens(text: str) -> list[str]:
    """Lowercased alnum tokens, stopwords and 1-2 char tokens dropped."""
    return [
        t
        for t in _TOKEN_RE.findall(text.lower())
        if len(t) >= 3 and t not in _STOPWORDS
    ]


def _vector(data: dict) -> dict[str, float]:
    """Weighted token vector for a parsed JD dict (JobDescription model_dump)."""
    vec: dict[str, float] = {}

    for field, weight in _FIELD_WEIGHTS.items():
        value = data.get(field)
        if not value:
            continue
        if isinstance(value, str):
            texts = [value]
        elif isinstance(value, list):
            texts = [v for v in value if isinstance(v, str)]
        elif isinstance(value, bool):
            continue
        else:
            texts = [str(value)]
        for text in texts:
            for tok in _tokens(text):
                vec[tok] = vec.get(tok, 0.0) + weight

    return vec


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two weighted token vectors (0.0–1.0)."""
    if not a or not b:
        return 0.0

    dot = sum(a[t] * b[t] for t in a.keys() & b.keys())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))

    return dot / (na * nb) if na and nb else 0.0


def _stored_job_dict(job: Job) -> dict:
    """Best-effort dict for a stored Job row: parsed JSON, else columns."""
    if job.extracted_json:  # type: ignore[truthy-function]
        try:
            data = json.loads(job.extracted_json)  # type: ignore[arg-type]
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            log.warning("job %s has invalid extracted_json", job.id)

    # Legacy rows without extracted_json — compare on the columns only.
    return {
        "position_title": job.position_title,
        "company_name": job.company_name,
    }


def _exact_match(parsed: dict, job: Job) -> bool:
    """Case-insensitive company+title equality (legacy dedup fast path)."""
    return (
        (parsed.get("company_name") or "").strip().lower()
        == (job.company_name or "").strip().lower()
        and (parsed.get("position_title") or "").strip().lower()
        == (job.position_title or "").strip().lower()
    )


def _dedup_config() -> dict:
    return load_config().get("dedup", {}) or {}


def job_dedup_node(state: State) -> dict:
    """Compare the extracted JD against every stored job; report verdict.

    Returns ``{"dedup_result": {...}}`` with::

        {
            "verdict": "duplicate" | "similar" | "new",
            "top_score": float,          # best match score
            "top_match_id": int | None,  # best match row id
            "matches": [                 # top-k, best first
                {"id", "score", "company_name", "position_title",
                 "already_applied"},
            ],
        }

    Runs a read-only SELECT over the jobs table — never writes.
    """
    parsed_job = state.get("parsed_job")
    if parsed_job is None:
        return {"dedup_result": None}

    parsed = parsed_job.model_dump() if hasattr(parsed_job, "model_dump") else dict(parsed_job)
    new_vec = _vector(parsed)

    empty = {
        "verdict": "new",
        "top_score": 0.0,
        "top_match_id": None,
        "matches": [],
    }
    if not new_vec:
        return {"dedup_result": empty}

    cfg = _dedup_config()
    dup_th = float(cfg.get("duplicate_threshold", DEFAULT_DUPLICATE_THRESHOLD))
    sim_th = float(cfg.get("similar_threshold", DEFAULT_SIMILAR_THRESHOLD))
    top_k = int(cfg.get("top_k", DEFAULT_TOP_K))

    init_db()
    session = SessionLocal()
    try:
        scored: list[dict] = []
        for job in session.query(Job).all():
            stored_vec = _vector(_stored_job_dict(job))
            if not stored_vec:
                continue

            score = _cosine(new_vec, stored_vec)
            # Exact company+title match always reads as a duplicate —
            # preserves the legacy NOCASE check as a guaranteed fast path.
            if _exact_match(parsed, job):
                score = max(score, dup_th)

            scored.append(
                {
                    "id": int(job.id),  # type: ignore[arg-type]
                    "score": round(score, 4),
                    "company_name": job.company_name,
                    "position_title": job.position_title,
                    "already_applied": bool(job.already_applied),
                }
            )
    finally:
        session.close()

    scored.sort(key=lambda m: m["score"], reverse=True)
    top = scored[:top_k]

    if top and top[0]["score"] >= dup_th:
        verdict = "duplicate"
    elif top and top[0]["score"] >= sim_th:
        verdict = "similar"
    else:
        verdict = "new"

    log.info("dedup verdict: %s (%d jobs compared)", verdict, len(scored))

    return {
        "dedup_result": {
            "verdict": verdict,
            "top_score": top[0]["score"] if top else 0.0,
            "top_match_id": top[0]["id"] if top else None,
            "matches": top,
        }
    }
