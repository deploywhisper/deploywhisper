# Story 3.6: Report Diff After Rerun

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a reviewer,
I want report diffs after reruns,
So that I can see which risks are new, resolved, or persistent.

## Acceptance Criteria

1. Given two related reports exist for the same project/workspace and workflow context, When the reviewer opens comparison, Then the diff shows new, resolved, persistent, changed-severity, and changed-context findings. And comparison respects redaction and project scope.

### Requirement Traceability

- Primary PRD requirements: Epic 3 coverage: REV-01..10, HIS-03, RSK-04..06, RSK-09..10, NFR-XAI-01..05, UX-DR1..10.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 3 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Duplicate title/category findings can be mispaired after description was removed from the finding fingerprint [services/report_service.py:823]
- [x] [Review][Patch] Guidance reordering can create false changed-context diffs because guidance is compared as an ordered tuple [services/report_service.py:949]
- [x] [Review][Patch] Comparable-report lookup does not isolate workflow context even though AC1 requires same project/workspace and workflow context [services/report_service.py:1238]
- [x] [Review][Patch] Duplicate finding pairing accepts same-description matches before evidence identity, hiding added/removed findings [services/report_service.py:1090]
- [x] [Review][Patch] Singleton fallback pairs findings with no shared description or evidence identity [services/report_service.py:1158]
- [x] [Review][Patch] Workflow context comparison is case/whitespace sensitive [services/report_service.py:819]
- [x] [Review][Decision] Workflow scoping ignores trigger_id — AC1 requires comparison within the same workflow context, but the current comparable-report key uses source_interface and trigger_type while ignoring audit.trigger_id. If trigger_id represents a stable workflow instance such as a PR/session, unrelated runs can be diffed together; if it represents a unique CI/job run, requiring equality would suppress valid reruns. Decide whether trigger_id is part of workflow context before patching.
- [x] [Review][Patch] Title/category drift is still reported as removed plus added instead of persistent plus changed-context [services/report_service.py:857]
- [x] [Review][Decision] Protected shared-report comparison needs an explicit auth model — Current report unlock uses a report-specific cookie, but compare fetches the previous shared report without carrying prior-report auth. Decide whether unlocking the current comparable report should grant compare access to the prior protected report, or whether the shared compare flow must require a separate compare unlock before patching.
- [x] [Review][Patch] Reviewer-facing comparison still says removed instead of resolved [frontend/src/screens/history.py:476]
- [x] [Review][Patch] Greedy evidence-overlap pairing can misclassify duplicate findings [services/report_service.py:1106]
- [x] [Review][Patch] Auto-compare serializes unreadable off-path reports instead of skipping them [services/report_service.py:1464]
- [x] [Review][Patch] Visible unreadable reports can still break history page serialization [services/report_service.py:3736]
- [x] [Review][Patch] Optimal evidence matching can become exponential on dense overlap components [services/report_service.py:1176]
- [x] [Review][Patch] Reviewer-facing current-side comparison still says added instead of new [frontend/src/screens/history.py:497]
- [x] [Review][Patch] UI history skips unreadable rows after pagination, which can hide readable reports behind unreadable page rows [services/report_service.py:3811]
- [x] [Review][Decision] Mixed legacy/current workflow provenance can suppress a valid previous comparison — `_reports_are_comparable` now requires exact source_interface/trigger_type/trigger_id equality. That satisfies strict workflow-context isolation for fully populated reports, but older persisted reports with blank audit context no longer compare with newer reruns that now carry provenance. Decide whether blank legacy workflow fields should act as compatibility wildcards, whether trigger_id strictness should require an explicit provenance version/backfill signal, or whether suppressing legacy comparisons is intentional.
- [x] [Review][Patch] UI history skip-unreadable pagination materializes all matching rows before slicing [services/report_service.py:3817]
- [x] [Review][Patch] Large dense-overlap evidence components silently fall back to approximate greedy pairing [services/report_service.py:1235]
- [x] [Review][Patch] Evidence-overlap scoring collapses repeated evidence identities into a set [services/report_service.py:911]
- [x] [Review][Patch] Comparison copy still describes artifact-only matching instead of project/workspace/workflow-scoped comparable reports [frontend/src/screens/history.py:454]
- [x] [Review][Patch] Workflow-context wildcard matching can compare reports from different workflows and can prefer a newer blank-context report over an exact prior match [services/report_service.py:830]
- [x] [Review][Patch] Skip-unreadable history filtering drops legacy readable reports with null or blank schema versions [models/repositories/analysis_reports.py:599]
- [x] [Review][Patch] Evidence-only matching can classify a different finding on the same resource as persistent changed-context instead of resolved plus new [services/report_service.py:1370]

