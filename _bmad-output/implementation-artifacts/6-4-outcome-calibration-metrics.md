# Story 6.4: Outcome Calibration Metrics

Status: review

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a maintainer,
I want deployment outcomes and feedback to inform calibration metrics,
So that false positives and false reassurance can be tracked.

## Acceptance Criteria

1. Given feedback and deployment outcomes exist, When calibration views or exports are generated, Then precision, recall proxy signals, false-positive rate, false-reassurance cases, and confidence trends are computed per project/workspace where possible. And historical report verdicts remain immutable.
2. Given feedback or outcome data is sparse or biased, When calibration metrics are shown, Then the dashboard labels confidence limitations and avoids implying statistical certainty.

### Requirement Traceability

- Primary PRD requirements: Epic 6 coverage: BEN-01..11, INC-09..11, HIS-04, HIS-06..07, NFR-PERF-01..05, DOC-14, DOC-27.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 6 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Implement and verify acceptance criterion 2. (AC: 2)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Include feedback-only calibration inputs instead of filtering feedback to analysis IDs with deployment outcomes. [services/backtesting_service.py:93]
- [x] [Review][Patch] Use consistent denominator units for false-positive rate so finding-level feedback cannot exceed deployment/report-level warned totals. [services/backtesting_service.py:378]
- [x] [Review][Patch] Preserve distinct false-reassurance cases and avoid counting reviewer missed-finding feedback against unrelated successful outcomes. [services/backtesting_service.py:390]
- [x] [Review][Patch] Prevent workspace-scoped backtests from updating the project-global weekly last-run marker. [services/backtesting_service.py:587]
- [x] [Review][Patch] Make confidence trend sampling internally consistent when one analysis has multiple deployment outcomes, and avoid reporting missing confidence as an average of 0.0. [services/backtesting_service.py:434]
- [x] [Review][Patch] Base sparse/biased feedback limitations on effective latest feedback signals or expose raw feedback history separately. [services/backtesting_service.py:481]
- [x] [Review][Patch] Add regression coverage for biased-feedback and feedback-only calibration paths required by AC2. [tests/test_services/test_backtesting_service.py:297]
- [x] [Review][Patch] Keep the history page workspace filter consistent by scoping risk trends with the selected workspace alongside history rows and calibration. [ui/routes/history.py:370]
- [x] [Review][Patch] Avoid scanning every persisted setting when invalidating one project's calibration snapshots. [services/backtesting_service.py:546]
- [x] [Review][Patch] Do not count missed-finding feedback on warned reports as false reassurance. [services/backtesting_service.py:465]
- [x] [Review][Patch] Refresh or expire stale workspace-scoped calibration snapshots before returning cached dashboard seeds. [services/backtesting_service.py:716]
- [x] [Review][Patch] Re-render history risk-trend and calibration summary cards after workspace/filter changes. [ui/routes/history.py:589]
- [x] [Review][Patch] Surface active feedback-bias limitations instead of displaying only the first calibration limitation. [ui/routes/history.py:257]
- [x] [Review][Patch] Treat corrupt cached calibration snapshots as stale and recompute instead of crashing history. [services/backtesting_service.py:759]
- [x] [Review][Patch] Reject future-dated cached calibration snapshots before applying freshness checks. [services/backtesting_service.py:292]
- [x] [Review][Patch] Invalidate calibration snapshots when analysis reports are deleted. [services/report_service.py:4711]
- [x] [Review][Patch] Separate reviewer-only false-reassurance signals from deployment-backed rates and feedback-bias labels. [services/backtesting_service.py:497]
- [x] [Review][Patch] Keep calibration feedback metrics scoped to the active 7-day backtest window or explicitly split windowed and lifetime feedback signals. [services/backtesting_service.py:93]
- [x] [Review][Patch] Validate cached calibration snapshot schema and resolved project/workspace scope before reusing fresh-looking snapshots. [services/backtesting_service.py:292]
- [x] [Review][Patch] Run and record local app startup/manual sanity validation for the changed history calibration UI flow. [ui/routes/history.py:160]
- [x] [Review][Patch] Tighten cached calibration snapshot validation to reject wrong-window, partial-shape, and malformed nested metric payloads. [services/backtesting_service.py:342]
- [x] [Review][Patch] Keep feedback-only cases out of deployment-sample confidence trend buckets or expose separate feedback-only bucket counts. [services/backtesting_service.py:631]
- [x] [Review][Patch] Sort false-reassurance cases by a common event timestamp across deployment-backed and reviewer-missed cases. [services/backtesting_service.py:559]
- [x] [Review][Patch] Make the empty history calibration seed mirror the full calibration payload shape. [ui/routes/history.py:88]

## Dev Notes

### Epic Context

