# Story 3.4: Confidence Ledger and Why-Not-Lower/Higher

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a reviewer,
I want to know why the verdict is not lower or higher,
So that severity reasoning is explainable.

## Acceptance Criteria

1. Given a verdict is produced, When the reviewer opens reasoning details, Then the report shows contributors, confidence factors, why-not-lower, why-not-higher, and uncertainty drivers. And explanations remain grounded in evidence and context.

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

- [x] [Review][Decision] Decide whether confidence-ledger reasoning must move into the shared report model — moved ledger derivation into `services/confidence_ledger.py`, attached the derived payload in `services/report_service.py`, and exposed it through API schemas so UI/API/shared report surfaces use one shared model.
- [x] [Review][Patch] Make contributor contribution parsing tolerant of legacy or malformed report payloads [`services/confidence_ledger.py`]
- [x] [Review][Patch] Ensure displayed contributors include the contributor used by why-not-lower reasoning [`services/confidence_ledger.py`]
- [x] [Review][Patch] Ground why-not-higher in report-specific evidence/context, not only generic threshold language [`services/confidence_ledger.py`]
- [x] [Review][Patch] Add confidence-ledger coverage to the shared `/reports/{id}` report view or redirect saved-report review to a surface that includes the ledger [`app.py`]
- [x] [Review][Patch] Fix why-not-higher threshold explanations so they cannot claim a score is below the next severity threshold when it is not, and align the low-to-medium boundary with canonical report-service severity floors. [`services/confidence_ledger.py:281`]
- [x] [Review][Patch] Avoid deriving Evidence Law failure text for list/summary serializations that intentionally omit evidence rows; ledger evidence-status wording must distinguish omitted detail from missing deterministic evidence. [`services/report_service.py:2630`]
- [x] [Review][Patch] Normalize or regenerate malformed/partial confidence-ledger list sections before rendering or redacting so a string payload cannot become one bullet per character and empty cards get sane fallback content. [`frontend/src/components/confidence_ledger.py:25`]
- [x] [Review][Patch] Filter uncertainty drivers so non-uncertainty administrative warnings do not appear as context/evidence uncertainty drivers. [`services/confidence_ledger.py:337`]
- [x] [Review][Patch] Complete the required manual screen-reader review validation or resolve the web-server startup blocker with recorded evidence. [`tests/e2e/report_review.keyboard.spec.js:3`]
- [x] [Review][Patch] Tolerate legacy or malformed contributor contribution values in the report-detail operational narrative before the confidence ledger renders. [`frontend/src/components/report_detail_page.py:154`]
- [x] [Review][Patch] Add exact command/result validation evidence to the Dev Agent Record for the Story 3.4 closure checks. [`_bmad-output/implementation-artifacts/3-4-confidence-ledger-and-why-not-lower-higher.md:98`]
- [x] [Review][Patch] Add API route/integration coverage proving serialized analysis responses include all five confidence-ledger sections. [`tests/test_api/test_analyses.py`]

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 3 / Story 3.4 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5.4

### Debug Log References

- Red phase: focused history-page tests first failed because `ui.components.confidence_ledger` did not exist.
- Green phase: focused ledger helper/detail-route tests passed after adding the renderer and aligning route assertions with existing confidence clamping for insufficient context.
- UI validation: keyboard review flow passed on the seeded Playwright report surface with the new confidence-ledger section in tab order.
- manual screen-reader validation was attempted with `APP_PORT=18080`, `APP_PORT=18081`, and `APP_PORT=18083`; the sandboxed seeded web server exited before Playwright test execution because retired Python UI startup attempted system semaphore access denied by the sandbox. The seeded-server startup blocker was resolved for the browser lane by disabling retired Python UI's process-pool setup in the E2E server and rerunning outside the sandbox.
- manual screen-reader validation rerun outside the sandbox reached the test body, but Guidepup failed with `manual screen-reader automation not supported`; `defaults read com.apple.manual screen-reader4/default SCREnableAppleScript` returned `1`, while `/private/var/db/Accessibility/.manual screen-readerAppleScriptEnabled` was absent. The required WebKit keyboard review lane passed outside the sandbox.
- Review fix validation: focused API/UI/service ledger tests passed, broader affected API/UI/service/CLI suite passed, full unittest discovery passed, whole-repo Ruff lint/format passed, WebKit Playwright review lane passed, high/high Bandit passed, dependency audit passed, and `git diff --check` passed.
- Final review follow-up validation commands/results:
  - `./.venv/bin/ruff check api/schemas.py app.py frontend/src/components/report_detail_page.py tests/test_api/test_schemas.py tests/test_api/test_analyses.py frontend/e2e/test_history_page.py` - passed.
  - `./.venv/bin/ruff check .` - passed.
  - `./.venv/bin/ruff format --check .` - passed (`271 files already formatted`).
  - `git diff --check` - passed.
  - `./.venv/bin/python -m unittest tests.test_api.test_schemas.ApiSchemaTests.test_persisted_report_exposes_confidence_ledger tests.test_api.test_schemas.ApiSchemaTests.test_persisted_report_normalizes_legacy_confidence_ledger tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_preserves_real_pipeline_metadata_in_persisted_contributors frontend.e2e.test_history_page.HistoryPageHelpersTests.test_confidence_ledger_normalizes_malformed_ledger_sections frontend.e2e.test_history_page.HistoryPageRenderingTests.test_history_detail_route_renders_confidence_ledger frontend.e2e.test_history_page.HistoryPageRenderingTests.test_history_detail_route_tolerates_legacy_contributor_values -q` - initially failed on a missing confidence fixture and legacy contributor metadata assumptions; passed after fixes (`Ran 6 tests ... OK`).
  - `./.venv/bin/python -m unittest tests.test_api.test_schemas tests.test_api.test_analyses tests.test_services.test_report_service frontend.e2e.test_history_page -q` - passed (`Ran 212 tests in 46.030s`, `OK`).
  - `./.venv/bin/python -m unittest discover -q` - passed (`Ran 399 tests in 42.251s`, `OK (skipped=1)`).
  - `./.venv/bin/bandit -r app.py api services ui tests/e2e/seeded_server.py --severity-level high --confidence-level high -q` - passed.
  - `./.venv/bin/python -m pip_audit -r requirements.txt` - passed (`No known vulnerabilities found`).
  - `bash scripts/ci-local.sh` - passed; local CI completed Ruff, format, dependency check, Bandit, compile, parser scenarios, and unittest discovery (`Ran 399 tests in 41.468s`, `OK (skipped=1)`).
  - `APP_PORT=18090 npm run test:ui-review` - passed (`3 passed (14.8s)`).
