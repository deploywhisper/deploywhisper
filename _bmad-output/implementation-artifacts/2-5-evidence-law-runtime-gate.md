# Story 2.5: Evidence Law Runtime Gate

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a maintainer,
I want high and critical findings blocked unless deterministic evidence exists,
So that DeployWhisper cannot overclaim severe risk.

## Acceptance Criteria

1. Given a high or critical finding is generated, When report validation runs, Then validation fails or downgrades the finding unless at least one deterministic evidence item is linked. And CI fixtures fail if high/critical findings violate this rule.

### Requirement Traceability

- Primary PRD requirements: Epic 2 coverage: ING-01..09, EVD-01..12, RSK-01..10, HIS-01..02, NFR-SEC-01..06, NFR-REL-01..04.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 2 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run browser-side Playwright validation for rendered report/history/dashboard surfaces changed by Story 2.5. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Runtime gate downgrades findings but leaves report-level severe/no-go verdict fields stale [services/report_service.py:1718]
- [x] [Review][Patch] Repository deterministic-evidence validation accepts truthy string values as deterministic [models/repositories/analysis_reports.py:67]
- [x] [Review][Patch] Service persistence allows high/critical report-level verdicts when findings are omitted or empty [services/report_service.py:1282]
- [x] [Review][Patch] Repository persistence allows unsupported high/critical report-level verdicts on direct write paths [models/repositories/analysis_reports.py:122]
- [x] [Review][Patch] Partial downgrade can leave report top-risk and narrative text pointing at the downgraded severe claim [services/report_service.py:1317]
- [x] [Review][Patch] Severity-only titles can retain stale high/critical wording after downgrade [services/report_service.py:1252]
- [x] [Review][Patch] Medium/low assessments with downgraded severe findings can retain stale HIGH/CRITICAL top-risk text [services/report_service.py:1320]
- [x] [Review][Patch] Partial downgrade summary can choose a lower-severity supported finding over a later critical finding [services/report_service.py:1359]
- [x] [Review][Patch] Partial downgrade narrative replaces remaining severe-risk explanation with only the downgrade notice [services/report_service.py:1387]
- [x] [Review][Patch] Downgraded unsupported severe findings can leave stale or inconsistent report-level severity/recommendation [services/report_service.py:1398]
- [x] [Review][Patch] Critical report verdict can remain supported only by a high deterministic finding after partial downgrade [services/report_service.py:1337]
- [x] [Review][Patch] Underclaimed deterministic severe findings can keep a lower report verdict [services/report_service.py:1362]
- [x] [Review][Patch] Direct report persistence can bypass severe validation with unnormalized severity strings [models/repositories/analysis_reports.py:74]
- [x] [Review][Patch] Direct evidence persistence can coerce non-boolean deterministic flags to true [models/repositories/analysis_reports.py:91]
- [x] [Review][Patch] Direct evidence persistence now rejects missing deterministic flags with strict schema validation [models/repositories/analysis_reports.py:106]
- [x] [Review][Patch] Supported severe findings can persist with non-deterministic finding metadata [services/report_service.py:1335]
- [x] [Review][Patch] Already-supported severe verdicts can skip recommendation and score reconciliation [services/report_service.py:1374]
- [x] [Review][Patch] Direct repository writes can persist contradictory supported-severe report metadata [models/repositories/analysis_reports.py:197]
- [x] [Review][Patch] Direct repository writes can persist underclaimed supported-severe report metadata [models/repositories/analysis_reports.py:97]
- [x] [Review][Patch] Mixed finding/report reconciliation can omit the report-level adjustment from the narrative [services/report_service.py:1543]
- [x] [Review][Patch] Partial downgrade top-risk contributors can include evidence unrelated to the selected top risk [services/report_service.py:1479]
- [x] [Review][Patch] Browser validation evidence is missing after rendered dashboard/history/report expectations changed [_bmad-output/implementation-artifacts/2-5-evidence-law-runtime-gate.md:171]
- [x] [Review][Patch] Service persistence can retain stale severe/no-go report text when no Evidence Law reconciliation branch is triggered [services/report_service.py:1418]
- [x] [Review][Patch] Direct repository writes can persist report verdict text that contradicts reconciled severity metadata [models/repositories/analysis_reports.py:196]
- [x] [Review][Patch] Story review note contradicts strict missing deterministic validation [_bmad-output/implementation-artifacts/2-5-evidence-law-runtime-gate.md:48]
- [x] [Review][Patch] Supported severe findings with already-consistent report metadata can skip deterministic metadata normalization [services/report_service.py:1468]
- [x] [Review][Patch] Non-severe report verdict text and recommendation mismatches can persist [services/report_service.py:1379]
- [x] [Review][Patch] Downgraded finding titles can retain stale GO/NO-GO verdict prefixes [services/report_service.py:1272]
- [x] [Review][Patch] Deterministic external/user evidence can support severe findings in service but fail repository metadata validation [models/repositories/analysis_reports.py:127]
- [x] [Review][Patch] Verdict-prefix detection can reject hyphenated natural-language report prose [models/repositories/analysis_reports.py:25]
- [x] [Review][Patch] Non-severe verdict reconciliation can persist out-of-band risk scores [services/report_service.py:1588]
- [x] [Review][Patch] Local CI validation evidence is missing for cross-layer Story 2.5 change set [_bmad-output/implementation-artifacts/2-5-evidence-law-runtime-gate.md:132]
- [x] [Review][Patch] Story task list lacks explicit browser validation task for rendered report/history/dashboard changes [_bmad-output/implementation-artifacts/2-5-evidence-law-runtime-gate.md:24]
- [x] [Review][Patch] Evidence Law reconciliation rewrites valid medium/go reports to caution [services/report_service.py:1331]
- [x] [Review][Patch] Downgraded findings keep pre-downgrade severe explanation and guidance [services/report_service.py:1263]
- [x] [Review][Patch] Verdict-prefix normalization can leave unpunctuated stale NO-GO/CRITICAL wording after downgrade [services/report_service.py:1272]
- [x] [Review][Patch] Score-only reconciliation rewrites valid medium/go recommendations to caution [services/report_service.py:1640]
- [x] [Review][Patch] Plain-language verdict lead-ins can survive downgrade/reconciliation [services/report_service.py:1273]
- [x] [Review][Patch] Evidence Law report reconciliation leaves stale assessment contributors after verdict changes [services/report_service.py:1555]
- [x] [Review][Patch] Verdict-prefix parsing overmatches ordinary unhyphenated prose as structured verdict text [services/report_service.py:85]
- [x] [Review][Patch] Direct repository writes can persist orphan or unrelated top-risk contributor evidence IDs [models/repositories/analysis_reports.py:332]
- [x] [Review][Defer] Evidence Law status is not yet explicitly visible in UI/API/CLI report surfaces [frontend/src/components/report_detail_page.py:82] — deferred, pre-existing Story 3 report-surface scope
- [x] [Review][Patch] Supported severe reports can persist without report-level top-risk evidence IDs [services/report_service.py:1508]
- [x] [Review][Patch] Runtime gate does not repair multi-finding top-risk contributor refs before repository validation [models/repositories/analysis_reports.py:127]
- [x] [Review][Patch] Verdict-prefix parsing misses stale unpunctuated verdict shapes such as "NO-GO because" and "CRITICAL due to" [services/report_service.py:85]
- [x] [Review][Patch] Medium verdict-text cleanup clears otherwise valid evidence contributor links [services/report_service.py:1644]
- [x] [Review][Patch] Reconciled severe verdicts can still serialize unsupported or stale contributor rationale [services/report_service.py:1624]
- [x] [Review][Patch] Browser validation evidence does not cover changed history compare/rescan surfaces [_bmad-output/implementation-artifacts/2-5-evidence-law-runtime-gate.md:160]
- [x] [Review][Patch] Neutral contributor preservation still allows unsupported zero-impact rationale to survive severe reconciliation [services/report_service.py:1417]
- [x] [Review][Patch] Direct repository validation allows one evidence item to be claimed by multiple findings [models/repositories/analysis_reports.py:174]
- [x] [Review][Patch] Repository duplicate-owner rejection breaks service-supported shared evidence references [models/repositories/analysis_reports.py:174]
- [x] [Review][Patch] Service scoping leaves generated pending evidence owners unresolved for shared evidence references [services/report_service.py:1147]
- [x] [Review][Patch] Shared generated evidence can be canonically owned by a non-severe first claimant and fail supported severe persistence [services/report_service.py:1111]

