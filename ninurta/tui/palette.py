"""Ninurta color palette — transparent violet theme.

Central source of truth for every color used by the TUI and the CLI
welcome screen. Change a value here and both surfaces repaint.
"""

from __future__ import annotations

# ── Violet Palette ──────────────────────────────────────────────────────────
# Transparent backgrounds let the terminal's native color & transparency show
BG = "transparent"
PANEL = "transparent"

# Violet family accents with shades
ACCENT = "#8b5cf6"          # Violet-500 — primary
ACCENT_DEEP = "#7c3aed"     # Violet-600 — deeper
ACCENT_LIGHT = "#a78bfa"    # Violet-400 — lighter / ametrine
TAGLINE = "#c4b5fd"         # Violet-300 — title / tagline
TEXT = "#ede9fe"            # Violet-100 — body / input text
MUTED = "#a78bfa"           # Violet-400 — dim / secondary

SCROLLBAR_HOVER = "#c4b5fd"

# Rich markup tokens (used by the CLI welcome screen)
PANEL_CLI = "#1e0b24"       # Deep violet background for terminal panels
BANNER_TOP = ACCENT_LIGHT
BANNER_BOTTOM = ACCENT_DEEP
