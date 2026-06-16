# Story 1.2: Project-Aware Analysis Submission

Status: review

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform engineer,
I want to provide or derive a project key during analysis,
So that reports are saved under the correct project.

## Acceptance Criteria

1. Given a user submits artifacts through UI, API, CLI, or GitHub flow, When a project key is provided or derivable, Then the analysis run and report are associated with that project. And missing or ambiguous project scope produces an explicit, actionable message.
2. Given a project key references an unknown, conflicting, or otherwise invalid project in the current local/admin phase, When analysis submission is attempted, Then the request is rejected before parsing artifacts. And no report, incident, outcome, feedback, topology, or scanner data is associated with that unauthorized project reference. Full project membership and role enforcement remains deferred to the lightweight RBAC story.

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

- [x] [Review][Decision] Missing analysis scope still falls back to the default project — Fixed by requiring explicit or derived project scope in the shared analysis submission path before parsing, returning `missing_project_scope` for API/CLI submissions without `project_key` or `project_id`, and updating docs/tests to preserve `unassigned` only as a legacy/default topology mapping.
- [x] [Review][Decision] Story AC2 requires unauthorized-project rejection but the current codebase has no caller access model — Resolved by clarifying the Story 1.2 local/admin phase scope: invalid/unknown/conflicting project references are rejected before parsing, while full project membership and role checks remain deferred to the lightweight RBAC story. Evidence: `_bmad-output/implementation-artifacts/1-2-project-aware-analysis-submission.md`, `docs/project-workspaces.md`.
- [x] [Review][Patch] Stale UI active-project selection can fall back to `unassigned` for new manual uploads — Fixed by validating saved active-project settings against existing project records before treating them as a selected project. [`services/project_service.py:449`]
- [x] [Review][Patch] `POST /api/v1/analyses` can return `404 project_not_found` but the route response contract omits 404 — Fixed by adding `404` to the route response model declaration. [`api/routes/analyses.py:153`]
- [x] [Review][Patch] Documented `project_id` analysis submission path lacks a direct success regression after the pre-parse resolution change — Fixed with direct API and CLI `project_id` success regressions. [`tests/test_api/test_analyses.py:330`]
- [x] [Review][Patch] UI and GitHub derivation handoffs are not covered by tests that exercise the new shared missing-scope guard end-to-end — Fixed with UI missing-scope guard coverage and a GitHub webhook test that runs the real shared analysis path with a repository-derived project. [`frontend/e2e/test_upload_panel.py:35`]
- [x] [Review][Patch] Explicit GitHub project override still auto-creates unknown scope — Fixed by treating `DEPLOYWHISPER_GITHUB_PROJECT_KEY` as an explicit existing-project reference while preserving auto-create only for repository-derived keys. [`integrations/github/app_service.py:384`]
- [x] [Review][Patch] Malformed GitHub project override is not normalized into a configuration error — Fixed by normalizing `ProjectResolutionError` and project-key validation `ValueError` into `GitHubAppConfigurationError` before analysis execution. [`integrations/github/app_service.py:391`]
- [x] [Review][Patch] Public API/CLI contract still advertises analysis project scope as optional — Fixed FastAPI field descriptions and CLI help text to state that either `project_key`/`--project` or `project_id`/`--project-id` is required. [`api/routes/analyses.py:169`, `cli/analyze.py:589`]
- [x] [Review][Patch] GitHub webhook masks invalid project scope as generic app misconfiguration — Fixed by adding a project-scope-specific GitHub App exception and mapping it to project error codes/statuses in the webhook route. [`api/routes/github_app.py:109`, `integrations/github/app_service.py:391`]
- [x] [Review][Patch] Conflicting project references are not regression-locked as pre-parse failures on API/CLI — Fixed by adding no-parse/no-report assertions to the API and CLI conflicting-reference regressions. [`tests/test_api/test_analyses.py:581`, `tests/test_cli/test_analyze.py:1254`]
- [x] [Review][Patch] Whitespace `project_key` breaks otherwise valid `project_id` submissions — Fixed by trimming blank project keys before project resolution and adding API, CLI, and service regressions for `project_id` plus blank `project_key`. [`services/analysis_service.py:682`, `services/project_service.py:357`]
- [x] [Review][Patch] Missing-scope fast-fail is still masked by API/CLI artifact preflight — Fixed by resolving required analysis scope before API/CLI artifact read/classification and adding unsupported-input regressions that now return `missing_project_scope` when scope is absent. [`api/routes/analyses.py:189`, `cli/analyze.py:283`]
- [x] [Review][Patch] Stale active-project recovery is inconsistent across pages — Fixed by making history list/detail pages use the same valid-saved-selection check as uploads before applying active project scope. [`frontend/src/components/upload_panel.py:142`, `frontend/src/screens/history.py:39`]
- [x] [Review][Decision] GitHub webhook project-scope failures now return non-2xx responses and may trigger repeated webhook retries — Fixed by acknowledging project-scope failures as handled webhook results, surfacing the project error in the response/check-run note, and skipping analysis/report creation. [`api/routes/github_app.py:109`, `integrations/github/app_service.py:391`]
- [x] [Review][Patch] Whitespace-only `project_key` can still resolve to the default project in the generic resolver — Fixed by rejecting blank-key-only references while still allowing valid `project_id` plus blank `project_key` form submissions. [`services/project_service.py:357`]
- [x] [Review][Patch] Stale deleted project selection makes `/history` unscoped while the shell can still advertise `Unassigned` — Fixed by scoping stale/no-saved-selection history views to `get_active_project()`'s default-project fallback instead of passing no project filter. [`frontend/src/screens/history.py:39`]
- [x] [Review][Patch] Repository-derived GitHub project keys can collide across distinct repositories and silently reuse the wrong project — Fixed by canonicalizing repository references, checking existing repository ownership before reuse, and adding a deterministic hash suffix for derived-key collisions. [`services/project_service.py:175`, `integrations/github/app_service.py:392`]
- [x] [Review][Patch] GitHub project-scope errors are only wrapped before the second shared-scope resolution, leaving a possible 500 if the project changes between lookup and analysis — Fixed by catching late shared-analysis project resolution failures and returning the same handled webhook result as initial project-scope failures. [`integrations/github/app_service.py:391`, `services/analysis_service.py:712`]
- [x] [Review][Patch] Repository-collision fallback still merges unrelated repositories when the existing matching project has no stored `repository_url` — Fixed by treating missing stored repository URLs as unconfirmed matches for repository-derived scope and forcing the collision-safe hashed key path. [`services/project_service.py:207`, `tests/test_services/test_project_service.py:325`]
- [x] [Review][Patch] GitHub webhook downgrades arbitrary analysis `ValueError`s into neutral project-scope no-ops — Fixed by allowing only known project-scope `ValueError` codes to become handled webhook results; unrelated analysis `ValueError`s now propagate as operational failures. [`integrations/github/app_service.py:459`, `tests/test_services/test_github_app_service.py:373`]
- [x] [Review][Patch] GitHub explicit project-scope failures do not fail fast before artifact download/classification — Fixed by resolving explicit GitHub project overrides immediately after webhook metadata/token validation and before PR artifact download or classification, with regressions asserting artifact loading is skipped. [`integrations/github/app_service.py:341`, `tests/test_services/test_github_app_service.py:247`]
- [x] [Review][Patch] Repository-derived project resolution ignores an existing project already bound to the same `repository_url` when its project key is custom — Fixed by preferring canonical repository-url matches before derived-key creation, preserving custom project keys for repository-derived submissions. [`services/project_service.py:399`, `tests/test_services/test_project_service.py:348`]
- [x] [Review][Patch] Legacy repository-backed projects with the derived project key and missing `repository_url` can silently fork into a new suffixed project instead of being reused and backfilled — Superseded by the later data-isolation decision: missing `repository_url` is treated as unconfirmed ownership, so repository-derived submissions use the collision-safe hashed key instead of display-name-based backfill. [`services/project_service.py:207`, `tests/test_services/test_project_service.py:362`]
- [x] [Review][Patch] Whitespace-only explicit project keys are normalized as missing scope, and a blank GitHub override is treated as unset instead of invalid explicit scope — Fixed by preserving blank-explicit state through shared analysis scope resolution and GitHub env override handling, returning `invalid_project_reference` before parsing or artifact download. [`services/analysis_service.py:688`, `integrations/github/app_service.py:347`, `tests/test_services/test_github_app_service.py:332`]
- [x] [Review][Decision] Repository-collision legacy backfill can silently bind a manually created project — Resolved in favor of data isolation: removed the display-name-based backfill heuristic, and records without `repository_url` now remain unconfirmed collisions that route repository-derived submissions to a deterministic hashed key. [`services/project_service.py:469`, `tests/test_services/test_project_service.py:362`]
- [x] [Review][Patch] Repository canonicalization misses common SSH/SCP-style Git remotes — Fixed by normalizing SCP-style Git remotes like `git@github.com:owner/repo.git` to the same canonical `owner/repo` form used by HTTPS remotes. [`services/project_service.py:189`, `tests/test_services/test_project_service.py:386`]
- [x] [Review][Patch] Repository matching drops the SCM host, so different remotes with the same owner/repo path can merge into the same project — Fixed by preserving the SCM host in canonical repository identity while keeping user-facing derived project keys path-based, and by passing host-aware GitHub repository references from webhook handling. [`services/project_service.py:188`, `integrations/github/app_service.py:530`, `tests/test_services/test_project_service.py:407`]

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 1 / Story 1.2 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5

