# Story 4.7: Incident Ingestion Management and Indexing

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform admin,
I want to manage incident ingestion status, indexing, reindexing, and failures,
So that organization incident memory stays understandable and maintainable.

## Acceptance Criteria

1. Given incident import jobs or indexed incident records exist, When an admin opens incident ingestion management, Then they can see import source, project/workspace scope, indexed count, rejected count, last indexed timestamp, redaction status, and failure summaries. And each failure includes an actionable correction path.
2. Given incidents are updated, deleted, or reimported, When reindexing runs, Then stale index entries are replaced or removed under the same project scope. And reports never mix old and new incident index state without exposing freshness.

### Requirement Traceability

- Primary PRD requirements: ADM-04, INC-04, INC-06.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 4 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Implement and verify acceptance criterion 2. (AC: 2)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Decision] Reindex removal semantics can delete unrelated incident history — `remove_missing_sources=True` currently deletes all scoped rows whose `source_file` is omitted, but the table has no import-origin/source registry to distinguish files managed by this reindex set from other valid incident memory. Decide whether to add provenance/source registry now, narrow the endpoint semantics, or defer stale-source removal behavior.
- [x] [Review][Patch] Reindex replacement is not atomic [services/incident_import_service.py:248] — existing rows are deleted before replacement ingestion, and the repository helper commits the delete; a later ingest failure can leave the incident index empty or partial.
- [x] [Review][Patch] Ingestion management does not persist or expose failed ingestion summaries [services/incident_service.py:310] — `rejected_count` and `failure_summaries` are hard-coded empty in status, so AC1 failure summaries and correction paths only exist in immediate 422 responses and are not visible from management.
- [x] [Review][Patch] Reports do not expose incident index freshness or version [services/analysis_service.py:441] — report context only snapshots incident index size, so consumers can see matches without knowing which incident index state or freshness they came from.
- [x] [Review][Patch] Project/workspace scope is not explicit in source status grouping [services/incident_service.py:296] — project-level status groups by `source_file` only, collapsing same-name files across workspaces and omitting per-source workspace scope/last-indexed detail in the UI.
- [x] [Review][Patch] Workspace reference errors are not masked for restricted callers [api/routes/incidents.py:81] — the incident route masks project lookup failures only, unlike neighboring scoped routes that also mask workspace reference probes.
- [x] [Review][Patch] Duplicate source files in one reindex request are accepted [services/incident_import_service.py:242] — deletion dedupes source names but insertion replays each duplicate file, creating ambiguous duplicate source state.
- [x] [Review][Patch] Original incident imports bypass the source registry [services/incident_import_service.py:166] — successful `import_incident_files` calls create incident records but no `incident_ingestion_sources` rows, and failed import validation is not persisted. As a result, management cannot show failed import-job summaries for Story 4.3 import failures, successful imports keep stale failure summaries if the same source previously failed reindex validation, and `remove_missing_sources=True` cannot remove omitted sources that were created by the original import path.
- [x] [Review][Patch] Empty authoritative reindex cannot clear all managed sources [services/incident_import_service.py:238] — `reindex_incident_files` rejects every empty `files` list before removal logic runs, so an operator cannot represent the valid "all incident sources were deleted" case with `remove_missing_sources=True`; AC2's deleted-incident branch remains unimplemented.
- [x] [Review][Patch] Project-scoped source registry uniqueness is not enforced for NULL workspaces [migrations/versions/023_add_incident_ingestion_sources.py:57] — the unique constraint over `(project_id, workspace_id, source_file)` allows duplicate project-level rows when `workspace_id` is NULL on SQLite/Postgres, but `upsert_incident_ingestion_source` assumes `scalar_one_or_none()` uniqueness and can fail or drift under retry/concurrent project-scope reindex.
- [x] [Review][Patch] Complete reindex cannot clear previously failed source entries [models/repositories/incident_ingestion_sources.py:59] — `list_managed_incident_source_files` excludes `status == "failed"`, so a failed source omitted from an authoritative reindex remains in management forever even when the operator intentionally dropped it from the complete source set.
- [x] [Review][Patch] Request-level validation failures are persisted as fake sources [services/incident_import_service.py:238] — batch errors such as an empty `files` list are recorded with `source_file="batch"`, causing the API/UI to show a non-existent incident source instead of a request-level failure.
- [x] [Review][Patch] Incident index freshness cannot represent stale report snapshots [services/incident_service.py:39] — freshness is limited to `current` or `empty` and is derived only from whether rows exist, so older reports keep rendering `freshness current` after the scoped incident index changes; AC2 requires report consumers to see when incident index state is stale instead of only seeing a historical version string.
- [x] [Review][Patch] Reindex does not invalidate backtesting snapshots [services/incident_import_service.py:374] — successful `reindex_incident_files` replaces/removes incident records and source registry rows but returns without calling `invalidate_backtesting_snapshot(project_id=...)`, unlike successful import. Cached backtesting or analysis state can continue using pre-reindex incident memory after an operator has rebuilt the index.
- [x] [Review][Patch] Reindex response metadata undercounts returned status sources [api/routes/incidents.py:244] — `meta.count` is set to `result.indexed_count`, while the response payload returns `result.status.sources`, which can include persisted failed sources as well as newly indexed files. API clients using `meta.count` can render incorrect badges or pagination.
- [x] [Review][Patch] Report freshness check fails open when incident snapshot lookup fails [services/report_service.py:3333] — `_context_with_incident_index_freshness` catches all exceptions from `get_incident_index_snapshot` and returns the stored context unchanged. If the current scoped incident index cannot be resolved, an older report can continue displaying a prior `current` freshness value instead of surfacing stale/unknown freshness.
- [x] [Review][Patch] Incident management UI does not enforce incident.manage [frontend/src/screens/incidents.py:48] — `/incidents` renders incident ingestion source names, rejection details, and freshness using only project visibility from `resolve_authorized_ui_active_project`, while the API route requires `incident.manage`. Reviewer/read-only UI actors with ordinary project visibility can reach admin incident-management data.
- [x] [Review][Patch] Legacy report incident freshness normalizes to empty for unknown populated indexes [services/report_service.py:3223] — legacy context payloads without `incident_index_freshness_status` default to `empty` even when `incident_index_size > 0`, and `_context_with_incident_index_freshness` skips `incidents:unknown`. Historical reports can therefore display a false empty incident index instead of unknown/stale freshness.
- [x] [Review][Patch] Migration coverage does not assert incident_ingestion_sources schema [tests/test_infra/test_migrations.py:976] — migration tests update the expected revision to `023_add_incident_ingestion_sources` but do not assert the new table, partial unique index, or project/workspace foreign keys after upgrade/bootstrap repair. The riskiest Story 4.7 schema guarantees can regress without test failure.
- [x] [Review][Patch] Project-wide authoritative reindex skips workspace-scoped managed incidents [services/incident_import_service.py:294] — project-scope reindex passes `workspace_id=None` into helpers that interpret `None` as `workspace_id IS NULL`, so workspace-scoped managed sources are invisible to `remove_missing_sources=True`. A complete project refresh can leave stale workspace incident records behind and underreport removals, violating AC2 for projects using workspaces.
- [x] [Review][Patch] Analysis context hard-fails when incident snapshot lookup fails [services/analysis_service.py:448] — `_build_context_completeness` calls `get_incident_index_snapshot` without fallback, so a transient incident-index lookup/schema failure aborts analysis instead of degrading incident context the way report fetch now marks freshness stale.
- [x] [Review][Patch] Project-wide reindex collapses distinct workspace sources that share a filename [services/incident_import_service.py:295] — project-scope reindex treats submitted source names as global across the project and calls record count/delete helpers with `include_workspace_scopes=True`; reindexing project-level `checkout.json` can delete `prod/checkout.json` or `staging/checkout.json` records and recreate only a project-level record. This violates AC2's scoped stale-entry replacement and the existing same-filename workspace grouping behavior.
- [x] [Review][Patch] Bootstrap schema completeness does not verify all incident_ingestion_sources integrity constraints [models/database.py:402] — `_incident_ingestion_sources_schema_complete()` checks columns, project FK, and indexes but does not verify the workspace FK, composite project/workspace scope FK, or status check constraint that migration coverage now asserts. A brownfield partial table can be stamped as revision `023_add_incident_ingestion_sources` while still missing Story 4.7 scope/status guarantees.
- [x] [Review][Patch] Bootstrap accepts non-partial project source uniqueness [models/database.py:475] — `_incident_ingestion_sources_schema_complete()` verifies that a unique `(project_id, source_file)` index exists but does not verify the required `workspace_id IS NULL` predicate. A brownfield table with a full unique `(project_id, source_file)` index can be stamped as revision `023_add_incident_ingestion_sources`, then reject valid same-filename workspace/project sources and violate AC2's scoped same-source replacement behavior.

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 4 / Story 4.7 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-05-22: Started fresh bmad-dev-story implementation on `feature/4-7-incident-ingestion-management`.
- 2026-05-22: Red phase confirmed with `./.venv/bin/python -m unittest tests.test_services.test_incident_service tests.test_api.test_incidents frontend.e2e.test_incidents_page -q`; expected failures covered missing incident ingestion status service, reindex service, API routes, and UI route.
- 2026-05-22: Focused regression passed with `./.venv/bin/python -m unittest tests.test_services.test_incident_service tests.test_api.test_incidents frontend.e2e.test_incidents_page -q`.
- 2026-05-22: Lint and format passed with `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- 2026-05-22: Full regression passed with `./.venv/bin/python -m unittest discover -q` (424 tests, 1 skipped).
- 2026-05-22: UI browser validation passed with `APP_PORT=18080 npm run test:ui-review` after default port 8080 was already occupied.
- 2026-05-22: Focused security scan passed with `./.venv/bin/bandit -q -r api/routes/incidents.py models/repositories/incident_records.py services/incident_import_service.py services/incident_service.py frontend/src/screens/incidents.py frontend/src/screens/dashboard.py app.py`.
- 2026-05-22: Addressed code review findings by adding durable ingestion source provenance, transaction-scoped reindex replacement, persisted failed-source summaries, report index freshness/version snapshots, explicit workspace source grouping, restricted workspace probe masking, and duplicate source-file rejection.
- 2026-05-22: Focused review-fix regression passed with `./.venv/bin/python -m unittest tests.test_services.test_incident_service tests.test_api.test_incidents frontend.e2e.test_incidents_page -q`.
- 2026-05-22: Compatibility regression passed with `./.venv/bin/python -m unittest tests.test_services.test_analysis_service tests.test_services.test_incident_service tests.test_api.test_incidents frontend.e2e.test_incidents_page tests.test_infra.test_container_contract tests.test_infra.test_migrations -q`.
- 2026-05-22: Report/evidence compatibility passed with `./.venv/bin/python -m unittest tests.test_services.test_report_service tests.test_models.test_evidence_models tests.test_models.test_evidence_tables frontend.e2e.test_context_completeness_panel -q`.
- 2026-05-22: Final lint and formatting checks passed with `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- 2026-05-22: Final full regression passed with `./.venv/bin/python -m unittest discover -q` (425 tests, 1 skipped).
- 2026-05-22: Final UI browser validation passed with `APP_PORT=18080 npm run test:ui-review` (3 Playwright tests passed).
- 2026-05-22: Final focused security scan passed with `./.venv/bin/bandit -q -r api/routes/incidents.py models/repositories/incident_records.py models/repositories/incident_ingestion_sources.py services/incident_import_service.py services/incident_service.py services/analysis_service.py services/report_service.py frontend/src/screens/incidents.py frontend/src/components/context_completeness_panel.py`.
- 2026-05-22: Diff whitespace check passed with `git diff --check`.
- 2026-05-22: Reproduced second-pass reviewer findings with `./.venv/bin/python -m unittest tests.test_services.test_incident_service tests.test_services.test_report_service -q` (7 failures, 1 error).
- 2026-05-22: Added reviewer-finding regressions for import source registry updates, authoritative empty reindex clearing, NULL-workspace uniqueness, failed-source removal, batch-error filtering, and stale report snapshots.
- 2026-05-22: Focused second-pass reviewer regression passed with `./.venv/bin/python -m unittest tests.test_services.test_incident_service.IncidentServiceTests.test_import_failure_status_persists_actionable_source_failures tests.test_services.test_incident_service.IncidentServiceTests.test_successful_import_clears_previous_failed_source_status tests.test_services.test_incident_service.IncidentServiceTests.test_remove_missing_sources_removes_managed_import_sources tests.test_services.test_incident_service.IncidentServiceTests.test_empty_authoritative_reindex_clears_all_managed_sources tests.test_services.test_incident_service.IncidentServiceTests.test_authoritative_reindex_clears_omitted_failed_source_status tests.test_services.test_incident_service.IncidentServiceTests.test_request_level_reindex_failures_do_not_create_batch_source tests.test_services.test_incident_service.IncidentServiceTests.test_project_scoped_source_registry_rejects_duplicate_null_workspace_key tests.test_services.test_report_service.ReportServiceTests.test_fetch_analysis_report_marks_incident_index_snapshot_stale -q`.
- 2026-05-22: Incident/report service regression passed with `./.venv/bin/python -m unittest tests.test_services.test_incident_service tests.test_services.test_report_service -q` (155 tests).
- 2026-05-22: Final second-pass lint and formatting checks passed with `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- 2026-05-22: Final second-pass full regression passed with `./.venv/bin/python -m unittest discover -q` (425 tests, 1 skipped).
- 2026-05-22: Final second-pass UI browser validation passed with `APP_PORT=18080 npm run test:ui-review` (3 Playwright tests passed).
- 2026-05-22: Final second-pass focused security scan passed with `./.venv/bin/bandit -q -r api/routes/incidents.py models/repositories/incident_records.py models/repositories/incident_ingestion_sources.py services/incident_import_service.py services/incident_service.py services/analysis_service.py services/report_service.py frontend/src/screens/incidents.py frontend/src/components/context_completeness_panel.py`.
- 2026-05-22: Final second-pass diff whitespace check passed with `git diff --check`.
- 2026-05-22: Reproduced third-pass reviewer findings with `./.venv/bin/python -m unittest tests.test_services.test_incident_service.IncidentServiceTests.test_reindex_invalidates_backtesting_snapshot_after_success tests.test_api.test_incidents.IncidentsApiTests.test_reindex_incidents_replaces_stale_entries_and_reports_failures tests.test_services.test_report_service.ReportServiceTests.test_fetch_analysis_report_marks_incident_index_stale_when_lookup_fails -q` (3 failures).
- 2026-05-22: Fixed third-pass reviewer findings by invalidating backtesting snapshots after successful reindex, aligning reindex response `meta.count` with returned status sources, and marking report incident index freshness stale when current snapshot lookup fails.
- 2026-05-22: Focused third-pass reviewer regression passed with `./.venv/bin/python -m unittest tests.test_services.test_incident_service.IncidentServiceTests.test_reindex_invalidates_backtesting_snapshot_after_success tests.test_api.test_incidents.IncidentsApiTests.test_reindex_incidents_replaces_stale_entries_and_reports_failures tests.test_services.test_report_service.ReportServiceTests.test_fetch_analysis_report_marks_incident_index_stale_when_lookup_fails -q`.
- 2026-05-22: Story 4.7 affected regression passed with `./.venv/bin/python -m unittest tests.test_services.test_incident_service tests.test_services.test_report_service tests.test_api.test_incidents frontend.e2e.test_incidents_page -q` (161 tests).
- 2026-05-22: Final third-pass lint and formatting checks passed with `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- 2026-05-22: Final third-pass full regression passed with `./.venv/bin/python -m unittest discover -q` (425 tests, 1 skipped).
- 2026-05-22: Final third-pass UI browser validation passed with `APP_PORT=18080 npm run test:ui-review` (3 Playwright tests passed).
- 2026-05-22: Final third-pass focused security scan passed with `./.venv/bin/bandit -q -r api/routes/incidents.py models/repositories/incident_records.py models/repositories/incident_ingestion_sources.py services/incident_import_service.py services/incident_service.py services/analysis_service.py services/report_service.py frontend/src/screens/incidents.py frontend/src/components/context_completeness_panel.py`.
- 2026-05-22: Final third-pass diff whitespace check passed with `git diff --check`.
- 2026-05-22: Reproduced fourth-pass reviewer findings with `./.venv/bin/python -m unittest frontend.e2e.test_incidents_page tests.test_services.test_incident_service.IncidentServiceTests.test_project_wide_authoritative_reindex_removes_workspace_managed_sources tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_context_completeness_degrades_when_incident_snapshot_fails tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_upgrades_legacy_context_completeness_json tests.test_infra.test_migrations.MigrationTests.test_init_db_repairs_current_schema_without_alembic_version -q` (3 failures, 1 error).
- 2026-05-22: Fixed fourth-pass reviewer findings by enforcing `incident.manage` for the incident management UI/navigation, removing workspace-managed sources during project-wide authoritative reindex, rendering legacy populated unknown incident freshness as `unknown`, adding incident snapshot fallback for analysis context, and asserting incident ingestion source migration schema/index/FKs.
- 2026-05-22: Focused fourth-pass reviewer regression passed with `./.venv/bin/python -m unittest frontend.e2e.test_incidents_page tests.test_services.test_incident_service.IncidentServiceTests.test_project_wide_authoritative_reindex_removes_workspace_managed_sources tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_context_completeness_degrades_when_incident_snapshot_fails tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_upgrades_legacy_context_completeness_json tests.test_infra.test_migrations.MigrationTests.test_init_db_repairs_current_schema_without_alembic_version -q`.
- 2026-05-22: Story 4.7 affected regression passed with `./.venv/bin/python -m unittest tests.test_services.test_incident_service tests.test_services.test_report_service tests.test_services.test_analysis_service tests.test_api.test_incidents frontend.e2e.test_incidents_page tests.test_infra.test_migrations -q` (223 tests).
- 2026-05-22: Final fourth-pass lint and formatting checks passed with `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- 2026-05-22: Final fourth-pass full regression passed with `./.venv/bin/python -m unittest discover -q` (426 tests, 1 skipped).
- 2026-05-22: Final fourth-pass UI browser validation passed with `APP_PORT=18080 npm run test:ui-review` (3 Playwright tests passed).
- 2026-05-22: Final fourth-pass focused security scan passed with `./.venv/bin/bandit -q -r frontend/project_authorization.py frontend/src/theme/tokens.css frontend/src/screens/incidents.py models/repositories/incident_records.py services/incident_import_service.py services/analysis_service.py services/report_service.py`.
- 2026-05-22: Final fourth-pass diff whitespace check passed with `git diff --check`.
- 2026-05-22: Reproduced fifth-pass reviewer findings with `./.venv/bin/python -m unittest tests.test_services.test_incident_service.IncidentServiceTests.test_project_wide_reindex_preserves_same_named_workspace_sources tests.test_infra.test_migrations.MigrationTests.test_init_db_rejects_partial_incident_ingestion_source_constraints -q` (workspace source deletion failure, then mixed-scope status ordering error exposed during fix).
- 2026-05-22: Fixed fifth-pass reviewer findings by preserving workspace-scoped same-filename sources during project-level source replacement, using explicit scope-aware status ordering for mixed project/workspace source groups, and requiring workspace FK, composite scope FK, and status check constraints before bootstrap stamps incident ingestion revision 023.
- 2026-05-22: Focused fifth-pass reviewer regression passed with `./.venv/bin/python -m unittest tests.test_services.test_incident_service.IncidentServiceTests.test_project_wide_reindex_preserves_same_named_workspace_sources tests.test_infra.test_migrations.MigrationTests.test_init_db_rejects_partial_incident_ingestion_source_constraints -q`.
- 2026-05-22: Story 4.7 affected regression passed with `./.venv/bin/python -m unittest tests.test_services.test_incident_service tests.test_services.test_report_service tests.test_services.test_analysis_service tests.test_api.test_incidents frontend.e2e.test_incidents_page tests.test_infra.test_migrations -q` (225 tests).
- 2026-05-22: Final fifth-pass lint and formatting checks passed with `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- 2026-05-22: Final fifth-pass full regression passed with `./.venv/bin/python -m unittest discover -q` (427 tests, 1 skipped).
- 2026-05-22: Final fifth-pass UI browser validation passed with `APP_PORT=18080 npm run test:ui-review` (3 Playwright tests passed).
- 2026-05-22: Final fifth-pass focused security scan passed with `./.venv/bin/bandit -q -r models/database.py models/repositories/incident_records.py services/incident_import_service.py services/incident_service.py`.
- 2026-05-22: Final fifth-pass diff whitespace check passed with `git diff --check`.
- 2026-05-22: Fixed sixth-pass reviewer finding by requiring the bootstrap schema completeness check to verify the partial `workspace_id IS NULL` predicate on the project/source unique index and adding a brownfield regression for a non-partial full unique index.
- 2026-05-22: Focused sixth-pass migration regression passed with `./.venv/bin/python -m unittest tests.test_infra.test_migrations.MigrationTests.test_init_db_rejects_full_incident_ingestion_project_source_unique_index tests.test_infra.test_migrations.MigrationTests.test_init_db_rejects_partial_incident_ingestion_source_constraints tests.test_infra.test_migrations.MigrationTests.test_init_db_repairs_current_schema_without_alembic_version -q` (3 tests).
- 2026-05-22: Story 4.7 affected regression passed with `./.venv/bin/python -m unittest tests.test_services.test_incident_service tests.test_services.test_report_service tests.test_services.test_analysis_service tests.test_api.test_incidents frontend.e2e.test_incidents_page tests.test_infra.test_migrations -q` (226 tests).
- 2026-05-22: Final sixth-pass lint and formatting checks passed with `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- 2026-05-22: Final sixth-pass full regression passed with `./.venv/bin/python -m unittest discover -q` (428 tests, 1 skipped).
- 2026-05-22: Final sixth-pass UI browser validation passed with `APP_PORT=18080 npm run test:ui-review` (3 Playwright tests passed).
- 2026-05-22: Final sixth-pass focused security scan passed with `./.venv/bin/bandit -q -r models/database.py tests/test_infra/test_migrations.py`.
- 2026-05-22: Final sixth-pass diff whitespace check passed with `git diff --check`.

### Completion Notes List

- Added project-scoped incident ingestion management status over existing incident records, including import source, indexed/rejected counts, last indexed timestamp, redaction status, freshness, and per-source failure slots.
- Added reindex support that validates all submitted incident files before replacing same-source records, optionally removes omitted sources in the same scope, and returns actionable correction paths for validation failures.
- Exposed incident management through `/api/v1/incidents/ingestion`, `/api/v1/incidents/reindex`, and a retired Python UI `/incidents` admin page linked from the primary navigation.
- Updated incident import documentation with management and reindexing behavior.
- Added ingestion source provenance so `remove_missing_sources` removes only registered managed sources in the requested project/workspace scope and preserves unrelated incident memory.
- Made reindex replacement transaction scoped, rejected duplicate source files, and persisted failed ingestion summaries for later management review.
- Exposed incident index version and freshness in report context and the context completeness panel.
- Registered original import-path successes and source-level failures in the ingestion source registry, while filtering request-level batch errors out of durable source rows.
- Allowed empty authoritative reindex requests to remove all managed sources, including previously failed source entries, without deleting unrelated manual incident memory.
- Added NULL-workspace-safe source registry uniqueness and stale report snapshot freshness rendering.
- Fixed final reviewer findings for reindex cache invalidation, reindex response metadata counts, and fail-stale report freshness when current incident snapshot lookup is unavailable.
- Fixed fourth-pass reviewer findings for incident management UI authorization, project-wide workspace source cleanup, legacy unknown incident freshness, analysis incident snapshot fallback, and migration schema coverage.
- Fixed fifth-pass reviewer findings for same-named workspace source preservation during project reindex, mixed-scope source status ordering, and complete bootstrap validation of incident ingestion source integrity constraints.
- Fixed sixth-pass reviewer finding for non-partial project/source uniqueness by making bootstrap validation require the partial `workspace_id IS NULL` predicate before stamping incident ingestion revision 023.

### File List

- `_bmad-output/implementation-artifacts/4-7-incident-ingestion-management-and-indexing.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `api/routes/incidents.py`
- `app.py`
- `docs/incident-import.md`
- `evidence/models.py`
- `migrations/versions/023_add_incident_ingestion_sources.py`
- `models/repositories/incident_records.py`
- `models/repositories/incident_ingestion_sources.py`
- `models/database.py`
- `models/tables.py`
- `services/analysis_service.py`
- `services/incident_import_service.py`
- `services/incident_service.py`
- `services/report_service.py`
- `tests/test_api/test_incidents.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_models/test_evidence_models.py`
- `tests/test_services/test_analysis_service.py`
- `tests/test_services/test_incident_service.py`
- `tests/test_services/test_report_service.py`
- `frontend/e2e/test_incidents_page.py`
- `frontend/src/components/context_completeness_panel.py`
- `ui/project_authorization.py`
- `frontend/src/screens/dashboard.py`
- `frontend/src/screens/incidents.py`
- `frontend/src/theme/tokens.css`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-22: Implemented incident ingestion management, reindexing, API/UI surfaces, docs, and regression coverage.
- 2026-05-22: Fixed second-pass reviewer findings for import registry lifecycle, authoritative source clearing, NULL-workspace uniqueness, failed-source cleanup, batch-error filtering, and stale report freshness.
- 2026-05-22: Fixed third-pass reviewer findings for reindex cache invalidation, response metadata counts, and fail-stale report freshness fallback.
- 2026-05-22: Fixed fourth-pass reviewer findings for incident UI capability gating, project-wide workspace source removal, unknown legacy incident freshness, analysis snapshot fallback, and migration schema assertions.
- 2026-05-22: Fixed fifth-pass reviewer findings for same-filename workspace source preservation, mixed-scope status ordering, and bootstrap incident ingestion source integrity checks.
- 2026-05-22: Fixed sixth-pass reviewer finding for bootstrap acceptance of non-partial project/source uniqueness.
