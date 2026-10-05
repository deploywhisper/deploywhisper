# Provider settings administration

Open `/settings` to select a narrative provider, model, API base and timeout.
DeployWhisper validates profile structure through its own `llm/providers.py`
adapter boundary before persisting the non-secret profile. Invalid saves return
`400 invalid_provider_settings` and leave the active profile unchanged. A valid
profile is saved even when the subsequent connectivity probe fails, allowing
operators to configure an offline provider without losing deterministic analysis.

## Credentials

Set credentials in the running process or container environment: `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `GEMINI_API_KEY` (or `GOOGLE_API_KEY`), `OPENROUTER_API_KEY`,
`GROQ_API_KEY`, or `XAI_API_KEY`. `LLM_API_KEY` is the generic fallback. Provider
specific keys take precedence. Restart the process/container after changing its
environment. Database profiles never retain API keys. Entering a key in Settings
uses it only for the immediate validation request; subsequent analysis resolves
credentials from the environment again. Existing legacy key rows for the saved
profile and active settings are removed when saving.

Keep credentials out of models and URLs. API bases must be absolute HTTP/HTTPS
URLs without userinfo, query parameters or fragments. Recognized credentials and the supplied/environment key are also rejected
in URL paths and model names, including percent-encoded representations.
Whitespace and control characters in API bases are rejected. Do not put any secrets in these fields. The settings API returns a masked key presence hint.

## Fully local operation and degraded output

Select Ollama and enable **Local-only mode**. Use an Ollama endpoint controlled
by your organization (for Compose on macOS, the configured host endpoint is
`http://host.docker.internal:11434`). Local-only mode rejects hosted providers
before provider invocation. Selecting Ollama is not a network firewall: the
operator is responsible for the endpoint and network boundary. Disable narration
with `NARRATOR_ENABLED=false` when deterministic-only operation is desired.

Missing credentials, unsupported legacy configuration, unavailable models and
provider failures preserve deterministic findings and the advisory verdict. Reports
persist `narrative_degraded`, `narrative_failure_notice` and provider/model/local-mode
metadata. Config-derived health checks validate profile structure without network
access; live validation and analysis may contact the explicitly selected provider.
Raw uploaded artifacts remain local; only sanitized structured summaries reach
narrative providers. See [secrets and artifact boundaries](secrets-and-artifact-boundaries.md).
