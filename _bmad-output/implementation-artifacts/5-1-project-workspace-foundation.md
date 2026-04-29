# Story 5.1: Project workspace foundation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform admin,
I want to create or select a lightweight project workspace before analysis,
so that reports, topology, history, and feedback stay isolated by project or repository instead of becoming a flat global pile.

## Acceptance Criteria

1. Users can create a project/workspace with project key, display name, and optional description, repository URL, and default branch.
2. Web UI requires selecting or creating a project before new manual analysis uploads, and makes the active project obvious in the shared workspace so users can change project context without returning to the dashboard upload panel.
3. API and CLI accept `project_key` or `project_id` for new analyses and project-scoped context operations.
4. GitHub integrations can accept an explicit project key and otherwise derive a stable default from repository name.
5. Analysis reports, topology imports, deployment outcomes, and reviewer feedback are scoped to a project/workspace, and dashboard/history/report views refresh consistently when the active project changes.
6. Existing installations can map legacy records into a default or unassigned project without losing history.
7. Scope explicitly excludes RBAC, SSO, org hierarchy, hosted SaaS scoping, and deep multi-tenant behavior.

### Requirement Traceability

- Primary PRD requirements: `HIS-08`, `ADM-08`, `WRK-08`
- Supporting PRD / NFR / differentiation requirements: `HIS-03`, `HIS-06`, `CTX-06`, `NFR-SEC-01`, `NFR-SEC-03`
- Coverage intent: `Delta`
- Story alignment note: This story introduces the smallest useful project/workspace container so later Epic 5 context features remain isolated by project without dragging the product into enterprise tenancy or auth scope.

## Tasks / Subtasks

- [x] Implement AC1: project/workspace model with key, display name, and optional description, repository URL, and default branch (AC: 1)
- [x] Implement AC2: web UI create/select project flow before manual analysis upload (AC: 2)
- [x] Implement AC3: API and CLI support for `project_key` or `project_id` on new analysis and project-scoped context operations (AC: 3)
- [x] Implement AC4: GitHub integration contract for explicit project key or repository-derived default (AC: 4)
- [x] Implement AC5: scope reports, topology imports, deployment outcomes, and reviewer feedback to the selected project/workspace (AC: 5)
- [x] Implement AC6: legacy-data migration or default/unassigned project mapping without history loss (AC: 6)
- [x] Implement AC7: enforce non-goals so this story does not add RBAC, SSO, org hierarchy, hosted SaaS scoping, or deep multi-tenant behavior (AC: 7)
- [x] Add deterministic tests, docs, and rollout notes covering project-scoped analysis flows and legacy mapping (AC: 1, 2, 3, 4, 5, 6, 7)
- [x] Implement AC2 refinement: shared-shell project selection/search flow that updates the active workspace across routed pages without requiring a return to the dashboard upload panel (AC: 2)
- [x] Make the active project visible in shared workspace chrome and preserve project-scoped history/report context after project changes (AC: 2, 5)
- [x] Add deterministic UI regression coverage for shared-shell project switching cues across dashboard and history surfaces (AC: 2, 5)

### Review Findings

