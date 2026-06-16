# Story 1.3: Project-Scoped Report Persistence

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform admin,
I want saved reports and analysis runs scoped to their project and optional workspace,
So that teams do not see unrelated deployment reviews by accident.

## Acceptance Criteria

1. Given analysis runs and reports are created or queried, When persistence and retrieval run, Then records are scoped to project and optional workspace where applicable. And report repository queries and API responses prevent accidental cross-project leakage.
2. Given a report lookup uses an ID from another project, When the caller's active project does not match the report scope, Then the response does not reveal report contents or metadata beyond an authorized error envelope.

### Requirement Traceability

- Primary PRD requirements: Epic 1 coverage: PRJ-01..10, HIS-08, NFR-SEC-07, DOC-22.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 1 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Implement and verify acceptance criterion 2. (AC: 2)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Require project scope when API retrieval filters by workspace_id [api/routes/analyses.py:131]
- [x] [Review][Patch] Validate full report workspace schema before stamping brownfield revision 015 [models/database.py:307]

## Dev Notes

### Epic Context

- Epic: 1. Project, Workspace, and RBAC Foundation
- Epic goal: Make DeployWhisper project-aware before reports, incidents, topology, scanner imports, and feedback become harder to migrate.
- Epic coverage: PRJ-01..10, HIS-08, NFR-SEC-07, DOC-22

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 1 / Story 1.3 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5.4 Codex

### Debug Log References

- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persist_analysis_report_stores_and_filters_workspace_scope tests.test_api.test_analyses.AnalysesApiTests.test_workspace_query_prevents_cross_workspace_report_lookup -q` - failed before implementation with `persist_analysis_report() got an unexpected keyword argument 'workspace_id'`.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persist_analysis_report_stores_and_filters_workspace_scope tests.test_api.test_analyses.AnalysesApiTests.test_workspace_query_prevents_cross_workspace_report_lookup -q` - passed after workspace persistence and API scope filtering implementation.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service tests.test_api.test_analyses tests.test_infra.test_migrations tests.test_infra.test_container_contract -q` - passed, 69 tests.
- `./.venv/bin/ruff check .` - passed.
- `./.venv/bin/ruff format --check .` - initially reported `services/project_service.py`; passed after running `./.venv/bin/ruff format services/project_service.py`.
- `./.venv/bin/python -m unittest discover -q` - passed, 247 tests, 1 skipped.
- `bash scripts/ci-local.sh` - passed; Bandit skipped because it is not installed locally.
- `git diff --check` - passed.
- `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_workspace_query_prevents_cross_workspace_report_lookup tests.test_infra.test_migrations.MigrationTests.test_init_db_rejects_partial_report_workspace_scope_schema tests.test_infra.test_migrations.MigrationTests.test_init_db_repairs_current_schema_without_alembic_version -q` - passed after review finding fixes.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service tests.test_api.test_analyses tests.test_infra.test_migrations tests.test_infra.test_container_contract -q` - passed, 70 tests.
- `./.venv/bin/ruff check .` - passed after review finding fixes.
- `./.venv/bin/ruff format --check .` - initially reported `tests/test_infra/test_migrations.py`; passed after running `./.venv/bin/ruff format tests/test_infra/test_migrations.py`.
- `./.venv/bin/python -m unittest discover -q` - passed, 248 tests, 1 skipped.
- `bash scripts/ci-local.sh` - passed; Bandit skipped because it is not installed locally.

### Completion Notes List

- Added nullable workspace scope to persisted analysis reports with Alembic migration `015_add_report_workspace_scope`.
- Extended report persistence, serialization, history/detail retrieval, dashboard/trend helpers, API schemas/routes, CLI analysis options, and project/workspace resolution to validate and filter optional workspace scope.
- Preserved unauthorized cross-scope behavior as standard not-found API envelopes so mismatched project/workspace lookups do not reveal report contents.
- Closed review findings by rejecting API report/history retrieval requests that supply `workspace_id` without project scope, and by rejecting partial brownfield report workspace schemas before stamping revision 015.
- Updated project workspace documentation with workspace-aware report submission and retrieval examples.

### File List

- `_bmad-output/implementation-artifacts/1-3-project-scoped-report-persistence.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `api/routes/analyses.py`
- `api/schemas.py`
- `cli/analyze.py`
- `docs/project-workspaces.md`
- `migrations/versions/015_add_report_workspace_scope.py`
- `models/database.py`
- `models/repositories/analysis_reports.py`
- `models/repositories/projects.py`
- `models/tables.py`
- `services/analysis_service.py`
- `services/project_service.py`
- `services/report_service.py`
- `tests/test_api/test_analyses.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_services/test_report_service.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-06: Implemented project/workspace-scoped report persistence, retrieval filters, API/CLI contracts, migration, docs, and regression coverage.
- 2026-05-06: Fixed code review findings for unscoped `workspace_id` API retrieval and partial brownfield revision 015 detection.
- 2026-05-06: Re-ran BMad code review with no remaining findings; story marked done.
