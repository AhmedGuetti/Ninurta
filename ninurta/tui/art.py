"""Shared Ninurta ASCII art — banner + bow, used by both the TUI and CLI."""

from __future__ import annotations

from pathlib import Path

from rich.markup import escape

from ninurta.tui.palette import BANNER_BOTTOM, BANNER_TOP

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
_BANNER_PATH = _ASSETS / "ninurta_banner.txt"
_BOW_PATH = _ASSETS / "bow_art.txt"


def load_banner() -> str:
    """Return the NINURTA pyfiglet banner, or a plain fallback."""
    try:
        return _BANNER_PATH.read_text(encoding="utf-8")
    except OSError:
        return "NINURTA"


def load_bow_art() -> str:
    """Return the bow dot/dash art, or an empty string if missing."""
    try:
        return _BOW_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def two_tone_banner(banner: str | None = None) -> str:
    """Split the banner into yellow (top) and orange (bottom) halves.

    Mirrors the HERMES-AGENT banner: top half yellow, bottom half
    orange/salmon with a drop-shadow feel.

    Lines are markup-escaped first: the pyfiglet ``big`` font contains
    backslashes (e.g. ``\\_|_____|_|``) that would otherwise be treated as
    Rich markup escape characters and swallow the following character —
    including the closing ``[/]`` tag.
    """
    lines = (banner if banner is not None else load_banner()).splitlines()
    if not lines:
        return ""
    mid = max(1, len(lines) // 2)
    out = []
    for i, ln in enumerate(lines):
        if not ln.strip():
            out.append("")
        elif i < mid:
            out.append(f"[bold {BANNER_TOP}]{escape(ln)}[/]")
        else:
            out.append(f"[bold {BANNER_BOTTOM}]{escape(ln)}[/]")
    return "\n".join(out)