- [x] [Review][Patch] Invalid explicit project references silently fall back to `unassigned`, so typoed `project_key`/`project_id` values can read or persist against the wrong workspace. [services/project_service.py:160]
- [x] [Review][Patch] Conflicting `project_id` and `project_key` inputs are accepted without consistency checks, which can silently scope analysis requests to the wrong project. [services/project_service.py:174]
- [x] [Review][Patch] GitHub repository-derived default keys ignore the owner/org segment, so repos like `acme/payments-api` and `othercorp/payments-api` collapse into the same workspace key. [services/project_service.py:168]
- [x] [Review][Patch] The upload UI auto-selects the default workspace on first render, so users can analyze immediately without making the explicit project selection or creation that AC2 requires. [ui/components/upload_panel.py:108]
- [x] [Review][Patch] Story 5.1 marks AC3 complete, but only analysis submission gained project parameters; project-scoped context operations are still missing from the current API and CLI surfaces. [cli/analyze.py:456]
- [x] [Review][Patch] Project-scoped topology reads can 500 if the latest `topology_versions.payload_json` row is malformed because `_load_latest_topology_payload()` blindly calls `json.loads` without converting JSON failures into a `TopologyStatus` validation response. [services/topology_service.py:63]
- [x] [Review][Patch] History previous-scan diff badges are keyed only by analyzed filenames, so unscoped history queries can compare unrelated projects that happened to scan the same file names. [services/report_service.py:705]
- [x] [Review][Patch] Direct report fetches remain unscoped because `fetch_analysis_report(report_id)` ignores project identity, so guessed report IDs can still expose another workspace’s detail view and comparisons. [services/report_service.py:1072]
- [x] [Review][Patch] The upload widget stays enabled before any project is selected or created, so AC2 is only enforced at analyze time instead of before manual uploads begin. [ui/components/upload_panel.py:436]
- [x] [Review][Patch] Default-project topology saves write to the database before mirroring the legacy file path, so an `OSError` on the legacy write leaves the compatibility file out of sync after commit. [services/topology_service.py:337]
- [x] [Review][Patch] `deploywhisper project` and `deploywhisper topology` accept missing subcommands and fall through to a success exit with the generic CLI banner instead of failing fast for automation callers. [cli/analyze.py:551]
- [x] [Review][Patch] API detail fetch still exposes cross-project reports when callers omit `project_id` / `project_key`, so report scoping is optional rather than enforced. [api/routes/analyses.py:231]
- [x] [Review][Patch] Partially invalid dual project references still succeed if one reference resolves and the other does not, so explicit scoping is not fully strict for API/CLI/context operations. [services/project_service.py:179]
- [x] [Review][Patch] Switching the selected project after files are already uploaded preserves the pending artifacts, so users can analyze files under a different workspace than the one they uploaded them for. [ui/components/upload_panel.py:200]
- [x] [Review][Patch] The settings page captures `active_project` at render time, so changing project before a topology upload can save topology into a stale workspace. [ui/routes/settings.py:275]
- [x] [Review][Patch] A missing `DEPLOYWHISPER_GITHUB_PROJECT_KEY` target currently propagates out of GitHub webhook handling instead of becoming a controlled configuration error or a created project. [integrations/github/app_service.py:380]
- [x] [Review][Patch] Changing the selected project after artifacts have already been uploaded still preserves the staged files, so users can run analysis under a different workspace than the one they uploaded the artifacts for. [ui/components/upload_panel.py:230]
- [x] [Review][Dismiss] Public report pages still bypass workspace isolation: `/reports/{id}` fetches any report by numeric ID and `fetch_shared_analysis_report()` treats every report as shareable unless a password is configured, so a guessed report URL can expose another workspace’s report outside project context. [app.py:434] — handled intentionally by Story 3.4’s accepted public-share contract
- [ ] [Review][Patch] Analysis list/detail project scoping is still inconsistent: `GET /api/v1/analyses` remains unscoped by default while `GET /api/v1/analyses/{id}` defaults to `unassigned`, so listed non-default reports can look missing unless the caller already knows the owning project. [api/routes/analyses.py:117]
- [ ] [Review][Patch] The dashboard can still render an `unassigned` active result while the upload flow says no workspace is selected, creating contradictory workspace state on first load. [ui/components/upload_panel.py:197]

## Dev Notes

- Epic context: Context Moat (2, 15-22 (overlaps Epics 3-4), P1).
- Epic goal: Add lightweight project/workspace isolation, automate topology discovery across supported infrastructure sources, capture deployment outcomes, and build the feedback loop. This epic turns DeployWhisper from "smart on day 1" to "measurably smarter every month" without expanding into enterprise auth or multi-tenant scope.
- This story is intentionally closer to SonarQube's project key model than to tenancy or permissions. Keep it lightweight and operator-friendly.
- Preserve the local-first and advisory-first posture. Project scoping is an isolation and history-organization feature, not a policy or auth feature.
- Keep the shared-core architecture intact: UI, API, and CLI must reuse one project-aware service boundary rather than inventing per-surface project handling.
- Existing saved analyses must remain visible through a safe default/unassigned project path rather than being dropped or silently reassigned.
- GitHub Action runtime/package lives in the external `deploywhisper/analyze-action` repo. This app repo should implement the API/docs/integration contract for project keys and repo-derived defaults, not host action runtime code.
- Do not add RBAC, SSO, org hierarchy, hosted SaaS scoping, or per-team permissions in this story.

### Project Structure Notes

- Likely implementation surfaces: `models/tables.py`, `models/repositories/`, `services/report_service.py`, `services/analysis_service.py`, `api/routes/`, `api/schemas.py`, `cli/analyze.py`, `ui/components/upload_panel.py`, `ui/routes/`, and tests under `tests/test_api`, `tests/test_services`, `tests/test_cli`, `tests/test_ui`.
- Persist project identity through structured models and repository methods; avoid ad-hoc JSON fields for core scoping.
- Keep project selection and project default derivation explicit in the shared service layer so UI/API/CLI/GitHub integrations stay consistent.

### References

- [Epics](../planning-artifacts/epics.md)
- [PRD](../planning-artifacts/prd.md)
- [Architecture](../planning-artifacts/architecture.md)
- [Project Context](../project-context.md)
- [Sprint Change Proposal](../planning-artifacts/sprint-change-proposal-2026-04-27-epic-5-project-workspace-foundation.md)
- [Sprint Change Proposal](../planning-artifacts/sprint-change-proposal-2026-04-28-epic-5-project-switching.md)

