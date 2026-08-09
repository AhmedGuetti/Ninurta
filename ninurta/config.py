"""Configuration management for Ninurta."""

from __future__ import annotations

import os
from pathlib import Path
import yaml

DEFAULT_CONFIG_FILENAME = "config.yaml"

DEFAULT_CONFIG = {
    "llm": {
        "provider": "gemini",
        "model": "gemini-3.6-flash",
        "gemini_api_key": None,
    }
}


def get_config_path() -> Path:
    """Return path to local config.yaml."""
    return Path(DEFAULT_CONFIG_FILENAME)


def load_config() -> dict:
    """Load configuration from config.yaml, creating a default one if it doesn't exist."""
    path = get_config_path()
    if not path.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if isinstance(data, dict):
                # Ensure existing configs get updated with any missing keys
                # like gemini_api_key without completely overriding user modifications
                if "llm" in data and isinstance(data["llm"], dict):
                    if "gemini_api_key" not in data["llm"]:
                        data["llm"]["gemini_api_key"] = None
                        save_config(data)
                return data
    except Exception:
        pass
    return DEFAULT_CONFIG


def save_config(config: dict) -> None:
    """Save configuration dictionary to config.yaml."""
    path = get_config_path()
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False)


def get_default_model_id() -> str:
    """Get the default model ID string from config or fallback."""
    cfg = load_config()
    llm_cfg = cfg.get("llm", {})
    provider = llm_cfg.get("provider", "gemini")
    model = llm_cfg.get("model", "gemini-3.6-flash")
    if provider and model:
        if ":" in model:
            return model
        return f"{provider}:{model}"
    return "gemini:gemini-3.6-flash"


def get_gemini_api_key() -> str | None:
    """Get the Gemini API key from environment variables or configuration file."""
    # Check env vars first
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        return key
    # Fallback to config
    cfg = load_config()
    return cfg.get("llm", {}).get("gemini_api_key")
