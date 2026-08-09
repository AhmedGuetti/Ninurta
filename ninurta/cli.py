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
                # Invoke the LangGraph workflow
                result = graph.invoke({"jd_text": jd_text, "parsed_job": None, "test_tool_result": None, "error": None})
                
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
            result = resume_graph.invoke(
                {
                    "resume_text": resume_text,
                    "parsed_resume": None,
                    "error": None,
                }
            )

            if result.get("error"):
                _console.print(f"[bold red]Resume pipeline error:[/] {result['error']}")
                return

            _console.print("\n[bold green]✓[/] Resume pipeline complete.")
        except Exception as exc:
            _console.print(f"[bold red]Pipeline error:[/] {exc}")

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
        f"[{ACCENT_LIGHT}]  extract[/] → extractor\n"
        f"[{ACCENT_LIGHT}]  resume[/]  → reader · validator · reviewer · saver\n\n"
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
