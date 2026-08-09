"""ninurta.tools — agent tool registry with auto-discovery.

Drop a new .py file in tools/builtins/ with @tool-decorated functions
and they auto-register — no imports needed anywhere else.
"""

from __future__ import annotations

import importlib
import pkgutil

from ninurta.tools.registry import ToolRegistry, registry, tool

_loaded = False


def load_tools(package: str = "ninurta.tools.builtins") -> ToolRegistry:
    """Import every module under *package* so their @tool decorators fire.

    Drop a new .py in tools/builtins/ and its tools auto-register — no edits
    anywhere else. Idempotent.
    """
    global _loaded
    if not _loaded:
        pkg = importlib.import_module(package)
        for mod in pkgutil.iter_modules(pkg.__path__):
            if not mod.name.startswith("_"):
                importlib.import_module(f"{package}.{mod.name}")
        _loaded = True
    return registry


# Auto-load built-in tools on package import
load_tools()

__all__ = ["registry", "tool", "load_tools", "ToolRegistry"]