## Dev Agent Record

### Agent Model Used

GPT-5 (Codex)

### Debug Log References

- 2026-04-28T14:10:00+05:30: `./.venv/bin/python -m unittest -q tests.test_services.test_project_service tests.test_services.test_topology_service tests.test_api.test_projects tests.test_api.test_analyses tests.test_cli.test_analyze tests.test_ui.test_upload_panel tests.test_services.test_report_service`
- 2026-04-28T14:32:00+05:30: `./.venv/bin/python -m unittest -q tests.test_services.test_github_app_service tests.test_models.test_evidence_tables tests.test_infra.test_migrations tests.test_infra.test_container_contract tests.test_ui.test_upload_panel tests.test_ui.test_settings_page tests.test_ui.test_history_page tests.test_ui.test_app_shell tests.test_api.test_projects tests.test_api.test_analyses tests.test_services.test_project_service tests.test_services.test_topology_service tests.test_services.test_report_service tests.test_cli.test_analyze`
- 2026-04-28T14:38:00+05:30: `./.venv/bin/ruff check .`
- 2026-04-28T14:39:00+05:30: `./.venv/bin/ruff format --check .`
- 2026-04-28T14:50:00+05:30: `./.venv/bin/python -m unittest discover -q`
- 2026-04-28T15:02:00+05:30: `bash scripts/ci-local.sh`
- 2026-04-28T16:10:00+05:30: `./.venv/bin/python -m unittest -q tests.test_services.test_project_service tests.test_services.test_topology_service tests.test_api.test_analyses tests.test_api.test_projects tests.test_api.test_context tests.test_cli.test_analyze tests.test_services.test_github_app_service tests.test_ui.test_upload_panel`
- 2026-04-28T16:20:00+05:30: `./.venv/bin/ruff check .`
- 2026-04-28T16:21:00+05:30: `./.venv/bin/ruff format --check .`
- 2026-04-28T16:28:00+05:30: `./.venv/bin/python -m unittest discover -q`
- 2026-04-28T16:38:00+05:30: `bash scripts/ci-local.sh`
- 2026-04-28T17:20:00+05:30: `./.venv/bin/python -m unittest -q tests.test_services.test_topology_service tests.test_services.test_report_service tests.test_ui.test_history_page tests.test_ui.test_upload_panel tests.test_api.test_analyses tests.test_cli.test_analyze`
- 2026-04-28T17:26:00+05:30: `./.venv/bin/ruff check .`
- 2026-04-28T17:27:00+05:30: `./.venv/bin/ruff format --check .`
- 2026-04-28T17:32:00+05:30: `./.venv/bin/python -m unittest discover -q`
- 2026-04-28T17:43:00+05:30: `bash scripts/ci-local.sh`
- 2026-04-28T18:05:00+05:30: `./.venv/bin/python -m unittest -q tests.test_services.test_project_service tests.test_ui.test_upload_panel tests.test_api.test_analyses tests.test_services.test_github_app_service tests.test_services.test_report_service tests.test_services.test_topology_service tests.test_ui.test_history_page tests.test_cli.test_analyze`
- 2026-04-28T18:14:00+05:30: `./.venv/bin/ruff check .`
- 2026-04-28T18:15:00+05:30: `./.venv/bin/ruff format --check .`
- 2026-04-28T18:18:00+05:30: `./.venv/bin/python -m unittest discover -q`
- 2026-04-28T18:29:00+05:30: `bash scripts/ci-local.sh`
- 2026-04-28T19:05:00+05:30: `./.venv/bin/python -m unittest -q tests.test_ui.test_upload_panel tests.test_ui.test_history_page tests.test_api.test_analyses tests.test_services.test_project_service`
- 2026-04-28T19:05:00+05:30: `./.venv/bin/ruff check ui/components/upload_panel.py tests/test_ui/test_upload_panel.py`
- 2026-04-28T19:20:00+05:30: Story 5.1 re-review triage reconciled the remaining public-share concern against Story 3.4’s accepted `/reports/{id}` contract; no actionable 5.1 findings remained
- 2026-04-28T21:05:00+05:30: `./.venv/bin/python -m unittest -q tests.test_ui.test_project_workspace_switcher tests.test_ui.test_app_shell tests.test_ui.test_history_page tests.test_ui.test_upload_panel tests.test_ui.test_settings_page`
- 2026-04-28T21:10:00+05:30: `./.venv/bin/ruff check .`
- 2026-04-28T21:11:00+05:30: `./.venv/bin/ruff format ui/theme.py`
- 2026-04-28T21:11:00+05:30: `./.venv/bin/ruff format --check .`
- 2026-04-28T21:14:00+05:30: `./.venv/bin/python -m unittest discover -q`
- 2026-04-28T21:16:00+05:30: `bash scripts/ci-local.sh`

