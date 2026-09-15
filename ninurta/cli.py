"""Ninurta CLI — Fire-based command dispatcher."""

from __future__ import annotations

import os
import sys

import fire
from rich.console import Console
from rich.table import Table

_console = Console()

BANNER = """\
[bold cyan]
  ███╗   ██╗██╗███╗   ██╗██╗   ██╗██████╗ ████████╗ █████╗
  ████╗  ██║██║████╗  ██║██║   ██║██╔══██╗╚══██╔══╝██╔══██╗
  ██╔██╗ ██║██║██╔██╗ ██║██║   ██║██████╔╝   ██║   ███████║
  ██║╚██╗██║██║██║╚██╗██║██║   ██║██╔══██╗   ██║   ██╔══██║
  ██║ ╚████║██║██║ ╚████║╚██████╔╝██║  ██║   ██║   ██║  ██║
  ╚═╝  ╚═══╝╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝
[/bold cyan]
[dim]  ⚡  Job-Search Automation Pipeline · Powered by Local LLMs   [v0.1.0][/dim]
"""

_DEFAULT_MODEL = "gemini-3.6-flash"


def _print_job_table(job) -> None:
    """Render an extracted JobDescription as a Rich table (shared by extract + pipeline)."""
    from rich import box
    from rich.table import Table

    t = Table(
        title="[bold green]Extracted Job Details[/]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=False,
    )
    t.add_column("Field", style="dim", min_width=22)
    t.add_column("Value")

    salary = ""
    if job.salary_min or job.salary_max:
        lo = job.salary_min or "?"
        hi = job.salary_max or "?"
        cur = job.salary_currency or ""
        per = job.salary_period or ""
        salary = f"{cur} {lo}–{hi} / {per}".strip()

    rows = [
        ("Position",          job.position_title),
        ("Company",           job.company_name),
        ("Location",          f"{job.city or ''}, {job.country or ''}".strip(", ")),
        ("Employment type",   job.employment_type),
        ("Work mode",         job.work_mode),
        ("Experience level",  job.experience_level),
        ("Salary",            salary),
        ("Skills required",   ", ".join(job.skills_required or [])),
        ("Source URL",        job.source_url),
    ]
    for field, value in rows:
        if value:
            t.add_row(field, value)
    _console.print(t)


def _print_match_result(match_data: dict) -> None:
    """Render the matcher's output as richly styled Markdown."""
    from rich.markdown import Markdown
    from rich.panel import Panel
    from ninurta.tui.palette import ACCENT, ACCENT_LIGHT, TAGLINE

    overall = match_data.get("overall_score", 0)
    skills = match_data.get("skills_score", 0)
    exp = match_data.get("experience_score", 0)
    edu = match_data.get("education_score", 0)
    resp = match_data.get("responsibilities_score", 0)
    
    overall_pct = int(overall * 100)
    score_color = "#00ff00" if overall_pct >= 80 else "#ffff00" if overall_pct >= 60 else "#ff0000"

    md_lines = [
        f"## 🎯 Match Analysis: **{overall_pct}%**",
        "",
        "### 📊 Breakdown",
        f"- **Skills:** {int(skills * 100)}%",
        f"- **Experience:** {int(exp * 100)}%"
    ]
    
    if edu is not None:
        md_lines.append(f"- **Education:** {int(edu * 100)}%")
    if resp is not None:
        md_lines.append(f"- **Responsibilities:** {int(resp * 100)}%")
        
    summary = match_data.get("summary")
    if summary:
        md_lines.extend(["", "### 📋 Summary", summary])
        
    strengths = match_data.get("strengths") or []
    if strengths:
        md_lines.extend(["", "### ✅ Strengths"])
        for s in strengths[:5]:
            md_lines.append(f"- {s}")
            
    gaps = match_data.get("gaps") or []
    if gaps:
        md_lines.extend(["", "### ⚠ Gaps"])
        for g in gaps[:5]:
            md_lines.append(f"- {g}")
            
    action_items = match_data.get("action_items") or []
    if action_items:
        md_lines.extend(["", "### 🔧 Action Items"])
        for a in action_items[:5]:
            md_lines.append(f"- {a}")

    md_str = "\n".join(md_lines)
    _console.print()
    _console.print(Panel(Markdown(md_str), border_style=ACCENT, title="[bold]Detailed Report[/]"))
    _console.print()


