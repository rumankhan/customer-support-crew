"""Resolve LLM provider (OpenAI default or Ollama Cloud) for the Application Crew."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)

Provider = Literal["openai", "ollama"]

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_MODEL = "gemma4:31b"
DEFAULT_OLLAMA_BASE_URL = "https://ollama.com/v1"


def _has(name: str) -> bool:
    value = os.getenv(name)
    return bool(value and value.strip())


def _strip(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


@dataclass(frozen=True)
class LlmSettings:
    provider: Provider
    model: str
    api_key: str
    base_url: Optional[str] = None


def resolve_llm_provider() -> Optional[Provider]:
    """Pick provider from LLM_PROVIDER or available keys.

    When both OpenAI and Ollama keys exist, default remains OpenAI unless
    LLM_PROVIDER=ollama is set explicitly.
    """
    explicit = (_strip("LLM_PROVIDER") or "").lower()
    if explicit in {"openai", "ollama"}:
        return explicit  # type: ignore[return-value]
    if explicit:
        logger.warning("Unknown LLM_PROVIDER=%s; falling back to key detection", explicit)

    has_openai = _has("OPENAI_API_KEY")
    has_ollama = _has("OLLAMA_API_KEY")

    if has_openai:
        return "openai"
    if has_ollama:
        return "ollama"
    return None


def resolve_llm_settings() -> Optional[LlmSettings]:
    provider = resolve_llm_provider()
    if provider is None:
        return None

    if provider == "ollama":
        api_key = _strip("OLLAMA_API_KEY")
        if not api_key:
            return None
        model = (
            _strip("OLLAMA_MODEL")
            or _strip("MODEL_NAME")
            or DEFAULT_OLLAMA_MODEL
        )
        base_url = _strip("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL
        return LlmSettings(
            provider="ollama",
            model=model,
            api_key=api_key,
            base_url=base_url.rstrip("/"),
        )

    api_key = _strip("OPENAI_API_KEY")
    if not api_key:
        return None
    model = (
        _strip("MODEL_NAME")
        or _strip("OPENAI_MODEL")
        or DEFAULT_OPENAI_MODEL
    )
    base_url = _strip("OPENAI_BASE_URL") or _strip("OPENAI_API_BASE")
    return LlmSettings(
        provider="openai",
        model=model,
        api_key=api_key,
        base_url=base_url.rstrip("/") if base_url else None,
    )


def build_crew_llm() -> Any:
    """Construct a CrewAI LLM for the resolved provider."""
    from crewai import LLM

    settings = resolve_llm_settings()
    if settings is None:
        raise RuntimeError(
            "No LLM configured. Set OPENAI_API_KEY "
            "or OLLAMA_API_KEY (+ optional LLM_PROVIDER=ollama)."
        )

    if settings.provider == "ollama":
        # LiteLLM OpenAI-compatible route for custom hosts (Ollama Cloud).
        litellm_model = settings.model
        if "/" not in litellm_model:
            litellm_model = f"openai/{litellm_model}"
        logger.info(
            "LLM provider=ollama model=%s base_url=%s",
            settings.model,
            settings.base_url,
        )
        return LLM(
            model=litellm_model,
            api_key=settings.api_key,
            base_url=settings.base_url,
        )

    kwargs: dict[str, Any] = {
        "model": settings.model,
        "api_key": settings.api_key,
    }
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    logger.info("LLM provider=openai model=%s", settings.model)
    return LLM(**kwargs)
