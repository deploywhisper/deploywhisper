"""Settings workflow orchestration."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError

from config import settings
from llm.providers import NarrativeProviderError, generate_completion_with_settings
from models.database import SessionLocal
from models.repositories.settings import delete_setting, get_setting, upsert_setting


class ProviderSettings(BaseModel):
    provider: str = Field(..., description="Configured provider name")
    model: str = Field(..., description="Configured model")
    api_base: str = Field(..., description="Configured API base")
    api_key: str | None = Field(default=None, description="Configured API key")
    local_mode: bool = Field(
        default=False, description="Whether local-only mode is active"
    )
    source: str = Field(..., description="Where the settings came from")


class ProviderReadiness(BaseModel):
    provider: str = Field(..., description="Configured provider name")
    model: str = Field(..., description="Configured model")
    local_mode: bool = Field(
        default=False, description="Whether local-only mode is active"
    )
    ready: bool = Field(
        ..., description="Whether the provider is reachable for analysis"
    )
    requires_api_key: bool = Field(
        ..., description="Whether this provider requires an API key"
    )
    has_api_key: bool = Field(
        ..., description="Whether an API key is currently available"
    )
    message: str = Field(..., description="Human-readable readiness summary")
    source: str = Field(..., description="Where the settings came from")


PROVIDER_CATALOG: dict[str, dict[str, str | bool | None]] = {
    "ollama": {
        "label": "Ollama (Local)",
        "model": "ollama/llama3",
        "api_base": "http://localhost:11434",
        "local_mode": True,
        "requires_api_key": False,
    },
    "openai": {
        "label": "OpenAI / ChatGPT",
        "model": "gpt-4.1-mini",
        "api_base": "https://api.openai.com/v1",
        "local_mode": False,
        "requires_api_key": True,
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "model": "claude-3-5-sonnet-latest",
        "api_base": "https://api.anthropic.com",
        "local_mode": False,
        "requires_api_key": True,
    },
    "gemini": {
        "label": "Google Gemini",
        "model": "gemini/gemini-2.0-flash",
        "api_base": "https://generativelanguage.googleapis.com",
        "local_mode": False,
        "requires_api_key": True,
    },
    "openrouter": {
        "label": "OpenRouter",
        "model": "openrouter/openai/gpt-4.1-mini",
        "api_base": "https://openrouter.ai/api/v1",
        "local_mode": False,
        "requires_api_key": True,
    },
    "groq": {
        "label": "Groq",
        "model": "groq/llama-3.3-70b-versatile",
        "api_base": "https://api.groq.com/openai/v1",
        "local_mode": False,
        "requires_api_key": True,
    },
    "xai": {
        "label": "xAI Grok",
        "model": "xai/grok-2-latest",
        "api_base": "https://api.x.ai/v1",
        "local_mode": False,
        "requires_api_key": True,
    },
}

DASHBOARD_RESULT_DURATION_OPTIONS = [60, 300, 600, 900, 1800]
DEFAULT_DASHBOARD_RESULT_DURATION_SECONDS = 300
PROVIDER_ENV_API_KEYS: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openrouter": ("OPENROUTER_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "xai": ("XAI_API_KEY",),
    "ollama": (),
}


def provider_select_options() -> dict[str, str]:
    """Return provider options for UI selection."""
    return {
        provider: str(config["label"]) for provider, config in PROVIDER_CATALOG.items()
    }


def provider_defaults(provider: str) -> dict[str, str | bool | None]:
    """Return defaults for a supported provider."""
    return PROVIDER_CATALOG.get(provider, PROVIDER_CATALOG["openai"]).copy()


def _provider_env_api_key(provider: str) -> str | None:
    for env_name in PROVIDER_ENV_API_KEYS.get(provider.lower(), ()):
        value = os.getenv(env_name)
        if value:
            return value
    return os.getenv("LLM_API_KEY")


def _provider_key(provider: str, field: str) -> str:
    return f"llm_provider_config::{provider}::{field}"


def save_provider_settings(
    *,
    provider: str,
    model: str,
    api_base: str,
    api_key: str | None = None,
    local_mode: bool = False,
    activate: bool = True,
) -> ProviderSettings:
    """Persist provider settings and optionally mark them as active."""
    with SessionLocal() as session:
        upsert_setting(session, key=_provider_key(provider, "model"), value=model)
        upsert_setting(session, key=_provider_key(provider, "api_base"), value=api_base)
        upsert_setting(
            session,
            key=_provider_key(provider, "local_mode"),
            value="true" if local_mode else "false",
        )
        delete_setting(session, _provider_key(provider, "api_key"))

        if activate:
            upsert_setting(session, key="active_llm_provider", value=provider)
            upsert_setting(session, key="llm_provider", value=provider)
            upsert_setting(session, key="llm_model", value=model)
            upsert_setting(session, key="llm_api_base", value=api_base)
            upsert_setting(
                session, key="llm_local_mode", value="true" if local_mode else "false"
            )
            delete_setting(session, "llm_api_key")

    return ProviderSettings(
        provider=provider,
        model=model,
        api_base=api_base,
        api_key=api_key,
        local_mode=local_mode,
        source="database",
    )


def get_provider_settings(provider: str | None = None) -> ProviderSettings:
    """Return active provider settings or a saved config for a specific provider."""
    requested_provider = provider
    try:
        with SessionLocal() as session:
            active_provider = get_setting(session, "active_llm_provider")
            legacy_provider = get_setting(session, "llm_provider")
            selected_provider = requested_provider or (
                active_provider.value
                if active_provider
                else legacy_provider.value
                if legacy_provider
                else settings.llm_provider
            )
            model = get_setting(session, _provider_key(selected_provider, "model"))
            api_base = get_setting(
                session, _provider_key(selected_provider, "api_base")
            )
            local_mode = get_setting(
                session, _provider_key(selected_provider, "local_mode")
            )

            if model and api_base and local_mode:
                return ProviderSettings(
                    provider=selected_provider,
                    model=model.value,
                    api_base=api_base.value,
                    api_key=_provider_env_api_key(selected_provider),
                    local_mode=local_mode.value == "true",
                    source="database",
                )

            if not requested_provider:
                legacy_model = get_setting(session, "llm_model")
                legacy_api_base = get_setting(session, "llm_api_base")
                legacy_local_mode = get_setting(session, "llm_local_mode")
                if (
                    legacy_provider
                    and legacy_model
                    and legacy_api_base
                    and legacy_local_mode
                ):
                    return ProviderSettings(
                        provider=legacy_provider.value,
                        model=legacy_model.value,
                        api_base=legacy_api_base.value,
                        api_key=_provider_env_api_key(legacy_provider.value),
                        local_mode=legacy_local_mode.value == "true",
                        source="database",
                    )
    except OperationalError:
        selected_provider = requested_provider or settings.llm_provider
    else:
        selected_provider = requested_provider or selected_provider

    defaults = provider_defaults(selected_provider)
    env_api_key = _provider_env_api_key(selected_provider)
    return ProviderSettings(
        provider=selected_provider,
        model=str(
            defaults["model"]
            if requested_provider
            else settings.llm_model or defaults["model"]
        ),
        api_base=str(
            defaults["api_base"]
            if requested_provider
            else settings.llm_api_base or defaults["api_base"]
        ),
        api_key=None if requested_provider else env_api_key,
        local_mode=bool(
            defaults["local_mode"]
            if requested_provider
            else settings.llm_provider == "ollama"
        ),
        source="environment",
    )


def validate_provider_settings(
    provider_settings: ProviderSettings, completion_client=None
) -> dict:
    """Validate provider configuration using the narrative provider boundary only."""
    try:
        generate_completion_with_settings(
            messages=[
                {"role": "system", "content": "Return a JSON object."},
                {"role": "user", "content": "{}"},
            ],
            provider=provider_settings.provider,
            model=provider_settings.model,
            api_base=provider_settings.api_base,
            api_key=provider_settings.api_key,
            local_mode=provider_settings.local_mode,
            completion_client=completion_client,
        )
        return {
            "valid": True,
            "message": "Provider configuration accepted for narrative generation.",
        }
    except NarrativeProviderError as exc:
        return {"valid": False, "message": str(exc)}


def check_provider_readiness(completion_client=None) -> ProviderReadiness:
    """Return whether the active provider is ready for live LLM-assisted analysis."""
    provider_settings = get_provider_settings()
    defaults = provider_defaults(provider_settings.provider)
    requires_api_key = bool(defaults.get("requires_api_key", False))
    has_api_key = bool(provider_settings.api_key)

    if requires_api_key and not has_api_key:
        return ProviderReadiness(
            provider=provider_settings.provider,
            model=provider_settings.model,
            local_mode=provider_settings.local_mode,
            ready=False,
            requires_api_key=True,
            has_api_key=False,
            message=(
                f"{provider_settings.provider} is selected but no API key is available in environment variables. "
                "Analysis can continue with heuristic-only results."
            ),
            source=provider_settings.source,
        )

    validation = validate_provider_settings(
        provider_settings, completion_client=completion_client
    )
    if validation["valid"]:
        return ProviderReadiness(
            provider=provider_settings.provider,
            model=provider_settings.model,
            local_mode=provider_settings.local_mode,
            ready=True,
            requires_api_key=requires_api_key,
            has_api_key=has_api_key,
            message="LLM provider connection validated for analysis.",
            source=provider_settings.source,
        )

    return ProviderReadiness(
        provider=provider_settings.provider,
        model=provider_settings.model,
        local_mode=provider_settings.local_mode,
        ready=False,
        requires_api_key=requires_api_key,
        has_api_key=has_api_key,
        message=validation["message"]
        + " Analysis can continue with heuristic-only results.",
        source=provider_settings.source,
    )


def activate_local_mode(*, model: str, api_base: str) -> ProviderSettings:
    """Persist a fully local narrative provider configuration."""
    return save_provider_settings(
        provider="ollama",
        model=model,
        api_base=api_base,
        api_key=None,
        local_mode=True,
        activate=True,
    )


def deactivate_local_mode() -> ProviderSettings:
    """Remove local-only mode flag and fall back to configured/environment provider."""
    with SessionLocal() as session:
        delete_setting(session, "llm_local_mode")
    return get_provider_settings()


def resolve_provider_runtime() -> dict:
    """Resolve the current provider runtime, including persisted secrets."""
    provider_settings = get_provider_settings()
    return {
        "provider": provider_settings.provider,
        "model": provider_settings.model,
        "api_base": provider_settings.api_base,
        "local_mode": provider_settings.local_mode,
        "api_key": provider_settings.api_key,
    }


def get_dashboard_result_display_duration_seconds() -> int:
    """Return the configured dashboard result visibility duration."""
    try:
        with SessionLocal() as session:
            duration = get_setting(session, "dashboard_result_display_duration_seconds")
    except OperationalError:
        duration = None

    if duration:
        try:
            seconds = int(duration.value)
        except ValueError:
            seconds = DEFAULT_DASHBOARD_RESULT_DURATION_SECONDS
        if seconds in DASHBOARD_RESULT_DURATION_OPTIONS:
            return seconds
    return DEFAULT_DASHBOARD_RESULT_DURATION_SECONDS


def save_dashboard_result_display_duration_seconds(seconds: int) -> int:
    """Persist the dashboard result visibility duration."""
    if seconds not in DASHBOARD_RESULT_DURATION_OPTIONS:
        raise ValueError(
            "Dashboard result display duration must be one of the supported preset values."
        )
    with SessionLocal() as session:
        upsert_setting(
            session, key="dashboard_result_display_duration_seconds", value=str(seconds)
        )
    return seconds
