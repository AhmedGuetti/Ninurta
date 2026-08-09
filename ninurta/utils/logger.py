"""Ninurta logger — simple Rich-based logging with configurable levels.

Usage
-----
    from ninurta.utils.logger import get_logger, configure_logging

    configure_logging("DEBUG")   # call once at CLI entry-point
    log = get_logger(__name__)   # per-module logger

    log.debug("thinking block: %s", thinking_text)
    log.info("Extraction complete")
    log.warning("No JSON found")
    log.error("Model failed: %s", err)
"""

from __future__ import annotations

import logging

from rich.console import Console
from rich.logging import RichHandler

_console = Console(stderr=True)
_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Set the root Ninurta logger level.  Call once from the CLI entry-point."""
    global _configured  # noqa: PLW0603

    root = logging.getLogger("ninurta")

    if not _configured:
        handler = RichHandler(
            console=_console,
            show_path=False,
            rich_tracebacks=True,
            markup=True,
            log_time_format="[%H:%M:%S]",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)
        root.propagate = False
        _configured = True

    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``ninurta`` namespace.

    If *name* already starts with ``ninurta.`` it is used as-is;
    otherwise ``ninurta.`` is prepended.
    """
    if not name.startswith("ninurta."):
        name = f"ninurta.{name}"
    return logging.getLogger(name)
