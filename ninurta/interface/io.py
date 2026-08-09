"""Interface I/O helpers — stdin reader and CSV writer."""

from __future__ import annotations

import csv
import select
import sys
from pathlib import Path

from rich.console import Console

_console = Console()


# ---------------------------------------------------------------------------
# Stdin reader
# ---------------------------------------------------------------------------

def _more_input_pending(timeout: float = 0.1) -> bool:
    """True if stdin already has buffered input beyond what we've consumed.

    Used to tell "user pressed Enter twice to submit" apart from "the pasted
    JD itself contains two blank lines in a row".  A clipboard paste arrives
    as one burst, so when we hit the double-blank sentinel and *more data is
    already queued*, that data is the rest of the same paste — not a submit.
    """
    try:
        readable, _, _ = select.select([sys.stdin], [], [], timeout)
        return bool(readable)
    except (OSError, ValueError):
        # select unavailable for this stream (e.g. Windows pipes) —
        # conservatively treat the double-blank as a submit (old behavior).
        return False


def read_stdin_until_double_enter(prompt: str = "") -> str | None:
    """Read lines from stdin until the user presses Enter twice in a row.

    Returns the accumulated text stripped of surrounding whitespace,
    or None when the user submits with nothing (just two blank lines).

    Terminal protocol
    -----------------
    - Paste (or type) the job description.
    - Press Enter on a blank line to submit (second blank line = go).
    - Two blank lines on an empty buffer = quit signal → returns None.

    Blank lines *inside* a pasted JD are preserved: the double-blank sentinel
    only fires when no further input is already buffered, so a JD containing
    paragraph gaps is not split into multiple submissions.
    """
    if prompt:
        _console.print(prompt)

    lines: list[str] = []
    consecutive_blanks = 0

    try:
        while True:
            # sys.stdin.readline() is safer than input() after Rich Live/Progress
            raw = sys.stdin.readline()

            if raw == "":
                # True EOF (Ctrl-D or piped stream exhausted) — stop reading
                break

            line = raw.rstrip("\n").rstrip("\r")

            if line == "":
                consecutive_blanks += 1
                if consecutive_blanks >= 2:
                    # Double blank line — but only submit if the rest of the
                    # paste (if any) has already arrived.  If more data is
                    # buffered, these blanks are part of the JD text.
                    if not _more_input_pending():
                        break       # genuine double Enter = submit / quit
                    # Blanks were inside the paste: keep them as content.
                    lines.append(line)
                    consecutive_blanks = 0
                elif lines:
                    lines.append(line)
            else:
                consecutive_blanks = 0
                lines.append(line)

    except KeyboardInterrupt:
        _console.print("\n[dim]Cancelled.[/dim]")
        return None

    # Strip trailing blank lines that were part of the sentinel
    while lines and lines[-1] == "":
        lines.pop()

    text = "\n".join(lines).strip()
    return text if text else None


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

def append_csv_row(path: Path, row: dict[str, str]) -> None:
    """Append *row* to the CSV at *path*, writing headers if the file is new."""
    path = Path(path)
    write_header = not path.exists() or path.stat().st_size == 0

    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)
