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


def handle_model_list(params: dict, transport) -> dict:
    """Return all registered providers and their models, plus current selection."""
    cfg = load_config()
    llm = cfg.get("llm", {})
    providers = llm.get("providers", {})

    # Auto-populate from current provider/model if providers section is empty
    if not providers:
        current_provider = llm.get("provider", "gemini")
        current_model = llm.get("model", "gemini-3.6-flash")
        providers = {current_provider: [current_model]}

    return {
        "providers": providers,
        "current_provider": llm.get("provider", "gemini"),
        "current_model": llm.get("model", "gemini-3.6-flash"),
    }


def handle_model_set(params: dict, transport) -> dict:
    """Change the default LLM model and clear the LLM cache.

    Accepts:
      - ``provider`` + ``model`` as separate args (new interactive flow)
      - ``model_id`` in ``provider:model`` format (legacy, e.g. ``gemini:gemini-3.6-flash``)
    If only ``model`` is given without ``provider``, keeps the current provider.
    """
    provider = (params.get("provider") or "").strip()
    model = (params.get("model") or "").strip()

    # Legacy mode: model_id = "provider:model"
    model_id = (params.get("model_id") or "").strip()
    if model_id and not provider and not model:
        provider, sep, model = model_id.partition(":")
        if not sep:
            model = model_id
            provider = ""

    if not model:
        raise ValueError("model is required (e.g. provider='gemini', model='gemini-3.6-flash')")

    cfg = load_config()
    llm = cfg.setdefault("llm", {})

    if provider:
        llm["provider"] = provider
    llm["model"] = model

    save_config(cfg)
    clear_llm_cache()

    new_id = f"{llm.get('provider', 'gemini')}:{llm.get('model', '?')}"
    logger.info("model switched to %s", new_id)
    return {"status": "ok", "model": new_id}
