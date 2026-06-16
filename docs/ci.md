# CI Pipeline

DeployWhisper uses GitHub Actions at [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

## Stages

- `quality`: installs dependencies, runs `pip check`, and bytecode-compiles project modules.
- `security`: runs dependency audit, Bandit static analysis, and secret-pattern scanning.
- `frontend`: installs the React SPA workspace, then runs typecheck, Vitest, and the production build.
- `changed-tests`: on pull requests, runs only changed Python test modules for faster early feedback.
- `test`: runs the full unittest suite in four logical shards with `fail-fast: false`.
- `report`: publishes a GitHub Actions summary and downloads any failure artifacts.
- `notify-failure`: optional Slack notification when `SLACK_WEBHOOK_URL` is configured.

Backend burn-in is intentionally skipped by default. The current repo uses a deterministic Python `unittest` stack plus a React frontend job for typecheck, Vitest, and production build.

Accessibility-focused UI verification now lives in the SPA Playwright lane. It is available through the root `test:ui-review` script and through the composed-container F0 loop required for UI PRs.

## Local Parity

Run the local CI-equivalent checks with:

```bash
bash scripts/ci-local.sh
```

To append the SPA browser/a11y checks locally:

```bash
npm install --prefix frontend
RUN_UI_A11Y=1 bash scripts/ci-local.sh
```

This runs `npm run test:ui-review`, which delegates to the `frontend/e2e/` Playwright suite.

For the React SPA migration workspace, run:

```bash
npm run ui:typecheck
npm run ui:test
npm run ui:build
```

The Phase 0 API schema is generated from the compose-run backend:

```bash
docker compose up -d
npm run ui:gen-api
```

`frontend/scripts/gen-api.sh` reads `http://localhost:8080/api/v1/openapi.json` and commits the resulting `frontend/src/api/schema.d.ts`.

Backend-for-ui changes must also run the compose verification loop before PR:

```bash
docker compose up -d --build
curl -fsSL http://localhost:8080/api/v1/health
curl -fsSL http://localhost:8080/api/v1/stats/summary
curl -fsSL "http://localhost:8080/api/v1/stats/verdict-distribution?days=30"
curl -fsSL http://localhost:8080/api/v1/projects
```

Record the response shapes in the PR body, then run `docker compose down`.

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
- React SPA typecheck, Vitest, and build must pass in the `frontend` job
- Pull requests get a changed-test fast-feedback run
- UI-facing stories must record browser-side Playwright validation before moving to review. Use `npm run test:ui-review` for the SPA e2e/a11y lane or `RUN_UI_A11Y=1 bash scripts/ci-local.sh` for the full local lane. If no UI surface is touched, record `UI validation not applicable` in the story Dev Agent Record.

## Notes

- Python version is pinned to `3.11` to match the Docker runtime.
- No CI secrets are required for the base pipeline.
- Slack notifications are optional and only activate when `SLACK_WEBHOOK_URL` is present.
