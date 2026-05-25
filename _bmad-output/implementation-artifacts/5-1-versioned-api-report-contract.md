# Story 5.1: Versioned API Report Contract

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a DeployWhisper user,
I want stable `/api/v1` report and analysis endpoints,
So that integrations can rely on machine-readable advisory output.

## Acceptance Criteria

1. Given an API client submits or retrieves analysis, When the API responds, Then it returns versioned report schema, project/workspace scope, evidence, findings, context, narrative status, and advisory recommendation. And errors use the existing API error envelope.

### Requirement Traceability

- Primary PRD requirements: Epic 5 coverage: WRK-01..10, REV-05..08, ADM-07, DOC-08.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 5 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Persisted report advisory semantics can diverge from the canonical submit-response advisory contract [services/report_service.py:3387]
- [x] [Review][Patch] Add regression coverage for persisted advisory parity and nested advisory top-risk redaction [tests/test_api/test_analyses.py:1079]
- [x] [Review][Patch] Persisted advisory still misclassifies built-in assessment warnings as narrative warnings [services/report_service.py:3401]
- [x] [Review][Patch] Submit advisory and persisted_report advisory can diverge on synthesized context_todos [services/report_service.py:3417]
- [x] [Review][Patch] List retrieval still omits evidence despite the Story 5.1 submit/list/detail contract [services/report_service.py:4185]
- [x] [Review][Patch] Add submit/list regression coverage for go advisory with narrative-only warnings [tests/test_api/test_analyses.py:146]
- [x] [Review][Patch] Document required advisory.top_risk in the report v2 advisory example [docs/schemas/report-v2.md:125]
- [x] [Review][Patch] Lock meta.api_version in report schema documentation tests [tests/test_docs/test_report_schema_documentation.py:32]
- [x] [Review][Patch] Advisory `partial_context` conflates evidence extraction gaps with parser partial context [services/report_service.py:3376]
- [x] [Review][Patch] History list pagination hydrates full evidence for the entire unpaginated scope [services/report_service.py:4180]
- [x] [Review][Patch] Normalize persisted advisory severity before strict API schema validation [services/report_service.py:3457]
- [x] [Review][Patch] Persisted advisory partial_context ignores per-artifact manifest partial signals [services/report_service.py:3368]
- [x] [Review][Patch] Partial-context derivation misses fallback manifest branches [services/report_service.py:3368]
- [x] [Review][Patch] Persisted advisory normalization can diverge from top-level severity/recommendation on legacy rows [services/report_service.py:3648]
- [x] [Review][Patch] Persisted advisory drops explicit partial_context signal when manifest/context signals look clean [services/report_service.py:3380]
- [x] [Review][Patch] Persisted JSON boolean-like strings can incorrectly mark advisory output as partial context [services/report_service.py:3267]
- [x] [Review][Patch] Submit response can bypass the API error envelope when persisted advisory is missing or invalid [api/routes/analyses.py:588]
- [x] [Review][Patch] Share summary ignores stored partial_context while advisory flags it [services/analysis_service.py:650]
- [x] [Review][Patch] Submit advisory fallback can diverge from persisted report advisory derivation [api/routes/analyses.py:76]
- [x] [Review][Patch] Legacy or recovered reports can disagree on partial_context between context_completeness and advisory [services/report_service.py:3283]
- [x] [Review][Patch] Advisory rebuild treats false-like string booleans as attention signals [services/report_service.py:3450]
- [x] [Review][Patch] OpenAPI docs omit runtime error envelopes for list/detail analysis endpoints [api/routes/analyses.py:396]
- [x] [Review][Patch] Share summary still treats false-like persisted booleans as attention signals [services/analysis_service.py:748]
- [x] [Review][Patch] Submit response can return a stale schema-valid advisory instead of rebuilding from persisted report fields [api/routes/analyses.py:76]
- [x] [Review][Patch] Submit response advisory and share summary can disagree on partial-context signals [api/routes/analyses.py:630]
- [x] [Review][Patch] Add create-response regression coverage for `meta.api_version` and report schema version [tests/test_api/test_analyses.py:1382]
- [x] [Review][Patch] Malformed persisted report context can bypass the submit-contract API error envelope [api/routes/analyses.py:87]
- [x] [Review][Patch] Non-finite legacy boolean values are normalized as truthy attention signals [services/report_service.py:3194]
- [x] [Review][Patch] Share summary still requires attention for narrative-only warnings while advisory does not [services/analysis_service.py:916]
- [x] [Review][Patch] Submit response still exposes transient findings/evidence/context instead of persisted contract values [api/schemas.py:1367]
- [x] [Review][Defer] List endpoint masks forbidden/conflicting scoped reads as empty success instead of an error envelope [api/routes/analyses.py:425] — deferred, pre-existing