### Debug Log References

- `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_rejects_unknown_project_before_parsing tests.test_cli.test_analyze.AnalyzeCliTests.test_analyze_command_rejects_unknown_project_before_parsing` - failed before implementation, proving the regressions reached parsing.
- `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_rejects_unknown_project_before_parsing tests.test_cli.test_analyze.AnalyzeCliTests.test_analyze_command_rejects_unknown_project_before_parsing` - passed after moving project resolution earlier.
- `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_cli.test_analyze frontend.e2e.test_upload_panel tests.test_services.test_github_app_service tests.test_services.test_analysis_service -q` - passed, 90 tests.
- `./.venv/bin/ruff check .` - passed.
- `./.venv/bin/ruff format --check .` - passed, 254 files already formatted.
- `./.venv/bin/python -m bandit --version` - Bandit unavailable in the virtualenv.
- `./.venv/bin/python -m unittest discover -q` - passed, 238 tests, 1 skipped.
- `bash scripts/ci-local.sh` - passed; local CI skipped Bandit because it is not installed.
- `./.venv/bin/python -m unittest tests.test_services.test_analysis_service.AnalysisServiceTests.test_analyze_uploaded_files_requires_explicit_project_scope_before_parsing tests.test_api.test_analyses tests.test_cli.test_analyze frontend.e2e.test_upload_panel tests.test_services.test_github_app_service -q` - passed, 81 tests.
- `./.venv/bin/ruff check .` - passed after review fix.
- `./.venv/bin/ruff format --check .` - failed on `tests/test_cli/test_analyze.py`; `./.venv/bin/ruff format tests/test_cli/test_analyze.py` formatted the file.
- `./.venv/bin/ruff check .` - passed after formatting.
- `./.venv/bin/ruff format --check .` - passed, 254 files already formatted.
- `./.venv/bin/python -m unittest discover -q` - passed after review fix, 239 tests, 1 skipped.
- `bash scripts/ci-local.sh` - passed after review fix; local CI skipped Bandit because it is not installed.
- `bmad-code-review` rerun - found 1 decision-needed item and 4 patch items; story returned to in-progress for follow-up.
- `./.venv/bin/python -m unittest tests.test_services.test_project_service.ProjectServiceTests.test_active_project_selection_flag_ignores_stale_saved_project tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_accepts_project_id tests.test_cli.test_analyze.AnalyzeCliTests.test_analyze_command_accepts_project_id frontend.e2e.test_upload_panel.UploadPanelTests.test_run_uploaded_analysis_requires_project_scope_before_parsing tests.test_services.test_github_app_service.GitHubAppServiceTests.test_handle_github_app_webhook_derives_project_for_real_analysis -q` - passed, 5 tests.
- `./.venv/bin/python -m unittest tests.test_services.test_project_service tests.test_api.test_analyses tests.test_cli.test_analyze frontend.e2e.test_upload_panel tests.test_services.test_github_app_service -q` - passed, 104 tests.
- `./.venv/bin/ruff check .` - passed after rerun-review fixes.
- `./.venv/bin/ruff format --check .` - passed, 254 files already formatted.
- `./.venv/bin/python -m unittest discover -q` - passed after rerun-review fixes, 241 tests, 1 skipped.
- `bash scripts/ci-local.sh` - passed after rerun-review fixes; local CI skipped Bandit because it is not installed.
- `bmad-code-review` rerun - found 3 patch items; story returned to in-progress for follow-up.
- `./.venv/bin/ruff check integrations/github/app_service.py api/routes/analyses.py cli/analyze.py tests/test_services/test_github_app_service.py` - passed after latest review-finding fixes.
- `./.venv/bin/ruff format --check integrations/github/app_service.py api/routes/analyses.py cli/analyze.py tests/test_services/test_github_app_service.py` - passed, 4 files already formatted.
- `./.venv/bin/python -m unittest tests.test_services.test_github_app_service.GitHubAppServiceTests.test_handle_github_app_webhook_prefers_explicit_project_key_override tests.test_services.test_github_app_service.GitHubAppServiceTests.test_handle_github_app_webhook_rejects_unknown_explicit_project_override tests.test_services.test_github_app_service.GitHubAppServiceTests.test_handle_github_app_webhook_rejects_malformed_project_override -q` - passed, 3 tests.
- `./.venv/bin/python -m unittest tests.test_services.test_github_app_service tests.test_api.test_analyses tests.test_cli.test_analyze -q` - passed, 80 tests.
- `./.venv/bin/ruff check .` - passed after latest review-finding fixes.
- `./.venv/bin/ruff format --check .` - passed, 254 files already formatted.
- `./.venv/bin/python -m unittest discover -q` - passed after latest review-finding fixes, 241 tests, 1 skipped.
- `bash scripts/ci-local.sh` - passed after latest review-finding fixes; local CI skipped Bandit because it is not installed.
- `bmad-code-review` rerun - Blind Hunter reported 2 intentional compatibility changes that were dismissed against Story 1.2 scope; Acceptance Auditor found 2 patch items; Edge Case Hunter found 3 patch items.
- `./.venv/bin/ruff check services/project_service.py services/analysis_service.py api/routes/analyses.py cli/analyze.py integrations/github/app_service.py api/routes/github_app.py frontend/src/screens/history.py tests/test_api/test_analyses.py tests/test_cli/test_analyze.py tests/test_services/test_project_service.py tests/test_api/test_github_app.py tests/test_services/test_github_app_service.py frontend/e2e/test_history_page.py` - passed after latest review-finding fixes.
- `./.venv/bin/ruff format --check services/project_service.py services/analysis_service.py api/routes/analyses.py cli/analyze.py integrations/github/app_service.py api/routes/github_app.py frontend/src/screens/history.py tests/test_api/test_analyses.py tests/test_cli/test_analyze.py tests/test_services/test_project_service.py tests/test_api/test_github_app.py tests/test_services/test_github_app_service.py frontend/e2e/test_history_page.py` - passed, 13 files already formatted.
- `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_cli.test_analyze tests.test_services.test_project_service tests.test_api.test_github_app tests.test_services.test_github_app_service frontend.e2e.test_history_page -q` - passed, 129 tests.
- `./.venv/bin/ruff check .` - passed after latest review-finding fixes.
- `./.venv/bin/ruff format --check .` - passed, 254 files already formatted.
- `./.venv/bin/python -m unittest discover -q` - passed after latest review-finding fixes, 245 tests, 1 skipped.
- `bash scripts/ci-local.sh` - passed after latest review-finding fixes; local CI skipped Bandit because it is not installed.
- `bmad-code-review` rerun - Acceptance Auditor found no findings; Blind Hunter and Edge Case Hunter found 1 decision-needed item and 4 patch items; story returned to in-progress for follow-up.
- `./.venv/bin/python -m unittest tests.test_services.test_project_service tests.test_services.test_github_app_service tests.test_api.test_github_app frontend.e2e.test_history_page -q` - failed before final collision canonicalization; repository URL and owner/repo forms created different project keys.
- `./.venv/bin/python -m unittest tests.test_services.test_project_service tests.test_services.test_github_app_service tests.test_api.test_github_app frontend.e2e.test_history_page -q` - passed after reviewer-finding fixes, 63 tests.
- `./.venv/bin/ruff check services/project_service.py integrations/github/app_service.py api/routes/github_app.py frontend/src/screens/history.py tests/test_services/test_project_service.py tests/test_services/test_github_app_service.py tests/test_api/test_github_app.py frontend/e2e/test_history_page.py` - passed.
- `./.venv/bin/ruff format --check services/project_service.py integrations/github/app_service.py api/routes/github_app.py frontend/src/screens/history.py tests/test_services/test_project_service.py tests/test_services/test_github_app_service.py tests/test_api/test_github_app.py frontend/e2e/test_history_page.py` - failed; `services/project_service.py` and `tests/test_services/test_github_app_service.py` needed formatting.
- `./.venv/bin/ruff format services/project_service.py tests/test_services/test_github_app_service.py` - reformatted 2 files.
- `./.venv/bin/ruff check services/project_service.py integrations/github/app_service.py api/routes/github_app.py frontend/src/screens/history.py tests/test_services/test_project_service.py tests/test_services/test_github_app_service.py tests/test_api/test_github_app.py frontend/e2e/test_history_page.py` - passed after formatting.
- `./.venv/bin/ruff format --check services/project_service.py integrations/github/app_service.py api/routes/github_app.py frontend/src/screens/history.py tests/test_services/test_project_service.py tests/test_services/test_github_app_service.py tests/test_api/test_github_app.py frontend/e2e/test_history_page.py` - passed, 8 files already formatted.
- `./.venv/bin/ruff check .` - passed after reviewer-finding fixes.
- `./.venv/bin/ruff format --check .` - passed, 254 files already formatted.
- `./.venv/bin/python -m unittest discover -q` - passed after reviewer-finding fixes, 245 tests, 1 skipped.
- `bash scripts/ci-local.sh` - passed after reviewer-finding fixes; local CI skipped Bandit because it is not installed.
- `bmad-code-review` rerun - found 3 patch items across Blind Hunter, Edge Case Hunter, and Acceptance Auditor; story returned to in-progress for follow-up.
- `./.venv/bin/python -m unittest tests.test_services.test_project_service tests.test_services.test_github_app_service tests.test_api.test_github_app frontend.e2e.test_history_page -q` - passed after latest reviewer-finding fixes, 66 tests.
- `./.venv/bin/ruff check services/project_service.py integrations/github/app_service.py tests/test_services/test_project_service.py tests/test_services/test_github_app_service.py` - passed.
- `./.venv/bin/ruff format --check services/project_service.py integrations/github/app_service.py tests/test_services/test_project_service.py tests/test_services/test_github_app_service.py` - passed, 4 files already formatted.
- `./.venv/bin/ruff check .` - passed after latest reviewer-finding fixes.
- `./.venv/bin/ruff format --check .` - passed, 254 files already formatted.
- `./.venv/bin/python -m unittest discover -q` - passed after latest reviewer-finding fixes, 245 tests, 1 skipped.
- `bash scripts/ci-local.sh` - passed after latest reviewer-finding fixes; local CI skipped Bandit because it is not installed.
- `bmad-code-review` rerun - Acceptance Auditor found no findings; Blind Hunter and Edge Case Hunter found 3 patch items; story returned to in-progress for follow-up.
- `./.venv/bin/python -m unittest tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_reuses_custom_key_repository_match tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_backfills_legacy_repository_match tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_disambiguates_manual_key_collision tests.test_services.test_analysis_service.AnalysisServiceTests.test_resolve_analysis_project_scope_rejects_blank_explicit_key tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_rejects_blank_explicit_project_key_before_parsing tests.test_cli.test_analyze.AnalyzeCliTests.test_analyze_command_rejects_blank_explicit_project_key_before_parsing tests.test_services.test_github_app_service.GitHubAppServiceTests.test_handle_github_app_webhook_handles_blank_project_override -q` - failed before reviewer-finding fixes, proving repository reuse/backfill and blank-explicit-scope regressions.
- `./.venv/bin/python -m unittest tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_reuses_custom_key_repository_match tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_backfills_legacy_repository_match tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_disambiguates_manual_key_collision tests.test_services.test_analysis_service.AnalysisServiceTests.test_resolve_analysis_project_scope_rejects_blank_explicit_key tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_rejects_blank_explicit_project_key_before_parsing tests.test_cli.test_analyze.AnalyzeCliTests.test_analyze_command_rejects_blank_explicit_project_key_before_parsing tests.test_services.test_github_app_service.GitHubAppServiceTests.test_handle_github_app_webhook_handles_blank_project_override -q` - passed after reviewer-finding fixes, 7 tests.
- `./.venv/bin/python -m unittest tests.test_services.test_project_service tests.test_services.test_analysis_service tests.test_api.test_analyses tests.test_cli.test_analyze tests.test_services.test_github_app_service -q` - passed after reviewer-finding fixes, 131 tests.
- `./.venv/bin/ruff check services/project_service.py services/analysis_service.py integrations/github/app_service.py tests/test_services/test_project_service.py tests/test_services/test_analysis_service.py tests/test_api/test_analyses.py tests/test_cli/test_analyze.py tests/test_services/test_github_app_service.py` - passed after reviewer-finding fixes.
- `./.venv/bin/ruff format --check services/project_service.py services/analysis_service.py integrations/github/app_service.py tests/test_services/test_project_service.py tests/test_services/test_analysis_service.py tests/test_api/test_analyses.py tests/test_cli/test_analyze.py tests/test_services/test_github_app_service.py` - passed after formatting, 8 files already formatted.
- `./.venv/bin/ruff check .` - passed after reviewer-finding fixes.
- `./.venv/bin/ruff format --check .` - passed after reviewer-finding fixes, 254 files already formatted.
- `./.venv/bin/python -m unittest discover -q` - passed after reviewer-finding fixes, 246 tests, 1 skipped.
- `bash scripts/ci-local.sh` - passed after reviewer-finding fixes; local CI skipped Bandit because it is not installed.
- `bmad-code-review` rerun - Blind Hunter found 1 decision-needed item and 1 patch item after dismissing the blank GitHub override concern as intentional explicit-scope behavior from the prior Story 1.2 review; Acceptance Auditor found no findings; Edge Case Hunter timed out twice, so the layer was marked failed and the story returned to in-progress.
- `./.venv/bin/python -m unittest tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_disambiguates_missing_repository_url_collision tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_reuses_scp_style_repository_remote tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_reuses_same_repository_key tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_disambiguates_manual_key_collision tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_reuses_custom_key_repository_match -q` - passed after latest reviewer-finding fixes, 5 tests.
- `./.venv/bin/python -m unittest tests.test_services.test_project_service tests.test_services.test_github_app_service -q` - passed after latest reviewer-finding fixes, 46 tests.
- `./.venv/bin/ruff check services/project_service.py tests/test_services/test_project_service.py` - passed after latest reviewer-finding fixes.
- `./.venv/bin/ruff format --check services/project_service.py tests/test_services/test_project_service.py` - passed after latest reviewer-finding fixes, 2 files already formatted.
- `./.venv/bin/ruff check .` - passed after latest reviewer-finding fixes.
- `./.venv/bin/ruff format --check .` - passed after latest reviewer-finding fixes, 254 files already formatted.
- `./.venv/bin/python -m unittest discover -q` - passed after latest reviewer-finding fixes, 246 tests, 1 skipped.
- `bash scripts/ci-local.sh` - passed after latest reviewer-finding fixes; local CI skipped Bandit because it is not installed.
- `bmad-code-review` rerun - Blind Hunter found 1 patch item after dismissing the UI scope handoff concern as already handled in `frontend/src/components/upload_panel.py` and the blank GitHub override concern as intentional explicit-scope behavior from prior Story 1.2 review; Edge Case Hunter and Acceptance Auditor timed out twice, so those layers were marked failed and the story returned to in-progress.
- `./.venv/bin/python -m unittest tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_disambiguates_same_path_cross_host_remote tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_reuses_scp_style_repository_remote tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_reuses_same_repository_key tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_reuses_custom_key_repository_match tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_disambiguates_repository_key_collision tests.test_services.test_project_service.ProjectServiceTests.test_resolve_project_reference_disambiguates_missing_repository_url_collision -q` - passed after latest reviewer-finding fixes, 6 tests.
- `./.venv/bin/python -m unittest tests.test_services.test_github_app_service -q` - passed after latest reviewer-finding fixes, 18 tests.
- `./.venv/bin/python -m unittest tests.test_services.test_project_service tests.test_services.test_github_app_service -q` - passed after latest reviewer-finding fixes, 47 tests.
- `./.venv/bin/ruff check services/project_service.py integrations/github/app_service.py tests/test_services/test_project_service.py` - passed after latest reviewer-finding fixes.
- `./.venv/bin/ruff format --check services/project_service.py integrations/github/app_service.py tests/test_services/test_project_service.py` - failed before formatting; `services/project_service.py` and `integrations/github/app_service.py` needed formatting.
- `./.venv/bin/ruff format services/project_service.py integrations/github/app_service.py` - reformatted 2 files.
- `./.venv/bin/ruff check services/project_service.py integrations/github/app_service.py tests/test_services/test_project_service.py` - passed after formatting.
- `./.venv/bin/ruff format --check services/project_service.py integrations/github/app_service.py tests/test_services/test_project_service.py` - passed after formatting, 3 files already formatted.
- `./.venv/bin/ruff check .` - passed after latest reviewer-finding fixes.
- `./.venv/bin/ruff format --check .` - passed after latest reviewer-finding fixes, 254 files already formatted.
- `./.venv/bin/python -m unittest discover -q` - passed after latest reviewer-finding fixes, 246 tests, 1 skipped.
- `bash scripts/ci-local.sh` - passed after latest reviewer-finding fixes; local CI skipped Bandit because it is not installed.

