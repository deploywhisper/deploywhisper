# Story 8.3: External Evidence Report Context

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a reviewer,
I want scanner context visible but clearly labeled,
So that I know what came from DeployWhisper versus another tool.

## Acceptance Criteria

1. Given external scanner findings are linked to a report, When the report, PR comment, or API output renders, Then scanner findings are labeled as external evidence. And they do not automatically become high/critical DeployWhisper findings.

### Requirement Traceability

- Primary PRD requirements: Epic 8 coverage: EXT-01..08, ADM-10, EVD-04, REV-02, WRK-04, DOC-25.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 8 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Report finding rows need explicit external-evidence labels [frontend/src/screens/Report.tsx:429]
- [x] [Review][Patch] Share-summary findings need per-finding external-evidence labels in JSON, markdown, and plain text [services/analysis_service.py:1624]
- [x] [Review][Patch] Evidence register title must not call external scanner context deterministic evidence [frontend/src/screens/Report.tsx:586]
- [x] [Review][Patch] Repository boundary needs a regression test for scanner-only severe evidence rejection [models/repositories/analysis_reports.py:425]
- [x] [Review][Patch] Report-detail API should emit server-derived external evidence labels instead of making the UI re-derive scanner provenance [services/report_service.py:4216]
- [x] [Review][Patch] Mixed DeployWhisper plus scanner findings should use precise `Includes external context` wording instead of labeling the entire finding `External evidence` [services/analysis_service.py:1515]
- [x] [Review][Patch] External scanner checks should inspect both `source_kind` and `source_type` instead of letting a stale `source_kind` hide scanner context [services/analysis_service.py:1508]
- [x] [Review][Patch] Report header still labels external scanner context as deterministic evidence [frontend/src/screens/Report.tsx:331]
- [x] [Review][Patch] Report-detail finding labels ignore external evidence linked only through `evidence_refs` [services/report_service.py:4394]
- [x] [Review][Patch] Share-summary finding evidence counts ignore ref-linked evidence when owned evidence exists [services/analysis_service.py:1484]
- [x] [Review][Patch] Legacy UI fallback does not preserve mixed-vs-external evidence labeling [frontend/src/screens/Report.tsx:200]
- [x] [Review][Patch] Header and evidence-register summary can render impossible external-evidence counts [frontend/src/screens/Report.tsx:218]
- [x] [Review][Patch] External-context labels treat every non-scanner source as DeployWhisper support [services/analysis_service.py:1525]
- [x] [Review][Patch] Share-summary output can omit external scanner findings outside the top-three slice [services/analysis_service.py:1678]
- [x] [Review][Patch] Share-summary external-context finding selection needs a hard bound and compact-mode duplicate-title handling [services/analysis_service.py:1688]
- [x] [Review][Patch] UI external-context evidence totals can undercount actual evidence rows when payload counts lag rendered rows [frontend/src/screens/Report.tsx:236]
- [x] [Review][Patch] Report schema example contradicts scanner-only evidence downgrade semantics [docs/schemas/report-v2.md:153]
- [x] [Review][Patch] UI external-context count should not undercount rendered scanner evidence rows when payload external count lags [frontend/src/screens/Report.tsx:236]
- [x] [Review][Patch] Share-summary extra external-context slots should prioritize pure scanner-only findings before mixed-context findings [services/analysis_service.py:1697]
- [x] [Review][Patch] Repository Evidence Law gate should not treat user-provided context as DeployWhisper deterministic support [models/repositories/analysis_reports.py:523]
- [x] [Review][Patch] UI external-context count should not exceed total evidence when payload external counts are stale-high [frontend/src/screens/Report.tsx:236]
- [x] [Review][Patch] Positive DeployWhisper source detection should not hard-code only known internal source names [models/repositories/analysis_reports.py:523]
- [x] [Review][Patch] Compact PR/share summary must preserve top-risk findings before adding lower-severity scanner context [services/analysis_service.py:1853]
- [x] [Review][Patch] Internal-only redacted reports should not undercount evidence totals [frontend/src/screens/Report.tsx:236]
- [x] [Review][Patch] Share-summary totals should not label all evidence deterministic when no external rows are visible [frontend/src/screens/Report.tsx:331]
- [x] [Review][Patch] Report-detail schema examples should show additive `evidence_label` fields [docs/schemas/report-v2.md:153]
- [x] [Review][Patch] Share-summary markdown should not duplicate severity prefixes [services/analysis_service.py:1742]
- [x] [Review][Patch] UI external-context count should trust rendered scanner rows when rendered rows already match payload total [frontend/src/screens/Report.tsx:236]
- [x] [Review][Patch] Story file list should include the report schema documentation regression test [tests/test_docs/test_report_schema_documentation.py:34]
- [x] [Review][Patch] Partially redacted reports should not count visible internal evidence rows as stale external context [frontend/src/screens/Report.tsx:233]
- [x] [Review][Patch] Cross-layer Story 8.3 completion should record `bash scripts/ci-local.sh` validation before remaining `done` [_bmad-output/implementation-artifacts/8-3-external-evidence-report-context.md:117]
- [x] [Review][Patch] Share-summary redaction should preserve external-context labels and counts when evidence rows are omitted [services/analysis_service.py:1773]
- [x] [Review][Patch] Story closure should happen on a short-lived Git Flow branch rather than `develop` [_bmad-output/project-context.md:76]
- [x] [Review][Patch] Redacted share summaries should preserve prior total evidence count alongside prior external count [services/analysis_service.py:1797]
- [x] [Review][Patch] Partially redacted share summaries should clamp stored external counts by visible internal evidence rows [services/analysis_service.py:1727]
- [x] [Review][Patch] Redacted evidence registers should render an explicit omitted-detail state instead of an empty body [frontend/src/screens/Report.tsx:662]