def _print_dedup_verdict(dedup_result: dict | None) -> None:
    """Stream the heuristic dedup verdict the way the TUI does."""
    verdict = (dedup_result or {}).get("verdict", "new")
    matches = (dedup_result or {}).get("matches") or []

    if verdict == "duplicate" and matches:
        m = matches[0]
        tag = "✓applied" if m.get("already_applied") else "seen before"
        _console.print(f"[bold yellow]⚡ Already in DB[/] (id={m['id']}, {m['score']:.0%} match, {tag})")
        if len(matches) > 1:
            others = ", ".join(f"id={x['id']} ({x['score']:.0%})" for x in matches[1:])
            _console.print(f"[dim]    └ similar too: {others}[/]")
    elif verdict == "similar" and matches:
        m = matches[0]
        _console.print(f"[bold yellow]⚠ Similar listing[/] (id={m['id']}, {m['score']:.0%} match) — check before applying")
    else:
        _console.print("[dim]· new listing (not in DB)[/]")


def _list_gemini_models() -> None:
    """Fetch and display available Gemini models with pricing and descriptions."""
    from ninurta.config import get_gemini_api_key
    api_key = get_gemini_api_key()
    if not api_key:
        _console.print("[bold red]Gemini API key is not set. Set GEMINI_API_KEY / GOOGLE_API_KEY environment variables, or configure 'gemini_api_key' in config.yaml.[/]")
        return
    
    try:
        from google import genai
        from ninurta.llm.base import get_pricing
    except ImportError:
        _console.print("[bold red]google-genai package not installed.[/]")
        return

    _console.print("[bold cyan]Fetching available Gemini models...[/]")
    client = genai.Client(api_key=api_key)
    
    t = Table(title="[bold green]Available Gemini 3.x Models[/]", expand=True)
    t.add_column("Model Name", style="cyan", no_wrap=True)
    t.add_column("Display Name", style="bold")
    t.add_column("Pricing / 1M (In/Out)", style="magenta")
    t.add_column("Description", style="dim")
    
    models = sorted(client.models.list(), key=lambda x: str(getattr(x, "name", "")))
    
    for m in models:
        name = str(getattr(m, "name", "unknown"))
        clean_name = name.replace("models/", "")
        
        if any(legacy in clean_name for legacy in ["gemini-1", "gemini-2", "bison", "vision"]):
            continue

        if "generateContent" in (getattr(m, "supported_actions", []) or []):
            display = str(getattr(m, "display_name", ""))
            desc = str(getattr(m, "description", ""))
            if len(desc) > 70:
                desc = desc[:67] + "..."
                
            pricing = get_pricing(clean_name)
            price_str = f"${pricing['input']:.3f} / ${pricing['output']:.3f}" if pricing["input"] > 0 else "See Google AI Docs"
            
            t.add_row(clean_name, display, price_str, desc)
    
    _console.print(t)
    _console.print("\n[dim]Note: 'gemini-3.6-flash' is the recommended model for fastest and cheapest extraction.[/dim]")


