"""JSON-RPC method handlers for the Ninurta TUI gateway.

This module exposes `get_dispatch_map` to provide the routing table for 
the gateway transport. Handlers logic resides in ``ninurta/gateway/handlers/``.
"""

from __future__ import annotations
import logging

from ninurta.gateway.handlers import (
    handle_session_send,
    handle_pipeline_cancel,
    handle_db_inspect,
    handle_model_get,
    handle_model_set,
    handle_config_get,
    handle_config_set,
)

# Ensure prompts are registered before the gateway tries to use them.
import ninurta.prompts.job_extractor  # noqa: F401 — registers @prompt("job_extractor")
import ninurta.prompts.matcher       # noqa: F401 — registers @prompt("matcher")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dispatch map
# ---------------------------------------------------------------------------

def get_dispatch_map() -> dict:
    """Route RPC method names to handlers."""
    return {
        "session.send": handle_session_send,
        "pipeline.cancel": handle_pipeline_cancel,
        "db.inspect": handle_db_inspect,
        "model.get": handle_model_get,
        "model.set": handle_model_set,
        "config.get": handle_config_get,
        "config.set": handle_config_set,
    }