### Completion Notes List

- Resolved analysis project scope once at the start of the shared `analyze_uploaded_files` pipeline and passed the resolved project ID through context building and report persistence.
- Preserved the existing UI, API, CLI, and GitHub project-aware flows while ensuring invalid explicit project references fail before parser execution.
- Added API and CLI regression tests that assert unknown project references return structured project errors, do not invoke parsing, and do not create reports.
- Fixed review finding by rejecting missing project scope before parser execution in the shared analysis pipeline.
- Added service, API, and CLI regression tests for `missing_project_scope`, and updated existing API/CLI success-path tests to pass explicit project scope.
- Updated workspace and CI advisory docs plus the README analysis endpoint notes to document required project scope for new API/CLI analysis submissions.
- Resolved the AC2 phase-scope decision by clarifying that Story 1.2 rejects invalid local/admin project references before parsing while full membership and role checks are deferred to Story 1.5.
- Fixed stale active-project selection so missing saved project records no longer enable manual UI uploads under the fallback `unassigned` project.
- Added the missing API `404` response contract and direct API/CLI `project_id` success regressions.
- Added UI and GitHub integration tests that exercise the shared missing-scope guard and repository-derived project handoff.
- Fixed explicit GitHub project override handling so unknown or malformed configured project keys fail as configuration errors and do not create projects or start analysis.
- Updated API and CLI contract text so generated metadata and help output match the required project-scope behavior.
- Fixed GitHub webhook project-scope errors so invalid project references return project-specific API error codes instead of generic app-unconfigured errors.
- Added pre-parse/no-report regression coverage for conflicting API/CLI project references.
- Normalized blank `project_key` values so valid `project_id` submissions are accepted even when form clients send empty project-key fields.
- Moved API/CLI analysis scope checks ahead of artifact read/classification so missing scope is the first actionable failure for submissions with artifacts.
- Aligned history page active-project recovery with upload behavior when a saved project selection becomes stale.
- Fixed blank-key-only project references so they cannot fall through to the default project.
- Fixed stale history project recovery so stale/no-saved selection scopes history to the default project instead of all reports.
- Fixed repository-derived GitHub project collisions by canonicalizing repository references and suffixing colliding derived keys with a deterministic repository hash.
- Fixed GitHub webhook project-scope failures so initial and late failures are handled as acknowledged no-analysis results with neutral check-run notes instead of non-2xx delivery failures or generic 500s.
- Fixed repository-derived collision handling for preexisting manual projects without repository URLs.
- Moved explicit GitHub project override resolution ahead of artifact download/classification.
- Narrowed GitHub analysis error handling so only actual project-scope errors are converted into neutral handled webhook results.
- Fixed repository matching so canonical identity includes the SCM host, preventing same owner/repo paths on different hosts from reusing the same project while preserving path-derived display keys.

