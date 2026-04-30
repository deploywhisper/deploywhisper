# Story 5.5: Deployment history capture

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a engineering manager,
I want every deployment and its outcome tracked,
so that I can measure risk trends over time.

## Acceptance Criteria

1. Webhook endpoint accepts deployment outcome notifications
2. Webhook payload: analysis_id, outcome (success/failure/rolled_back), deployed_at, linked_incident_id
3. CLI alternative: `deploywhisper outcome record --analysis-id X --outcome success`
4. History queryable via API

### Requirement Traceability

- Primary PRD requirements: `CTX-06`, `HIS-06`
- Supporting PRD / NFR / differentiation requirements: `HIS-01`, `HIS-02`
- Coverage intent: `Baseline + Delta`
- Story alignment note: Extend current report persistence into deployment-outcome capture without breaking audit history.

## Tasks / Subtasks

- [x] Implement AC1: Webhook endpoint accepts deployment outcome notifications (AC: 1)
- [x] Implement AC2: Webhook payload: analysis_id, outcome (success/failure/rolled_back), deployed_at, linked_incident_id (AC: 2)
- [x] Implement AC3: CLI alternative: `deploywhisper outcome record --analysis-id X --outcome success` (AC: 3)
- [x] Implement AC4: History queryable via API (AC: 4)
- [x] Add or update automated verification, fixtures, docs, and rollout notes required for this story (AC: 1, 2, 3, 4)

## Dev Notes

- Epic context: Context Moat (2, 15-22 (overlaps Epics 3-4), P1).
- Epic goal: Automate topology discovery across supported infrastructure sources. Capture deployment outcomes. Build the feedback loop. This epic turns DeployWhisper from "smart on day 1" to "measurably smarter every month".
- This story contributes directly to context moat and should be scoped so later stories can build on stable contracts rather than rewrites.
- Epic 5 is the feedback/context moat. Topology freshness, deployment outcomes, and reviewer feedback are first-class context signals that must remain auditable.
- Capture history and feedback in a way that can support later calibration and backtesting without rewriting the persistence model again.
- Outcome and feedback ingestion should be explicit and operator-visible; hidden heuristics will undermine trust.
- Preserve the project-context guardrails: shared analysis core, local-first handling of raw IaC, advisory-first outputs, and deterministic tests over flaky integration assumptions.

### Project Structure Notes

- Likely implementation surfaces: services/topology_service.py, services/report_service.py, api/routes/, models/, ui/routes/, cli/, tests/.
- Keep new capabilities in the correct layer instead of duplicating logic across UI, API, CLI, integrations, or docs.
- If this story introduces a new top-level folder or runtime surface, align it with the architecture document before implementation starts.

### References

- [Epics](../planning-artifacts/epics.md)
- [PRD](../planning-artifacts/prd.md)
- [Architecture](../planning-artifacts/architecture.md)
- [Project Context](../project-context.md)

## Dev Agent Record

### Agent Model Used

GPT-5 (Codex)

### Debug Log References

- `./.venv/bin/python -m unittest -q tests.test_infra.test_migrations tests.test_services.test_deployment_outcome_service tests.test_api.test_deployments tests.test_cli.test_analyze`
- `./.venv/bin/python -m unittest -q tests.test_infra.test_migrations tests.test_api.test_deployments tests.test_services.test_deployment_outcome_service tests.test_cli.test_analyze`
- `./.venv/bin/python -m unittest -q tests.test_infra.test_migrations`
- `./.venv/bin/ruff check .`
- `./.venv/bin/ruff format --check .`
- `./.venv/bin/python -m unittest discover -q`
- `bash scripts/ci-local.sh`

### Completion Notes List

- Added migration `011_add_deployment_outcome_fields` so deployment outcomes now persist `deployed_at` and optional `linked_incident_id` without replacing the existing Epic 5 project-scoped table.
- Added shared deployment outcome capture/query support through `services/deployment_outcome_service.py` and `models/repositories/deployment_outcomes.py`, with validation that derives the owning project from `analysis_id` and rejects mismatched project references.
- Added `POST /api/v1/deployments/outcomes` and `GET /api/v1/deployments/outcomes` for webhook-style ingestion and API history queries.
- Added CLI support for `deploywhisper outcome record --analysis-id X --outcome success`, plus optional `--deployed-at`, `--linked-incident-id`, `--environment`, and validation-only project flags.
- Added operator documentation and rollout notes in `docs/deployment-history.md`.
- Added regression coverage for migrations, shared service behavior, API contracts, CLI behavior, and migration inventory expectations.
- Validation passed with repo-wide Ruff checks, focused regression tests, full `unittest discover -q`, and `bash scripts/ci-local.sh`. Local CI still skipped Bandit because Bandit is not installed in this environment.
- Fixed code-review finding: migration `011_add_deployment_outcome_fields` now backfills `incident_records` into the Alembic chain so `alembic upgrade head` yields a complete schema without relying on ORM metadata side effects.
- Fixed code-review finding: `POST /api/v1/deployments/outcomes` now requires `X-DeployWhisper-Outcome-Token`, and the docs/tests were updated to reflect the explicit mutation-token requirement.
- Fixed follow-up code-review finding: migration `011_add_deployment_outcome_fields` now records whether it created `incident_records` and drops that table on downgrade only when `011` introduced it, preserving pre-existing schemas while restoring revision `010` accurately.

### File List

- `_bmad-output/implementation-artifacts/5-5-deployment-history-capture.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `api/routes/deployments.py`
- `api/schemas.py`
- `app.py`
- `cli/analyze.py`
- `docs/deployment-history.md`
- `migrations/versions/011_add_deployment_outcome_fields.py`
- `models/database.py`
- `models/repositories/deployment_outcomes.py`
- `models/tables.py`
- `services/deployment_outcome_service.py`
- `tests/test_api/test_deployments.py`
- `tests/test_cli/test_analyze.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_services/test_deployment_outcome_service.py`

### Change Log

- 2026-04-30: Implemented Story 5.5 deployment outcome capture across migration, shared service, API, CLI, tests, and rollout documentation.
- 2026-04-30: Fixed Story 5.5 review findings for pure-Alembic incident schema coverage and authenticated outcome ingestion.
- 2026-04-30: Fixed Story 5.5 review finding for accurate downgrade behavior when `011` creates `incident_records`.