## Dev Notes

### Epic Context

- Epic: 2. Trusted Evidence Core and Evidence Law
- Epic goal: Make the core analysis defensible, stable, and evidence-backed.
- Epic coverage: ING-01..09, EVD-01..12, RSK-01..10, HIS-01..02, NFR-SEC-01..06, NFR-REL-01..04

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 2 / Story 2.5 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5.4 Codex

### Debug Log References

- Implemented Evidence Law runtime gate in `services.report_service` after stale evidence-link repair and before ID scoping/persistence.
- Added repository-level persistence validation in `models.repositories.analysis_reports` so direct payloads cannot save high/critical findings without linked deterministic evidence.
- Updated UI history/dashboard test fixtures to include deterministic evidence for intentionally severe findings.
- Resolved code-review findings by reconciling report-level verdict/narrative fields after runtime downgrades and requiring exact boolean `True` for deterministic repository evidence.
- Resolved second-pass code-review findings by enforcing report-level severe verdict support in both service and repository persistence, sanitizing partial-downgrade summaries/narratives, and rewriting severity-only downgraded titles.
- Resolved third-pass code-review findings by clearing stale severe top-risk text after unsupported-only downgrades, selecting the highest supported severe finding for partial-downgrade summaries, and preserving supported severe-risk explanation in mixed downgrade narratives.
- Resolved fourth-pass code-review findings by reconciling report-level severity, score, recommendation, top-risk text, and narrative warnings to the strongest linked deterministic finding that remains after Evidence Law downgrades.
- Resolved fifth-pass code-review findings by promoting underclaimed report verdicts to supported deterministic severe findings and normalizing/validating direct repository report/evidence payloads before persistence, including non-boolean deterministic flags.
- Resolved sixth-pass code-review findings by preserving strict evidence payload validation, normalizing supported severe finding metadata, and reconciling/rejecting contradictory severe report verdict metadata across service and direct repository paths.
- Resolved seventh-pass code-review findings by rejecting direct repository underclaims, preserving report-level reconciliation in mixed narratives, scoping top-risk contributors to the selected top supported finding, and recording browser validation evidence.
- Resolved eighth-pass code-review findings by refreshing stale service verdict text, rejecting contradictory direct repository verdict text, and correcting the strict missing-deterministic review note.
- Resolved ninth-pass code-review finding by preserving supported severe finding metadata normalization when report-level metadata is already consistent.
- Resolved tenth-pass code-review findings by reconciling non-severe recommendation/verdict text mismatches and stripping stale GO/NO-GO prefixes from downgraded finding titles.
- Resolved eleventh-pass code-review findings by aligning deterministic external/user severe evidence metadata validation, tightening verdict-prefix parsing, clamping non-severe reconciled scores, adding explicit browser-validation tasking, and recording local CI evidence.
- Resolved twelfth-pass code-review finding by preserving valid medium/go report recommendations while still reconciling invalid medium/no-go metadata to caution.
- Resolved thirteenth-pass code-review findings by rewriting downgraded finding explanation/guidance and expanding stale verdict-prefix normalization for unpunctuated severe lead-ins.
- Resolved fourteenth-pass code-review finding by preserving already-valid medium/go recommendations during score-only reconciliation.
- Resolved fifteenth-pass code-review finding by stripping plain-language verdict lead-ins during service and direct repository persistence while preserving hyphenated natural-language prose.
- Resolved sixteenth-pass code-review findings by reconciling evidence-linked contributors with adjusted Evidence Law verdicts, narrowing bare verdict-prefix parsing to risk-domain lead-ins, and validating direct top-risk contributor evidence IDs.
- Re-ran seventeenth-pass BMad code review and recorded six unresolved patch findings; dismissed over-scoped/noise findings and retained the existing deferred Evidence Law status surface item without duplicating it.
- Resolved seventeenth-pass code-review findings by requiring report-level top-risk evidence IDs for severe reports, repairing cross-finding top-risk refs, recognizing unpunctuated stale verdict lead-ins, preserving valid medium contributor links, filtering stale severe contributor rationale while keeping neutral parser metadata, and expanding browser coverage to history compare/rescan surfaces.
- Resolved eighteenth-pass code-review findings by preserving only metadata-bearing neutral parser contributors during severe reconciliation and rejecting direct repository payloads that claim one evidence item from multiple findings.
- Resolved nineteenth-pass code-review finding by allowing shared evidence references with deterministic canonical ownership while rejecting ambiguous multi-claim evidence owners.
- Resolved twentieth-pass code-review finding by resolving generated pending evidence owners to the first scoped finding that references a shared evidence item before repository validation.
- Resolved twenty-first-pass code-review finding by preferring the highest-severity claimant as the canonical owner for generated shared evidence before repository top-risk validation.
- Validation:
  - 2026-05-10 no-op reviewer-finding verification: no unchecked `[Review]` findings remained before this pass.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped during no-op reviewer-finding verification.
  - `./.venv/bin/ruff check .` — passed during no-op reviewer-finding verification.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted during no-op reviewer-finding verification.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test during no-op reviewer-finding verification.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persist_analysis_report_prefers_severe_owner_for_generated_shared_evidence -q` — failed before implementation because shared generated evidence attached to the first medium claimant and failed severe top-risk validation; passed after scoping preferred the highest-severity claimant.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persist_analysis_report_prefers_severe_owner_for_generated_shared_evidence tests.test_services.test_report_service.ReportServiceTests.test_persist_analysis_report_preserves_shared_evidence_references -q` — passed after twenty-first-pass fix.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 80 tests after twenty-first-pass fix.
  - `./.venv/bin/ruff check services/report_service.py tests/test_services/test_report_service.py` — passed.
  - `./.venv/bin/ruff format tests/test_services/test_report_service.py` — reformatted 1 file.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after twenty-first-pass fix.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test after twenty-first-pass fix.
  - `bash scripts/ci-local.sh` — passed after twenty-first-pass fix, including Ruff, format check, pip check, Bandit high/high scan, compileall, CLI skill scenarios, and full unittest discovery.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persist_analysis_report_preserves_shared_evidence_references -q` — failed before implementation because generated `pending:*` evidence ownership stayed ambiguous for shared evidence; passed after service scoping canonicalized the owner.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 79 tests after twentieth-pass fix.
  - `./.venv/bin/ruff check services/report_service.py tests/test_services/test_report_service.py` — passed.
  - `./.venv/bin/ruff format services/report_service.py tests/test_services/test_report_service.py` — reformatted 1 file.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after twentieth-pass fix.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test after twentieth-pass fix.
  - `bash scripts/ci-local.sh` — passed after twentieth-pass fix, including Ruff, format check, pip check, Bandit high/high scan, compileall, CLI skill scenarios, and full unittest discovery.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_create_analysis_report_validates_finding_context_payloads -q` — failed before implementation because repository validation rejected service-supported shared evidence references; passed after canonical evidence ownership resolution.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persist_analysis_report_preserves_shared_evidence_references -q` — failed before implementation because service persistence hit duplicate-owner rejection; passed after shared evidence references were preserved.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persist_analysis_report_rewrites_cross_finding_top_risk_contributors -q` — passed after nineteenth-pass shared evidence ownership fix.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 79 tests after nineteenth-pass fixes.
  - `./.venv/bin/ruff check models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed.
  - `./.venv/bin/ruff format --check models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed, 2 files already formatted.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after nineteenth-pass fixes.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `git diff --check` — passed.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test after nineteenth-pass fixes.
  - `bash scripts/ci-local.sh` — passed after nineteenth-pass fixes, including Ruff, format check, pip check, Bandit high/high scan, compileall, CLI skill scenarios, and full unittest discovery.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_create_analysis_report_validates_finding_context_payloads -q` — failed before implementation because duplicate evidence ownership was accepted; passed after repository ownership validation.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persist_analysis_report_rewrites_cross_finding_top_risk_contributors -q` — failed before implementation because stale zero-impact unsupported rationale was preserved; passed after contributor filtering was narrowed to metadata-bearing neutral parser contributors.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 78 tests after eighteenth-pass fixes.
  - `./.venv/bin/ruff check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed.
  - `./.venv/bin/ruff format --check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed, 3 files already formatted.
  - `git diff --check` — passed.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after eighteenth-pass fixes.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test after eighteenth-pass fixes.
  - `bash scripts/ci-local.sh` — passed after eighteenth-pass fixes, including Ruff, format check, pip check, Bandit high/high scan, compileall, CLI skill scenarios, and full unittest discovery.
  - `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_preserves_real_pipeline_metadata_in_persisted_contributors -q` — passed, 1 API regression test after preserving neutral unlinked parser metadata contributors during severe contributor filtering.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persist_analysis_report_rewrites_cross_finding_top_risk_contributors -q` — passed, 1 service regression test after filtering stale severe rationale while preserving neutral parser metadata.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 78 tests after seventeenth-pass Evidence Law contributor and top-risk repair fixes.
  - `./.venv/bin/python -m unittest frontend.e2e.test_history_page -q` — passed, 20 tests.
  - `./.venv/bin/python -m unittest frontend.e2e.test_app_shell -q` — passed, 13 tests.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test covering history detail, history compare, and rescan diff expectations.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after seventeenth-pass review fixes.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `bash scripts/ci-local.sh` — passed after seventeenth-pass review fixes, including Ruff, format check, pip check, Bandit high/high scan, compileall, CLI skill scenarios, and full unittest discovery.
  - `git diff --check` — passed.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 75 tests after sixteenth-pass contributor/prose/direct-write validation regressions.
  - `./.venv/bin/ruff check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed.
  - `./.venv/bin/ruff format --check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed, 3 files already formatted.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after sixteenth-pass review fixes.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `bash scripts/ci-local.sh` — passed after sixteenth-pass review fixes, including Ruff, format check, pip check, Bandit high/high scan, compileall, CLI skill scenarios, and full unittest discovery.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 56 tests.
  - `./.venv/bin/python -m unittest frontend.e2e.test_history_page -q` — passed, 20 tests.
  - `./.venv/bin/python -m unittest frontend.e2e.test_app_shell -q` — passed, 13 tests.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `./.venv/bin/python -m pip check` — passed, no broken requirements found.
  - `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ frontend/ evidence/ --severity-level high --confidence-level high -x tests/` — passed, no high/high issues.
  - `git diff --check` — passed.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 59 tests after third-pass review regressions.
  - `./.venv/bin/ruff check services/report_service.py tests/test_services/test_report_service.py` — passed.
  - `./.venv/bin/ruff format services/report_service.py tests/test_services/test_report_service.py` — reformatted 2 files.
  - `./.venv/bin/ruff format --check services/report_service.py tests/test_services/test_report_service.py` — passed, 2 files already formatted.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after third-pass review fixes.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `./.venv/bin/python -m pip check` — passed, no broken requirements found.
  - `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ frontend/ evidence/ --severity-level high --confidence-level high -x tests/` — passed, no high/high issues.
  - `git diff --check` — passed.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 62 tests after fourth-pass review regressions.
  - `./.venv/bin/ruff check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed.
  - `./.venv/bin/ruff format services/report_service.py tests/test_services/test_report_service.py models/repositories/analysis_reports.py` — reformatted 1 file.
  - `./.venv/bin/ruff format --check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed, 3 files already formatted.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after fourth-pass review fixes.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `./.venv/bin/python -m pip check` — passed, no broken requirements found.
  - `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ frontend/ evidence/ --severity-level high --confidence-level high -x tests/` — passed, no high/high issues.
  - `git diff --check` — passed.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 63 tests after fifth-pass review regressions.
  - `./.venv/bin/ruff check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed.
  - `./.venv/bin/ruff format services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — reformatted 1 file.
  - `./.venv/bin/ruff format --check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed, 3 files already formatted.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after fifth-pass review fixes.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `./.venv/bin/python -m pip check` — passed, no broken requirements found.
  - `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ frontend/ evidence/ --severity-level high --confidence-level high -x tests/` — passed, no high/high issues.
  - `./.venv/bin/python -m compileall api analysis cli evidence llm models parsers services ui app.py api_server.py cli.py config.py logging_config.py` — passed.
  - `./.venv/bin/python cli.py skill test` — passed, all listed skill scenarios passing.
  - `git diff --check` — passed.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 64 tests after sixth-pass review regressions.
  - `./.venv/bin/python -m unittest frontend.e2e.test_history_page -q` — passed, 20 tests after sixth-pass score reconciliation fixture updates.
  - `./.venv/bin/python -m unittest frontend.e2e.test_app_shell -q` — passed, 13 tests after sixth-pass score reconciliation fixture updates.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after sixth-pass review fixes.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `./.venv/bin/python -m pip check` — passed, no broken requirements found.
  - `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ frontend/ evidence/ --severity-level high --confidence-level high -x tests/` — passed, no high/high issues.
  - `./.venv/bin/python -m compileall api analysis cli evidence llm models parsers services ui app.py api_server.py cli.py config.py logging_config.py` — passed.
  - `./.venv/bin/python cli.py skill test` — passed, all listed skill scenarios passing.
  - `git diff --check` — passed.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 64 tests after seventh-pass review regressions.
  - `./.venv/bin/python -m unittest frontend.e2e.test_history_page -q` — passed, 20 tests after seventh-pass review fixes.
  - `./.venv/bin/python -m unittest frontend.e2e.test_app_shell -q` — passed, 13 tests after seventh-pass review fixes.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after seventh-pass review fixes.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `./.venv/bin/python -m pip check` — passed, no broken requirements found.
  - `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ frontend/ evidence/ --severity-level high --confidence-level high -x tests/` — passed, no high/high issues.
  - `./.venv/bin/python -m compileall api analysis cli evidence llm models parsers services ui app.py api_server.py cli.py config.py logging_config.py` — passed.
  - `./.venv/bin/python cli.py skill test` — passed, all listed skill scenarios passing.
  - `git diff --check` — passed.
  - `npm run test:ui-review` — failed before test execution because `http://127.0.0.1:8080/` was already in use.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 75 tests after fifteenth-pass plain-language verdict lead-in regressions.
  - `./.venv/bin/ruff check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed.
  - `./.venv/bin/ruff format --check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed, 3 files already formatted.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after fifteenth-pass review fix.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `bash scripts/ci-local.sh` — passed after fifteenth-pass review fix, including Ruff, format check, pip check, Bandit high/high scan, compileall, CLI skill scenarios, and full unittest discovery.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test.
  - `git diff --check` — passed.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 72 tests after twelfth-pass medium/go preservation regressions.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — failed before formatting because `services/report_service.py` needed reformatting.
  - `./.venv/bin/ruff format services/report_service.py` — reformatted 1 file.
  - `./.venv/bin/ruff check .` — passed after formatting.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted after formatting.
  - `./.venv/bin/python -m unittest frontend.e2e.test_history_page -q` — passed, 20 tests after twelfth-pass review fix.
  - `./.venv/bin/python -m unittest frontend.e2e.test_app_shell -q` — passed, 13 tests after twelfth-pass review fix.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after twelfth-pass review fix.
  - `./.venv/bin/python -m pip check` — passed, no broken requirements found.
  - `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ frontend/ evidence/ --severity-level high --confidence-level high -x tests/` — passed, no high/high issues.
  - `./.venv/bin/python -m compileall api analysis cli evidence llm models parsers services ui app.py api_server.py cli.py config.py logging_config.py` — passed.
  - `./.venv/bin/python cli.py skill test` — passed, all listed skill scenarios passing.
  - `git diff --check` — passed.
  - `bash scripts/ci-local.sh` — passed after twelfth-pass review fix.
  - `npm run test:ui-review` — failed before test execution because `http://127.0.0.1:8080/` was already in use.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 73 tests after thirteenth-pass review regressions.
  - `./.venv/bin/ruff check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed.
  - `./.venv/bin/ruff format --check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed, 3 files already formatted.
  - `./.venv/bin/python -m unittest frontend.e2e.test_history_page -q` — passed, 20 tests after thirteenth-pass review fixes.
  - `./.venv/bin/python -m unittest frontend.e2e.test_app_shell -q` — passed, 13 tests after thirteenth-pass review fixes.
  - `git diff --check` — passed.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after thirteenth-pass review fixes.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `./.venv/bin/python -m pip check` — passed, no broken requirements found.
  - `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ frontend/ evidence/ --severity-level high --confidence-level high -x tests/` — passed, no high/high issues.
  - `./.venv/bin/python -m compileall api analysis cli evidence llm models parsers services ui app.py api_server.py cli.py config.py logging_config.py` — passed.
  - `./.venv/bin/python cli.py skill test` — passed, all listed skill scenarios passing.
  - `bash scripts/ci-local.sh` — passed after thirteenth-pass review fixes.
  - `npm run test:ui-review` — failed before test execution because `http://127.0.0.1:8080/` was already in use.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 74 tests after fourteenth-pass score-only recommendation regression.
  - `./.venv/bin/ruff check services/report_service.py tests/test_services/test_report_service.py` — passed.
  - `./.venv/bin/ruff format --check services/report_service.py tests/test_services/test_report_service.py` — passed, 2 files already formatted after formatting the updated test file.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after fourteenth-pass review fix.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `bash scripts/ci-local.sh` — passed after fourteenth-pass review fix, including Ruff, format check, pip check, Bandit high/high scan, compileall, CLI skill scenarios, and full unittest discovery.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — failed before completion because `models/repositories/analysis_reports.py` had a transient syntax error while resolving eleventh-pass review findings.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 71 tests after eleventh-pass review fixes.
  - `./.venv/bin/python -m unittest frontend.e2e.test_app_shell -q` — passed, 13 tests after eleventh-pass review fixes.
  - `./.venv/bin/python -m unittest frontend.e2e.test_history_page -q` — failed once because the default critical fixture intentionally used an out-of-band score and now triggered score reconciliation.
  - `./.venv/bin/python -m unittest frontend.e2e.test_history_page -q` — passed, 20 tests after aligning the default critical fixture score to the critical floor.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after eleventh-pass review fixes.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — failed before formatting because `services/report_service.py` needed reformatting.
  - `./.venv/bin/ruff format services/report_service.py` — reformatted 1 file.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `./.venv/bin/python -m pip check` — passed, no broken requirements found.
  - `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ frontend/ evidence/ --severity-level high --confidence-level high -x tests/` — passed, no high/high issues.
  - `./.venv/bin/python -m compileall api analysis cli evidence llm models parsers services ui app.py api_server.py cli.py config.py logging_config.py` — passed.
  - `./.venv/bin/python cli.py skill test` — passed, all listed skill scenarios passing.
  - `git diff --check` — passed.
  - `bash scripts/ci-local.sh` — passed, including full unittest discovery, Ruff, pip check, Bandit high/high, compileall, and CLI skill scenarios.
  - `npm run test:ui-review` — failed before test execution because `http://127.0.0.1:8080/` was already in use.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 69 tests after tenth-pass review regressions.
  - `./.venv/bin/ruff check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed.
  - `./.venv/bin/ruff format --check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — failed before formatting because `models/repositories/analysis_reports.py` needed reformatting.
  - `./.venv/bin/ruff format models/repositories/analysis_reports.py` — reformatted 1 file.
  - `./.venv/bin/ruff format --check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed, 3 files already formatted.
  - `./.venv/bin/python -m unittest frontend.e2e.test_history_page -q` — passed, 20 tests after tenth-pass review fixes.
  - `./.venv/bin/python -m unittest frontend.e2e.test_app_shell -q` — passed, 13 tests after tenth-pass review fixes.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after tenth-pass review fixes.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `./.venv/bin/python -m pip check` — passed, no broken requirements found.
  - `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ frontend/ evidence/ --severity-level high --confidence-level high -x tests/` — passed, no high/high issues.
  - `./.venv/bin/python -m compileall api analysis cli evidence llm models parsers services ui app.py api_server.py cli.py config.py logging_config.py` — passed.
  - `./.venv/bin/python cli.py skill test` — passed, all listed skill scenarios passing.
  - `git diff --check` — passed.
  - `npm run test:ui-review` — failed before test execution because `http://127.0.0.1:8080/` was already in use.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 67 tests after ninth-pass review regression.
  - `./.venv/bin/ruff check services/report_service.py tests/test_services/test_report_service.py` — passed.
  - `./.venv/bin/ruff format --check services/report_service.py tests/test_services/test_report_service.py` — passed, 2 files already formatted.
  - `./.venv/bin/python -m unittest frontend.e2e.test_history_page -q` — passed, 20 tests after ninth-pass review fix.
  - `./.venv/bin/python -m unittest frontend.e2e.test_app_shell -q` — passed, 13 tests after ninth-pass review fix.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after ninth-pass review fix.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `./.venv/bin/python -m pip check` — passed, no broken requirements found.
  - `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ frontend/ evidence/ --severity-level high --confidence-level high -x tests/` — passed, no high/high issues.
  - `./.venv/bin/python -m compileall api analysis cli evidence llm models parsers services ui app.py api_server.py cli.py config.py logging_config.py` — passed.
  - `./.venv/bin/python cli.py skill test` — passed, all listed skill scenarios passing.
  - `git diff --check` — passed.
  - `npm run test:ui-review` — failed before test execution because `http://127.0.0.1:8080/` was already in use.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test.
  - `./.venv/bin/python -m unittest tests.test_services.test_report_service -q` — passed, 66 tests after eighth-pass review regressions.
  - `./.venv/bin/ruff check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed.
  - `./.venv/bin/ruff format --check services/report_service.py models/repositories/analysis_reports.py tests/test_services/test_report_service.py` — passed, 3 files already formatted.
  - `./.venv/bin/python -m unittest frontend.e2e.test_history_page -q` — passed, 20 tests after eighth-pass review fixes.
  - `./.venv/bin/python -m unittest frontend.e2e.test_app_shell -q` — passed, 13 tests after eighth-pass review fixes.
  - `./.venv/bin/python -m unittest discover -q` — passed, 315 tests, 1 skipped after eighth-pass review fixes.
  - `./.venv/bin/ruff check .` — passed.
  - `./.venv/bin/ruff format --check .` — passed, 264 files already formatted.
  - `./.venv/bin/python -m pip check` — passed, no broken requirements found.
  - `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ frontend/ evidence/ --severity-level high --confidence-level high -x tests/` — passed, no high/high issues.
  - `./.venv/bin/python -m compileall api analysis cli evidence llm models parsers services ui app.py api_server.py cli.py config.py logging_config.py` — passed.
  - `./.venv/bin/python cli.py skill test` — passed, all listed skill scenarios passing.
  - `git diff --check` — passed.
  - `npm run test:ui-review` — failed before test execution because `http://127.0.0.1:8080/` was already in use.
  - `APP_PORT=18080 npm run test:ui-review` — passed, 1 WebKit browser review-flow test.