## Dev Notes

### Epic Context

- Epic: 5. Workflow-Native Delivery
- Epic goal: Deliver the report in real review workflows without duplicating analysis logic.
- Epic coverage: WRK-01..10, REV-05..08, ADM-07, DOC-08

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 5 / Story 5.1 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

Codex (GPT-5)

### Debug Log References

- Red phase: `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_list_analyses_returns_persisted_reports tests.test_api.test_analyses.AnalysesApiTests.test_get_analysis_returns_single_report tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_returns_structured_result -q` failed before implementation on missing `meta.api_version` and `persisted_report.advisory`.
- Focused API regression: `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_list_analyses_returns_persisted_reports tests.test_api.test_analyses.AnalysesApiTests.test_get_analysis_returns_single_report tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_returns_structured_result -q` passed after implementation.
- Affected suite: `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_docs.test_report_schema_documentation -q` passed, 59 tests.
- Schema fixture regression: `./.venv/bin/python -m unittest tests.test_api.test_schemas -q` passed, 7 tests.
- Lint/format: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed.
- Full suite: `./.venv/bin/python -m unittest discover -q` passed, 429 tests, 1 skipped.
- Local CI: `bash scripts/ci-local.sh` passed, including Ruff, format check, pip check, Bandit, compileall, parser scenarios, and unittest discovery.
- UI validation not applicable: no UI route, NiceGUI component, rendered report/history/dashboard surface, browser interaction, keyboard behavior, or accessibility semantics changed.
- Review fix targeted regressions: `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_get_analysis_preserves_go_advisory_with_narrative_warning tests.test_services.test_report_service.ReportServiceTests.test_shared_report_redaction_prefers_longest_overlapping_filename -q` passed, 2 tests.
- Review fix affected suite: `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_services.test_report_service -q` passed, 193 tests.
- Review fix lint/format: `./.venv/bin/ruff check services/report_service.py tests/test_api/test_analyses.py tests/test_services/test_report_service.py` passed; `./.venv/bin/ruff format --check services/report_service.py tests/test_api/test_analyses.py tests/test_services/test_report_service.py` passed.
- Review fix full validation: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed; `./.venv/bin/python -m unittest discover -q` passed, 430 tests, 1 skipped; `bash scripts/ci-local.sh` passed.
- Re-review fix targeted regressions: `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_returns_structured_result tests.test_api.test_analyses.AnalysesApiTests.test_get_analysis_flags_insufficient_context_as_assessment_warning tests.test_api.test_analyses.AnalysesApiTests.test_get_analysis_preserves_go_advisory_with_narrative_warning -q` passed, 3 tests.
- Re-review fix affected suites: `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_services.test_report_service -q` passed, 194 tests; `./.venv/bin/python -m unittest tests.test_api.test_schemas tests.test_docs.test_report_schema_documentation -q` passed, 9 tests.
- Re-review fix lint/format: `./.venv/bin/ruff check api/routes/analyses.py services/report_service.py tests/test_api/test_analyses.py` passed; `./.venv/bin/ruff format --check api/routes/analyses.py services/report_service.py tests/test_api/test_analyses.py` passed.
- Re-review fix full validation: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed; `./.venv/bin/python -m unittest discover -q` passed, 431 tests, 1 skipped; `bash scripts/ci-local.sh` passed.
- Re-review evidence/list targeted regressions: `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_list_analyses_preserves_go_advisory_with_narrative_warning tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_preserves_go_advisory_with_narrative_warning tests.test_services.test_report_service.ReportServiceTests.test_fetch_filtered_history_page_includes_evidence_payloads tests.test_docs.test_report_schema_documentation.ReportSchemaDocumentationTests.test_report_v2_guide_covers_machine_consumers_and_contract_fields -q` passed, 4 tests.
- Re-review evidence/list affected suites: `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_services.test_report_service tests.test_docs.test_report_schema_documentation -q` passed, 198 tests.
- Re-review evidence/list lint/format: `./.venv/bin/ruff check services/report_service.py tests/test_api/test_analyses.py tests/test_services/test_report_service.py tests/test_docs/test_report_schema_documentation.py` passed; `./.venv/bin/ruff format --check services/report_service.py tests/test_api/test_analyses.py tests/test_services/test_report_service.py tests/test_docs/test_report_schema_documentation.py` passed.
- Re-review evidence/list full validation: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed; `./.venv/bin/python -m unittest discover -q` passed, 433 tests, 1 skipped; `bash scripts/ci-local.sh` passed, including Ruff, format check, pip check, Bandit, compileall, parser scenarios, and unittest discovery.
- Re-review advisory/scope targeted regressions: `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_filtered_history_page_uses_lightweight_scope_for_diff_candidates tests.test_services.test_report_service.ReportServiceTests.test_persisted_advisory_keeps_evidence_gap_separate_from_partial_context tests.test_services.test_report_service.ReportServiceTests.test_persisted_advisory_normalizes_legacy_severity_values tests.test_services.test_report_service.ReportServiceTests.test_fetch_filtered_history_page_includes_evidence_payloads -q` passed, 4 tests.
- Re-review advisory/scope affected suites: `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_services.test_report_service tests.test_docs.test_report_schema_documentation tests.test_api.test_schemas -q` passed, 208 tests.
- Re-review advisory/scope lint/format: `./.venv/bin/ruff check services/report_service.py tests/test_services/test_report_service.py` passed; `./.venv/bin/ruff format services/report_service.py tests/test_services/test_report_service.py` formatted 1 file; `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed.
- Re-review advisory/scope full validation: `./.venv/bin/python -m unittest discover -q` passed, 433 tests, 1 skipped; `bash scripts/ci-local.sh` passed, including Ruff, format check, pip check, Bandit, compileall, parser scenarios, and unittest discovery.
- UI validation not applicable: no UI route, NiceGUI component, rendered report/history/dashboard surface, browser interaction, keyboard behavior, or accessibility semantics changed.
- Latest re-review red phase: `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persisted_advisory_honors_manifest_item_partial_context -q` failed before implementation on missing manifest-item partial context detection.
- Latest re-review targeted regressions: `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persisted_advisory_honors_manifest_item_partial_context tests.test_services.test_report_service.ReportServiceTests.test_persisted_advisory_keeps_evidence_gap_separate_from_partial_context tests.test_services.test_report_service.ReportServiceTests.test_persisted_advisory_normalizes_legacy_severity_values tests.test_services.test_report_service.ReportServiceTests.test_fetch_filtered_history_page_uses_lightweight_scope_for_diff_candidates -q` passed, 4 tests.
- Latest re-review lint/format: `./.venv/bin/ruff check services/report_service.py tests/test_services/test_report_service.py` passed; `./.venv/bin/ruff format --check services/report_service.py tests/test_services/test_report_service.py` passed.
- Latest re-review affected suites: `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_services.test_report_service tests.test_docs.test_report_schema_documentation tests.test_api.test_schemas -q` passed, 209 tests.
- Latest re-review full validation: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed; `./.venv/bin/python -m unittest discover -q` passed, 433 tests, 1 skipped; `bash scripts/ci-local.sh` passed, including Ruff, format check, pip check, Bandit, compileall, parser scenarios, and unittest discovery.
- UI validation not applicable: no UI route, NiceGUI component, rendered report/history/dashboard surface, browser interaction, keyboard behavior, or accessibility semantics changed.
- Final re-review red phase: `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_degrades_on_malformed_submission_manifest_json tests.test_services.test_report_service.ReportServiceTests.test_persisted_advisory_normalizes_legacy_severity_values -q` failed before implementation on fallback manifest partial-context and top-level legacy normalization assertions.
- Final re-review targeted regressions: `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_degrades_on_malformed_submission_manifest_json tests.test_services.test_report_service.ReportServiceTests.test_persisted_advisory_normalizes_legacy_severity_values -q` passed, 2 tests.
- Final re-review lint/format: `./.venv/bin/ruff check services/report_service.py tests/test_services/test_report_service.py` passed; `./.venv/bin/ruff format --check services/report_service.py tests/test_services/test_report_service.py` passed.
- Final re-review affected suites: `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_services.test_report_service tests.test_docs.test_report_schema_documentation tests.test_api.test_schemas -q` passed, 209 tests.
- Final re-review full validation: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed; `./.venv/bin/python -m unittest discover -q` passed, 433 tests, 1 skipped; `bash scripts/ci-local.sh` passed, including Ruff, format check, pip check, Bandit, compileall, parser scenarios, and unittest discovery.
- UI validation not applicable: no UI route, NiceGUI component, rendered report/history/dashboard surface, browser interaction, keyboard behavior, or accessibility semantics changed.
- Stored partial-context red phase: `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persisted_advisory_honors_stored_partial_context_signal -q` failed before implementation on missing `context_completeness.partial_context`.
- Stored partial-context targeted regressions: `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persisted_advisory_honors_stored_partial_context_signal tests.test_services.test_report_service.ReportServiceTests.test_persisted_advisory_honors_manifest_item_partial_context tests.test_services.test_report_service.ReportServiceTests.test_persisted_advisory_keeps_evidence_gap_separate_from_partial_context tests.test_models.test_evidence_models.EvidenceModelTests.test_context_completeness_constructs_and_serializes -q` passed, 4 tests.
- Stored partial-context affected suites: `./.venv/bin/python -m unittest tests.test_models.test_evidence_models tests.test_services.test_report_service tests.test_api.test_schemas tests.test_docs.test_report_schema_documentation -q` passed, 165 tests; `./.venv/bin/python -m unittest tests.test_api.test_analyses -q` passed, 61 tests.
- Stored partial-context lint/format: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed.
- Stored partial-context full validation: `./.venv/bin/python -m unittest discover -q` passed, 433 tests, 1 skipped; `bash scripts/ci-local.sh` passed, including Ruff, format check, pip check, Bandit, compileall, parser scenarios, and unittest discovery.
- UI validation not applicable: no UI route, NiceGUI component, rendered report/history/dashboard surface, browser interaction, keyboard behavior, or accessibility semantics changed.
- Reviewer findings red phase: `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persisted_advisory_treats_false_like_strings_as_false tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_share_summary_requires_attention_for_stored_partial_context tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_falls_back_when_persisted_advisory_is_invalid -q` failed before implementation on boolean-like persisted partial-context flags, stored share-summary partial-context parity, and invalid persisted advisory fallback.
- Reviewer findings targeted regressions: `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_persisted_advisory_treats_false_like_strings_as_false tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_share_summary_requires_attention_for_stored_partial_context tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_falls_back_when_persisted_advisory_is_invalid -q` passed, 3 tests.
- Reviewer findings affected suites: `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_services.test_report_service tests.test_services.test_analysis_service -q` passed, 239 tests.
- Reviewer findings lint/format: `./.venv/bin/ruff format api/routes/analyses.py services/report_service.py services/analysis_service.py tests/test_api/test_analyses.py tests/test_services/test_report_service.py tests/test_services/test_analysis_service.py` formatted 2 files; `./.venv/bin/ruff check api/routes/analyses.py services/report_service.py services/analysis_service.py tests/test_api/test_analyses.py tests/test_services/test_report_service.py tests/test_services/test_analysis_service.py` passed; `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed.
- Reviewer findings full validation: `./.venv/bin/python -m unittest discover -q` passed, 434 tests, 1 skipped; `bash scripts/ci-local.sh` passed, including Ruff, format check, pip check, Bandit, compileall, parser scenarios, and unittest discovery.
- UI validation not applicable: no UI route, NiceGUI component, rendered report/history/dashboard surface, browser interaction, keyboard behavior, or accessibility semantics changed.
- Submit advisory fallback parity red phase: `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_falls_back_when_persisted_advisory_is_invalid -q` failed before implementation on missing persisted-report evidence-gap advisory derivation.
- Submit advisory fallback parity targeted regression: `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_falls_back_when_persisted_advisory_is_invalid -q` passed, 1 test.
- Submit advisory fallback parity affected suite: `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_services.test_report_service tests.test_services.test_analysis_service -q` passed, 239 tests.
- Submit advisory fallback parity lint/format: `./.venv/bin/ruff format api/routes/analyses.py services/report_service.py tests/test_api/test_analyses.py` left 3 files unchanged; `./.venv/bin/ruff check api/routes/analyses.py services/report_service.py tests/test_api/test_analyses.py` passed; `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed.
- Submit advisory fallback parity full validation: `./.venv/bin/python -m unittest discover -q` passed, 434 tests, 1 skipped; `bash scripts/ci-local.sh` passed, including Ruff, format check, pip check, Bandit, compileall, parser scenarios, and unittest discovery.
- UI validation not applicable: no UI route, NiceGUI component, rendered report/history/dashboard surface, browser interaction, keyboard behavior, or accessibility semantics changed.
- Reviewer follow-up red phase: `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_degrades_on_malformed_submission_manifest_json tests.test_services.test_report_service.ReportServiceTests.test_report_advisory_builder_normalizes_false_like_boolean_strings tests.test_services.test_report_service.ReportServiceTests.test_legacy_context_partial_context_matches_recovered_manifest_signal tests.test_api.test_analyses.AnalysesApiTests.test_openapi_documents_analysis_submission_contract -q` failed before implementation on OpenAPI runtime error docs, false-like advisory boolean handling, and context/advisory partial_context parity.
- Reviewer follow-up targeted regressions: `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_fetch_report_degrades_on_malformed_submission_manifest_json tests.test_services.test_report_service.ReportServiceTests.test_report_advisory_builder_normalizes_false_like_boolean_strings tests.test_services.test_report_service.ReportServiceTests.test_legacy_context_partial_context_matches_recovered_manifest_signal tests.test_api.test_analyses.AnalysesApiTests.test_openapi_documents_analysis_submission_contract -q` passed, 4 tests.
- Reviewer follow-up affected suite: `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_services.test_report_service tests.test_docs.test_report_schema_documentation tests.test_api.test_schemas -q` passed, 214 tests.
- Reviewer follow-up lint/format: `./.venv/bin/ruff format api/routes/analyses.py services/report_service.py tests/test_api/test_analyses.py tests/test_services/test_report_service.py` left 4 files unchanged; `./.venv/bin/ruff check api/routes/analyses.py services/report_service.py tests/test_api/test_analyses.py tests/test_services/test_report_service.py` passed; `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed.
- Reviewer follow-up full validation: `./.venv/bin/python -m unittest discover -q` passed, 434 tests, 1 skipped; `bash scripts/ci-local.sh` passed, including Ruff, format check, pip check, Bandit, compileall, parser scenarios, and unittest discovery.
- UI validation not applicable: no UI route, NiceGUI component, rendered report/history/dashboard surface, browser interaction, keyboard behavior, or accessibility semantics changed.
- Share-summary boolean red phase: `./.venv/bin/python -m unittest tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_share_summary_normalizes_false_like_context_booleans tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_share_summary_normalizes_false_like_narrative_availability -q` failed before implementation on false-like context and narrative availability string handling.
- Share-summary boolean targeted regressions: `./.venv/bin/python -m unittest tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_share_summary_normalizes_false_like_context_booleans tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_share_summary_normalizes_false_like_narrative_availability -q` passed, 2 tests.
- Share-summary boolean affected suite: `./.venv/bin/python -m unittest tests.test_services.test_analysis_service tests.test_api.test_analyses tests.test_services.test_report_service tests.test_docs.test_report_schema_documentation tests.test_api.test_schemas -q` passed, 252 tests.
- Share-summary boolean lint/format: `./.venv/bin/ruff format services/analysis_service.py tests/test_services/test_analysis_service.py` reformatted 1 file; `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed.
- Share-summary boolean full validation: `./.venv/bin/python -m unittest discover -q` passed, 434 tests, 1 skipped; `bash scripts/ci-local.sh` passed, including Ruff, format check, pip check, Bandit, compileall, parser scenarios, and unittest discovery.
- UI validation not applicable: no UI route, NiceGUI component, rendered report/history/dashboard surface, browser interaction, keyboard behavior, or accessibility semantics changed.
- Current reviewer findings red phase: `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_rebuilds_stale_valid_persisted_advisory tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_share_summary_matches_advisory_partial_context tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_invalid_advisory_context_uses_error_envelope tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_preserves_go_advisory_with_narrative_warning tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_share_summary_ignores_non_finite_boolean_signals tests.test_services.test_report_service.ReportServiceTests.test_report_advisory_builder_ignores_non_finite_boolean_signals -q` failed before implementation on stale submit advisory, share-summary partial-context parity, malformed-context API envelope, and non-finite boolean normalization.
- Current reviewer findings targeted regressions: `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_rebuilds_stale_valid_persisted_advisory tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_share_summary_matches_advisory_partial_context tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_invalid_advisory_context_uses_error_envelope tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_preserves_go_advisory_with_narrative_warning tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_share_summary_ignores_non_finite_boolean_signals tests.test_services.test_report_service.ReportServiceTests.test_report_advisory_builder_ignores_non_finite_boolean_signals -q` passed, 6 tests.
- Current reviewer findings affected suites: `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_services.test_analysis_service tests.test_services.test_report_service -q` passed, 248 tests.
- Current reviewer findings lint/format: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed.
- Current reviewer findings full validation: `./.venv/bin/python -m unittest discover -q` passed, 437 tests, 1 skipped; `bash scripts/ci-local.sh` passed, including Ruff, format check, pip check, Bandit, compileall, parser scenarios, and unittest discovery.
- UI validation not applicable: no UI route, NiceGUI component, rendered report/history/dashboard surface, browser interaction, keyboard behavior, or accessibility semantics changed.
- Latest patch reviewer red phase: `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_preserves_go_advisory_with_narrative_warning tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_returns_structured_result -q` failed before implementation on create-response transient findings/evidence/context values instead of persisted-report contract values.
- Latest patch reviewer targeted regressions: `./.venv/bin/python -m unittest tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_preserves_go_advisory_with_narrative_warning tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_returns_structured_result -q` passed, 2 tests.
- Latest patch reviewer affected suites: `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_services.test_analysis_service tests.test_services.test_report_service -q` passed, 248 tests.
- Latest patch reviewer lint/format: `./.venv/bin/ruff check api/schemas.py services/analysis_service.py tests/test_api/test_analyses.py` passed; `./.venv/bin/ruff format --check api/schemas.py services/analysis_service.py tests/test_api/test_analyses.py` passed.
- Latest patch reviewer full validation: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed; `./.venv/bin/python -m unittest discover -q` passed, 437 tests, 1 skipped; `bash scripts/ci-local.sh` passed, including Ruff, format check, pip check, Bandit, compileall, parser scenarios, and unittest discovery.
- UI validation not applicable: no UI route, NiceGUI component, rendered report/history/dashboard surface, browser interaction, keyboard behavior, or accessibility semantics changed.
- Clean re-review validation: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed; `./.venv/bin/python -m unittest tests.test_api.test_analyses tests.test_services.test_analysis_service tests.test_services.test_report_service tests.test_api.test_schemas tests.test_docs.test_report_schema_documentation -q` passed, 257 tests; `./.venv/bin/python -m unittest discover -q` passed, 437 tests, 1 skipped.
- Clean re-review result: no new decision-needed, patch, or defer findings; moved story to done.

### Completion Notes List

- Added `meta.api_version: "v1"` to report-bearing API metadata helpers and response meta models.
- Added a persisted-report `advisory` payload for analysis submit/list/detail responses, derived from durable report state and preserving `advisory_only=true` / `should_block=false`.
- Resolved reviewer findings by distinguishing attention-worthy persisted warnings from narrative-only warnings, preserving `go` advisory semantics for clean low-risk reports with narrative provider warnings.
- Added regression coverage for persisted advisory parity and nested advisory top-risk redaction.
- Resolved re-review findings by deriving submit-response `data.advisory` from the persisted advisory payload, keeping synthesized `context_todos` and nested advisory flags identical between `advisory` and `persisted_report.advisory`.
- Tightened persisted warning classification so only warnings prefixed as narrative warnings are treated as narrative-only; built-in assessment and persistence warnings still require advisory attention.
- Resolved re-review evidence/list findings by including persisted evidence payloads in history/list serialization for Story 5.1 submit/list/detail contract parity.
- Added submit and list regressions proving clean `go` advisory semantics survive narrative-only provider warnings without assessment warnings or attention flags.
- Locked required report contract documentation fields for `meta.api_version` and `advisory.top_risk`.
- Kept the implementation in the existing API schema and report serialization layer; no new dependencies or persistence migrations were needed.
- Updated report schema and project workspace documentation for the `/api/v1` contract.
- Resolved latest re-review findings by keeping evidence extraction gaps separate from parser `partial_context`, while still surfacing `evidence_gaps` in persisted advisory uncertainty and attention signals.
- Kept history page evidence payloads for paginated list items while making the previous-scan comparison scope lightweight and evidence-free.
- Normalized persisted advisory severity values before strict schema validation so legacy casing or unknown stored values do not break `/api/v1` response serialization.
- Resolved the latest reviewer finding by deriving persisted advisory `partial_context` from per-artifact manifest item partial/status/parse-status signals, not only top-level manifest partial analysis.
- Preserved evidence-gap separation from parser partial context while still surfacing evidence gaps through advisory uncertainty and attention signals.
- Resolved final re-review findings by applying the same manifest item partial/status/parse-status rules to fallback manifest items when canonical manifest JSON is unavailable.
- Normalized top-level persisted report severity and recommendation during serialization so legacy stored values match the advisory payload contract.
- Resolved stored partial-context review finding by persisting the upstream `RiskAssessment.partial_context` signal into context completeness, honoring it during persisted advisory derivation, and documenting the report schema field.
- Resolved reviewer findings by applying strict persisted boolean normalization to partial-context flags, falling back to the canonical advisory builder when persisted submit advisory data is invalid, and making share summaries honor stored `partial_context`.
- Resolved submit advisory fallback parity by deriving invalid or missing submit-response advisory data from the canonical persisted-report advisory builder, preserving evidence gaps and manifest/context signals.
- Resolved reviewer follow-ups by aligning recovered/legacy context `partial_context` with advisory `partial_context`, normalizing false-like advisory booleans, and documenting list/detail/submit runtime error envelopes in OpenAPI.
- Resolved share-summary boolean review finding by normalizing false-like persisted `insufficient_context`, `narrative_available`, and `narrative_degraded` values before computing context labels and human-attention copy.
- Resolved current reviewer findings by always rebuilding submit-response advisory from canonical persisted-report fields, routing malformed persisted advisory context through the API error envelope, aligning share-summary partial-context detection with advisory manifest semantics, adding create-response contract regressions for API/report schema versions, and ignoring non-finite legacy boolean values.
- Resolved latest patch reviewer findings by making share summaries use advisory attention semantics instead of treating narrative-only warnings as attention-worthy, and by serializing submit-response findings, evidence, context, blast radius, rollback plan, and incident matches from the persisted report contract.

### File List

- `api/schemas.py`
- `api/routes/analyses.py`
- `evidence/models.py`
- `services/report_service.py`
- `services/analysis_service.py`
- `tests/test_api/test_analyses.py`
- `tests/test_api/test_schemas.py`
- `tests/test_docs/test_report_schema_documentation.py`
- `tests/test_models/test_evidence_models.py`
- `tests/test_services/test_report_service.py`
- `tests/test_services/test_analysis_service.py`
- `docs/schemas/report-v2.md`
- `docs/project-workspaces.md`
- `_bmad-output/implementation-artifacts/5-1-versioned-api-report-contract.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-25: Implemented `/api/v1` versioned report contract metadata and persisted advisory payload coverage; moved story to review.
- 2026-05-25: Resolved code review findings for persisted advisory parity and nested advisory redaction coverage; moved story to done.
- 2026-05-25: Resolved re-review findings for warning classification and submit/persisted advisory parity; kept story done.
- 2026-05-25: Resolved re-review findings for evidence payload list retrieval, narrative-only go advisory submit/list coverage, and report schema documentation locks; kept story done.
- 2026-05-25: Resolved re-review findings for advisory partial-context semantics, lightweight history pagination scope, and persisted advisory severity normalization; kept story done.
- 2026-05-25: Resolved latest re-review finding for per-artifact manifest partial-context advisory detection; kept story done.
- 2026-05-25: Resolved final re-review findings for fallback manifest partial-context detection and top-level/advisory normalization parity; kept story done.
- 2026-05-25: Resolved stored partial-context advisory review finding; moved story to review.
- 2026-05-25: Resolved reviewer findings for persisted boolean normalization, submit advisory fallback, and share-summary partial-context parity; moved story to review.
- 2026-05-25: Resolved submit fallback advisory parity review finding; moved story to review.
- 2026-05-25: Resolved reviewer follow-ups for partial-context parity, advisory boolean normalization, and OpenAPI error envelopes; moved story to review.
- 2026-05-25: Resolved share-summary false-like persisted boolean review finding; moved story to review.
- 2026-05-25: Resolved current reviewer findings for stale submit advisory rebuild, share-summary/advisory partial-context parity, create-response version coverage, malformed-context error envelopes, and non-finite boolean normalization; moved story to review.
- 2026-05-25: Resolved latest patch reviewer findings for narrative-only share-summary attention semantics and persisted create-response contract parity; moved story to review.
- 2026-05-25: Re-ran BMad code review cleanly with full validation; moved story to done.
