"""Model-related JSON-RPC handlers."""

import logging
from ninurta.config import load_config, save_config
from ninurta.llm.factory import clear_llm_cache

logger = logging.getLogger(__name__)

def handle_model_get(params: dict, transport) -> dict:
    """Return the current model ID and provider."""
    cfg = load_config()
    llm = cfg.get("llm", {})
    provider = llm.get("provider", "gemini")
    model = llm.get("model", "gemini-3.6-flash")
    return {"provider": provider, "model": model, "full": f"{provider}:{model}"}


def handle_model_set(params: dict, transport) -> dict:
    """Change the default LLM model and clear the LLM cache.

    Accepts a ``model_id`` in ``provider:model`` format (e.g. ``gemini:gemini-3.6-flash``).
    If no provider prefix is given, keeps the current provider and only updates the model name.
    """
    model_id = (params.get("model_id") or "").strip()
    if not model_id:
        raise ValueError("model_id is required (e.g. 'gemini:gemini-3.6-flash')")

    cfg = load_config()
    llm = cfg.setdefault("llm", {})

    provider, sep, model = model_id.partition(":")
    if sep:
        llm["provider"] = provider
        llm["model"] = model
    else:
        # No provider prefix → only change the model, keep current provider
        llm["model"] = model_id

    save_config(cfg)
    clear_llm_cache()

    new_id = f"{llm.get('provider', 'gemini')}:{llm.get('model', '?')}"
    logger.info("model switched to %s", new_id)
    return {"status": "ok", "model": new_id}