## Dev Notes

### Epic Context

- Epic: 8. Existing Security Tool Integration
- Epic goal: Make DeployWhisper complementary to scanners rather than a replacement or severity passthrough.
- Epic coverage: EXT-01..08, ADM-10, EVD-04, REV-02, WRK-04, DOC-25

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 8 / Story 8.3 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5.4 Codex

### Debug Log References

- 2026-06-24: Red tests added for scanner-only severe downgrade, share-summary external scanner context labeling, and report UI external evidence labeling.
- 2026-06-24: `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persist_analysis_report_downgrades_external_scanner_only_severe_finding tests.test_services.test_adapter_output_contract.AdapterOutputContractTests.test_share_summary_labels_external_scanner_context_for_comments` failed before implementation, then passed after implementation.
- 2026-06-24: `npm run ui:test -- Report.test.tsx` passed after adding the report UI regression.
- 2026-06-24: `./.venv/bin/python -m unittest tests.test_services.test_report_service tests.test_services.test_adapter_output_contract` passed.
- 2026-06-24: `./.venv/bin/ruff check .` passed.
- 2026-06-24: `./.venv/bin/ruff format --check .` initially reported formatting drift in `models/repositories/analysis_reports.py` and `services/analysis_service.py`; `./.venv/bin/ruff format models/repositories/analysis_reports.py services/analysis_service.py` reformatted both files.
- 2026-06-24: `./.venv/bin/ruff check .` passed after formatting.
- 2026-06-24: `./.venv/bin/ruff format --check .` passed after formatting.
- 2026-06-24: `./.venv/bin/python -m pip check` passed.
- 2026-06-24: `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ evidence/ --severity-level high --confidence-level high -x tests/` passed with no high-severity issues.
- 2026-06-24: `./.venv/bin/python -m unittest discover -q` passed after formatting: 345 tests, 1 skipped.
- 2026-06-24: `npm run ui:typecheck` passed.
- 2026-06-24: `docker compose up -d --build` completed and started the composed app.
- 2026-06-24: `curl -fsSL http://127.0.0.1:8080/api/v1/health` returned status `ok`.
- 2026-06-24: `BASE_URL=http://127.0.0.1:8080 npm run test:ui-review` passed: 8 Playwright tests.
- 2026-06-24: `docker compose down` stopped and removed the validation stack.
- 2026-06-24: Code review findings fixed: per-finding external evidence labels added to report rows and share-summary findings; evidence register title now distinguishes scanner context from deterministic items; repository regression added for scanner-only severe direct persistence rejection.
- 2026-06-24: `./.venv/bin/python -m unittest tests.test_services.test_report_service tests.test_services.test_adapter_output_contract` passed after review fixes: 182 tests.
- 2026-06-24: `npm run ui:test -- Report.test.tsx` passed after review fixes: 9 tests.
- 2026-06-24: `npm run ui:typecheck` passed after review fixes.
- 2026-06-24: `./.venv/bin/ruff check .` passed after review fixes.
- 2026-06-24: `./.venv/bin/ruff format --check .` passed after review fixes: 255 files already formatted.
- 2026-06-24: `./.venv/bin/python -m unittest discover -q` passed after review fixes: 345 tests, 1 skipped.
- 2026-06-24: `docker compose up -d --build` completed after review fixes and rebuilt the production frontend bundle.
- 2026-06-24: `curl -fsSL http://127.0.0.1:8080/api/v1/health` returned status `ok` after review fixes.
- 2026-06-24: `BASE_URL=http://127.0.0.1:8080 npm run test:ui-review` passed after review fixes: 8 Playwright tests.
- 2026-06-24: `docker compose down` stopped and removed the validation stack after review fixes.
- 2026-06-25: Second-pass review findings fixed: report-detail API now emits server-derived finding/evidence labels, mixed DeployWhisper plus scanner findings use `Includes external context`, and scanner checks inspect both `source_kind` and `source_type`.
- 2026-06-25: `./.venv/bin/python -m unittest tests.test_services.test_report_service tests.test_services.test_adapter_output_contract` initially failed on a stale test expectation for normalized `source_kind`, then passed after correction: 182 tests.
- 2026-06-25: `npm run ui:test -- Report.test.tsx` passed after second-pass review fixes: 10 tests.
- 2026-06-25: `./.venv/bin/ruff check .` passed after second-pass review fixes.
- 2026-06-25: `./.venv/bin/ruff format --check .` passed after second-pass review fixes: 255 files already formatted.
- 2026-06-25: `npm run ui:typecheck` passed after second-pass review fixes.
- 2026-06-25: `./.venv/bin/python -m unittest discover -q` passed after second-pass review fixes: 345 tests, 1 skipped.
- 2026-06-25: `docker compose up -d --build` completed after second-pass review fixes and rebuilt the production frontend bundle.
- 2026-06-25: `curl -fsSL http://127.0.0.1:8080/api/v1/health` returned status `ok` after second-pass review fixes.
- 2026-06-25: `BASE_URL=http://127.0.0.1:8080 npm run test:ui-review` passed after second-pass review fixes: 8 Playwright tests.
- 2026-06-25: `docker compose down` stopped and removed the validation stack after second-pass review fixes.
- 2026-06-25: Third-pass review findings fixed: report overview/register summary copy now distinguishes external context, report-detail labels merge ORM-owned evidence with `evidence_refs`, and share-summary per-finding evidence counts use ref-linked evidence.
- 2026-06-25: `npm run ui:test -- Report.test.tsx` passed after third-pass review fixes: 10 tests.
- 2026-06-25: `./.venv/bin/python -m unittest tests.test_services.test_report_service tests.test_services.test_adapter_output_contract` passed after third-pass review fixes: 183 tests.
- 2026-06-25: `./.venv/bin/ruff check .` passed after third-pass review fixes.
- 2026-06-25: `./.venv/bin/ruff format --check .` passed after third-pass review fixes: 255 files already formatted.
- 2026-06-25: `npm run ui:typecheck` passed after third-pass review fixes.
- 2026-06-25: `./.venv/bin/python -m unittest discover -q` passed after third-pass review fixes: 345 tests, 1 skipped.
- 2026-06-25: `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ evidence/ --severity-level high --confidence-level high -x tests/` passed after third-pass review fixes with no high-severity issues.
- 2026-06-25: `docker compose up -d --build` completed after third-pass review fixes and rebuilt the production frontend bundle.
- 2026-06-25: `curl -fsSL http://127.0.0.1:8080/api/v1/health` returned status `ok` after third-pass review fixes.
- 2026-06-25: `BASE_URL=http://127.0.0.1:8080 npm run test:ui-review` passed after third-pass review fixes: 8 Playwright tests.
- 2026-06-25: `docker compose down` stopped and removed the validation stack after third-pass review fixes.
- 2026-06-25: Fourth-pass review regressions added for share-summary external findings past top-three, scanner plus user-context labeling, legacy UI fallback mixed labels, and single-source evidence count rendering; focused red tests failed before implementation and passed after fixes.
- 2026-06-25: `./.venv/bin/python -m unittest tests.test_services.test_adapter_output_contract.AdapterOutputContractTests.test_share_summary_keeps_external_scanner_findings_after_top_three tests.test_services.test_adapter_output_contract.AdapterOutputContractTests.test_share_summary_does_not_treat_user_context_as_deploywhisper_support tests.test_services.test_report_service.ReportServiceTests.test_persist_analysis_report_does_not_label_user_context_as_deploywhisper_support` passed after fourth-pass fixes: 3 tests.
- 2026-06-25: `npm run ui:test -- Report.test.tsx` passed after fourth-pass fixes: 12 tests.
- 2026-06-25: `./.venv/bin/python -m unittest tests.test_services.test_report_service tests.test_services.test_adapter_output_contract` passed after fourth-pass fixes: 186 tests.
- 2026-06-25: `npm run ui:typecheck` passed after fourth-pass fixes.
- 2026-06-25: `./.venv/bin/ruff format services/analysis_service.py services/report_service.py tests/test_services/test_adapter_output_contract.py tests/test_services/test_report_service.py` completed after fourth-pass fixes: 4 files left unchanged.
- 2026-06-25: `./.venv/bin/ruff check .` passed after fourth-pass fixes.
- 2026-06-25: `./.venv/bin/ruff format --check .` passed after fourth-pass fixes: 255 files already formatted.
- 2026-06-25: `git diff --check` passed after fourth-pass fixes.
- 2026-06-25: `./.venv/bin/python -m unittest discover -q` passed after fourth-pass fixes: 345 tests, 1 skipped.
- 2026-06-25: `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ evidence/ --severity-level high --confidence-level high -x tests/` passed after fourth-pass fixes with no high-severity issues.
- 2026-06-25: `docker compose up -d --build` completed after fourth-pass fixes and rebuilt the production frontend bundle.
- 2026-06-25: `curl -fsSL http://127.0.0.1:8080/api/v1/health` returned status `ok` after fourth-pass fixes.
- 2026-06-25: `BASE_URL=http://127.0.0.1:8080 npm run test:ui-review` passed after fourth-pass fixes: 8 Playwright tests.
- 2026-06-25: `docker compose down` stopped and removed the validation stack after fourth-pass fixes.
- 2026-06-26: Fifth-pass review findings fixed: share-summary external-context expansion is bounded, compact markdown preserves duplicate-titled external labels, report UI totals include actual rendered evidence rows, and report schema docs now show mixed external context for high findings.
- 2026-06-26: `./.venv/bin/python -m unittest tests.test_services.test_adapter_output_contract.AdapterOutputContractTests.test_share_summary_caps_external_scanner_findings_after_top_three tests.test_services.test_adapter_output_contract.AdapterOutputContractTests.test_share_summary_compact_markdown_keeps_duplicate_title_external_label tests.test_services.test_adapter_output_contract.AdapterOutputContractTests.test_share_summary_keeps_external_scanner_findings_after_top_three` passed after fifth-pass fixes: 3 tests.
- 2026-06-26: `npm run ui:test -- Report.test.tsx` passed after fifth-pass fixes: 13 tests.
- 2026-06-26: `npm run ui:typecheck` passed after fifth-pass fixes.
- 2026-06-26: `./.venv/bin/ruff format services/analysis_service.py tests/test_services/test_adapter_output_contract.py` completed after fifth-pass fixes: 2 files left unchanged.
- 2026-06-26: `./.venv/bin/python -m unittest tests.test_services.test_report_service tests.test_services.test_adapter_output_contract` passed after fifth-pass fixes: 188 tests.
- 2026-06-26: `./.venv/bin/ruff check .` passed after fifth-pass fixes.
- 2026-06-26: `./.venv/bin/ruff format --check .` passed after fifth-pass fixes: 255 files already formatted.
- 2026-06-26: `git diff --check` passed after fifth-pass fixes.
- 2026-06-26: `./.venv/bin/python -m unittest discover -q` passed after fifth-pass fixes: 345 tests, 1 skipped.
- 2026-06-26: `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ evidence/ --severity-level high --confidence-level high -x tests/` passed after fifth-pass fixes with no high-severity issues.
- 2026-06-26: `docker compose up -d --build` completed after fifth-pass fixes and rebuilt the production frontend bundle.
- 2026-06-26: `curl -fsSL http://127.0.0.1:8080/api/v1/health` returned status `ok` after fifth-pass fixes.
- 2026-06-26: `BASE_URL=http://127.0.0.1:8080 npm run test:ui-review` passed after fifth-pass fixes: 8 Playwright tests.
- 2026-06-26: `docker compose down` stopped and removed the validation stack after fifth-pass fixes.
- 2026-06-26: Sixth-pass review findings fixed: UI external-context counts now prefer rendered scanner rows when payload external counts lag, and share-summary extra external-context slots prioritize scanner-only findings before mixed-context findings.
- 2026-06-26: `./.venv/bin/python -m unittest tests.test_services.test_adapter_output_contract.AdapterOutputContractTests.test_share_summary_caps_external_scanner_findings_after_top_three` passed after sixth-pass fixes: 1 test.
- 2026-06-26: `npm run ui:test -- Report.test.tsx` passed after sixth-pass fixes: 13 tests.
- 2026-06-26: `./.venv/bin/ruff format services/analysis_service.py tests/test_services/test_adapter_output_contract.py` completed after sixth-pass fixes: 1 file reformatted, 1 file left unchanged.
- 2026-06-26: `npm run ui:typecheck` passed after sixth-pass fixes.
- 2026-06-26: `./.venv/bin/python -m unittest tests.test_services.test_report_service tests.test_services.test_adapter_output_contract` passed after sixth-pass fixes: 188 tests.
- 2026-06-26: `./.venv/bin/ruff check .` passed after sixth-pass fixes.
- 2026-06-26: `./.venv/bin/ruff format --check .` passed after sixth-pass fixes: 255 files already formatted.
- 2026-06-26: `git diff --check` passed after sixth-pass fixes.
- 2026-06-26: `./.venv/bin/python -m unittest discover -q` passed after sixth-pass fixes: 345 tests, 1 skipped.
- 2026-06-26: `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ evidence/ --severity-level high --confidence-level high -x tests/` passed after sixth-pass fixes with no high-severity issues.
- 2026-06-26: `docker compose up -d --build` completed after sixth-pass fixes and rebuilt the production frontend bundle.
- 2026-06-26: `curl -fsSL http://127.0.0.1:8080/api/v1/health` returned status `ok` after sixth-pass fixes.
- 2026-06-26: `BASE_URL=http://127.0.0.1:8080 npm run test:ui-review` passed after sixth-pass fixes: 8 Playwright tests.
- 2026-06-26: `docker compose down` stopped and removed the validation stack after sixth-pass fixes.
- 2026-06-26: Seventh-pass BMad code review found repository/user-context Evidence Law drift and stale-high UI external-count handling; acceptance auditor reported no findings.
- 2026-06-26: `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_create_analysis_report_validates_finding_context_payloads` passed after seventh-pass fixes: 1 test.
- 2026-06-26: `npm run ui:test -- Report.test.tsx` passed after seventh-pass fixes: 14 tests.
- 2026-06-26: `./.venv/bin/ruff format models/repositories/analysis_reports.py tests/test_services/test_report_service.py` completed after seventh-pass fixes: 1 file reformatted, 1 file left unchanged.
- 2026-06-26: `npm run ui:typecheck` passed after seventh-pass fixes.
- 2026-06-26: `./.venv/bin/python -m unittest tests.test_services.test_report_service tests.test_services.test_adapter_output_contract` passed after seventh-pass fixes: 188 tests.
- 2026-06-26: `./.venv/bin/ruff check .` passed after seventh-pass fixes.
- 2026-06-26: `./.venv/bin/ruff format --check .` passed after seventh-pass fixes: 255 files already formatted.
- 2026-06-26: `git diff --check` passed after seventh-pass fixes.
- 2026-06-26: `./.venv/bin/python -m unittest discover -q` passed after seventh-pass fixes: 345 tests, 1 skipped.
- 2026-06-26: Eighth-pass BMad code review found hard-coded internal-source allowlisting, compact share-summary top-risk truncation, internal-only redacted report undercounting, deterministic wording drift, and missing `evidence_label` schema examples; all were fixed.
- 2026-06-26: Ninth-pass BMad code review found duplicated severity prefixes in share-summary markdown and stale-high UI external-context counts when rendered rows already match payload totals; both were fixed.
- 2026-06-26: Final BMad rerun Blind Hunter reported no findings; Acceptance Auditor found only the story file-list omission for `tests/test_docs/test_report_schema_documentation.py`, which was fixed.
- 2026-06-26: `npm run ui:test -- Report.test.tsx` passed after final review fixes: 16 tests.
- 2026-06-26: `npm run ui:typecheck` passed after final review fixes.
- 2026-06-26: `./.venv/bin/python -m unittest tests.test_services.test_report_service tests.test_services.test_adapter_output_contract tests.test_docs.test_report_schema_documentation` passed after final review fixes: 191 tests.
- 2026-06-26: `./.venv/bin/ruff check .` passed after final review fixes.
- 2026-06-26: `./.venv/bin/ruff format --check .` passed after final review fixes: 255 files already formatted.
- 2026-06-26: `git diff --check` passed after final review fixes.
- 2026-06-26: Final Edge Case Hunter found a partially redacted stale-high external-count boundary; final Acceptance Auditor required `bash scripts/ci-local.sh` validation to be recorded for the cross-layer diff; both were fixed.
- 2026-06-26: `npm run ui:test -- Report.test.tsx` passed after the final partial-redaction count fix: 17 tests.
- 2026-06-26: `npm run ui:typecheck` passed after the final partial-redaction count fix.
- 2026-06-26: Final BMad clean-confirmation rerun reported no code findings from Blind Hunter and no edge-case findings from Edge Case Hunter.
- 2026-06-26: `docker compose up -d --build` completed after the final UI count fix and rebuilt the production frontend bundle.
- 2026-06-26: `curl -fsSL http://127.0.0.1:8080/api/v1/health` returned status `ok` after the final UI count fix.
- 2026-06-26: `BASE_URL=http://127.0.0.1:8080 npm run test:ui-review` passed after the final UI count fix: 8 Playwright tests.
- 2026-06-26: `./.venv/bin/python -m unittest discover -q` passed after the final UI count fix: 345 tests, 1 skipped.
- 2026-06-26: `bash scripts/ci-local.sh` passed after final review fixes: Ruff, format check, pip check, Bandit high-confidence gate, compileall, `cli.py skill test`, and 345 unittest tests with 1 skipped.
- 2026-06-26: BMad rerun found share-summary redaction drift and non-compliant closure on `develop`; fixes moved the worktree to `feature/8-3-external-evidence-report-context` and made redacted share summaries reuse stored external-context labels/counts.
- 2026-06-26: `./.venv/bin/python -m unittest tests.test_services.test_adapter_output_contract.AdapterOutputContractTests.test_share_summary_preserves_external_context_when_evidence_rows_omitted tests.test_services.test_adapter_output_contract.AdapterOutputContractTests.test_share_summary_labels_external_scanner_context_for_comments` passed after BMad rerun fixes: 2 tests.
- 2026-06-26: `./.venv/bin/ruff format services/analysis_service.py tests/test_services/test_adapter_output_contract.py` completed after BMad rerun fixes: 1 file reformatted, 1 file left unchanged.
- 2026-06-26: `./.venv/bin/python -m unittest tests.test_services.test_adapter_output_contract tests.test_services.test_report_service tests.test_docs.test_report_schema_documentation` passed after BMad rerun fixes: 192 tests.
- 2026-06-26: `./.venv/bin/ruff check .` passed after BMad rerun fixes.
- 2026-06-26: `./.venv/bin/ruff format --check .` passed after BMad rerun fixes: 255 files already formatted.
- 2026-06-26: `git diff --check` passed after BMad rerun fixes.
- 2026-06-26: Clean-confirmation rerun found redacted share-summary total/external-count drift; fixes preserve prior total evidence count and clamp stored external counts by visible internal rows.
- 2026-06-26: `./.venv/bin/python -m unittest tests.test_services.test_adapter_output_contract.AdapterOutputContractTests.test_share_summary_preserves_external_context_when_evidence_rows_omitted tests.test_services.test_adapter_output_contract.AdapterOutputContractTests.test_share_summary_caps_external_context_when_rows_are_partially_redacted` passed after redacted count fixes: 2 tests.
- 2026-06-26: `./.venv/bin/ruff format services/analysis_service.py tests/test_services/test_adapter_output_contract.py` completed after redacted count fixes: 2 files left unchanged.
- 2026-06-26: Clean-confirmation Edge Case Hunter found the redacted Confidence evidence register rendered a populated title with an empty body; the register now shows an omitted/redacted evidence-detail empty state.
- 2026-06-26: `npm run ui:test -- Report.test.tsx` passed after the redacted evidence-register empty-state fix: 17 tests.
- 2026-06-26: `npm run ui:typecheck` passed after the redacted evidence-register empty-state fix.
- 2026-06-26: `./.venv/bin/python -m unittest tests.test_services.test_adapter_output_contract tests.test_services.test_report_service tests.test_docs.test_report_schema_documentation` passed after the redacted evidence-register empty-state fix: 193 tests.
- 2026-06-26: `./.venv/bin/ruff check .` passed after the redacted evidence-register empty-state fix.
- 2026-06-26: `./.venv/bin/ruff format --check .` passed after the redacted evidence-register empty-state fix: 255 files already formatted.
- 2026-06-26: `git diff --check` passed after the redacted evidence-register empty-state fix.
- 2026-06-26: `bash scripts/ci-local.sh` passed after the redacted evidence-register empty-state fix: Ruff, format check, pip check, Bandit high-confidence gate, compileall, `cli.py skill test`, and 345 unittest tests with 1 skipped.

