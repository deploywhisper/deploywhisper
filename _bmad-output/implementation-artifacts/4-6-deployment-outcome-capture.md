# Story 4.6: Deployment Outcome Capture

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform engineer,
I want to record deployment outcomes after review,
So that DeployWhisper can learn from success, failure, rollback, and incident outcomes.

## Acceptance Criteria

1. Given a deployment follows a DeployWhisper report, When outcome data is captured, Then success, failure, rollback, linked incident, notes, project, and workspace are stored. And the outcome is available for calibration and backtesting.

### Requirement Traceability

- Primary PRD requirements: Epic 4 coverage: INC-01..12, CTX-03..04, HIS-05..07, HIS-09, ADM-04, RSK-12, DOC-23.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 4 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Persist deployment notes as their own outcome field instead of aliasing them to summary [services/deployment_outcome_service.py:120]
- [x] [Review][Patch] Keep rollback as an input-only alias and keep response outcome schemas canonical [api/schemas.py:93]
- [x] [Review][Patch] Update CLI outcome help text to include the rollback alias [cli/analyze.py:946]
- [x] [Review][Patch] Reject partial deployment outcome notes schemas before Alembic attempts to add the notes column again [models/database.py:612]

## Dev Notes

### Epic Context

- Epic: 4. Day-Zero Risk Patterns and Incident Memory
- Epic goal: Give new installs useful memory immediately and grow organization-specific learning over time.
- Epic coverage: INC-01..12, CTX-03..04, HIS-05..07, HIS-09, ADM-04, RSK-12, DOC-23

### Architecture and Product Guardrails

- Preserve DeployWhisper's local-first raw artifact boundary: raw IaC, scanner artifacts, incident exports, and sensitive context stay in the user's infrastructure by default.
- Preserve the advisory-first core. Optional adapters may interpret report outputs, but canonical report semantics remain advisory unless explicit story scope says otherwise.
- Reuse the shared analysis core and service layer before adapting UI, API, CLI, GitHub, or future workflow surfaces.
- Keep Evidence Law behavior intact: no high or critical finding without deterministic evidence.
- Keep project/workspace scope explicit for reports, incidents, topology, outcomes, feedback, scanner imports, and connector-related data.
- Do not introduce new dependencies unless the active story explicitly requires and justifies them.

### Source Tree Guidance

- API routes belong under `api/routes/` and should use existing `ApiRoute` / `ApiError` envelope patterns.
- Shared orchestration belongs in `services/`; parsers normalize input, analysis modules score/derive risk, and surfaces adapt outputs.
- UI work belongs under `frontend/src/screens/` and `frontend/src/components/`, following the existing retired Python UI composition style.
- CLI behavior belongs under `cli/` and must call the same service-layer paths as UI/API flows.
- Persistence work belongs under `models/` with Alembic migrations when schema changes are required.
- Documentation required by a story should be updated in the same workstream.

### Testing Requirements