## Dev Notes

### Epic Context

- Epic: 3. Report and Review Experience
- Epic goal: Make the report experience fast, inspectable, and honest.
- Epic coverage: REV-01..10, HIS-03, RSK-04..06, RSK-09..10, NFR-XAI-01..05, UX-DR1..10

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 3 / Story 3.6 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5.4

### Debug Log References

- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_returns_findings_and_evidence_deltas tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_is_stable_when_duplicate_finding_order_flips frontend.e2e.test_history_page.HistoryPageRenderingTests.test_public_report_route_shows_compare_button_and_diff_view frontend.e2e.test_history_page.HistoryPageRenderingTests.test_history_detail_route_shows_compare_button_and_diff_view -q` - failed as expected before implementation because persistent/changed-context buckets were missing.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_returns_findings_and_evidence_deltas tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_is_stable_when_duplicate_finding_order_flips frontend.e2e.test_history_page.HistoryPageRenderingTests.test_public_report_route_shows_compare_button_and_diff_view frontend.e2e.test_history_page.HistoryPageRenderingTests.test_history_detail_route_shows_compare_button_and_diff_view -q` - passed, 4 tests.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_returns_findings_and_evidence_deltas tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_preserves_duplicate_findings tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_is_stable_when_duplicate_finding_order_flips tests.test_services.test_report_service.ReportServiceTests.test_fetch_shared_report_comparison_respects_filename_redaction tests.test_services.test_report_service.ReportServiceTests.test_fetch_shared_report_comparison_redacts_manifest_only_failed_files tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_project_boundaries -q` - passed, 6 tests.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_does_not_mispair_duplicate_title_category_findings tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_ignores_guidance_reordering tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_workflow_contexts -q` - failed as expected before review fixes, covering all 3 reviewer findings.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_does_not_mispair_duplicate_title_category_findings tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_ignores_guidance_reordering tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_workflow_contexts -q` - passed, 3 tests.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_returns_findings_and_evidence_deltas tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_preserves_duplicate_findings tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_is_stable_when_duplicate_finding_order_flips tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_does_not_mispair_duplicate_title_category_findings tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_ignores_guidance_reordering tests.test_services.test_report_service.ReportServiceTests.test_fetch_shared_report_comparison_respects_filename_redaction tests.test_services.test_report_service.ReportServiceTests.test_fetch_shared_report_comparison_redacts_manifest_only_failed_files tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_project_boundaries tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_workflow_contexts tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_use_immediately_previous_comparable_report tests.test_services.test_report_service.ReportServiceTests.test_filtered_history_ignores_unreadable_off_page_reports_for_diffs tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_compute_history_signature_once_per_report -q` - passed, 12 tests.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_matches_duplicate_same_description_by_evidence tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_does_not_pair_singletons_without_identity tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_normalize_workflow_contexts tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_does_not_mispair_duplicate_title_category_findings tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_workflow_contexts -q` - passed, 5 tests.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_returns_findings_and_evidence_deltas tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_preserves_duplicate_findings tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_is_stable_when_duplicate_finding_order_flips tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_does_not_mispair_duplicate_title_category_findings tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_matches_duplicate_same_description_by_evidence tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_does_not_pair_singletons_without_identity tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_ignores_guidance_reordering tests.test_services.test_report_service.ReportServiceTests.test_fetch_shared_report_comparison_respects_filename_redaction tests.test_services.test_report_service.ReportServiceTests.test_fetch_shared_report_comparison_redacts_manifest_only_failed_files tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_project_boundaries tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_workflow_contexts tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_normalize_workflow_contexts tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_use_immediately_previous_comparable_report tests.test_services.test_report_service.ReportServiceTests.test_filtered_history_ignores_unreadable_off_page_reports_for_diffs tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_compute_history_signature_once_per_report -q` - passed, 15 tests.
- `./.venv/bin/python -m unittest frontend.e2e.test_history_page.HistoryPageRenderingTests -q` - passed, 22 tests.
- `./.venv/bin/ruff check .` - passed.
- `./.venv/bin/ruff format --check .` - passed, 271 files already formatted.
- `./.venv/bin/python -m unittest discover -q` - passed, 400 tests, 1 skipped.
- `./.venv/bin/bandit -r app.py services ui tests/e2e/seeded_server.py --severity-level high --confidence-level high -q` - passed with no high-confidence/high-severity findings.
- `./.venv/bin/python -m pip_audit -r requirements.txt` - passed, no known vulnerabilities found.
- `APP_PORT=18080 npm run test:ui-review` - failed once after the second review fix because the browser fixture used different evidence identity for its intended persistent finding; updated the fixture, then passed: 3 WebKit browser tests.
- `bash scripts/ci-local.sh` - passed after final changes: lint/format/dependency checks, Bandit, parser fixtures, and 400 tests with 1 skipped.
- `git diff --check` - passed.
- manual screen-reader validation intentionally not run per project directive.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_pairs_title_category_drift_by_evidence tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_trigger_ids tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_normalize_workflow_contexts tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_matches_duplicate_same_description_by_evidence tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_does_not_pair_singletons_without_identity tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_does_not_mispair_duplicate_title_category_findings tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_workflow_contexts -q` - passed, 7 tests.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_returns_findings_and_evidence_deltas tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_preserves_duplicate_findings tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_is_stable_when_duplicate_finding_order_flips tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_does_not_mispair_duplicate_title_category_findings tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_matches_duplicate_same_description_by_evidence tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_pairs_title_category_drift_by_evidence tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_does_not_pair_singletons_without_identity tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_ignores_guidance_reordering tests.test_services.test_report_service.ReportServiceTests.test_fetch_shared_report_comparison_respects_filename_redaction tests.test_services.test_report_service.ReportServiceTests.test_fetch_shared_report_comparison_redacts_manifest_only_failed_files tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_project_boundaries tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_workflow_contexts tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_trigger_ids tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_normalize_workflow_contexts tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_use_immediately_previous_comparable_report tests.test_services.test_report_service.ReportServiceTests.test_filtered_history_ignores_unreadable_off_page_reports_for_diffs tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_compute_history_signature_once_per_report -q` - passed, 17 tests.
- `./.venv/bin/ruff check .` - passed after final review-rerun fixes.
- `./.venv/bin/ruff format --check .` - passed after final review-rerun fixes, 271 files already formatted.
- `./.venv/bin/python -m unittest discover -q` - passed after final review-rerun fixes, 400 tests with 1 skipped.
- `./.venv/bin/bandit -r app.py services ui tests/e2e/seeded_server.py --severity-level high --confidence-level high -q` - passed after final review-rerun fixes with no high-confidence/high-severity findings.
- `./.venv/bin/python -m pip_audit -r requirements.txt` - passed after final review-rerun fixes, no known vulnerabilities found.
- `APP_PORT=18080 npm run test:ui-review` - passed after final review-rerun fixes: 3 WebKit browser tests.
- `bash scripts/ci-local.sh` - passed after final review-rerun fixes: lint/format/dependency checks, Bandit, parser fixtures, and 400 tests with 1 skipped.
- `git diff --check` - passed after final review-rerun fixes.
- manual screen-reader validation intentionally not run per project directive after final review-rerun fixes.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_uses_optimal_evidence_matching tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_matches_duplicate_same_description_by_evidence tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_pairs_title_category_drift_by_evidence tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_ignores_unreadable_off_path_reports tests.test_services.test_report_service.ReportServiceTests.test_filtered_history_ignores_unreadable_off_page_reports_for_diffs frontend.e2e.test_history_page.HistoryPageRenderingTests.test_public_report_route_shows_compare_button_and_diff_view frontend.e2e.test_history_page.HistoryPageRenderingTests.test_history_detail_route_shows_compare_button_and_diff_view frontend.e2e.test_history_page.HistoryPageRenderingTests.test_public_report_route_blocks_compare_view_when_previous_report_is_protected frontend.e2e.test_history_page.HistoryPageRenderingTests.test_public_report_compare_allows_same_password_protected_reruns -q` - passed, 9 tests.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_returns_findings_and_evidence_deltas tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_preserves_duplicate_findings tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_is_stable_when_duplicate_finding_order_flips tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_does_not_mispair_duplicate_title_category_findings tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_matches_duplicate_same_description_by_evidence tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_uses_optimal_evidence_matching tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_pairs_title_category_drift_by_evidence tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_does_not_pair_singletons_without_identity tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_ignores_guidance_reordering tests.test_services.test_report_service.ReportServiceTests.test_fetch_shared_report_comparison_respects_filename_redaction tests.test_services.test_report_service.ReportServiceTests.test_fetch_shared_report_comparison_redacts_manifest_only_failed_files tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_project_boundaries tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_workflow_contexts tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_trigger_ids tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_normalize_workflow_contexts tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_use_immediately_previous_comparable_report tests.test_services.test_report_service.ReportServiceTests.test_filtered_history_ignores_unreadable_off_page_reports_for_diffs tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_ignores_unreadable_off_path_reports tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_compute_history_signature_once_per_report frontend.e2e.test_history_page.HistoryPageRenderingTests -q` - passed, 42 tests.
- `./.venv/bin/ruff check .` - passed after reviewer finding fixes.
- `./.venv/bin/ruff format --check .` - passed after reviewer finding fixes, 271 files already formatted.
- `git diff --check` - passed after reviewer finding fixes.
- `./.venv/bin/python -m unittest discover -q` - passed after reviewer finding fixes, 401 tests with 1 skipped.
- `./.venv/bin/bandit -r app.py services ui tests/e2e/seeded_server.py --severity-level high --confidence-level high -q` - passed after reviewer finding fixes with no high-confidence/high-severity findings.
- `./.venv/bin/python -m pip_audit -r requirements.txt` - passed after reviewer finding fixes, no known vulnerabilities found.
- `APP_PORT=18080 npm run test:ui-review` - passed after reviewer finding fixes: 3 WebKit browser tests.
- `bash scripts/ci-local.sh` - passed after reviewer finding fixes: lint/format/dependency checks, Bandit, parser fixtures, and 401 tests with 1 skipped.
- manual screen-reader validation intentionally not run per project directive after reviewer finding fixes.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_filtered_history_ignores_visible_unreadable_reports tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_caps_dense_evidence_matching frontend.e2e.test_history_page.HistoryPageRenderingTests.test_public_report_route_shows_compare_button_and_diff_view frontend.e2e.test_history_page.HistoryPageRenderingTests.test_history_detail_route_shows_compare_button_and_diff_view -q` - failed once with an indentation error introduced during the helper extraction, then passed after correction: 4 tests.
- `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_list_analyses_rejects_newer_report_schema_versions tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_ignores_unreadable_off_path_reports tests.test_services.test_report_service.ReportServiceTests.test_filtered_history_ignores_visible_unreadable_reports tests.test_services.test_report_service.ReportServiceTests.test_filtered_history_ignores_unreadable_off_page_reports_for_diffs -q` - passed, 4 tests.
- Story 3.6 regression slice including API schema strictness, comparison matching, unreadable-history handling, and `HistoryPageRenderingTests` - passed, 45 tests.
- `./.venv/bin/ruff check .` - passed after latest reviewer finding fixes.
- `./.venv/bin/ruff format --check .` - passed after latest reviewer finding fixes, 271 files already formatted.
- `git diff --check` - passed after latest reviewer finding fixes.
- `./.venv/bin/python -m unittest discover -q` - failed once because the initial visible-row skip also softened the API list schema contract, then passed after narrowing the skip to history/previous-comparable flows: 401 tests with 1 skipped.
- `./.venv/bin/bandit -r app.py services ui tests/e2e/seeded_server.py --severity-level high --confidence-level high -q` - passed after latest reviewer finding fixes with no high-confidence/high-severity findings.
- `./.venv/bin/python -m pip_audit -r requirements.txt` - passed after latest reviewer finding fixes, no known vulnerabilities found.
- `APP_PORT=18080 npm run test:ui-review` - passed after latest reviewer finding fixes: 3 WebKit browser tests.
- `bash scripts/ci-local.sh` - passed after latest reviewer finding fixes: lint/format/dependency checks, Bandit, parser fixtures, and 401 tests with 1 skipped.
- manual screen-reader validation intentionally not run per project directive after latest reviewer finding fixes.
- `bmad-code-review` rerun on Story 3.6 working-tree diff - clean review, all review findings remain checked and no new decision/patch/defer findings were added.
- `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_list_analyses_rejects_newer_report_schema_versions tests.test_services.test_report_service.ReportServiceTests.test_filtered_history_backfills_after_visible_unreadable_reports tests.test_services.test_report_service.ReportServiceTests.test_filtered_history_ignores_visible_unreadable_reports tests.test_services.test_report_service.ReportServiceTests.test_filtered_history_ignores_unreadable_off_page_reports_for_diffs tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_ignores_unreadable_off_path_reports -q` - passed after final pagination reviewer fix, 5 tests.
- Story 3.6 regression slice including API schema strictness, comparison matching, unreadable-history pagination/backfill handling, and `HistoryPageRenderingTests` - passed after final pagination reviewer fix, 46 tests.
- `./.venv/bin/ruff check .` - passed after final pagination reviewer fix.
- `./.venv/bin/ruff format --check .` - passed after final pagination reviewer fix, 271 files already formatted.
- `git diff --check` - passed after final pagination reviewer fix.
- `./.venv/bin/python -m unittest discover -q` - passed after final pagination reviewer fix, 401 tests with 1 skipped.
- `./.venv/bin/bandit -r app.py services ui tests/e2e/seeded_server.py --severity-level high --confidence-level high -q` - passed after final pagination reviewer fix with no high-confidence/high-severity findings.
- `./.venv/bin/python -m pip_audit -r requirements.txt` - passed after final pagination reviewer fix, no known vulnerabilities found. Initial sandbox run failed due DNS/network isolation, then the same command passed with network access.
- `APP_PORT=18080 npm run test:ui-review` - passed after final pagination reviewer fix: 3 WebKit browser tests.
- `bash scripts/ci-local.sh` - passed after final pagination reviewer fix: lint/format/dependency checks, Bandit, parser fixtures, and 401 tests with 1 skipped.
- manual screen-reader validation intentionally not run per project directive after final pagination reviewer fix.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_match_legacy_blank_workflow_context tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_cross_trigger_ids tests.test_services.test_report_service.ReportServiceTests.test_filtered_history_skip_unreadable_keeps_database_pagination tests.test_services.test_report_service.ReportServiceTests.test_filtered_history_backfills_after_visible_unreadable_reports tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_caps_dense_evidence_matching tests.test_services.test_report_service.ReportServiceTests.test_evidence_identity_counts_preserve_repeated_identities frontend.e2e.test_history_page.HistoryPageRenderingTests.test_public_report_route_shows_compare_button_and_diff_view frontend.e2e.test_history_page.HistoryPageRenderingTests.test_history_detail_route_shows_compare_button_and_diff_view -q` - passed after final reviewer finding fixes, 8 tests.
- Story 3.6 regression slice including API schema strictness, comparison matching, unreadable-history pagination/backfill handling, dense evidence matching, legacy workflow provenance, and `HistoryPageRenderingTests` - passed after final reviewer finding fixes, 49 tests.
- `./.venv/bin/ruff check .` - passed after final reviewer finding fixes.
- `./.venv/bin/ruff format --check .` - passed after final reviewer finding fixes, 271 files already formatted.
- `git diff --check` - passed after final reviewer finding fixes.
- `./.venv/bin/python -m unittest discover -q` - passed after final reviewer finding fixes, 401 tests with 1 skipped.
- `./.venv/bin/bandit -r app.py services ui tests/e2e/seeded_server.py --severity-level high --confidence-level high -q` - passed after final reviewer finding fixes with no high-confidence/high-severity findings.
- `./.venv/bin/python -m pip_audit -r requirements.txt` - passed after final reviewer finding fixes, no known vulnerabilities found.
- `APP_PORT=18080 npm run test:ui-review` - passed after final reviewer finding fixes: 3 WebKit browser tests.
- `bash scripts/ci-local.sh` - passed after final reviewer finding fixes: lint/format/dependency checks, Bandit, parser fixtures, and 401 tests with 1 skipped.
- manual screen-reader validation intentionally not run per project directive after final reviewer finding fixes.
- `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_does_not_pair_different_findings_on_same_evidence tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_prefer_exact_context_over_legacy_blank tests.test_services.test_report_service.ReportServiceTests.test_previous_scan_diffs_do_not_treat_partial_context_as_wildcard tests.test_services.test_report_service.ReportServiceTests.test_filtered_history_includes_legacy_blank_schema_reports tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_comparison_uses_legacy_blank_schema_previous_report -q` - passed after latest reviewer finding fixes, alongside related matching/schema regressions: 8 tests.
- Story 3.6 regression slice including API schema strictness, comparison matching, unreadable-history handling, legacy blank schema compatibility, and `HistoryPageRenderingTests` - passed after latest reviewer finding fixes, 54 tests.
- `./.venv/bin/ruff check .` - passed after latest reviewer finding fixes.
- `./.venv/bin/ruff format --check .` - passed after latest reviewer finding fixes, 271 files already formatted.
- `git diff --check` - passed after latest reviewer finding fixes.
- `./.venv/bin/python -m unittest discover -q` - passed after latest reviewer finding fixes, 401 tests with 1 skipped.
- `./.venv/bin/bandit -r app.py services ui tests/e2e/seeded_server.py --severity-level high --confidence-level high -q` - passed after latest reviewer finding fixes with no high-confidence/high-severity findings.
- `./.venv/bin/python -m pip_audit -r requirements.txt` - passed after latest reviewer finding fixes, no known vulnerabilities found.
- `APP_PORT=18080 npm run test:ui-review` - passed after latest reviewer finding fixes: 3 WebKit browser tests.
- `bash scripts/ci-local.sh` - passed after latest reviewer finding fixes: lint/format/dependency checks, Bandit, parser fixtures, and 401 tests with 1 skipped.
- manual screen-reader validation intentionally not run per project directive after latest reviewer finding fixes.

