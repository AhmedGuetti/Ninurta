"""Database inspection JSON-RPC handlers."""

import json
from ninurta.db.session import SessionLocal, init_db
from ninurta.db.models import Job, Resume

def _db_summary(session) -> str:
    """Return a compact summary of all tables."""
    resumes = session.query(Resume).all()
    jobs = session.query(Job).all()
    lines = [
        f"resumes: {len(resumes)}",
        f"jobs: {len(jobs)}",
    ]
    if resumes:
        lines.append("─ resumes ─")
        for r in resumes[:5]:
            lines.append(f"  [{r.id}] {r.name}")
    if jobs:
        lines.append("─ jobs ─")
        for j in jobs[:5]:
            lines.append(
                f"  [{j.id}] {j.position_title} @ {j.company_name}"
                f"{' ✓applied' if j.already_applied else ''}"
            )
    return "\n".join(lines)


def _db_row(session, table: str, row_id: int) -> str:
    """Return a detailed view of a single row."""
    if table in ("resumes", "resume"):
        row = session.query(Resume).filter(Resume.id == row_id).first()
        if not row:
            return f"resume id={row_id} not found"
        created = row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else "?"
        lines = [
            f"Resume #{row.id}: {row.name}",
            f"created: {created}",
            "",
        ]
        if row.parsed_json:
            try:
                parsed = json.loads(row.parsed_json)
                body: list[str] = []

                # ── Contact ──────────────────────────────────────────
                contact = parsed.get("contact", {})
                n_before = len(body)
                for fld in ("email", "phone", "linkedin"):
                    v = contact.get(fld, "")
                    if v:
                        body.append(f"  {fld:22s} {v}")
                if len(body) > n_before:
                    body.insert(n_before, "  ── Contact " + "─" * 30)

                sections = parsed.get("sections", {})

                # ── Profile / Summary ────────────────────────────────
                for label in ("profile", "summary", "objective"):
                    if label in sections:
                        n_before = len(body)
                        txt = sections[label]
                        if isinstance(txt, str) and txt.strip():
                            preview = txt[:200].replace("\n", " ")
                            body.append(f"  {preview}")
                            if len(txt) > 200:
                                body.append(f"  … ({len(txt)} chars total)")
                        if len(body) > n_before:
                            body.insert(n_before, f"  ── {label.title()} " + "─" * 30)
                        break

                # ── Skills ───────────────────────────────────────────
                if "skills" in sections:
                    n_before = len(body)
                    sk = sections["skills"]
                    if isinstance(sk, dict):
                        for cat, items in sk.items():
                            if isinstance(items, list) and items:
                                body.append(f"  {cat:22s} {', '.join(items)}")
                    elif isinstance(sk, list):
                        if sk:
                            body.append(f"  {'skills':22s} {', '.join(str(s) for s in sk)}")
                    elif isinstance(sk, str) and sk.strip():
                        body.append(f"  {sk}")
                    if len(body) > n_before:
                        body.insert(n_before, "  ── Skills " + "─" * 30)

                # ── Experience ───────────────────────────────────────
                exp = sections.get("experience")
                if isinstance(exp, list) and exp:
                    n_before = len(body)
                    for i, e in enumerate(exp, 1):
                        title_parts = []
                        if e.get("position"):
                            title_parts.append(e["position"])
                        if e.get("company"):
                            title_parts.append(f"@ {e['company']}")
                        if e.get("period"):
                            title_parts.append(f"({e['period']})")
                        body.append(f"  [{i}] {' '.join(title_parts)}")
                        if e.get("location"):
                            body.append(f"      {e['location']}")
                        mission = e.get("mission", "")
                        if mission:
                            body.append(f"      {mission[:200]}")
                        for a in e.get("achievements", [])[:4]:
                            body.append(f"      • {a}")
                    if len(body) > n_before:
                        body.insert(n_before, f"  ── Experience ({len(exp)} entries) " + "─" * 30)

                # ── Education ────────────────────────────────────────
                edu = sections.get("education")
                if isinstance(edu, list) and edu:
                    n_before = len(body)
                    for i, e in enumerate(edu, 1):
                        parts = []
                        if e.get("degree"):
                            parts.append(e["degree"])
                        if e.get("institution"):
                            parts.append(f"@ {e['institution']}")
                        if e.get("period"):
                            parts.append(f"({e['period']})")
                        body.append(f"  [{i}] {' '.join(parts)}")
                        if e.get("location"):
                            body.append(f"      {e['location']}")
                        if e.get("details"):
                            body.append(f"      {e['details'][:200]}")
                    if len(body) > n_before:
                        body.insert(n_before, f"  ── Education ({len(edu)} entries) " + "─" * 30)

                # ── Projects ─────────────────────────────────────────
                proj = sections.get("projects")
                if isinstance(proj, list) and proj:
                    n_before = len(body)
                    for i, p in enumerate(proj, 1):
                        name = p.get("name", "")
                        desc = p.get("description", "")
                        link = p.get("link", "")
                        body.append(f"  [{i}] {name}")
                        if desc:
                            body.append(f"      {desc[:200]}")
                        if link:
                            body.append(f"      {link}")
                    if len(body) > n_before:
                        body.insert(n_before, f"  ── Projects ({len(proj)} entries) " + "─" * 30)

                # ── Achievements / Awards ────────────────────────────
                ach = sections.get("achievements")
                if isinstance(ach, list) and ach:
                    n_before = len(body)
                    for a in ach[:8]:
                        body.append(f"  • {a}")
                    if len(body) > n_before:
                        body.insert(n_before, f"  ── Achievements ({len(ach)} items) " + "─" * 30)

                # ── Other sections (catch-all: str or list) ──────────
                for sect_name, sect_data in sections.items():
                    if sect_name in ("profile", "summary", "objective",
                                     "skills", "experience", "education",
                                     "projects", "achievements"):
                        continue  # already handled above
                    n_before = len(body)
                    if isinstance(sect_data, str) and sect_data.strip():
                        body.append(f"  {sect_data[:300]}")
                    elif isinstance(sect_data, list) and sect_data:
                        for item in sect_data[:5]:
                            body.append(f"  • {item}")
                    elif isinstance(sect_data, dict):
                        for k, v in sect_data.items():
                            if isinstance(v, list):
                                body.append(f"  {k}: {', '.join(str(x) for x in v[:10])}")
                            else:
                                body.append(f"  {k}: {v}")
                    if len(body) > n_before:
                        body.insert(n_before, f"  ── {sect_name.title()} " + "─" * 30)

                lines.extend(body)

            except json.JSONDecodeError:
                lines.append("  (parsed_json is malformed)")
        lines.append("")
        lines.append(f"raw text: {len(row.content or '')} chars")
        return "\n".join(lines)

    if table in ("jobs", "job"):
        row = session.query(Job).filter(Job.id == row_id).first()
        if not row:
            return f"job id={row_id} not found"
        applied = "✓ yes" if row.already_applied else "no"
        created = row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else "?"
        lines = [
            f"Job #{row.id}: {row.position_title} @ {row.company_name}",
            f"applied: {applied} · created: {created}",
            "",
        ]
        if row.extracted_json:
            try:
                jd = json.loads(row.extracted_json)

                # Build sections lazily — only show headers when content exists.
                body: list[str] = []

                def _add_kv(label, key=None):
                    if key is None:
                        key = label
                    v = jd.get(key)
                    if v is not None and v != "" and v != []:
                        body.append(f"  {label:22s} {v}")
                        return True
                    return False

                def _add_list(key, label=None):
                    v = jd.get(key)
                    if isinstance(v, list) and v:
                        body.append(f"  {label or key:22s} {', '.join(v)}")
                        return True
                    return False

                def _section(title):
                    body.append(f"  ── {title} " + "─" * 30)

                # ── Role ──────────────────────────────────────────────
                n_before = len(body)
                _add_kv("position_title")
                _add_kv("employment_type")
                _add_kv("work_mode")
                _add_kv("experience_level")
                _add_kv("years_required")
                _add_kv("department")
                if len(body) > n_before:
                    body.insert(n_before, f"  ── Role " + "─" * 30)

                # ── Company ───────────────────────────────────────────
                n_before = len(body)
                _add_kv("company_name")
                _add_kv("company_description")
                _add_kv("industry")
                loc_parts = [p for p in [jd.get("city"), jd.get("region"), jd.get("country")] if p]
                if loc_parts:
                    body.append(f"  {'location':22s} {', '.join(loc_parts)}")
                if len(body) > n_before:
                    body.insert(n_before, f"  ── Company " + "─" * 30)

                # ── Compensation ─────────────────────────────────────
                n_before = len(body)
                sal_min = jd.get("salary_min")
                sal_max = jd.get("salary_max")
                sal_cur = jd.get("salary_currency", "")
                sal_per = jd.get("salary_period", "")
                if sal_min or sal_max:
                    rng = f"{sal_min or '?'} – {sal_max or '?'} {sal_cur} / {sal_per or 'yr'}"
                    body.append(f"  {'salary':22s} {rng}")
                _add_list("benefits")
                if len(body) > n_before:
                    body.insert(n_before, f"  ── Compensation " + "─" * 30)

                # ── Skills ───────────────────────────────────────────
                n_before = len(body)
                _add_list("skills_required", "required")
                _add_list("nice_to_have_skills", "nice to have")
                _add_list("languages_required", "languages")
                _add_list("certifications")
                if len(body) > n_before:
                    body.insert(n_before, f"  ── Skills " + "─" * 30)

                # ── Responsibilities ─────────────────────────────────
                n_before = len(body)
                resp = jd.get("responsibilities", [])
                if resp:
                    for r in resp[:8]:
                        body.append(f"  • {r}")
                if len(body) > n_before:
                    body.insert(n_before, f"  ── Responsibilities " + "─" * 30)

                # ── Application ──────────────────────────────────────
                n_before = len(body)
                _add_kv("contact")
                _add_kv("application_method")
                visa = jd.get("visa_sponsorship")
                if visa is not None:
                    body.append(f"  {'visa sponsorship':22s} {'yes' if visa else 'no'}")
                _add_kv("posted_date")
                _add_kv("application_deadline")
                _add_kv("source_url")
                if len(body) > n_before:
                    body.insert(n_before, f"  ── Application " + "─" * 30)

                lines.extend(body)

            except json.JSONDecodeError:
                lines.append("  (extracted_json is malformed)")
        lines.append("")
        lines.append(f"raw JD: {len(row.raw_job_description or '')} chars")
        return "\n".join(lines)

    return f"unknown table '{table}' — try 'resumes' or 'jobs'"