class NinurtaCLI:
    """Ninurta — multi-agent job-search automation pipeline."""

    def extract(
        self,
        csv_path: str = "jobs.csv",
        debug: bool = False,
    ) -> None:
        """Interactively extract job-description fields → CSV."""
        from pathlib import Path
        from rich import box
        from rich.table import Table
        from ninurta.graph import graph
        from ninurta.schemas.job_description import JobDescription
        from ninurta.interface.io import append_csv_row, read_stdin_until_double_enter
        from ninurta.utils.logger import configure_logging

        configure_logging("DEBUG" if debug else "INFO")
        _console.print(BANNER)
        
        csv_path_obj = Path(csv_path)

        _console.rule("[bold cyan]Job Extractor (LangGraph)[/]")
        _console.print(
            f"[dim]Results → [/dim][bold]{csv_path_obj}[/]\n"
            "[dim]Paste a JD and press Enter twice.  Empty + Enter twice = quit.[/]\n"
        )

        def _print_result(job: JobDescription) -> None:
            _print_job_table(job)

        def _print_usage_summary() -> None:
            """Print a token usage / cost summary if usage was tracked."""
            from ninurta.llm.factory import get_llm
            try:
                llm = get_llm()
                u = llm.usage
                if u.total_calls == 0:
                    return

                cost = u.estimate_cost(llm.model_id)

                t = Table(
                    title="[bold]Session Usage Summary[/]",
                    box=box.ROUNDED,
                    show_header=False,
                    expand=False,
                )
                t.add_column("Metric", style="dim", min_width=20)
                t.add_column("Value", justify="right")

                t.add_row("Model",           f"[bold]{llm.model_id}[/]")
                t.add_row("API calls",       str(u.total_calls))
                t.add_row("Input tokens",    f"{u.total_input_tokens:,}")
                t.add_row("Output tokens",   f"[bold]{u.total_output_tokens:,}[/]")
                if u.total_thinking_tokens:
                    t.add_row("Thinking tokens", f"{u.total_thinking_tokens:,}")
                t.add_row("Estimated cost",  f"[bold green]${cost:.4f}[/]")

                _console.print()
                _console.print(t)
            except Exception:
                pass

        loop = 0
        while True:
            loop += 1
            _console.rule(f"[dim]Posting #{loop}[/]", style="dim")

            jd_text = read_stdin_until_double_enter(
                prompt="[bold cyan]Paste job description ↓[/]  [dim](Enter×2 to submit / quit)[/]\n"
            )

            if not jd_text:
                _print_usage_summary()
                _console.print("\n[bold yellow]Goodbye![/]")
                break

            try:
                from rich.status import Status
                result = {}
                with Status("[bold cyan]Extracting job description...[/bold cyan]") as status:
                    for event in graph.stream({"jd_text": jd_text, "parsed_job": None, "test_tool_result": None, "error": None}):
                        for node_name, state_update in event.items():
                            if node_name == "extractor":
                                status.update("[bold magenta]Extracted constraints... Checking DB for duplicates...[/]")
                            elif node_name == "job_dedup":
                                status.update("[bold green]✓ Extraction complete[/]")
                            result.update(state_update)
                
                if result.get("error"):
                    _console.print(f"[bold red]Extraction failed:[/] {result['error']}")
                    continue
                
                job = result.get("parsed_job")
                if not job:
                    _console.print("[bold red]Failed to parse job description.[/]")
                    continue

                if debug and result.get("test_tool_result"):
                    _console.print(f"[dim yellow]Test Node Output:[/] {result['test_tool_result']}")

                _print_result(job)

                # Save to SQLite Database
                from ninurta.db import save_job
                db_res = save_job(job, jd_text)
                if db_res["status"] == "already_applied":
                    _console.print("[bold yellow]⚠ This job listing already exists! Flagged as ALREADY APPLIED.[/]")
                else:
                    _console.print("[bold green]✓[/] Saved to SQLite database ([dim]ninurta.db[/])")

                row = job.to_csv_row()
                append_csv_row(csv_path_obj, row)
                _console.print(
                    f"[bold green]✓[/] Saved  [bold]{csv_path_obj}[/]  "
                    f"([dim]{len(row)} fields[/])\n"
                )
            except Exception as exc:
                _console.print(f"[bold red]Pipeline error:[/] {exc}")
                continue

    def resume(self, file: str = "", debug: bool = False) -> None:
        """Parse a resume, correct the dict, summarize sections, export markdown.

        Args:
            file:  Optional path to a resume file (.pdf, .docx, .txt, .md).
                   When omitted, the resume is read interactively from stdin
                   (paste + Enter twice).
            debug: Enable debug logging.
        """
        from ninurta.graph import resume_graph
        from ninurta.interface.io import read_stdin_until_double_enter
        from ninurta.utils.logger import configure_logging

        configure_logging("DEBUG" if debug else "INFO")
        _console.print(BANNER)

        _console.rule("[bold cyan]Resume Pipeline (LangGraph)[/]")

        if file:
            from ninurta.interface.documents import extract_text
            resume_text = extract_text(file)
            _console.print(f"[dim]Loaded resume from [/][bold]{file}[/]\n")
        else:
            _console.print(
                "[dim]Paste your resume and press Enter twice.  "
                "Empty + Enter twice = quit.[/]\n"
            )
            resume_text = read_stdin_until_double_enter(
                prompt="[bold cyan]Paste resume ↓[/]  [dim](Enter×2 to submit / quit)[/]\n"
            )

        if not resume_text:
            _console.print("\n[bold yellow]Goodbye![/]")
            return

        try:
            from rich.status import Status
            result = {}
            with Status("[bold cyan]Parsing and validating resume...[/]") as status:
                for event in resume_graph.stream(
                    {
                        "resume_text": resume_text,
                        "parsed_resume": None,
                        "error": None,
                    }
                ):
                    for node_name, state_update in event.items():
                        if node_name == "resume_reader":
                            status.update("[bold magenta]Resume read. Validating...[/]")
                        elif node_name == "resume_validator":
                            status.update("[bold yellow]Validation complete. Reviewing...[/]")
                        elif node_name == "resume_reviewer":
                            status.update("[bold cyan]Review complete. Saving...[/]")
                        elif node_name == "resume_saver":
                            status.update("[bold green]✓ Saved to DB[/]")
                        result.update(state_update)

            if result.get("error"):
                _console.print(f"[bold red]Resume pipeline error:[/] {result['error']}")
                return

            _console.print("\n[bold green]✓[/] Resume pipeline complete.")
        except Exception as exc:
            _console.print(f"[bold red]Pipeline error:[/] {exc}")

    def pipeline(self, stage: str = "full", file: str = "", job_id: int = 0, debug: bool = False) -> None:
        """Run the full pipeline, or a single stage of it.

        Stages:
          full     extract JD → dedup → load resume → score   (one shot)
          extract  extract JD → dedup → SAVE job to DB
          resume   parse resume → validate → review → SAVE to DB
          match    score a resume against a JD (extracted, or from DB by id)

        Args:
            stage:  Which stage to run: full | extract | resume | match.
            file:   Optional input file.  For full/extract/match a plain-text
                    JD; for resume a .docx/.pdf/.txt/.md resume.  When omitted,
                    the input is pasted interactively (Enter twice to submit).
            job_id: For `match` only — score an already-saved JD from the DB
                    by id (skips extraction).  Omit to paste/extract a JD.
            debug:  Enable debug logging.
        """
        from ninurta.utils.logger import configure_logging

        configure_logging("DEBUG" if debug else "INFO")

        if stage == "resume":
            # resume() prints its own banner + rules — delegate cleanly.
            self._pipeline_resume(file)
            return

        _console.print(BANNER)
        if stage == "full":
            self._pipeline_full(file)
        elif stage == "extract":
            self._pipeline_extract(file)
        elif stage == "match":
            self._pipeline_match(file, job_id)
        else:
            _console.print(
                f"[bold red]Unknown stage: {stage}[/] — use full | extract | resume | match"
            )

    def _read_jd_input(self, file: str) -> str | None:
        """Read a job description from a file or interactive paste."""
        from ninurta.interface.io import read_stdin_until_double_enter

        if file:
            with open(file, "r", encoding="utf-8") as f:
                text = f.read().strip()
            _console.print(f"[dim]Loaded JD from [/][bold]{file}[/] ([dim]{len(text)} chars[/])\n")
            return text or None

        _console.print(
            "[dim]Paste the job description and press Enter twice.  "
            "Empty + Enter twice = quit.[/]\n"
        )
        return read_stdin_until_double_enter(
            prompt="[bold cyan]Paste JD ↓[/]  [dim](Enter×2 to submit / quit)[/]\n"
        )

    def _extract_jd(self, jd_text: str):
        """Run the extract graph; return (parsed_job, dedup_result) or None on error."""
        from rich.status import Status
        from ninurta.graph import extract_graph

        result = {}
        with Status("[bold cyan]Extracting job description...[/bold cyan]") as status:
            for event in extract_graph.stream({"jd_text": jd_text}):  # type: ignore[arg-type]
                for node_name, state_update in event.items():
                    if node_name == "extractor":
                        status.update("[bold magenta]Extracted constraints... Checking DB for duplicates...[/]")
                    elif node_name == "job_dedup":
                        dedup = state_update.get("dedup_result")
                        if dedup:
                            verdict = dedup.get("verdict")
                            if verdict == "duplicate":
                                status.update("[bold green]✓ Found duplicate[/]")
                            elif verdict == "similar":
                                status.update("[bold yellow]⚠ Found similar listing[/]")
                            else:
                                status.update("[bold green]✓ New listing[/]")
                    result.update(state_update)
        if result.get("error"):
            _console.print(f"[bold red]Extraction failed:[/] {result['error']}")
            return None, None
        parsed_job = result.get("parsed_job")
        if not parsed_job:
            _console.print("[bold red]Failed to parse job description.[/]")
            return None, None
        return parsed_job, result.get("dedup_result")

    def _load_resume_or_quit(self):
        """Load resume (DB first, disk fallback); persist if from disk so the
        match report can link it.  Returns (parsed, raw)."""
        from ninurta.interface.resume_loader import load_resume_from_db, load_resume_from_disk

        parsed, raw = load_resume_from_db()
        if parsed or raw:
            name = (parsed or {}).get("name", "unknown")
            _console.print(f"[dim]✓ using resume from DB: [/][bold]{name}[/]\n")
            return parsed, raw

        _console.print("[dim]· no resume in DB, parsing from disk…[/]")
        parsed, raw = load_resume_from_disk()
        if parsed or raw:
            name = (parsed or {}).get("name", "unknown")
            # Persist the disk parse so the match report links a real resume row.
            if parsed is not None:
                try:
                    from ninurta.db.operations import save_resume

                    save_resume(parsed, raw or "")
                except Exception as exc:  # noqa: BLE001 — persistence must not block scoring
                    _console.print(f"[dim yellow]⚠ could not persist resume ({exc})[/]")
            _console.print(f"[dim]✓ parsed resume from disk: [/][bold]{name}[/]\n")
            return parsed, raw

        _console.print("[bold red]✗ no resume found in DB or on disk — scoring skipped.[/]")
        return None, None

    def _score(self, parsed_job, parsed_resume, resume_text, job_id=None, jd_text="") -> dict | None:
        """Run the matcher (score_graph), print the result, persist a report.

        When ``job_id`` is None the job is saved first (mark_applied=False —
        scoring a JD is not an application); the report links job × resume ×
        score in the DB.  Returns match_data or None.
        """
        from rich.status import Status
        from ninurta.graph import score_graph

        match_state = {
            "jd_text": "",
            "parsed_job": parsed_job,
            "parsed_resume": parsed_resume,
            "resume_text": resume_text,
        }
        
        result = {}
        with Status("[bold yellow]🧠 Starting analysis of score...[/]") as status:
            for event in score_graph.stream(match_state):  # type: ignore[arg-type]
                for node_name, state_update in event.items():
                    if node_name == "matcher":
                        status.update("[bold green]✓ Analysis complete[/]")
                    result.update(state_update)
        if result.get("error"):
            _console.print(f"[bold red]Scoring error:[/] {result['error']}")
            return None
        match_data = result.get("match_result")
        if not match_data:
            _console.print("[bold red]No match data returned.[/]")
            return None
        _print_match_result(match_data)

        # ── Persist: job (if new) + structured report ─────────────────
        from ninurta.db.operations import save_job, save_match_report

        try:
            if job_id is None:
                job_id = save_job(parsed_job, jd_text, mark_applied=False)["job_id"]
            rep = save_match_report(job_id, match_data)
            _console.print(
                f"[dim]💾 report #{rep['report_id']} saved "
                f"(job #{job_id} × resume #{rep['resume_id'] or '—'}) — "
                f"`ninurta pipeline match --job_id={job_id}` to re-score[/]"
            )
        except Exception as exc:  # noqa: BLE001 — persistence must not kill the run
            _console.print(f"[dim yellow]⚠ could not save report ({exc})[/]")

        return match_data

    def _pipeline_full(self, file: str) -> None:
        """Stage 'full': extract → dedup → resume → score (the TUI chain)."""
        _console.rule("[bold cyan]Full Pipeline — extract → dedup → resume → score[/]")

        jd_text = self._read_jd_input(file)
        if not jd_text:
            _console.print("\n[bold yellow]Goodbye![/]")
            return

        _console.print("[dim]▸ extracting…[/]")
        parsed_job, dedup = self._extract_jd(jd_text)
        if not parsed_job:
            return

        _print_job_table(parsed_job)
        _print_dedup_verdict(dedup)

        parsed_resume, resume_text = self._load_resume_or_quit()
        if not parsed_resume and not resume_text:
            return

        resume_name = (parsed_resume or {}).get("name", "resume")
        _console.print(
            f"[dim]▸ scoring ({resume_name} vs {parsed_job.position_title})…[/]"
        )
        self._score(parsed_job, parsed_resume, resume_text, jd_text=jd_text)

    def _pipeline_extract(self, file: str) -> None:
        """Stage 'extract': extract JD → dedup → save to DB."""
        _console.rule("[bold cyan]Stage: JD extraction → save to DB[/]")

        jd_text = self._read_jd_input(file)
        if not jd_text:
            _console.print("\n[bold yellow]Goodbye![/]")
            return

        _console.print("[dim]▸ extracting…[/]")
        parsed_job, dedup = self._extract_jd(jd_text)
        if not parsed_job:
            return

        _print_job_table(parsed_job)
        _print_dedup_verdict(dedup)

        from ninurta.db import save_job

        db_res = save_job(parsed_job, jd_text)
        if db_res["status"] == "already_applied":
            _console.print(
                "[bold yellow]⚠ This job listing already exists! Flagged as ALREADY APPLIED.[/]"
            )
        else:
            _console.print(f"[bold green]✓[/] Saved to SQLite database ([dim]job id={db_res['job_id']}[/])")

    def _pipeline_resume(self, file: str) -> None:
        """Stage 'resume': parse → validate → review → save to DB."""
        # Same pipeline the `ninurta resume` command runs (reader → validator
        # → reviewer → saver) — delegate to keep one implementation.
        self.resume(file=file)

    def _pipeline_match(self, file: str, job_id: int) -> None:
        """Stage 'match': score resume vs a JD — extracted now or from DB by id."""
        _console.rule("[bold cyan]Stage: Resume vs JD — score[/]")

        if job_id > 0:
            # Score an already-saved JD from the DB (no extraction).
            from ninurta.db.models import Job
            from ninurta.db.session import SessionLocal, init_db
            from ninurta.schemas.job_description import JobDescription

            init_db()
            session = SessionLocal()
            try:
                job_row = session.query(Job).filter(Job.id == job_id).first()
            finally:
                session.close()

            if not job_row:
                _console.print(f"[bold red]No job with id={job_id} in DB.[/]")
                return

            try:
                parsed_job = JobDescription.model_validate_json(job_row.extracted_json)  # type: ignore[arg-type]
            except Exception:
                parsed_job = JobDescription(
                    company_name=job_row.company_name,
                    position_title=job_row.position_title,
                )
            _console.print(
                f"[dim]✓ loaded job from DB: [/][bold]{parsed_job.position_title} @ {parsed_job.company_name}[/]"
            )
            dedup = None
        else:
            jd_text = self._read_jd_input(file)
            if not jd_text:
                _console.print("\n[bold yellow]Goodbye![/]")
                return
            _console.print("[dim]▸ extracting…[/]")
            parsed_job, dedup = self._extract_jd(jd_text)
            if not parsed_job:
                return
            _print_job_table(parsed_job)
            _print_dedup_verdict(dedup)

        parsed_resume, resume_text = self._load_resume_or_quit()
        if not parsed_resume and not resume_text:
            return

        resume_name = (parsed_resume or {}).get("name", "resume")
        _console.print(
            f"[dim]▸ scoring ({resume_name} vs {parsed_job.position_title})…[/]"
        )
        self._score(parsed_job, parsed_resume, resume_text, job_id=job_id if job_id > 0 else None)

    def tui(self) -> None:
        """Launch the Ninurta chat TUI (Node/Ink)."""
        import subprocess
        from pathlib import Path

        tui_dir = Path(__file__).resolve().parent / "tui-node"
        index_path = tui_dir / "index.jsx"
        tsx_bin = tui_dir / "node_modules" / ".bin" / "tsx"

        if not index_path.exists():
            _console.print("[bold red]TUI not found.[/] Run `npm install` in ninurta/tui-node/ first.")
            return

        if not tsx_bin.exists():
            _console.print("[bold red]tsx not found.[/] Run `npm install` in ninurta/tui-node/ first.")
            return

        from ninurta.config import get_default_model_id
        model_id = get_default_model_id()
        cwd = os.getcwd()

        try:
            subprocess.run(
                [str(tsx_bin), str(index_path), model_id, cwd],
                check=False,
            )
        except KeyboardInterrupt:
            pass
        finally:
            print()

    def models(self, provider: str = "gemini") -> None:
        """List available models for a given provider."""
        if provider.lower() == "gemini":
            _list_gemini_models()
        else:
            _console.print(f"[bold yellow]Listing models for provider '{provider}' is not implemented yet.[/]")


