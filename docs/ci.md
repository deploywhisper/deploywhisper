# CI Pipeline

DeployWhisper uses GitHub Actions at [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

Repository supply-chain scans run separately through the
[Scorecard and CodeQL workflows](security/supply-chain-scanning.md). The guide
documents result visibility, PR-local versus default-branch coverage and the
required high-priority finding dispositions.

## Stages

- `quality`: installs dependencies, runs `pip check`, and bytecode-compiles project modules.
- `security`: runs dependency audit, Bandit static analysis, and secret-pattern scanning.
- `frontend`: installs the React SPA workspace, then runs typecheck, Vitest, and the production build.
- `changed-tests`: on pull requests, runs only changed Python test modules for faster early feedback.
- `test`: runs the Python suite with pytest in four logical shards with `fail-fast: false`.
- The blocking `tests/test_llm` shard includes the prompt-injection regression
  suite documented in
  [`docs/ai-safety/prompt-injection-testing.md`](./ai-safety/prompt-injection-testing.md).
- `report`: publishes a GitHub Actions summary and downloads any failure artifacts.
- `notify-failure`: optional Slack notification when `SLACK_WEBHOOK_URL` is configured.

Backend burn-in is intentionally skipped by default. Tests remain written in
the standard-library `unittest` style, while GitHub executes them through
pytest for discovery, coverage, and sharding. The React frontend job covers
typecheck, Vitest, and the production build.

Accessibility-focused UI verification now lives in the SPA Playwright lane. It is available through the root `test:ui-review` script and through the composed-container F0 loop required for UI PRs.

## Local Parity

Run the local CI-equivalent checks with:

```bash
bash scripts/ci-local.sh
```

The local script runs each `tests/test_*` directory explicitly. A root
`python -m unittest discover` command is only a smoke check because unittest
does not recurse into non-package directories such as `tests/test_cli`.
It also runs the prompt-injection suite as an early safety gate before the
broader targets.

To append the SPA browser/a11y checks locally:

```bash
npm install --prefix frontend
docker compose up -d --build
BASE_URL=http://localhost:8080 RUN_UI_A11Y=1 bash scripts/ci-local.sh
```

This runs `npm run test:ui-review`, which delegates to the `frontend/e2e/` Playwright suite. UI browser validation must use the composed app at `http://localhost:8080/`; do not run E2E, a11y, keyboard, or screenshot checks through `npm run ui:dev` or legacy prefixed SPA routes.

For the React SPA migration workspace, run:

```bash
npm run ui:typecheck
npm run ui:test
npm run ui:build
```

These commands cover static frontend quality only. They do not replace the compose browser loop for UI-facing work.

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

UI-facing changes must run the browser loop from the same composed instance:

```bash
BASE_URL=http://localhost:8080 npm run test:ui-review
```

Use root SPA routes under `http://localhost:8080/`, for example `/`, `/history`, `/settings`, `/skills`, `/incidents`, and `/reports/{id}`.

Provider administration browser checks use rejected saves and unsaved UI
interactions by default, preserving active and inactive profiles and environment
provenance. Successful-save coverage requires an explicit opt-in:

```bash
BASE_URL=http://localhost:8080 PROVIDER_ADMIN_TEST_MUTATION=1 npm run test:ui-review -- provider-administration.spec.ts
```

Run this command only against a disposable Compose app and database. The opted-in
test changes the active provider and its OpenAI profile and intentionally leaves
those changes in the disposable database. Recreating the container alone does
not isolate a persistent database; use a separate disposable data volume or bind
mount and remove it after verification. Validation uses a closed localhost port
and a synthetic transient key, so it never sends traffic to a hosted provider.
The checks cover successful saves, transient-key validation, and environment
credential re-resolution. Run once with no OpenAI environment key (clear both
`OPENAI_API_KEY` and generic `LLM_API_KEY`) to cover the missing-key warning,
then with a synthetic environment key to cover environment credential recovery.

Connector credential browser coverage also requires an explicit disposable-storage
opt-in because it creates project, topology, incident, scanner, and report records:

```bash
BASE_URL=http://localhost:8080 CONNECTOR_SECURITY_TEST_DISPOSABLE=1 npm run test:ui-review -- connector-security.spec.ts
```

Use a separate disposable Compose data volume or a tmpfs mount for `/app/data`,
then remove that storage after verification. Do not set this flag against an
operator database. The test is skipped without it. It checks scanner identities
and redaction in the import API, plus a matching incident in the persisted report
API and rendered report. Imported scanner findings are standalone context and
are not automatically attached to analysis reports.

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
./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short
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
- Every pytest shard must pass its assigned targets
- Prompt-injection boundary tests must pass in local CI, the CI LLM shard, and
  the explicit release gate
- React SPA typecheck, Vitest, and build must pass in the `frontend` job
- Pull requests get a changed-test fast-feedback run
- UI-facing stories must record browser-side Playwright validation before moving to review. Use `docker compose up -d --build` plus `BASE_URL=http://localhost:8080 npm run test:ui-review` for the SPA e2e/a11y lane, or `BASE_URL=http://localhost:8080 RUN_UI_A11Y=1 bash scripts/ci-local.sh` for the full local lane. If no UI surface is touched, record `UI validation not applicable` in the story Dev Agent Record.

## Notes

- Python version is pinned to `3.11` to match the Docker runtime.
- No CI secrets are required for the base pipeline.
- Slack notifications are optional and only activate when `SLACK_WEBHOOK_URL` is present.

### Dependency freshness and delivery permissions

Dependabot proposes weekly Python, root/frontend npm and GitHub Actions updates targeting `develop`; updates must pass normal review/CI. Frontend CI audits both npm graphs at all severities. Runtime Python audit remains enabled. Workflow defaults are read-only; container pushes, release creation and committed analytics snapshots receive only their required job-scoped writes. Public analytics feeds receive no GitHub bearer credential. Third-party workflow actions are SHA-pinned and included in automated update coverage. See [the remediation record](security/remediation-2026-10-07.md) for advisory dispositions and validation limits.

### Hash-locked Python installations

Use `python -m pip install --require-hashes --only-binary=:all: -r requirements.txt`
for runtime-only setup. Contributors and local CI use the same command with
`requirements-dev.txt`, which includes runtime dependencies and reviewed test,
lint and audit tools. Both locks include transitive distributions and SHA256
hashes; a version pin alone does not verify downloaded bytes.

For runtime updates, edit `requirements-runtime.txt` and keep the dependency
list in `pyproject.toml` synchronized. For tool updates, edit
`requirements-dev-input.txt`. Install the official `uv` 0.11.2 development tool,
then run `bash scripts/lock-dependencies.sh` to regenerate **both** locks and
run the hash/parity tests plus relevant application/CI checks. This generator
uses universal resolution for the declared Python floor, retaining platform
and Python-version markers; production execution is verified on Python 3.11.

Dependabot can refresh ordinary hashed requirements files. Review its changes
alongside source inputs and packaging metadata, regenerate any stale lock, and
require the parity tests before accepting an update. Automatic merging is not
enabled. Fuzzing uses its own small hashed lock and documented update command
in [the fuzzing guide](security/fuzzing.md). Docker digest update proposals also
need build/runtime verification before merging.
