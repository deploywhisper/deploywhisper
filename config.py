"""Centralized runtime configuration for DeployWhisper."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os


PROVIDER_ENV_API_KEYS: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openrouter": ("OPENROUTER_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "xai": ("XAI_API_KEY",),
    "ollama": (),
}


def provider_credential_values() -> tuple[str, ...]:
    """Return configured credentials for screening, regardless of key precedence."""
    names = {"LLM_API_KEY"} | {
        name
        for provider_names in PROVIDER_ENV_API_KEYS.values()
        for name in provider_names
    }
    return tuple(
        dict.fromkeys(value for name in sorted(names) if (value := os.getenv(name)))
    )


CONNECTOR_CREDENTIAL_ENV_NAMES = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_ACCESS_TOKEN",
    "DEPLOYWHISPER_GITHUB_APP_CLIENT_SECRET",
    "DEPLOYWHISPER_GITHUB_APP_WEBHOOK_SECRET",
    "DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY",
    "DEPLOYWHISPER_API_TOKEN",
    "DEPLOYWHISPER_SHARE_TOKEN",
    "APP_SHARE_MANAGEMENT_TOKEN",
    "DEPLOYWHISPER_OUTCOME_TOKEN",
    "APP_DEPLOYMENT_OUTCOME_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_SECRET_KEY",
    "AWS_SECURITY_TOKEN",
    "KUBERNETES_TOKEN",
    "K8S_TOKEN",
    "KUBE_TOKEN",
    "AZURE_CLIENT_SECRET",
    "AZURE_STORAGE_KEY",
    "AZURE_STORAGE_ACCOUNT_KEY",
    "AZURE_STORAGE_SAS_TOKEN",
    "GOOGLE_OAUTH_ACCESS_TOKEN",
    "CLOUDSDK_AUTH_ACCESS_TOKEN",
    "TFC_TOKEN",
    "TFE_TOKEN",
)


def connector_credential_values() -> tuple[str, ...]:
    """Collect literal connector credentials; credential-file paths remain references."""
    names = set(CONNECTOR_CREDENTIAL_ENV_NAMES) | {
        name for name in os.environ if name.startswith("TF_TOKEN_")
    }
    return tuple(
        dict.fromkeys(value for name in sorted(names) if (value := os.getenv(name)))
    )


def configured_credential_values() -> tuple[str, ...]:
    """Return credentials shared by screening boundaries, never persistent storage."""
    return tuple(
        dict.fromkeys(provider_credential_values() + connector_credential_values())
    )


def _float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        parsed = float(raw_value)
    except ValueError:
        return default
    if not math.isfinite(parsed) or parsed <= 0:
        return default
    return parsed


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "DeployWhisper")
    app_version: str = os.getenv("APP_VERSION", "1.3.0")
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8080"))
    app_base_url: str | None = os.getenv("APP_BASE_URL") or os.getenv("PUBLIC_APP_URL")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/deploywhisper.db")
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    llm_model: str = os.getenv("LLM_MODEL", "ollama/qwen2.5-coder:3b")
    llm_api_base: str = os.getenv("LLM_API_BASE", "http://localhost:11434")
    llm_request_timeout_seconds: float = _float_env("LLM_REQUEST_TIMEOUT_SECONDS", 60.0)
    narrator_enabled: bool = os.getenv("NARRATOR_ENABLED", "true").lower() == "true"
    topology_path: str = os.getenv(
        "TOPOLOGY_PATH", "data/topology/service_topology.json"
    )
    artifact_snapshot_dir: str = os.getenv(
        "ARTIFACT_SNAPSHOT_DIR", "data/report-artifacts"
    )
    share_management_token: str | None = os.getenv(
        "DEPLOYWHISPER_SHARE_TOKEN"
    ) or os.getenv("APP_SHARE_MANAGEMENT_TOKEN")
    deployment_outcome_token: str | None = os.getenv(
        "DEPLOYWHISPER_OUTCOME_TOKEN"
    ) or os.getenv("APP_DEPLOYMENT_OUTCOME_TOKEN")
    github_app_enabled: bool = (
        os.getenv("DEPLOYWHISPER_GITHUB_APP_ENABLED", "false").lower() == "true"
    )
    github_app_id: str | None = os.getenv("DEPLOYWHISPER_GITHUB_APP_ID") or None
    github_app_slug: str | None = os.getenv("DEPLOYWHISPER_GITHUB_APP_SLUG") or None
    github_app_client_id: str | None = (
        os.getenv("DEPLOYWHISPER_GITHUB_APP_CLIENT_ID") or None
    )
    github_app_client_secret: str | None = (
        os.getenv("DEPLOYWHISPER_GITHUB_APP_CLIENT_SECRET") or None
    )
    github_app_webhook_secret: str | None = (
        os.getenv("DEPLOYWHISPER_GITHUB_APP_WEBHOOK_SECRET") or None
    )
    github_app_private_key: str | None = (
        os.getenv("DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY") or None
    )
    github_app_private_key_path: str | None = (
        os.getenv("DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY_PATH") or None
    )
    skills_registry_base_url: str | None = (
        os.getenv("DEPLOYWHISPER_SKILLS_REGISTRY_URL")
        or os.getenv("APP_BASE_URL")
        or os.getenv("PUBLIC_APP_URL")
        or None
    )
    skills_local_source_dir: str | None = (
        os.getenv("DEPLOYWHISPER_SKILLS_SOURCE_DIR") or None
    )
    public_skills_registry_url: str = os.getenv(
        "DEPLOYWHISPER_PUBLIC_SKILLS_REGISTRY_URL",
        "https://deploywhisper.github.io/skills-registry/",
    )
    github_app_api_base_url: str = os.getenv(
        "DEPLOYWHISPER_GITHUB_APP_API_BASE_URL",
        "https://api.github.com",
    )
    github_app_authorize_url: str = os.getenv(
        "DEPLOYWHISPER_GITHUB_APP_AUTHORIZE_URL",
        "https://github.com/login/oauth/authorize",
    )
    github_app_access_token_url: str = os.getenv(
        "DEPLOYWHISPER_GITHUB_APP_ACCESS_TOKEN_URL",
        "https://github.com/login/oauth/access_token",
    )
    github_app_pr_events_enabled: bool = (
        os.getenv("DEPLOYWHISPER_GITHUB_APP_PR_EVENTS_ENABLED", "false").lower()
        == "true"
    )
    github_app_checks_enabled: bool = (
        os.getenv("DEPLOYWHISPER_GITHUB_APP_CHECKS_ENABLED", "true").lower() == "true"
    )
    llm_api_key: str | None = (
        os.getenv("LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
        or os.getenv("GROQ_API_KEY")
        or os.getenv("XAI_API_KEY")
    )


settings = Settings()