def main() -> None:
    """Entry-point registered in pyproject.toml.

    Bare ``ninurta`` (no arguments) shows the welcome screen;
    any subcommand dispatches through Fire.
    """
    if len(sys.argv) == 1:
        _show_welcome()
        return
    fire.Fire(NinurtaCLI)


def _show_welcome() -> None:
    """Render the Ninurta welcome screen (simple mode) with Rich.

    Mirrors the ``ninurta tui`` header: two-tone banner, tagline,
    bow art on the side, and a summary of available commands.
    """
    import os

    from rich.columns import Columns
    from rich.panel import Panel

    from ninurta import __version__
    from ninurta.config import get_default_model_id
    from ninurta.tui.art import load_bow_art, two_tone_banner
    from ninurta.tui.palette import ACCENT, ACCENT_LIGHT, TAGLINE

    _console.print()
    _console.print(two_tone_banner())
    _console.print(f"[bold {TAGLINE}]§ Ninurta · God of War and the Hunt — Lord of the Bow[/]")
    _console.print()

    side = Panel(
        f"[{ACCENT_LIGHT}]{load_bow_art()}[/]\n\n"
        f"[{ACCENT_LIGHT}]▸ {get_default_model_id()}[/]\n"
        f"[{ACCENT_LIGHT}]▸ {os.getcwd()}[/]",
        title=f"[{ACCENT}]Ninurta[/]",
        border_style=ACCENT,
    )

    info = Panel(
        f"[bold {ACCENT}]Ninurta v{__version__}[/]\n\n"
        f"[bold {ACCENT}]▼ Pipelines[/]\n"
        f"[{ACCENT_LIGHT}]  pipeline full[/]      extract → dedup → resume → score\n"
        f"[{ACCENT_LIGHT}]  pipeline extract[/]   extract JD + save to DB\n"
        f"[{ACCENT_LIGHT}]  pipeline resume[/]    parse + save resume\n"
        f"[{ACCENT_LIGHT}]  pipeline match[/]     score resume vs JD\n\n"
        f"[bold {ACCENT}]▼ Commands[/]\n"
        f"[{ACCENT_LIGHT}]  ninurta tui[/]      interactive chat interface\n"
        f"[{ACCENT_LIGHT}]  ninurta extract[/]  parse a job description\n"
        f"[{ACCENT_LIGHT}]  ninurta resume[/]   parse + validate + save resume\n"
        f"[{ACCENT_LIGHT}]  ninurta models[/]   list available models",
        title=f"[{ACCENT}]Commands[/]",
        border_style=ACCENT,
    )

    _console.print(Columns([side, info], equal=False))
    _console.print()
    _console.print(
        "[dim]– ready[/]  [green]▪[/]  [dim]|  try [/]"
        f"[{ACCENT_LIGHT}]ninurta resume --file=resume/resume_en.docx[/]"
    )
    _console.print("[dim]Type below and press Enter — it echoes back.  `quit` / Ctrl+D to exit.[/]")
    _console.print()

    _prompt_loop()


def _prompt_loop() -> None:
    """Simple interactive prompt at the bottom of the welcome screen.

    Echoes whatever the user types (no agent connected), and exits on
    ``quit``/``exit``/``q`` or EOF (Ctrl+D).
    """
    from ninurta.tui.palette import ACCENT_LIGHT, TAGLINE

    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            _console.print("\n[dim]Goodbye![/]")
            return

        if not text:
            continue
        if text.lower() in ("quit", "exit", "q"):
            _console.print("[dim]Goodbye![/]")
            return

        _console.print(f"[bold {TAGLINE}]you:[/] {text}")
        _console.print(f"[{ACCENT_LIGHT}]ninurta:[/] You said — {text}")


if __name__ == "__main__":
    main()