- Epic: 6. Benchmarks, Calibration, and Honest Failure Reporting
- Epic goal: Prove trust claims with measurable, repeatable evidence.
- Epic coverage: BEN-01..11, INC-09..11, HIS-04, HIS-06..07, NFR-PERF-01..05, DOC-14, DOC-27

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
- UI work belongs under `ui/routes/` and `ui/components/`, following the existing NiceGUI composition style.
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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 6 / Story 6.4 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

Codex GPT-5

### Debug Log References

- 2026-06-03: Loaded BMad config, sprint status, project context, and Story 6.4.
- 2026-06-03: Started implementation on `feature/6-4-outcome-calibration-metrics`.
- 2026-06-03: Added RED service/UI tests for feedback-derived calibration metrics, workspace scoping, sparse-data labeling, and historical verdict immutability.
- 2026-06-03: Extended `services.backtesting_service` to compute false-positive rate, false-reassurance cases/rate, recall proxy signals, confidence trend buckets, confidence limitation labels, and workspace-scoped calibration snapshots.
- 2026-06-03: Updated feedback writes to invalidate calibration snapshots without mutating historical reports.
- 2026-06-03: Updated the history calibration card to show the shared "Directional only" / limitation label.
- 2026-06-03: Updated outcome-linking documentation for the new calibration fields and directional-evidence semantics.
- 2026-06-03: Validation passed: `./.venv/bin/python -m unittest tests.test_services.test_backtesting_service.BacktestingServiceTests.test_run_weekly_backtest_includes_feedback_outcome_calibration_metrics -q`.
- 2026-06-03: Validation passed: `./.venv/bin/python -m unittest tests.test_ui.test_history_page.HistoryPageRenderingTests.test_history_page_renders_calibration_snapshot_from_backtest_feed -q`.
- 2026-06-03: Validation passed: `./.venv/bin/python -m unittest tests.test_services.test_backtesting_service -q`.
- 2026-06-03: Validation passed: `./.venv/bin/python -m unittest tests.test_services.test_feedback_service -q`.
- 2026-06-03: Validation passed: `./.venv/bin/python -m unittest tests.test_ui.test_history_page -q`.
- 2026-06-03: Validation passed: `./.venv/bin/ruff check .`.
- 2026-06-03: Validation passed: `./.venv/bin/ruff format --check .`.
- 2026-06-03: Validation passed: `./.venv/bin/bandit -q services/backtesting_service.py services/feedback_service.py ui/routes/history.py`.
- 2026-06-03: Validation passed: `./.venv/bin/python -m unittest discover -q` (447 tests, 1 skipped).
- 2026-06-03: Validation passed: `bash scripts/ci-local.sh`.
- 2026-06-03: UI validation note: `npm run test:ui-review` failed because `127.0.0.1:8080` was already in use; reran with `APP_PORT=18080 npm run test:ui-review` and Playwright passed (4 tests).
- 2026-06-03: Addressed code-review findings for feedback-only calibration inputs, rate denominators, false-reassurance case identity, workspace last-run behavior, confidence bucket sampling, effective feedback limitation labels, workspace-scoped history trends, and targeted snapshot invalidation.
- 2026-06-03: Added regression coverage for feedback-only signals, biased/sparse feedback labels, bounded false-positive rates, distinct missed-finding cases, workspace-scoped scheduler state, duplicate-outcome confidence buckets, unknown-confidence buckets, and workspace-scoped history trend fetching.
- 2026-06-03: Validation passed after review fixes: `./.venv/bin/python -m unittest tests.test_services.test_backtesting_service -q`.
- 2026-06-03: Validation passed after review fixes: `./.venv/bin/python -m unittest tests.test_ui.test_history_page -q`.
- 2026-06-03: Validation passed after review fixes: `./.venv/bin/ruff check .`.
- 2026-06-03: Validation passed after review fixes: `./.venv/bin/ruff format --check .`.
- 2026-06-03: Validation passed after review fixes: `./.venv/bin/bandit -q services/backtesting_service.py services/feedback_service.py ui/routes/history.py models/repositories/settings.py`.
- 2026-06-03: Validation passed after review fixes: `./.venv/bin/python -m unittest discover -q` (449 tests, 1 skipped).
- 2026-06-03: Validation passed after review fixes: `bash scripts/ci-local.sh`.
- 2026-06-03: UI validation passed after review fixes: `APP_PORT=18080 npm run test:ui-review` (4 Playwright tests).
- 2026-06-03: Final validation refresh passed: `./.venv/bin/python -m unittest tests.test_services.test_backtesting_service -q` (16 tests), `./.venv/bin/python -m unittest tests.test_ui.test_history_page -q` (54 tests), `./.venv/bin/python -m unittest discover -q` (449 tests, 1 skipped), `bash scripts/ci-local.sh`, and `APP_PORT=18080 npm run test:ui-review` (4 Playwright tests).
- 2026-06-03: Re-ran BMad code review on Story 6.4. Four patch findings remain open; story moved back to in-progress for follow-up fixes.
- 2026-06-03: Fixed second rerun code-review findings: warned reports no longer count as false reassurance, stale workspace calibration snapshots refresh on read, history summary cards rerender after filters, and all active calibration limitation labels are shown.
- 2026-06-03: Validation passed after second rerun fixes: `./.venv/bin/python -m unittest tests.test_services.test_backtesting_service -q` (18 tests), `./.venv/bin/python -m unittest tests.test_ui.test_history_page -q` (56 tests), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/bandit -q services/backtesting_service.py services/feedback_service.py ui/routes/history.py models/repositories/settings.py`, `./.venv/bin/python -m unittest discover -q` (451 tests, 1 skipped), `bash scripts/ci-local.sh`, and `APP_PORT=18080 npm run test:ui-review` (4 Playwright tests).
- 2026-06-03: Re-ran BMad code review on Story 6.4. Four patch findings remain open; story moved back to in-progress for follow-up fixes. Dismissed as noise: initial workspace summary mismatch because no workspace is selected on first render, latest-feedback ordering because feedback repository returns newest-first, and report-level missed-note collapse because Story 6.4 intentionally uses latest effective feedback.
- 2026-06-03: Fixed third rerun code-review findings: malformed/future-dated cached calibration snapshots now recompute, report deletion invalidates calibration snapshots, and reviewer-only missed feedback is separated from deployment-backed false-reassurance rates and feedback-bias labels.
- 2026-06-03: Validation passed after third rerun fixes: `./.venv/bin/python -m unittest tests.test_services.test_backtesting_service -q` (22 tests), `./.venv/bin/python -m unittest tests.test_ui.test_history_page -q` (56 tests), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/bandit -q services/backtesting_service.py services/feedback_service.py services/report_service.py ui/routes/history.py models/repositories/settings.py`, `./.venv/bin/python -m unittest discover -q` (451 tests, 1 skipped), `bash scripts/ci-local.sh`, and `APP_PORT=18080 npm run test:ui-review` (4 Playwright tests).
- 2026-06-03: Re-ran BMad code review on Story 6.4. Three patch findings remain open; story moved back to in-progress for follow-up fixes. Dismissed as noise: initial workspace summary mismatch because no workspace is selected on first render, latest-feedback ordering because the feedback repository returns newest-first, and risk-assessment row duplication because `risk_assessments.analysis_id` is the primary key.
- 2026-06-03: Fixed fourth rerun code-review findings: calibration metrics now use windowed feedback while preserving lifetime feedback history counts, cached calibration snapshots validate schema and project/workspace scope before reuse, and local app startup/history-route sanity was run.
- 2026-06-03: Validation passed after fourth rerun fixes: `./.venv/bin/python -m unittest tests.test_services.test_backtesting_service -q` (25 tests), `./.venv/bin/python -m unittest tests.test_ui.test_history_page -q` (56 tests), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/bandit -q services/backtesting_service.py services/feedback_service.py services/report_service.py ui/routes/history.py models/repositories/settings.py models/repositories/feedback_events.py`, `./.venv/bin/python -m unittest discover -q` (451 tests, 1 skipped), `bash scripts/ci-local.sh`, `APP_PORT=18080 npm run test:ui-review` (4 Playwright tests), and local app sanity: `APP_PORT=18081 ./.venv/bin/python app.py` plus `curl -fsSL http://127.0.0.1:18081/history` returned the rendered history page. Initial sandboxed app startup hit a NiceGUI process-pool `PermissionError`, so the same command was rerun outside the sandbox for validation.
- 2026-06-03: Re-ran BMad code review on Story 6.4. Four patch findings remain open; story moved back to in-progress for follow-up fixes. Dismissed as noise: initial history summaries cannot be workspace-scoped on first render because the route has no deep-link/preselected workspace path and initializes the workspace filter to all workspaces.
- 2026-06-03: Fixed fifth rerun code-review findings: cached calibration snapshots now reject wrong-window, partial, and malformed nested metric payloads; feedback-only cases stay out of deployment confidence trend buckets; false-reassurance cases sort by event timestamp across sources; and the empty history calibration seed mirrors the full payload shape.
- 2026-06-03: Validation passed after fifth rerun fixes: `./.venv/bin/python -m unittest tests.test_services.test_backtesting_service -q` (29 tests), `./.venv/bin/python -m unittest tests.test_ui.test_history_page -q` (57 tests), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/bandit -q services/backtesting_service.py services/feedback_service.py services/report_service.py ui/routes/history.py models/repositories/settings.py models/repositories/feedback_events.py`, `./.venv/bin/python -m unittest discover -q` (452 tests, 1 skipped), `bash scripts/ci-local.sh`, `APP_PORT=18080 npm run test:ui-review` (4 Playwright tests), and local app sanity: `APP_PORT=18081 ./.venv/bin/python app.py` plus `curl -fsSL http://127.0.0.1:18081/history` returned the rendered history page.
- 2026-06-03: Final closeout review found additional patch findings around cache window bounds, orphaned feedback, stale-feedback limitation labels, duplicate-source false-reassurance evidence, and confidence bucket count units; patched before closeout.
- 2026-06-03: Validation passed after final closeout fixes: `./.venv/bin/python -m unittest tests.test_services.test_backtesting_service -q` (32 tests), `./.venv/bin/python -m unittest tests.test_ui.test_history_page -q` (57 tests), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/bandit -q services/backtesting_service.py services/feedback_service.py services/report_service.py ui/routes/history.py models/repositories/settings.py models/repositories/feedback_events.py`, `./.venv/bin/python -m unittest discover -q` (452 tests, 1 skipped), `bash scripts/ci-local.sh`, `APP_PORT=18080 npm run test:ui-review` (4 Playwright tests), and local app sanity: `APP_PORT=18081 ./.venv/bin/python app.py` plus `curl -fsSL http://127.0.0.1:18081/history` returned the rendered history page.

