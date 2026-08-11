"""Shared utilities for the Ninurta TUI gateway."""

import logging

logger = logging.getLogger(__name__)

# EUR/USD rate (fixed reference)
_USD_TO_EUR = 0.926


def _format_cost_table(
    model_id: str,
    input_tok: int,
    output_tok: int,
    thinking_tok: int,
    cost_usd: float,
) -> str:
    """Build a unicode box-drawing cost table as a plain string."""
    cost_eur = cost_usd * _USD_TO_EUR
    rows = [
        ("Model",          model_id),
        ("Input tokens",   f"{input_tok:,}"),
        ("Output tokens",  f"{output_tok:,}"),
    ]
    if thinking_tok:
        rows.append(("Thinking tokens", f"{thinking_tok:,}"))
    rows += [
        ("Cost (USD)",     f"${cost_usd:.5f}"),
        ("Cost (EUR)",     f"\u20ac{cost_eur:.5f}"),
    ]
    col1_w = max(len(r[0]) for r in rows) + 2
    col2_w = max(len(r[1]) for r in rows) + 2
    total_w = col1_w + col2_w + 3
    title = " Run Cost Summary "
    top_pad = max(0, total_w - 2 - len(title))
    lines = ["\u250c" + title + "\u2500" * top_pad + "\u2510"]
    lines.append("\u251c" + "\u2500" * col1_w + "\u252c" + "\u2500" * col2_w + "\u2524")
    for label, value in rows:
        l = f" {label} ".ljust(col1_w)
        v = f" {value} ".ljust(col2_w)
        lines.append(f"\u2502{l}\u2502{v}\u2502")
    lines.append("\u2514" + "\u2500" * col1_w + "\u2534" + "\u2500" * col2_w + "\u2518")
    return "\n".join(lines)