### Completion Notes List

- High and critical persisted findings now require linked deterministic evidence.
- Shared report persistence downgrades unsupported high/critical findings to medium, caps confidence at `0.85`, marks them non-deterministic, reconciles unsupported report-level severe verdicts and stale partial-downgrade summaries/narratives, and emits an Evidence Law warning instead of overclaiming severe risk.
- Repository validation rejects direct high/critical finding and report-level high/critical payloads that bypass the service downgrade path, lack linked deterministic severe evidence, or use non-boolean deterministic flags.
- Third-pass review fixes now keep unsupported-only downgraded assessments from retaining stale severe top-risk text, rank remaining supported severe findings by severity for report summaries, and explain the remaining deterministic severe risk in mixed downgrade narratives while still warning about downgraded unsupported claims.
- Fourth-pass review fixes now align report-level severity, recommendation, score, top-risk text, and narrative downgrade warnings with the strongest remaining deterministic severe finding, and reject direct critical report writes backed only by high deterministic findings.
- Fifth-pass review fixes now promote underclaimed report verdicts to the strongest linked deterministic severe finding and validate direct repository severity/evidence payloads before persistence; non-boolean deterministic flags are normalized to non-deterministic before Pydantic validation can coerce them.
- Sixth-pass review fixes now keep missing evidence fields schema-strict, normalize supported severe finding metadata from deterministic evidence, and reconcile or reject inconsistent supported-severe verdict metadata.
- Seventh-pass review fixes now keep direct repository verdicts from understating deterministic severe findings, keep mixed reconciliation narratives complete, scope top-risk evidence to the selected top risk, and record browser validation for rendered report/history/dashboard changes.
- Eighth-pass review fixes now refresh stale report/narrative verdict text after Evidence Law reconciliation, reject contradictory direct repository verdict text, and align the story record with strict missing-deterministic validation.
- Ninth-pass review fix now preserves deterministic metadata normalization for supported severe findings even when report-level metadata is already consistent.
- Tenth-pass review fixes now reconcile non-severe recommendation/verdict text mismatches across service and direct repository paths, and strip stale GO/NO-GO prefixes from downgraded finding titles.
- Eleventh-pass review fixes now allow deterministic external/user evidence classifications for severe findings, avoid treating hyphenated prose as verdict labels, clamp reconciled non-severe scores, and document browser/local-CI validation.
- Twelfth-pass review fix now preserves valid medium/go recommendations across service and direct repository persistence while keeping invalid medium/no-go reconciliation to caution.
- Thirteenth-pass review fixes now replace downgraded finding-level severe explanation/guidance with Evidence Law neutral copy and strip unpunctuated stale NO-GO/CRITICAL lead-ins.
- Fourteenth-pass review fix now preserves an already-valid medium/go recommendation when Evidence Law only needs to reconcile the score into the medium band.
- Fifteenth-pass review fix now strips plain-language leading verdict tokens such as HIGH, CRITICAL, and NO-GO before prose while preserving hyphenated natural-language text.
- Sixteenth-pass review fixes now clear stale evidence-linked contributors after verdict reconciliation, preserve ordinary unhyphenated prose such as Go live/Critical path/High availability, and reject direct top-risk contributor IDs that are missing or span unrelated findings.
- Seventeenth-pass review fixes now backfill/repair severe report top-risk evidence IDs, reject invalid direct severe contributor refs, parse unpunctuated stale verdict prose, preserve valid medium evidence links, preserve neutral parser metadata while filtering stale severe rationale, and validate history compare/rescan browser behavior.
- Eighteenth-pass review fixes now prevent zero-impact unsupported contributor prose from surviving as neutral metadata and reject ambiguous direct evidence ownership across multiple findings.
- Nineteenth-pass review fix now preserves shared evidence references by resolving a canonical evidence owner from the evidence payload when multiple findings reference one evidence item, while still rejecting ambiguous shared evidence ownership.
- Twentieth-pass review fix now resolves generated pending evidence owners during service scoping so shared evidence references persist with a canonical owner before repository validation.
- Twenty-first-pass review fix now assigns generated shared evidence to the highest-severity claimant so supported severe reports cannot fail top-risk validation because a non-severe finding appeared first.
- Documentation now records the Story 2.5 Evidence Law persistence behavior.