### Completion Notes List

- Added first-class persistent and changed-context finding buckets to persisted report comparisons while preserving existing new, resolved, severity-changed, and evidence delta outputs.
- Changed persistent finding matching to tolerate description changes and classify description, evidence, confidence, explanation, guidance, evidence classification, uncertainty, and skill context changes as changed context.
- Rendered `Persistent findings` and `Changed context` sections in retired Python UI history comparison and shared report HTML, including empty states and shared-report redaction coverage for the new buckets.
- Updated regression coverage for service comparisons, duplicate finding stability, redaction, history rendering, and browser review flow.
- Updated README report-history/shared-report documentation for persistent and changed-context diffs.
- Fixed reviewer findings by pairing duplicate title/category findings with evidence identity when descriptions differ, normalizing guidance ordering before context comparison, and requiring comparable reports to match project, workspace, workflow context, and artifact signature.
- Fixed second reviewer-rerun findings by making evidence identity the first persistent-finding match, restricting description fallback to descriptions unique in both reports, removing unsafe singleton fallback pairing, and normalizing workflow context case/whitespace.
- Fixed final review-rerun findings by treating trigger ID as part of the normalized workflow context and pairing title/category drift through evidence identity so it surfaces as changed context instead of removed plus added.
- Fixed latest reviewer findings by requiring a separate previous-report unlock for protected shared comparisons, using resolved terminology in reviewer-facing comparison copy, replacing greedy evidence-overlap matching with optimal one-to-one pairing, and skipping unreadable off-path report candidates during auto-compare.
- Fixed latest reviewer-rerun findings by skipping unreadable visible history rows only in UI/history comparison flows, bounding dense evidence matching with deterministic greedy fallback, and using New findings terminology in reviewer-facing current-side comparison copy while preserving API schema strictness.
- Fixed final pagination reviewer finding by filtering unreadable schema rows before UI history pagination/backfill while preserving default API schema strictness.
- Fixed final Story 3.6 reviewer findings by adding legacy blank workflow-context compatibility, restoring DB-backed skip-unreadable pagination, surfacing dense-match approximation warnings, preserving repeated evidence identity counts, and updating comparison copy to project/workspace/workflow scoped language.
- Fixed latest reviewer findings by ranking exact workflow-context matches ahead of blank legacy fallback, preserving blank legacy `v1` schema reports under skip-unreadable filters, and blocking evidence-only pairing when the same resource carries a different finding.
- Re-ran `bmad-code-review` after the latest fixes; no new findings were raised.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/3-6-report-diff-after-rerun.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `app.py`
- `models/repositories/analysis_reports.py`
- `services/report_service.py`
- `tests/e2e/report_review.keyboard.spec.js`
- `tests/e2e/seeded_server.py`
- `tests/test_services/test_report_service.py`
- `frontend/e2e/test_history_page.py`
- `frontend/src/screens/history.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-19: Implemented report comparison persistent and changed-context finding buckets across service, history UI, shared report HTML, tests, and README.
- 2026-05-19: Fixed Story 3.6 code-review findings for duplicate pairing, guidance ordering, and workflow-context comparison isolation.
- 2026-05-19: Fixed Story 3.6 review-rerun findings for same-description duplicate pairing, singleton no-identity pairing, normalized workflow context, and browser fixture persistence identity.
- 2026-05-19: Fixed Story 3.6 final review-rerun findings for trigger ID workflow scoping and title/category drift changed-context classification.
- 2026-05-19: Fixed Story 3.6 reviewer findings for protected shared comparison auth, resolved wording, optimal evidence matching, and unreadable candidate skipping.
- 2026-05-20: Fixed Story 3.6 review-rerun findings for visible unreadable history rows, bounded dense evidence matching, and new/resolved reviewer vocabulary.
- 2026-05-20: Fixed Story 3.6 reviewer finding for unreadable schema rows hiding readable reports during UI history pagination.
- 2026-05-20: Fixed Story 3.6 reviewer findings for legacy workflow provenance, skip-unreadable pagination, dense evidence matching warnings, repeated evidence identity scoring, and scoped comparison copy.
- 2026-05-20: Fixed Story 3.6 reviewer findings for workflow-context match ranking, legacy blank schema filtering, and evidence-only different-finding pairing.
- 2026-05-20: Re-ran Story 3.6 code review clean and moved the story to done.