### Completion Notes List

- External scanner evidence now remains classified as external context and is not counted as DeployWhisper deterministic proof for high/critical Evidence Law support.
- Scanner-only high/critical report findings are downgraded/reconciled by the report service, and direct repository persistence no longer treats scanner evidence as sufficient severe support.
- Share-summary JSON, markdown, and plain text now include external scanner context counts/summaries for PR-comment and API consumers.
- Share-summary JSON, markdown, and plain text now label affected top findings as `External evidence`, not only the aggregate scanner context.
- Report overview, findings tab, and evidence register render `external_scanner` evidence as `External evidence` for reviewers.
- The evidence register title no longer calls scanner context deterministic evidence when external scanner items are present.
- Report-detail API output now carries server-derived `evidence_label` values on findings and evidence items; the UI only falls back to derivation for older payloads.
- Mixed DeployWhisper plus scanner findings now render `Includes external context` rather than labeling the entire finding `External evidence`.
- External scanner checks now inspect both `source_kind` and `source_type` so stale source-kind values cannot hide scanner context.
- The repository Evidence Law gate now uses the same positive DeployWhisper evidence-source rule as report/share-summary labeling, so `user_context` cannot support severe DeployWhisper findings.
- UI evidence summary counts now cap external-context counts at the total evidence count when payload counts are stale-high.
- Report overview and evidence register count labels now say when evidence includes external context instead of calling mixed scanner context deterministic evidence.
- Report-detail API finding labels now include external evidence linked by `evidence_refs`, even when a finding also owns DeployWhisper evidence.
- Share-summary top-finding `evidence_count` now counts the same linked evidence set used for external-context labels.
- Legacy UI fallback labeling now mirrors server-side linked-evidence semantics before consulting `evidence_classification`.
- Report header and evidence register use one evidence-count source, avoiding contradictory external-context totals when evidence rows are partial or redacted.
- External-context labels now use a positive DeployWhisper evidence-source predicate, so `user_context` does not make scanner evidence look first-party.
- Share-summary output now preserves external-labeled scanner findings beyond the ordinary top-three finding slice.
- Share-summary external-context expansion is now bounded and compact markdown keeps duplicate-titled external labels.
- Report header and evidence register totals now prefer the largest available evidence count across rendered rows and share-summary payload counts.
- Report header and evidence register external-context counts now prefer rendered scanner rows when payload external counts lag.
- Share-summary extra external-context slots now prioritize pure scanner-only findings before mixed-context findings.
- Report schema docs, evidence model docs, and the checked-in TypeScript API schema mirror were updated for the additive share-summary fields and per-finding label.
- Positive DeployWhisper evidence classification now excludes known non-DeployWhisper sources without rejecting future internal parser/source names.
- Compact share-summary markdown keeps the top three ranked findings before bounded external-context expansion.
- Internal-only redacted reports now preserve evidence totals without inventing deterministic wording.
- Share-summary markdown de-duplicates severity prefixes for findings whose titles already carry severity.
- Report-detail schema examples and documentation regression tests now cover additive `evidence_label` fields.
- Partially redacted report summaries cap external-context counts by visible non-external evidence rows, so stale payload totals cannot classify visible internal evidence as external context.
- Redacted share-summary generation preserves stored external-context finding labels and external evidence counts when detailed evidence rows are omitted.
- Redacted share-summary generation also preserves stored total evidence counts, preventing contradictory `0 evidence items` with external-context summaries.
- Partially redacted share summaries clamp stored external counts by the number of visible non-external rows.
- Redacted evidence registers now show an explicit omitted/redacted detail state when aggregate counts exist but row-level evidence has been suppressed.
- Story closure work now lives on `feature/8-3-external-evidence-report-context` instead of `develop`.