### File List

- `_bmad-output/implementation-artifacts/1-2-project-aware-analysis-submission.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `README.md`
- `api/routes/analyses.py`
- `api/routes/github_app.py`
- `docs/ci-advisory-consumption.md`
- `docs/project-workspaces.md`
- `integrations/github/app_service.py`
- `services/analysis_service.py`
- `services/project_service.py`
- `tests/test_api/test_analyses.py`
- `tests/test_api/test_github_app.py`
- `tests/test_cli/test_analyze.py`
- `tests/test_services/test_github_app_service.py`
- `tests/test_services/test_analysis_service.py`
- `tests/test_services/test_project_service.py`
- `frontend/e2e/test_history_page.py`
- `frontend/e2e/test_upload_panel.py`
- `frontend/src/screens/history.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-05: Implemented project-scope fast-fail behavior for analysis submission and moved story to review.
- 2026-05-05: Fixed review finding by rejecting missing analysis project scope before parsing and updating API/CLI docs and regression coverage.
- 2026-05-05: Re-ran code review; unresolved decision and patch findings moved story back to in-progress.
- 2026-05-05: Fixed rerun review findings and moved story back to review.
- 2026-05-05: Re-ran code review; unresolved GitHub override and public contract findings moved story back to in-progress.
- 2026-05-05: Fixed latest review findings for GitHub explicit project overrides and API/CLI contract text; moved story back to review.
- 2026-05-05: Re-ran code review; unresolved GitHub webhook error-contract and conflicting-reference regression findings moved story back to in-progress.
- 2026-05-05: Fixed latest review findings for GitHub project-scope errors, API/CLI preflight, blank keys, conflicting-reference regressions, and stale history scope; moved story back to review.
- 2026-05-05: Re-ran code review; unresolved GitHub webhook delivery decision and project-scope edge-case findings moved story back to in-progress.
- 2026-05-05: Fixed latest reviewer findings for webhook project-scope handling, blank-key fallback, stale history scope, repository-key collisions, and late GitHub scope errors; moved story back to review.
- 2026-05-05: Re-ran code review; unresolved GitHub project-scope fast-fail and repository collision findings moved story back to in-progress.
- 2026-05-05: Fixed latest reviewer findings for manual repository-key collisions, explicit GitHub scope fast-fail ordering, and non-project analysis ValueError handling; moved story back to review.
- 2026-05-06: Fixed latest reviewer finding for SCM host-aware repository identity; moved story back to review.