- Use standard-library `unittest` in the existing `tests/test_*` layout.
- Add focused regression tests for the layer changed by the story before broad refactors.
- For Python changes, run `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, and `./.venv/bin/python -m unittest discover -q` before closing implementation.
- Use `bash scripts/ci-local.sh` for broader or cross-layer changes.

### Project Structure Notes

- Follow the current repository shape documented in `_bmad-output/project-context.md` and `AGENTS.md`.
- If implementation reveals a conflict between this story and the current code baseline, keep the smallest compatible change and update the story notes rather than silently drifting from the PRD.

### References

- `_bmad-output/planning-artifacts/epics.md` - source Epic 4 / Story 4.6 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `./.venv/bin/python -m unittest tests.test_services.test_deployment_outcome_service tests.test_api.test_deployments tests.test_cli.test_analyze -q` - red phase failed as expected before implementation because `notes`, `rollback`, and CLI `--notes` were not accepted.
- `./.venv/bin/python -m unittest tests.test_services.test_deployment_outcome_service tests.test_api.test_deployments tests.test_cli.test_analyze -q` - passed after implementation, 75 tests.
- `./.venv/bin/ruff format services/deployment_outcome_service.py api/schemas.py api/routes/deployments.py cli/analyze.py tests/test_services/test_deployment_outcome_service.py tests/test_api/test_deployments.py tests/test_cli/test_analyze.py` - passed; formatted touched Python files.
- `./.venv/bin/ruff check .` - passed.
- `./.venv/bin/ruff format --check .` - passed.
- `./.venv/bin/bandit -q services/deployment_outcome_service.py api/routes/deployments.py cli/analyze.py` - first run flagged a pre-existing `assert` in touched CLI code; replaced it with an explicit guard and reran successfully.
- `./.venv/bin/python -m unittest discover -q` - passed, 420 tests, 1 skipped.
- `bash scripts/ci-local.sh` - passed; included lint, format check, dependency check, Bandit, and full unittest discovery with 420 tests, 1 skipped.
- `./.venv/bin/python -m unittest tests.test_services.test_deployment_outcome_service tests.test_api.test_deployments tests.test_cli.test_analyze tests.test_infra.test_migrations -q` - review-fix red/green loop; first run exposed missing migration bootstrap handling, then passed after adding migration/head coverage, 99 tests.
- `./.venv/bin/ruff format models/database.py tests/test_infra/test_migrations.py` - passed; files already formatted.
- `./.venv/bin/bandit -q services/deployment_outcome_service.py api/routes/deployments.py cli/analyze.py models/database.py models/tables.py models/repositories/deployment_outcomes.py migrations/versions/022_add_deployment_outcome_notes.py` - passed.
- `./.venv/bin/python -m unittest tests.test_infra.test_container_contract -q` - passed, 5 tests.
- `./.venv/bin/python -m unittest discover -q` - review-fix full suite passed, 420 tests, 1 skipped.
- `bash scripts/ci-local.sh` - review-fix local CI passed; included Ruff, format check, dependency check, Bandit, parser scenarios, and full unittest discovery with 420 tests, 1 skipped.
- `./.venv/bin/ruff format models/database.py tests/test_infra/test_migrations.py` - second review-fix pass; files already formatted.
- `./.venv/bin/python -m unittest tests.test_infra.test_migrations -q` - passed after partial deployment outcome notes schema guard, 25 tests.
- `./.venv/bin/ruff check .` - second review-fix pass; passed.
- `./.venv/bin/ruff format --check .` - second review-fix pass; passed.
- `./.venv/bin/bandit -q services/deployment_outcome_service.py api/routes/deployments.py cli/analyze.py models/database.py models/tables.py models/repositories/deployment_outcomes.py migrations/versions/022_add_deployment_outcome_notes.py` - second review-fix pass; passed.
- `./.venv/bin/python -m unittest tests.test_services.test_deployment_outcome_service tests.test_api.test_deployments tests.test_cli.test_analyze tests.test_infra.test_migrations tests.test_infra.test_container_contract -q` - second review-fix pass; passed, 105 tests.
- `git diff --check` - second review-fix pass; passed.
- `./.venv/bin/python -m unittest discover -q` - second review-fix full suite passed, 421 tests, 1 skipped.
- `bash scripts/ci-local.sh` - second review-fix local CI passed; included Ruff, format check, dependency check, Bandit, parser scenarios, and full unittest discovery with 421 tests, 1 skipped.
- UI validation not applicable; this story did not change UI routes, components, rendered report surfaces, browser interactions, keyboard behavior, or accessibility semantics.

### Completion Notes List

- Deployment outcome capture now accepts `rollback` as an input alias while storing the canonical `rolled_back` outcome for calibration and backtesting.
- Outcome capture now accepts operator `notes` through the service, API, and CLI while preserving the existing `summary` field and serialized contract.
- API and CLI examples now document deployment outcome notes and rollback alias behavior.
- Regression coverage verifies scoped project/workspace persistence, linked incident capture, notes serialization, API webhook/list behavior, CLI recording, and backtesting availability.
- Replaced a touched CLI assertion with an explicit runtime guard so static analysis remains clean.
- Review fixes persist deployment outcome notes in an independent database field instead of mirroring summary, preserve `rollback` as an input-only alias while response schemas remain canonical, and document the CLI alias in help text.
- Added Alembic revision `022_add_deployment_outcome_notes` plus brownfield bootstrap and container contract coverage for the new deployment outcome `notes` column.
- Added a brownfield bootstrap guard and regression test so partial/manual deployment outcome `notes` schemas fail with an explicit recovery error instead of colliding with the Alembic add-column migration.

### File List

- `services/deployment_outcome_service.py`
- `api/schemas.py`
- `api/routes/deployments.py`
- `cli/analyze.py`
- `docs/deployment-history.md`
- `models/tables.py`
- `models/repositories/deployment_outcomes.py`
- `models/database.py`
- `migrations/versions/022_add_deployment_outcome_notes.py`
- `tests/test_services/test_deployment_outcome_service.py`
- `tests/test_api/test_deployments.py`
- `tests/test_cli/test_analyze.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_infra/test_container_contract.py`
- `_bmad-output/implementation-artifacts/4-6-deployment-outcome-capture.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-22: Implemented deployment outcome capture hardening, notes alias, rollback alias, docs, and regression coverage.
- 2026-05-22: Addressed review findings with independent notes persistence, canonical response outcome schema, CLI rollback help text, migration coverage, and local CI verification.
- 2026-05-22: Addressed follow-up review finding for partial deployment outcome notes schema handling and reran focused/full/local CI validation.

## Course Correction — 2026-10-07

Status reconciled to `done` against merged delivery [PR #70](https://github.com/deploywhisper/deploywhisper/pull/70), the completed task/review-fix records above, and the accepted v1.4.0 baseline in `docs/verification/v1.4.0-release.json`. This is administrative closeout of existing delivery, not a claim that a new implementation review or application test run occurred today. Historical review attempts remain intact. See `../planning-artifacts/sprint-change-proposal-2026-10-07-v1.4.0-status-reconciliation.md`.
