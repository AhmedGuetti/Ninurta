"""Resume saver node — persist the (validated + reviewed) resume dict to the DB.

The parsed dict is stored as JSON in ``Resume.parsed_json``.  The schema is
deliberately flexible: sections may be strings, lists, or dicts (e.g. the
LLM-categorized skills), so any shape round-trips losslessly and later reads
just ``json.loads`` it back.
"""

from __future__ import annotations

from rich.console import Console

from ninurta.state import State
from ninurta.utils.logger import get_logger

log = get_logger(__name__)
_console = Console()


def resume_saver_node(state: State) -> dict:
    """Persist the parsed resume to the resumes table (upsert by name)."""
    parsed = state.get("parsed_resume")
    resume_text = state.get("resume_text", "")
    if not parsed:
        return {"error": "No parsed resume in state."}

    try:
        from ninurta.db.operations import save_resume  # noqa: PLC0415

        result = save_resume(parsed, resume_text)
        status = result["status"]
        if status == "created":
            _console.print(
                f"[bold green]✓[/] Resume saved to database "
                f"([dim]new record #{result['resume_id']}[/])"
            )
        else:
            _console.print(
                f"[bold green]✓[/] Resume updated in database "
                f"([dim]record #{result['resume_id']}[/])"
            )
        log.info("Resume %s in DB (id=%s)", status, result["resume_id"])
        return {"error": None}

    except Exception as exc:
        # Never fail the pipeline on DB issues — the export still proceeds
        log.error("Failed to save resume to DB: %s", exc)
        _console.print(
            f"[bold yellow]⚠ Could not save resume to database ({exc}) — "
            "continuing without persistence.[/]"
        )
        return {"error": None}