### File List

- `_bmad-output/implementation-artifacts/8-3-external-evidence-report-context.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `api/schemas.py`
- `docs/evidence-model.md`
- `docs/schemas/report-v2.md`
- `frontend/src/api/schema.d.ts`
- `frontend/src/screens/Report.test.tsx`
- `frontend/src/screens/Report.tsx`
- `frontend/src/screens/report.css`
- `models/repositories/analysis_reports.py`
- `services/analysis_service.py`
- `services/report_service.py`
- `tests/test_services/test_adapter_output_contract.py`
- `tests/test_docs/test_report_schema_documentation.py`
- `tests/test_services/test_report_service.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-06-24: Implemented external scanner report context labeling and prevented scanner-only evidence from satisfying high/critical DeployWhisper severity proof.
- 2026-06-24: Fixed code review findings for per-finding external labels across report, PR-comment/API summaries, evidence register copy, and repository boundary coverage.
- 2026-06-25: Fixed second-pass code review findings for server-derived report-detail labels, mixed external-context wording, and stale `source_kind` scanner detection.
- 2026-06-25: Fixed third-pass code review findings for external-context header copy, ref-linked report-detail labels, and ref-linked share-summary evidence counts.
- 2026-06-25: Fixed fourth-pass code review findings for legacy UI fallback labels, evidence-count source consistency, positive DeployWhisper evidence-source detection, and external scanner findings outside top-three share-summary output.
- 2026-06-26: Fixed fifth-pass code review findings for bounded share-summary external-context expansion, stale UI count fallback, and scanner evidence schema example semantics.
- 2026-06-26: Fixed sixth-pass code review findings for stale UI external-count fallback and scanner-only priority in share-summary extra slots.
- 2026-06-26: Fixed seventh-pass code review findings for repository user-context Evidence Law support and stale-high UI external evidence counts.
- 2026-06-26: Fixed final-pass review findings for source-classification breadth, compact summary ordering, redacted report counts, neutral evidence wording, schema examples, severity-prefix de-duplication, and story file-list completeness.
- 2026-06-26: Fixed clean-confirmation findings for partially redacted stale-high external-context counts and recorded required local CI validation.
- 2026-06-26: Fixed BMad rerun findings for redacted share-summary external-context preservation and Git Flow branch compliance.
- 2026-06-26: Fixed clean-confirmation findings for redacted share-summary total/external count consistency.
- 2026-06-26: Fixed clean-confirmation finding for the redacted evidence-register empty state.
