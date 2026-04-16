"""Centralized runtime configuration for DeployWhisper."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "DeployWhisper")
    app_version: str = os.getenv("APP_VERSION", "0.1.0")
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8080"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/deploywhisper.db")
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    llm_model: str = os.getenv("LLM_MODEL", "ollama/llama3")
    llm_api_base: str = os.getenv("LLM_API_BASE", "http://localhost:11434")
    topology_path: str = os.getenv("TOPOLOGY_PATH", "data/topology/service_topology.json")
    llm_api_key: str | None = (
        os.getenv("LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
    )


settings = Settings()
