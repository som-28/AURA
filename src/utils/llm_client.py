"""Shared OpenAI-compatible client configuration for local and hosted models."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def get_llm_client() -> tuple[Any, str, str] | None:
    """Return (client, model, provider), or None when the provider is unconfigured.

    Ollama exposes an OpenAI-compatible chat completions endpoint. Its API key is
    only a placeholder; requests stay on the configured local Ollama host.
    """
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    timeout = float(os.getenv("LLM_REQUEST_TIMEOUT", "120"))

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai Python package is required for LLM providers") from exc

    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1").strip()
        model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b").strip()
        if not base_url or not model:
            raise RuntimeError("OLLAMA_BASE_URL and OLLAMA_MODEL must be set")
        client = OpenAI(
            base_url=base_url.rstrip("/"),
            api_key=os.getenv("OLLAMA_API_KEY", "ollama") or "ollama",
            timeout=timeout,
        )
        return client, model, "Ollama/Qwen"

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key or api_key == "your-openai-api-key-here":
            return None
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        return OpenAI(api_key=api_key, timeout=timeout), model, "OpenAI"

    raise RuntimeError(f"Unsupported LLM_PROVIDER: {provider}. Use 'ollama' or 'openai'.")
