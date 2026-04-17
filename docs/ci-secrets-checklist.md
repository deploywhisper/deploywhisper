# CI Secrets Checklist

## Required Secrets

None for the base DeployWhisper CI pipeline.

The default pipeline installs dependencies, runs Python quality checks, and executes tests without external credentials.

## Optional Secrets

### `SLACK_WEBHOOK_URL`

Use this only if you want GitHub Actions to send a Slack message on CI failure.

- Scope: repository or environment secret
- Used by: `notify-failure` job in `.github/workflows/ci.yml`
- Rotation: follow your workspace Slack webhook rotation policy

## Secrets Hygiene

- Do not store provider API keys in GitHub Actions unless a future pipeline job truly needs live provider calls.
- Keep the base CI pipeline offline from external LLM providers.
- Prefer GitHub environment secrets over hardcoded workflow values.
- Review artifact contents before extending the pipeline with richer logs or database exports.
