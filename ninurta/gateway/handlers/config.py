"""Config-related JSON-RPC handlers."""

from typing import Any
from ninurta.config import load_config, save_config

def _mask_key(value: Any) -> Any:
    """Mask API keys so they never leak over the RPC wire."""
    if isinstance(value, str) and value:
        return f"{value[:4]}…{value[-4:]}"
    return value

def handle_config_get(params: dict, transport) -> dict:
    """Inspect configuration — API keys masked."""
    cfg = load_config()
    safe: dict[str, Any] = {}
    llm = cfg.get("llm", {})
    if isinstance(llm, dict):
        safe["llm"] = {
            k: (_mask_key(v) if "key" in k.lower() else v)
            for k, v in llm.items()
        }
    return {"config": safe}


def handle_config_set(params: dict, transport) -> dict:
    """Update non-secret config keys (keys are never settable over RPC)."""
    patch = params.get("config") or {}
    cfg = load_config()
    llm = cfg.setdefault("llm", {})
    if isinstance(patch, dict) and isinstance(llm, dict):
        for k, v in patch.items():
            if "key" in k.lower():
                continue  # never allow API keys over the wire
            llm[k] = v

    save_config(cfg)
    return {"status": "ok"}
