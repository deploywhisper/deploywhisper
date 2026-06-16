# Story 1.4: Project-Scoped Learning and Context Records

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform admin,
I want incidents, outcomes, feedback, topology, and scanner imports scoped consistently,
So that future learning and context never cross project boundaries.

## Acceptance Criteria

1. Given incidents, deployment outcomes, feedback, topology, or scanner imports are created or queried, When they are created or queried, Then they are scoped to project and optional workspace where applicable. And repository queries and API responses prevent accidental cross-project leakage.
2. Given a context or learning record has no project scope, When validation runs before persistence, Then persistence fails with an actionable error unless the object type is explicitly global by architecture.

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

- [x] [Review][Patch] Enforce database-level project/workspace consistency for scoped learning/context rows [migrations/versions/016_scope_learning_context_records.py:112]
- [x] [Review][Patch] Do not mirror workspace-scoped default-project topology into the legacy global topology file [services/topology_service.py:967]

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 1 / Story 1.4 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `./.venv/bin/python -m pytest tests/test_services/test_incident_service.py tests/test_services/test_deployment_outcome_service.py tests/test_services/test_feedback_service.py tests/test_services/test_topology_service.py -q` - passed, 35 tests.
- `./.venv/bin/python -m pytest tests/test_analysis/test_incident_matcher.py tests/test_services/test_backtesting_service.py tests/test_services/test_analysis_service.py -q` - passed, 28 tests.
- `./.venv/bin/python -m pytest tests/test_api/test_deployments.py tests/test_api/test_context.py tests/test_cli/test_analyze.py -q` - passed, 51 tests.
- `./.venv/bin/python -m pytest tests/test_infra/test_migrations.py tests/test_infra/test_container_contract.py -q` - passed, 22 tests.
- `./.venv/bin/python -m pytest tests/test_analysis/test_incident_matcher.py tests/test_services/test_incident_service.py tests/test_services/test_deployment_outcome_service.py tests/test_services/test_feedback_service.py tests/test_services/test_topology_service.py tests/test_services/test_backtesting_service.py tests/test_services/test_analysis_service.py tests/test_api/test_deployments.py tests/test_api/test_context.py tests/test_cli/test_analyze.py tests/test_infra/test_migrations.py tests/test_infra/test_container_contract.py -q` - passed, 136 tests.
- `./.venv/bin/python -m unittest frontend.e2e.test_history_page.HistoryPageRenderingTests.test_history_page_renders_calibration_snapshot_from_backtest_feed -q -b` - passed, 1 test.
- `./.venv/bin/ruff check .` - passed.
- `./.venv/bin/ruff format --check .` - passed, 256 files already formatted.
- `./.venv/bin/python -m unittest discover -q -b` - passed, 249 tests, 1 skipped.
- `bash scripts/ci-local.sh` - passed; Bandit security scan skipped because Bandit is not installed.
- `./.venv/bin/python -m pytest tests/test_infra/test_migrations.py::MigrationTests::test_upgrade_head_creates_evidence_schema_on_clean_database tests/test_infra/test_migrations.py::MigrationTests::test_learning_context_scope_rejects_cross_project_workspace_rows tests/test_services/test_topology_service.py::TopologyServiceTests::test_default_project_workspace_topology_does_not_update_legacy_file -q` - passed, 3 tests.
- `./.venv/bin/python -m pytest tests/test_infra/test_migrations.py tests/test_infra/test_container_contract.py tests/test_services/test_topology_service.py tests/test_services/test_incident_service.py tests/test_services/test_deployment_outcome_service.py tests/test_services/test_feedback_service.py -q` - passed, 59 tests.

### Completion Notes List

- Added database and Alembic support for project/workspace-scoped learning and context records across incidents, outcomes, feedback, and topology records.
- Enforced explicit project scope for incident persistence and propagated project/workspace scope through incident matching, deployment outcomes, feedback summaries, topology import/query paths, API schemas, and CLI commands.
- Added cross-project and cross-workspace regression coverage for repository/service behavior, migration shape, API/CLI integration paths, and topology isolation.
- Made the history calibration snapshot test deterministic within the rolling 7-day backtesting window.
- Addressed code-review findings by adding database-level project/workspace consistency constraints for scoped learning/context rows and preventing workspace-scoped default-project topology from updating the legacy project-level topology file.

### File List

- `_bmad-output/implementation-artifacts/1-4-project-scoped-learning-and-context-records.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `analysis/incident_matcher.py`
- `api/routes/deployments.py`
- `api/routes/settings.py`
- `api/schemas.py`
- `cli/analyze.py`
- `docs/deployment-history.md`
- `migrations/versions/016_scope_learning_context_records.py`
- `models/database.py`
- `models/repositories/deployment_outcomes.py`
- `models/repositories/feedback_events.py`
- `models/repositories/incident_records.py`
- `models/tables.py`
- `services/analysis_service.py`
- `services/deployment_outcome_service.py`
- `services/feedback_service.py`
- `services/incident_service.py`
- `services/topology_service.py`
- `tests/test_analysis/test_incident_matcher.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_services/test_deployment_outcome_service.py`
- `tests/test_services/test_feedback_service.py`
- `tests/test_services/test_incident_service.py`
- `tests/test_services/test_topology_service.py`
- `frontend/e2e/test_history_page.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-06: Implemented project/workspace-scoped learning and context record persistence, query filtering, API/CLI propagation, regression coverage, and validation.