- Local screen-reader validation is not applicable for this project environment per project directive; use the React SPA Playwright/a11y lane unless manual assistive-technology validation is explicitly requested.
- BMad code review rerun: clean review; Blind Hunter, Edge Case Hunter, and Acceptance Auditor passes found no new actionable findings.

### Completion Notes List

- Added shared confidence-ledger derivation in `services/confidence_ledger.py` and attached it to persisted report serialization so UI, API, CLI-shaped persisted payloads, and public report views consume the same derived model.
- Made contributor parsing tolerant of legacy string, decimal-string, and malformed values; sorted displayed contributors by parsed contribution so why-not-lower reasoning cannot cite a hidden contributor.
- Grounded why-not-higher in report-specific score threshold, strongest finding, top contributor, confidence, context, and Evidence Law status.
- Rendered the ledger on immediate upload results, persisted history detail pages, and shared `/reports/{id}` HTML reports.
- Added deterministic unit coverage for shared ledger derivation, persisted report serialization/redaction, API schema exposure, public report rendering, and persisted history detail rendering.
- Added Playwright keyboard/review coverage for the new ledger section and updated README feature copy.
- Security scan note: targeted high-severity/high-confidence Bandit passes, and the dependency audit reports no known vulnerabilities after the prior retired Python UI security upgrade.
- Re-run code review note: BMad review found five unresolved patch findings, so the story was returned to in-progress for follow-up.
- Follow-up review fixes: aligned confidence-ledger thresholds with canonical severity floors, prevented false below-threshold why-not-higher copy, distinguished omitted summary evidence from missing deterministic evidence, normalized malformed ledger sections before render/redaction, filtered administrative warnings out of uncertainty drivers, and resolved the E2E seeded-server startup blocker with recorded manual screen-reader environment evidence.
- Final review follow-up fixes: hardened report-detail operational narrative rendering for legacy contributor values and missing contributor metadata, normalized legacy schema confidence-ledger payloads, regenerated public report fallback ledgers, and added API route assertions proving assessment, persisted-report, and detail responses include all five ledger sections.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/3-4-confidence-ledger-and-why-not-lower-higher.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `api/schemas.py`
- `app.py`
- `services/confidence_ledger.py`
- `services/report_service.py`
- `tests/e2e/report_review.keyboard.spec.js`
- `tests/e2e/seeded_server.py`
- `tests/test_api/test_analyses.py`
- `tests/test_api/test_schemas.py`
- `tests/test_services/test_report_service.py`
- `frontend/e2e/test_history_page.py`
- `frontend/src/components/confidence_ledger.py`
- `frontend/src/components/report_detail_page.py`
- `frontend/src/components/upload_panel.py`
- `frontend/src/screens/confidence.py`
- `frontend/src/screens/report_header.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-19: Implemented confidence ledger reasoning details on report UI surfaces with unit, browser, lint, and regression validation.
- 2026-05-19: Fixed all Story 3.4 code-review findings by moving ledger derivation to the shared service/report model, hardening legacy contributor handling, grounding why-not-higher, exposing the ledger through schemas, and adding shared `/reports/{id}` coverage.
- 2026-05-19: Re-ran BMad code review; five patch findings remain open and Story 3.4 returned to in-progress.
- 2026-05-19: Fixed the remaining Story 3.4 review findings, reran focused/full validation, and returned Story 3.4 to review with manual screen-reader environment limitations recorded.
- 2026-05-19: Re-ran BMad code review; three patch findings remain open and Story 3.4 returned to in-progress.
- 2026-05-19: Fixed the final Story 3.4 review findings, recorded exact validation evidence, and returned Story 3.4 to review; local manual screen-reader validation is explicitly not applicable for this project environment.
- 2026-05-19: Re-ran BMad code review; clean review with no new actionable findings, and Story 3.4 moved to done.