### Completion Notes List

- Implemented shared calibration metrics on the existing weekly backtesting feed rather than adding a separate dashboard-only path.
- Added project/workspace-scoped calibration snapshots and feedback-triggered cache invalidation.
- Preserved existing `overall_precision` / `overall_recall` fields while adding structured `calibration_metrics`, `false_positive_cases`, `false_reassurance_cases`, `confidence_trends`, `confidence_limitations`, `confidence_label`, and `statistical_certainty`.
- Historical report verdict fields remain immutable; calibration changes aggregate views only.
- Sparse or biased inputs are labeled as directional evidence and not statistically certain.
- Review fixes now include feedback-only reviewer signals, latest-effective feedback counts, bounded reviewer feedback rates, workspace-safe scheduler state, and consistent workspace filtering across history summaries.
- Second rerun review fixes now exclude warned reports from false-reassurance feedback counts, expire stale cached calibration snapshots, refresh history summary cards after workspace/filter changes, and preserve all active limitation labels.
- Third rerun review fixes now harden cached calibration snapshot reads, invalidate calibration caches on report deletion, and keep deployment-backed rates distinct from reviewer-only missed-feedback evidence.
- Fourth rerun review fixes now keep weekly feedback-derived metrics scoped to the active backtest window, expose lifetime feedback only as history context, reject old-schema or wrong-scope cached calibration snapshots, and record direct local app/history-route validation.
- Fifth rerun review fixes now fully validate cached calibration payload shape, keep feedback-only evidence out of deployment confidence buckets, apply event-time ordering to false-reassurance cases, and align the empty history seed with the full calibration payload.
- Final closeout review fixes now validate cached window bounds, ignore orphaned feedback after report deletion, preserve deployment-backed and reviewer-missed false-reassurance evidence separately, and keep confidence bucket error counts on sampled-analysis units.