def handle_db_inspect(params: dict, transport) -> dict:
    """Inspect database: summary, list table, or view a specific row.

    Params:
        table: 'resumes' | 'jobs' (optional, omit for summary)
        id:    row ID (optional, requires table)
    """
    init_db()
    session = SessionLocal()
    try:
        table = (params.get("table") or "").strip().lower()
        row_id = params.get("id")

        if not table:
            text = _db_summary(session)
        elif row_id is not None:
            text = _db_row(session, table, int(row_id))
        else:
            # List all rows of a table
            if table in ("resumes", "resume"):
                rows = session.query(Resume).order_by(Resume.id).all()
                if not rows:
                    text = "no resumes in db"
                else:
                    text = "\n".join(f"[{r.id}] {r.name}" for r in rows)
            elif table in ("jobs", "job"):
                rows = session.query(Job).order_by(Job.id.desc()).all()
                if not rows:
                    text = "no jobs in db"
                else:
                    text = "\n".join(
                        f"[{j.id}] {j.position_title} @ {j.company_name}"
                        f"{' ✓' if j.already_applied else ''}"
                        for j in rows
                    )
            else:
                text = f"unknown table '{table}' — try 'resumes' or 'jobs'"
    finally:
        session.close()

    # Return text only — caller (useMainApp) handles display; no turn.end push
    # to avoid the double-append bug.
    return {"text": text}