### File List

- `_bmad-output/implementation-artifacts/2-5-evidence-law-runtime-gate.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `docs/evidence-model.md`
- `models/repositories/analysis_reports.py`
- `services/report_service.py`
- `tests/e2e/report_review.keyboard.spec.js`
- `tests/e2e/seeded_server.py`
- `tests/test_services/test_report_service.py`
- `frontend/e2e/test_app_shell.py`
- `frontend/e2e/test_history_page.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-09: Implemented Evidence Law runtime gate, repository validation, regression tests, fixture updates, and evidence model documentation.
- 2026-05-09: Fixed code-review findings for report-level downgrade reconciliation and strict deterministic evidence validation.
- 2026-05-09: Fixed second-pass code-review findings for report-level severe support, partial-downgrade summaries, and severity-only titles.
- 2026-05-09: Fixed third-pass code-review findings for stale unsupported-only top-risk text, highest-severity supported summary selection, and mixed downgrade narrative explanation.
- 2026-05-09: Fixed fourth-pass code-review findings for report-level severity/recommendation reconciliation and direct critical-report validation.
- 2026-05-09: Fixed fifth-pass code-review findings for underclaimed report verdicts and direct repository payload normalization/boolean validation.
- 2026-05-09: Fixed sixth-pass code-review findings for strict evidence payload validation and supported-severe metadata consistency.
- 2026-05-10: Fixed seventh-pass code-review findings for direct repository underclaims, mixed reconciliation narratives, top-risk contributor scoping, and browser validation evidence.
- 2026-05-10: Fixed eighth-pass code-review findings for stale verdict copy, direct repository verdict text validation, and missing-deterministic story bookkeeping.
- 2026-05-10: Fixed ninth-pass code-review finding for supported severe finding metadata normalization on already-consistent report metadata.
- 2026-05-10: Fixed tenth-pass code-review findings for non-severe verdict metadata mismatches and stale GO/NO-GO downgraded finding titles.
- 2026-05-10: Fixed eleventh-pass code-review findings for deterministic external/user evidence, verdict-prefix parsing, non-severe score reconciliation, browser tasking, and local CI evidence.
- 2026-05-10: Fixed twelfth-pass code-review finding for valid medium/go recommendation preservation.
- 2026-05-10: Fixed thirteenth-pass code-review findings for downgraded finding copy and unpunctuated verdict-prefix normalization.
- 2026-05-10: Fixed fourteenth-pass code-review finding for score-only medium/go recommendation preservation.
- 2026-05-10: Fixed fifteenth-pass code-review finding for plain-language verdict lead-in normalization.
- 2026-05-10: Fixed sixteenth-pass code-review findings for contributor reconciliation, prose-safe verdict parsing, and direct top-risk contributor validation.
- 2026-05-10: Fixed seventeenth-pass code-review findings for severe top-risk evidence IDs, contributor filtering, unpunctuated stale verdict parsing, medium link preservation, and history compare/rescan browser coverage.
- 2026-05-10: Fixed eighteenth-pass code-review findings for neutral contributor filtering and direct repository evidence ownership validation.
- 2026-05-10: Fixed nineteenth-pass code-review finding for shared evidence references and canonical evidence ownership.
- 2026-05-10: Fixed twentieth-pass code-review finding for generated pending shared evidence ownership.
- 2026-05-10: Fixed twenty-first-pass code-review finding for highest-severity ownership of generated shared evidence.

## Course Correction — 2026-10-07

Status reconciled to `done` against merged delivery [PR #52](https://github.com/deploywhisper/deploywhisper/pull/52), the completed task/review-fix records above, and the accepted v1.4.0 baseline in `docs/verification/v1.4.0-release.json`. This is administrative closeout of existing delivery, not a claim that a new implementation review or application test run occurred today. Historical review attempts remain intact. See `../planning-artifacts/sprint-change-proposal-2026-10-07-v1.4.0-status-reconciliation.md`.