### File List

- `docs/outcome-linking.md`
- `models/repositories/feedback_events.py`
- `models/repositories/settings.py`
- `services/backtesting_service.py`
- `services/feedback_service.py`
- `services/report_service.py`
- `tests/test_services/test_backtesting_service.py`
- `tests/test_ui/test_history_page.py`
- `ui/routes/history.py`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-06-03: Implemented outcome calibration metrics and moved story to review.
- 2026-06-03: Fixed Story 6.4 review findings, expanded regressions, and moved story back to review.
- 2026-06-03: Re-ran code review and moved story back to in-progress for four remaining patch findings.
- 2026-06-03: Fixed remaining Story 6.4 rerun review findings, expanded regressions, and moved story back to review.
- 2026-06-03: Re-ran code review and moved story back to in-progress for four cache/deletion/calibration-math patch findings.
- 2026-06-03: Fixed third rerun review findings, expanded regressions, and moved story back to review.
- 2026-06-03: Re-ran code review and moved story back to in-progress for three feedback-window, cache-validation, and local-run evidence patch findings.
- 2026-06-03: Fixed fourth rerun review findings, expanded regressions, and moved story back to review.
- 2026-06-03: Re-ran code review and moved story back to in-progress for four cache-shape, confidence-bucket, ordering, and empty-seed patch findings.
- 2026-06-03: Fixed fifth rerun review findings, expanded regressions, and moved story back to review.
- 2026-06-03: Fixed final closeout review findings and kept Story 6.4 in review for closeout.
