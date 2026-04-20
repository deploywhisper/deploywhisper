# CI Pipeline

DeployWhisper uses GitHub Actions at [.github/workflows/ci.yml](/Users/psaho01/ai-deploy-whisper/.github/workflows/ci.yml).

## Stages

- `quality`: installs dependencies, runs `pip check`, and bytecode-compiles project modules.
- `security`: runs dependency audit, Bandit static analysis, and secret-pattern scanning.
- `changed-tests`: on pull requests, runs only changed Python test modules for faster early feedback.
- `test`: runs the full unittest suite in four logical shards with `fail-fast: false`.
- `report`: publishes a GitHub Actions summary and downloads any failure artifacts.
- `notify-failure`: optional Slack notification when `SLACK_WEBHOOK_URL` is configured.

Backend burn-in is intentionally skipped by default. The current repo uses a deterministic Python `unittest` stack rather than a UI-heavy flaky E2E surface.

## Local Parity

Run the local CI-equivalent checks with:

```bash
bash scripts/ci-local.sh
```

For full local parity with the CI security lane, make sure `bandit` is installed in the active environment or available via `BANDIT_BIN`. When available, `scripts/ci-local.sh` runs the same two-pass Bandit gate used in CI.

To run only changed tests relative to the default base branch:

```bash
bash scripts/test-changed.sh
```

Override the base ref if needed:

```bash
BASE_REF=origin/develop bash scripts/test-changed.sh
```

To mirror one CI shard locally:

```bash
PYTHON_BIN=./.venv/bin/python bash scripts/run-test-targets.sh tests/test_api tests/test_cli tests/test_infra
```

## Failure Artifacts

On failure, the pipeline uploads:

- `quality-logs`
- `changed-tests-log`
- `shard-log-*`

These logs are retained for 14 days.

## Quality Gates

- Dependency graph must pass `pip check`
- Security scan must pass dependency audit, Bandit high/high gate, and secret-leak checks
- Source tree must compile with `python -m compileall`
- Every shard must pass its assigned `unittest` targets
- Pull requests get a changed-test fast-feedback run

## Notes

- Python version is pinned to `3.11` to match the Docker runtime.
- No CI secrets are required for the base pipeline.
- Slack notifications are optional and only activate when `SLACK_WEBHOOK_URL` is present.
