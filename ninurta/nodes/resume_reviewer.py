"""Resume reviewer node — let the user correct/add fields in the parsed resume dict.

Runs AFTER the LLM validator so the user reviews the validated dict and has
the final say.  Accepts either a JSON object (deep-merged over the dict) or
``key: value`` lines (dotted keys supported, e.g. ``contact.email: foo@bar.com``).
"""

from __future__ import annotations

import json

from rich.console import Console

from ninurta.interface.io import read_stdin_until_double_enter
from ninurta.state import State
from ninurta.utils.logger import get_logger

log = get_logger(__name__)
_console = Console()


def _deep_merge(base: dict, override: dict) -> None:
    """Merge *override* into *base* in place (nested dicts merged, lists replaced)."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _set_nested(data: dict, dotted_key: str, value: str) -> None:
    """Set ``contact.email`` style dotted keys on *data*."""
    parts = dotted_key.split(".")
    target = data
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def _review_and_correct(parsed: dict) -> dict:
    """Show the dict and let the user override/add fields interactively.

    Accepts either:
      * a JSON object   → merged over the parsed dict (adds/overrides keys)
      * ``key: value`` lines → e.g. ``contact.email: foo@bar.com``
    Pressing Enter twice with no input accepts the dict as-is.
    """
    _console.print("\n[bold cyan]── Parsed resume (review & correct) ──[/]")
    _console.print(json.dumps(parsed, indent=2, ensure_ascii=False))

    _console.print(
        "\n[dim]Press Enter twice to accept, or paste corrections:[/]\n"
        "[dim]  • JSON object      →  merged over the parsed dict[/]\n"
        "[dim]  • key: value lines →  e.g.  [bold]contact.email: foo@bar.com[/][/]\n"
    )

    raw = read_stdin_until_double_enter(
        prompt="[bold cyan]Corrections (or Enter×2 to accept) ↓[/]"
    )
    if not raw:
        _console.print("[dim]No corrections — using validated dict as-is.[/]")
        return parsed

    raw = raw.strip()
    try:
        if raw.startswith("{"):
            override = json.loads(raw)
            if not isinstance(override, dict):
                raise ValueError("JSON must be an object")
            _deep_merge(parsed, override)
        else:
            for line in raw.splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    _set_nested(parsed, key.strip(), value.strip())
        _console.print("[bold green]✓[/] Corrections applied.")
    except Exception as exc:  # noqa: BLE001 — user input is best-effort
        _console.print(
            f"[bold yellow]Could not apply corrections ({exc}) — "
            "using validated dict as-is.[/]"
        )
    return parsed


def resume_reviewer_node(state: State) -> dict:
    """Second resume node: interactive user review/correction of the dict."""
    parsed = state.get("parsed_resume")
    if not parsed:
        return {"error": "No parsed resume in state."}

    corrected = _review_and_correct(parsed)
    return {"parsed_resume": corrected, "error": None}
