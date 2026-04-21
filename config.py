"""Centralized runtime configuration for DeployWhisper."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "DeployWhisper")
    app_version: str = os.getenv("APP_VERSION", "1.0.0")
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8080"))
    app_base_url: str | None = os.getenv("APP_BASE_URL") or os.getenv("PUBLIC_APP_URL")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/deploywhisper.db")
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    llm_model: str = os.getenv("LLM_MODEL", "ollama/llama3")
    llm_api_base: str = os.getenv("LLM_API_BASE", "http://localhost:11434")
    narrator_enabled: bool = os.getenv("NARRATOR_ENABLED", "true").lower() == "true"
    topology_path: str = os.getenv(
        "TOPOLOGY_PATH", "data/topology/service_topology.json"
    )
    artifact_snapshot_dir: str = os.getenv(
        "ARTIFACT_SNAPSHOT_DIR", "data/report-artifacts"
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