### Completion Notes List

- Added first-class project/workspace persistence with migration `010_add_project_workspaces`, project-aware report scoping, per-project topology storage, and scoped placeholder tables for deployment outcomes and reviewer feedback.
- Added shared project services plus `GET/POST /api/v1/projects`, project-aware analysis intake in the API and CLI, and project metadata on persisted report payloads and history filters.
- Updated the dashboard upload flow to require an explicit project workspace selection or creation before manual analysis, and scoped dashboard/history/settings views to the active project context.
- Updated the GitHub App integration to accept an explicit `DEPLOYWHISPER_GITHUB_PROJECT_KEY` override and otherwise derive a stable project key from the repository name, creating the project on demand.
- Documented rollout and legacy-mapping behavior in `docs/project-workspaces.md`, including the compatibility path for existing reports and file-based topology.
- Validation passed with repo-wide Ruff checks, full `unittest discover -q`, and `scripts/ci-local.sh`. Local CI still skipped Bandit because it is not installed in this environment.
- Fixed the Story 5.1 review findings by making explicit project references fail fast, rejecting conflicting `project_id`/`project_key` inputs, switching GitHub default derivation to owner-safe keys, requiring explicit upload-project selection before manual analysis, and adding project-scoped topology context operations for the API and CLI.
- Fixed the second Story 5.1 review pass by scoping direct report/history comparison retrieval to projects, handling malformed stored topology payloads as validation responses, failing topology legacy-mirror writes before DB commit, disabling uploads before project selection, and making `project` / `topology` CLI subcommands mandatory for automation callers.
- Fixed the third Story 5.1 review pass by default-scoping API detail fetches to `unassigned`, rejecting partially invalid dual project references, clearing staged uploads on project switch, resolving the current project at settings-upload time, and allowing GitHub explicit project-key overrides to create or fail in a controlled way.
- Verified the final Story 5.1 rerun finding is resolved in the live upload-panel flow: switching projects with staged artifacts clears pending uploads and requires re-upload under the newly selected workspace.
- Re-ran code review after all patches. No actionable Story 5.1 findings remain; the only residual concern was the intentional public-share behavior introduced and accepted in Story 3.4.
- Applied the 2026-04-28 project-switching correction by adding a shared-shell project selector with global create-project access, making the active/default workspace visible across routed pages, and extending regression coverage so dashboard/history surfaces reflect the same active project context.
- Validation passed again after the cross-page workspace refinement: focused UI unittests, repo-wide Ruff check/format check, full `unittest discover -q`, and `scripts/ci-local.sh` all passed. Local CI still skipped Bandit because it is not installed in this environment.

### File List

- _bmad-output/implementation-artifacts/5-1-project-workspace-foundation.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- api/routes/analyses.py
- api/routes/projects.py
- api/routes/settings.py
- api/schemas.py
- app.py
- cli/analyze.py
- data/deploywhisper.db
- docs/project-workspaces.md
- integrations/github/app_service.py
- migrations/versions/010_add_project_workspaces.py
- models/database.py
- models/repositories/analysis_reports.py
- models/repositories/projects.py
- models/tables.py
- services/analysis_service.py
- services/project_service.py
- services/report_service.py
- services/topology_service.py
- tests/test_api/test_analyses.py
- tests/test_api/test_context.py
- tests/test_api/test_projects.py
- tests/test_cli/test_analyze.py
- tests/test_infra/test_container_contract.py
- tests/test_infra/test_migrations.py
- tests/test_models/test_evidence_tables.py
- tests/test_services/test_github_app_service.py
- tests/test_services/test_project_service.py
- tests/test_services/test_report_service.py
- tests/test_services/test_topology_service.py
- tests/test_ui/test_app_shell.py
- tests/test_ui/test_project_workspace_switcher.py
- tests/test_ui/test_settings_page.py
- tests/test_ui/test_upload_panel.py
- ui/components/project_workspace_switcher.py
- ui/components/upload_panel.py
- ui/routes/dashboard.py
- ui/routes/history.py
- ui/routes/settings.py
- ui/theme.py
- _bmad-output/planning-artifacts/ux-design-specification.md

### Change Log

- 2026-04-28: Implemented project workspace foundations across persistence, UI/API/CLI intake, topology scoping, GitHub project derivation, and rollout documentation.
- 2026-04-28: Refined Story 5.1 so project switching is available from shared workspace chrome, with active-project visibility and cross-page UI regression coverage.
