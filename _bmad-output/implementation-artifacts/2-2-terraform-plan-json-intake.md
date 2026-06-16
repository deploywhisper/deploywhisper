# Story 2.2: Terraform Plan JSON Intake

Status: review

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform engineer,
I want Terraform plan JSON accepted as a first-class input,
So that deployment review can use concrete planned changes instead of only source files.

## Acceptance Criteria

1. Given a Terraform plan JSON file is submitted, When intake and parsing run, Then plan actions, resources, modules, and relevant metadata are normalized into the shared change model. And unsupported or redacted plan fields are reported explicitly.

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
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Valid all-`no-op` Terraform plans fail parsing [parsers/terraform_parser.py:158] — fixed by preserving `no-op` resource changes as normalized plan entries and scoring them as no planned change.
- [x] [Review][Patch] Module-scoped resources lose resource-specific summaries [parsers/terraform_parser.py:39] — fixed by classifying Terraform plan summaries from the resource `type`, even when the address is module-scoped.
- [x] [Review][Patch] CLI output metadata contract lacks direct regression coverage [tests/test_cli/test_analyze.py:566] — fixed with direct CLI parse-batch metadata assertions.
- [x] [Review][Patch] Top-level Terraform plan metadata and unsupported sections are silently dropped [parsers/terraform_parser.py:191] — fixed by carrying plan format/Terraform versions and reporting unsupported top-level sections as `plan.<field>`.
- [x] [Review][Patch] Terraform replacement actions normalize as pure destroys in downstream risk/evidence layers [analysis/risk_scorer.py:121] — fixed by normalizing delete/create replacement actions as `replace` in risk scoring and evidence hints.
- [x] [Review][Patch] Terraform data-source read actions score as infrastructure modifications [analysis/risk_scorer.py:121] — fixed by treating `read` as a non-mutating low-risk action in risk scoring and evidence hints.
- [x] [Review][Patch] Terraform `no-op` blast-radius text can imply downstream impact when topology matches [analysis/risk_scorer.py:371] — fixed by returning no-planned-change blast-radius text before topology-specific messaging.
- [x] [Review][Patch] Terraform replacement and mixed destructive actions are still not canonical at the shared change-model boundary [parsers/terraform_parser.py:220] — fixed by canonicalizing Terraform actions into the shared change model while preserving raw action lists in metadata.
- [x] [Review][Patch] Terraform metadata details are duplicated into persisted and LLM-visible summary text [parsers/terraform_parser.py:192] — fixed by keeping plan metadata structured in `UnifiedChange.metadata` and removing metadata expansion from summaries.
- [x] [Review][Patch] Module-scoped non-allowlisted resources are still summarized as module-level changes [parsers/terraform_parser.py:79] — fixed by treating module-scoped addresses with a resource `type` as resources, not module-level changes.
- [x] [Review][Patch] Root-scope Terraform unknown/sensitive markers are silently dropped [parsers/terraform_parser.py:88] — fixed by reporting root-level markers as `<root>`.
- [x] [Review][Patch] Non-mutating `no-op`/`read` reasoning can still imply downstream impact when topology matches [analysis/risk_scorer.py:400] — fixed by using non-mutating blast-radius reasoning before topology downstream-impact text.
- [x] [Review][Patch] Composite action downgrades can hide destructive changes [analysis/risk_scorer.py:124] — fixed by centralizing shared action normalization and only treating `no-op`/`read` as non-mutating when they are the sole action.
- [x] [Review][Patch] Non-mutating Terraform plan entries still produce blast-radius impact [analysis/blast_radius.py:64] — fixed by filtering non-mutating changes out of blast-radius traversal and unmatched-resource warnings.
- [x] [Review][Patch] Rollback guidance does not understand the new Terraform action vocabulary [analysis/rollback_planner.py:46] — fixed by skipping non-mutating changes and treating `replace` as destructive for rollback priority, criticality, estimates, and complexity.
- [x] [Review][Patch] Interaction-risk scoring can be fabricated from non-mutating Terraform entries [analysis/interaction_risk.py:68] — fixed by excluding non-mutating changes from cross-tool interaction grouping.
- [x] [Review][Patch] Missing or unknown Terraform action lists are coerced into mutating `modify` changes [parsers/base.py:54] — fixed by requiring non-empty known Terraform plan actions before creating normalized changes, with explicit parser failures for missing or unsupported action lists.
- [x] [Review][Patch] Terraform plan entries without an address are normalized as fake `unknown` resources [parsers/terraform_parser.py:198] — fixed by validating resource-change addresses and rejecting missing or blank addresses instead of manufacturing an `unknown` resource.
- [x] [Review][Patch] Malformed supported metadata shapes are silently dropped instead of reported explicitly [parsers/terraform_parser.py:105] — fixed by reporting invalid supported metadata shapes as `change.<field>.invalid` unsupported-field markers while preserving safe normalized metadata values.
- [x] [Review][Patch] Zero-diff Terraform plan JSON files are rejected instead of accepted as first-class plan input [parsers/registry.py:136] — fixed by emitting a plan-level `no-op` normalized entry for valid Terraform plan JSON files with empty `resource_changes`.
- [x] [Review][Patch] LLM-assisted scoring reintroduces risk points for non-mutating `no-op` and `read` entries [analysis/risk_scorer.py:628] — fixed by centralizing contribution calculation and forcing non-mutating contributors to remain low severity with zero contribution after LLM scoring.
- [x] [Review][Patch] Read-only typed Terraform resources can still get mutating summaries [parsers/terraform_parser.py:47] — fixed by short-circuiting `read` summaries before resource-type-specific mutating summary text.
- [x] [Review][Patch] Terraform replacement actions still classify as medium-risk `go` findings despite destructive replacement semantics [analysis/risk_scorer.py:45] — fixed by classifying replacement actions as high-risk in risk/evidence scoring and applying destructive-critical/production semantics.
- [x] [Review][Patch] Non-mutating Terraform `no-op` and `read` entries can still force a `no-go` recommendation through raw-file security flags [analysis/risk_scorer.py:459] — fixed by bypassing raw-file security flags for `no-op` and `read` contributors.
- [x] [Review][Patch] LLM-assisted scoring can still replace deterministic non-mutating reasoning with high-risk wording [analysis/risk_scorer.py:621] — fixed by preserving deterministic non-mutating reasoning while still recording LLM scoring source metadata.
- [x] [Review][Patch] UI upload results do not explicitly display Terraform plan metadata [frontend/src/components/upload_panel.py:588] — fixed by passing parse batches into upload results and rendering Terraform module, replacement, unknown, redacted, and unsupported metadata.
- [x] [Review][Patch] Persisted report and history surfaces drop Terraform plan metadata after intake [services/report_service.py:1475] — fixed by carrying parser metadata into risk contributors, API schemas, persisted report payloads, and history/report detail surfaces.
- [x] [Review][Patch] Terraform plan JSON without `resource_changes` is accepted as a synthetic no-op plan [parsers/terraform_parser.py:263] — fixed by requiring `resource_changes` to be present and only synthesizing no-op for an explicit empty list.
- [x] [Review][Patch] Non-native or contradictory Terraform action sets can be accepted and silently normalized [parsers/terraform_parser.py:20] — fixed by validating native Terraform plan action vocabulary and supported action combinations before normalization.
- [x] [Review][Patch] Parser metadata is threaded through API/persistence/UI without JSON-safety validation [parsers/base.py:32] — fixed by sanitizing parser metadata to JSON-safe primitives and containers at the shared change-model boundary.
- [x] [Review][Patch] All-non-mutating Terraform plans still invoke LLM scoring and can emit irrelevant provider-failure warnings [analysis/risk_scorer.py:716] — fixed by short-circuiting LLM scoring when every contributor is `no-op` or `read`.
- [x] [Review][Patch] UI/report metadata rendering truncates explicit redacted and unsupported Terraform field lists [frontend/src/components/change_table.py:10] — fixed by rendering full redacted and unsupported field lists while keeping less critical metadata compact.
- [x] [Review][Patch] Upload feedback rerender drops the parse-batch metadata table [frontend/src/components/upload_panel.py:451] — fixed by preserving and passing the current parse batch on feedback-triggered result rerenders.
- [x] [Review][Patch] Review-facing UI validation was not recorded for the metadata rendering changes [_bmad-output/project-context.md:73] — fixed by running and recording `npm run test:ui-review` for the changed review surfaces.
- [x] [Review][Patch] Terraform resource addresses are validated with trim semantics but returned untrimmed [parsers/terraform_parser.py:168] — fixed by returning canonical stripped resource addresses and adding padded-address parser coverage.
- [x] [Review][Patch] Duplicate Terraform action entries are accepted because validation collapses actions through a set [parsers/terraform_parser.py:150] — fixed by rejecting duplicate action entries before supported-action-set normalization.
- [x] [Review][Patch] Plan-scoped unsupported fields are duplicated onto every per-resource metadata record [parsers/terraform_parser.py:198] — fixed by separating plan-level unsupported fields into `plan_unsupported_fields` and attaching them once per parsed plan.
- [x] [Review][Patch] Upload-panel metadata rerender coverage inspects source text instead of runtime behavior [frontend/e2e/test_upload_panel.py:208] — fixed by extracting and behavior-testing the feedback rerender callback that preserves parse-batch metadata.
- [x] [Review][Patch] Non-mutating Terraform plan entries still emit evidence items for no-change inputs [evidence/extractor.py:96] — fixed by suppressing Terraform `no-op` and `read` entries at evidence extraction while preserving them in parse-batch metadata.
- [x] [Review][Patch] Upload change table can flood review results with non-mutating Terraform `no-op` and `read` entries [frontend/src/components/change_table.py:91] — fixed by filtering Terraform non-mutating entries from the default normalized-change review table.
- [x] [Review][Patch] API/CLI coverage does not assert `plan_unsupported_fields` serialization or duplicate-action parse failures [tests/test_api/test_analyses.py:720] — fixed with API and CLI assertions for plan-level unsupported fields and duplicate Terraform action parse failures.
- [x] [Review][Patch] Upload metadata rerender test does not verify rendered metadata survives feedback rerender [frontend/e2e/test_upload_panel.py:209] — fixed by rendering the preserved parse batch through the change table in the rerender callback regression.
- [x] [Review][Patch] Empty Terraform plan `plan_unsupported_fields` persistence/history path lacks real-parser coverage [tests/test_services/test_report_service.py:209] — fixed with real Terraform parser coverage for empty-plan `plan_unsupported_fields` through report fetch and history metadata.
- [x] [Review][Patch] Real analysis pipeline drops Terraform parser metadata before persisted report/history rendering [analysis/risk_engine.py:34] — fixed by passing parser metadata into evidence-backed risk scoring and covering the real parser-to-persisted-report/history path.
- [x] [Review][Patch] Filtering Terraform non-mutating rows can hide plan-level unsupported fields from upload review results [frontend/src/components/change_table.py:71] — fixed by surfacing hidden Terraform plan-scope metadata before the mutating change table.
- [x] [Review][Patch] Persisted report/history still lose Terraform metadata for all-non-mutating plans [services/analysis_service.py:693] — fixed by scoring all-non-mutating Terraform batches as deterministic low-risk contributors when evidence extraction intentionally returns no evidence, preserving parser metadata through persisted report/history payloads.
- [x] [Review][Patch] Upload review hides non-plan metadata on filtered Terraform no-op/read rows [frontend/src/components/change_table.py:66] — fixed by rendering complete hidden Terraform metadata lines for filtered `no-op`/`read` rows.
- [x] [Review][Patch] Hidden Terraform plan metadata is merged across files without file attribution [frontend/src/components/change_table.py:66] — fixed by prefixing hidden Terraform metadata with the originating parsed file name instead of aggregating metadata across files.
- [x] [Review][Patch] Browser-level regression coverage is missing for Terraform metadata rendering and feedback rerender [tests/e2e/report_review.keyboard.spec.js:68] — fixed by seeding Terraform metadata in the browser review harness and asserting metadata survives dashboard feedback rerender and history-detail navigation.
- [x] [Review][Patch] Explicit empty evidence can suppress mutating batch scoring [services/analysis_service.py:89] — fixed by re-extracting evidence for mutating batches when callers pass an explicit empty evidence list while preserving deterministic all-non-mutating Terraform scoring.
- [x] [Review][Patch] Non-object Terraform plan JSON roots fail with an unclean parser error [parsers/terraform_parser.py:280] — fixed by rejecting non-object Terraform plan JSON roots with a clean parser `ValueError`.
- [x] [Review][Patch] Mixed Terraform plans lose non-mutating metadata after persistence [evidence/extractor.py:117] — fixed by carrying Terraform `no-op`/`read` changes as zero-score supplemental contributors in evidence-backed mixed assessments, with persisted report/history coverage.
- [x] [Review][Patch] `change.generated_config` is silently dropped instead of surfaced [parsers/terraform_parser.py:218] — fixed by reporting `change.generated_config` in unsupported Terraform metadata instead of accepting and discarding it.
- [x] [Review][Patch] Required security validation was recorded as skipped rather than completed [scripts/ci-local.sh:18] — fixed by installing Bandit in the local venv and rerunning local CI with the Bandit high/high gate active, plus `pip_audit`.
- [x] [Review][Patch] Story completion artifact does not reconcile to the full diff [_bmad-output/implementation-artifacts/2-2-terraform-plan-json-intake.md:208] — fixed by reconciling this story's file list with the current full diff.

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 2 / Story 2.2 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-05-08: Started implementation on `feature/2-2-terraform-plan-json-intake`.
- 2026-05-08: Implementation plan: add metadata support to shared parser/API change payloads, extend Terraform plan JSON parsing for modules/actions and redaction/unknown-field notes, update report schema docs, and lock behavior with parser/API/service regressions.
- 2026-05-08: Focused parser/API regression run passed: `./.venv/bin/python -m unittest tests.test_parsers.test_terraform_parser tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_persists_submission_manifest_with_partial_coverage -q` (6 tests OK).
- 2026-05-08: Ruff validation passed: `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- 2026-05-08: Full unittest validation passed: `./.venv/bin/python -m unittest discover -q` (300 tests OK, 1 skipped).
- 2026-05-08: Local CI passed: `bash scripts/ci-local.sh` (Bandit not installed; security scan skipped by script).
- 2026-05-08: Code review findings fixed for all-`no-op` plan parsing, module-scoped resource summaries, and CLI metadata coverage.
- 2026-05-08: Focused review-fix validation passed: parser, registry, CLI metadata, risk scorer, and evidence extractor regressions (24 tests OK), plus focused Ruff check and format check.
- 2026-05-08: Full review-fix validation passed: `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q` (300 tests OK, 1 skipped), `bash scripts/ci-local.sh` (Bandit not installed; security scan skipped by script), and `git diff --check`.
- 2026-05-08: Re-review findings fixed for top-level Terraform plan metadata reporting, replacement/read action normalization, and topology-aware `no-op` blast-radius text.
- 2026-05-08: Re-review fix validation passed: focused parser/registry/risk/evidence/API/CLI tests (28 tests OK), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, and `./.venv/bin/python -m unittest discover -q` (300 tests OK, 1 skipped).
- 2026-05-08: Local CI passed after re-review fixes: `bash scripts/ci-local.sh` (Bandit not installed; security scan skipped by script).
- 2026-05-08: Follow-up review findings fixed for canonical Terraform shared actions, metadata-only plan details, generic module-scoped resource summaries, root unknown/sensitive markers, and non-mutating topology reasoning.
- 2026-05-08: Follow-up review fix validation passed: focused parser/registry/risk/evidence/API/CLI tests (31 tests OK), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q` (300 tests OK, 1 skipped), and `bash scripts/ci-local.sh` (Bandit not installed; security scan skipped by script).
- 2026-05-08: Re-ran BMad code review. Blind Hunter and Edge Case Hunter completed; Acceptance Auditor timed out and was recorded as a failed layer. Review produced four actionable patch findings and one dismissed speculative metadata-contract hardening item.
- 2026-05-08: Fixed review findings for shared action precedence, non-mutating blast-radius impact, rollback planning action vocabulary, and non-mutating interaction-risk false positives.
- 2026-05-08: Review-fix validation passed: focused parser/risk/blast-radius/rollback/interaction/evidence tests (36 tests OK), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q` (300 tests OK, 1 skipped), and `bash scripts/ci-local.sh` (Bandit not installed; security scan skipped by script).
- 2026-05-08: Re-ran BMad code review. Blind Hunter, Edge Case Hunter, and Acceptance Auditor completed. Review produced six actionable patch findings and dismissed two non-blocking policy/payload-shape concerns.
- 2026-05-08: Fixed latest review findings for Terraform plan action/address validation, invalid metadata shape reporting, zero-diff plan intake, LLM non-mutating score preservation, and read-only typed summaries.
- 2026-05-08: Latest review-fix validation passed: focused parser/registry/risk tests (35 tests OK), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q` (300 tests OK, 1 skipped), `bash scripts/ci-local.sh` (Bandit not installed; security scan skipped by script), and `git diff --check`.
- 2026-05-08: Re-ran BMad code review. Blind Hunter, Edge Case Hunter, and Acceptance Auditor completed. Review produced five actionable patch findings and dismissed two non-blocking parser-policy concerns.
- 2026-05-08: Fixed latest review findings for replacement risk severity, non-mutating security/LLM verdict preservation, and Terraform metadata reporting across upload and persisted report surfaces.
- 2026-05-08: Latest review-fix validation passed: focused risk/evidence/report/UI tests (85 tests OK), ruff check/format, full unittest discovery (301 tests OK, 1 skipped), local CI (Bandit skipped by script because not installed), and git diff --check.
- 2026-05-08: Re-ran BMad code review. Blind Hunter, Edge Case Hunter, and Acceptance Auditor completed. Review produced seven actionable patch findings after triage and dismissed two findings as already handled or not required for non-mutating blast-radius output.
- 2026-05-08: Fixed latest review findings for Terraform plan JSON shape/action validation, parser metadata JSON-safety, deterministic non-mutating scoring, full redacted/unsupported metadata rendering, upload feedback rerender metadata preservation, and review UI harness validation.
- 2026-05-08: Latest review-fix validation passed: focused parser/risk/UI tests (73 tests OK), API/CLI/service regression tests (173 tests OK), post-format combined focused suite (246 tests OK), Ruff check/format, full unittest discovery (303 tests OK, 1 skipped), local CI (303 tests OK, 1 skipped; Bandit skipped by script because not installed), `APP_PORT=18080 npm run test:ui-review` (1 WebKit test passed), and `git diff --check`.
- 2026-05-08: Fixed follow-up review findings for trimmed Terraform plan addresses, duplicate action validation, plan-level unsupported-field deduplication, and runtime upload feedback rerender coverage.
- 2026-05-08: Follow-up review-fix validation passed: focused parser/UI/API/report/history tests (131 tests OK), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q` (303 tests OK, 1 skipped), `bash scripts/ci-local.sh` (303 tests OK, 1 skipped; Bandit skipped by script because not installed), `APP_PORT=18080 npm run test:ui-review` (1 WebKit test passed), and `git diff --check`.
- 2026-05-08: Re-ran BMad code review. Blind Hunter, Edge Case Hunter, and Acceptance Auditor completed. Review produced five actionable patch findings around non-mutating evidence/UI behavior and additional API/CLI/UI/persistence coverage.
- 2026-05-08: Fixed latest review findings for non-mutating Terraform evidence suppression, upload change-table filtering, API/CLI duplicate-action and `plan_unsupported_fields` serialization coverage, rendered upload rerender metadata coverage, and empty-plan real-parser persistence/history metadata coverage.
- 2026-05-08: Latest review-fix validation passed: focused evidence/API/CLI/UI/report regressions (11 tests OK), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q` (304 tests OK, 1 skipped), `bash scripts/ci-local.sh` (304 tests OK, 1 skipped; Bandit skipped by script because not installed), `APP_PORT=18080 npm run test:ui-review` (1 WebKit test passed), and `git diff --check`.
- 2026-05-08: Re-ran BMad code review. Local Blind Hunter, Edge Case Hunter, and Acceptance Auditor passes completed. Review produced two actionable patch findings around real-pipeline Terraform metadata propagation and non-mutating row filtering hiding plan-level unsupported metadata.
- 2026-05-08: Fixed latest review findings for real-pipeline Terraform metadata propagation and upload plan-level metadata visibility.
- 2026-05-08: Latest review-fix validation passed: focused service/API/UI regressions (4 tests OK), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q` (306 tests OK, 1 skipped), `bash scripts/ci-local.sh` (306 tests OK, 1 skipped; Bandit skipped by script because not installed), `APP_PORT=18080 npm run test:ui-review` (1 WebKit test passed), and `git diff --check`.
- 2026-05-08: Re-ran BMad code review. Blind Hunter, Edge Case Hunter, and Acceptance Auditor completed. Review produced four actionable patch findings around non-mutating Terraform metadata persistence, hidden upload metadata attribution, and browser-level metadata/rerender coverage; one Blind Hunter finding about empty change IDs was dismissed because `UnifiedChange` populates change IDs after validation.
- 2026-05-08: Fixed latest review findings for all-non-mutating Terraform metadata persistence, hidden non-mutating upload metadata attribution, first-mutating resource plan metadata placement, and browser-level metadata/feedback-rerender coverage.
- 2026-05-08: Latest review-fix validation passed: targeted regressions (5 tests OK), affected parser/service/API/UI suite (97 tests OK), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q` (308 tests OK, 1 skipped), `bash scripts/ci-local.sh` (308 tests OK, 1 skipped; Bandit skipped by script because not installed), `APP_PORT=18080 npm run test:ui-review` (1 WebKit test passed), and `git diff --check`.
- 2026-05-08: Re-ran BMad code review. Blind Hunter, Edge Case Hunter, and Acceptance Auditor completed. Acceptance Auditor was clean; Blind/Edge produced two actionable patch findings for explicit empty evidence on mutating batches and non-object Terraform plan JSON parser errors. Two blind-layer findings were dismissed as noise because `app.run()` already honors `APP_PORT`/`APP_HOST`, and legacy `modify`/`destroy` plan actions are intentionally rejected as non-native Terraform plan JSON.
- 2026-05-08: Fixed latest review findings for explicit-empty-evidence mutating batch scoring and non-object Terraform plan JSON parser errors.
- 2026-05-08: Latest review-fix validation passed: focused parser/service regressions (3 tests OK), affected parser/service suites (41 tests OK), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q` (308 tests OK, 1 skipped), `bash scripts/ci-local.sh` (308 tests OK, 1 skipped; Bandit skipped by script because not installed), `APP_PORT=18080 npm run test:ui-review` (1 WebKit test passed), and `git diff --check`.
- 2026-05-08: Re-ran BMad code review. Blind Hunter, Edge Case Hunter, and Acceptance Auditor completed. Review produced four actionable patch findings for mixed-plan non-mutating metadata persistence, `generated_config` reporting, security validation evidence, and story file-list reconciliation; one planned-values unsupported-field concern was dismissed as intentional explicit partial-coverage reporting.
- 2026-05-08: Fixed latest review findings for mixed-plan non-mutating metadata persistence, `generated_config` unsupported-field reporting, completed security validation evidence, and story file-list reconciliation.
- 2026-05-08: Latest review-fix validation passed: focused parser/service/API regressions (3 tests OK), affected parser/service/API suites (88 tests OK), `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q` (308 tests OK, 1 skipped), `./.venv/bin/python -m pip_audit -r requirements.txt` (no known vulnerabilities), `bash scripts/ci-local.sh` (Bandit active; high/high gate passed; 308 tests OK, 1 skipped), `APP_PORT=18080 npm run test:ui-review` (1 WebKit test passed), and `git diff --check`.

### Completion Notes List

- Added parser-normalized change metadata to the shared `UnifiedChange` model and API `ChangeData` payload.
- Extended Terraform plan JSON intake to preserve module address, provider/resource metadata, action lists, replacement paths, unknown-after-apply paths, redacted sensitive paths, and unsupported plan fields.
- Preserved Terraform plan JSON `no-op` resources as low-risk normalized entries so valid no-change plans remain accepted.
- Documented the parse batch change metadata contract in the report v2 schema notes.
- Resolved code review findings by preserving Terraform `no-op` plan resources without scoring them as modifications, restoring resource-specific summaries for module-scoped resources, and adding CLI metadata output coverage.
- Resolved re-review findings by reporting top-level Terraform plan metadata/unsupported sections, treating replacement/read actions correctly downstream, and keeping `no-op` blast-radius text consistent when topology is available.
- Resolved follow-up review findings by canonicalizing Terraform parser actions at the shared model boundary, keeping Terraform metadata out of summaries, preserving root marker paths, and avoiding downstream-impact reasoning for non-mutating actions.
- Resolved latest review findings by centralizing action normalization and applying non-mutating/replacement semantics consistently across risk scoring, blast radius, rollback planning, interaction risk, parser output, and evidence hints.
- Re-ran BMad code review and moved the story back to in-progress for unresolved Terraform parser and non-mutating LLM-scoring patch findings.
- Resolved latest review findings by rejecting malformed Terraform action/address records, preserving invalid metadata shape markers, accepting zero-diff plans as plan-level no-op entries, preserving non-mutating zero scores after LLM scoring, and using read-only summaries for typed read entries.
- Re-ran BMad code review and moved the story back to in-progress for unresolved replacement-risk, non-mutating verdict, and Terraform metadata reporting patch findings.
- Resolved latest review findings by treating replacements as high/destructive risk, preserving deterministic no-op/read verdicts, carrying Terraform metadata into persisted contributors, and rendering metadata in upload/history report surfaces.
- Re-ran BMad code review and moved the story back to in-progress for unresolved Terraform action validation, metadata JSON-safety, non-mutating LLM, metadata rendering, upload rerender, and UI-review validation findings.
- Resolved latest review findings by tightening Terraform plan JSON validation, sanitizing parser metadata, keeping all-non-mutating plans deterministic, preserving upload metadata rerenders, fully enumerating redacted/unsupported Terraform metadata in UI/report surfaces, and restoring the seeded UI-review harness for project-scoped review flows.
- Resolved follow-up review findings by canonicalizing whitespace-padded Terraform plan addresses, rejecting duplicate native actions, reporting plan-level unsupported fields once per parsed plan, and replacing source-inspection rerender coverage with behavior coverage.
- Re-ran BMad code review and moved the story back to in-progress for unresolved non-mutating evidence/UI behavior and coverage patch findings.
- Resolved latest review findings by keeping Terraform no-op/read entries parse-visible but out of evidence and default upload review rows, and by adding API/CLI/UI/report regressions for the remaining metadata and duplicate-action coverage gaps.
- Re-ran BMad code review and moved the story back to in-progress for unresolved real-pipeline metadata propagation and upload plan-level metadata visibility patch findings.
- Resolved latest review findings by preserving parser metadata through evidence-backed scoring into persisted report/history contributors, and by rendering hidden non-mutating Terraform plan metadata in upload review results.
- Re-ran BMad code review and moved the story back to in-progress for unresolved non-mutating metadata persistence, hidden upload metadata attribution, and browser-level metadata/rerender coverage patch findings.
- Resolved latest review findings by preserving all-non-mutating Terraform metadata through deterministic low-risk contributors, rendering complete hidden metadata with file attribution, attaching plan-level metadata to the first mutating resource when present, and adding browser coverage for metadata rendering across feedback rerender and history detail.
- Re-ran BMad code review and moved the story back to in-progress for unresolved explicit-empty-evidence mutating scoring and non-object Terraform plan JSON parser hardening patch findings.
- Resolved latest review findings by restoring mutating evidence extraction fallback for explicit empty evidence lists while preserving all-non-mutating Terraform metadata scoring, and by rejecting non-object Terraform plan roots with a clean parser error.
- Re-ran BMad code review and moved the story back to in-progress for unresolved mixed-plan metadata persistence, generated-config reporting, security validation evidence, and story file-list reconciliation patch findings.
- Resolved latest review findings by preserving non-mutating Terraform metadata in mixed persisted assessments, surfacing generated Terraform config as unsupported metadata, completing security validation with Bandit active, and reconciling the completion file list.

### File List

- `_bmad-output/implementation-artifacts/2-2-terraform-plan-json-intake.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `.agents/skills/bmad-create-story/checklist.md`
- `.agents/skills/bmad-create-story/template.md`
- `.agents/skills/bmad-dev-story/checklist.md`
- `.agents/skills/bmad-dev-story/workflow.md`
- `AGENTS.md`
- `_bmad-output/project-context.md`
- `analysis/blast_radius.py`
- `analysis/interaction_risk.py`
- `analysis/risk_engine.py`
- `analysis/rollback_planner.py`
- `analysis/risk_scorer.py`
- `api/schemas.py`
- `docs/ci.md`
- `docs/schemas/report-v2.md`
- `evidence/extractor.py`
- `parsers/base.py`
- `parsers/terraform_parser.py`
- `playwright.config.cjs`
- `services/analysis_service.py`
- `tests/e2e/seeded_server.py`
- `tests/e2e/report_review.keyboard.spec.js`
- `tests/test_api/test_analyses.py`
- `tests/test_analysis/test_risk_scorer.py`
- `tests/test_analysis/test_blast_radius.py`
- `tests/test_analysis/test_interaction_risk.py`
- `tests/test_analysis/test_rollback_planner.py`
- `tests/test_cli/test_analyze.py`
- `tests/test_parsers/test_terraform_parser.py`
- `tests/test_parsers/test_registry.py`
- `tests/test_services/test_analysis_service.py`
- `tests/test_services/test_evidence_extractor.py`
- `tests/test_services/test_github_app_service.py`
- `tests/test_services/test_report_service.py`
- `frontend/e2e/test_history_page.py`
- `frontend/e2e/test_upload_panel.py`
- `frontend/src/components/change_table.py`
- `frontend/src/components/report_detail_page.py`
- `frontend/src/components/upload_panel.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-08: Implemented Terraform plan JSON metadata normalization and moved story to review.
- 2026-05-08: Fixed code review findings for all-`no-op` Terraform plan intake, module-scoped resource summaries, and CLI metadata regression coverage.
- 2026-05-08: Fixed re-review findings for top-level Terraform plan metadata reporting and downstream non-mutating/replacement action handling.
- 2026-05-08: Fixed follow-up re-review findings for canonical shared Terraform actions, summary/metadata separation, root marker reporting, and topology-aware non-mutating reasoning.
- 2026-05-08: Re-ran code review and moved story back to in-progress for unresolved patch findings.
- 2026-05-08: Fixed latest review findings across shared action normalization, blast-radius filtering, rollback planning, and interaction-risk detection; moved story back to review.
- 2026-05-08: Re-ran code review and moved story back to in-progress for unresolved Terraform parser and non-mutating LLM-scoring patch findings.
- 2026-05-08: Fixed latest Terraform parser and risk-scoring review findings; moved story back to review.
- 2026-05-08: Re-ran code review and moved story back to in-progress for unresolved replacement-risk, non-mutating verdict, and Terraform metadata reporting patch findings.
- 2026-05-08: Fixed latest replacement-risk, non-mutating verdict, and Terraform metadata reporting review findings; moved story back to review.
- 2026-05-08: Re-ran code review and moved story back to in-progress for unresolved Terraform action validation, metadata JSON-safety, non-mutating LLM, metadata rendering, upload rerender, and UI-review validation patch findings.
- 2026-05-08: Fixed latest Terraform validation, metadata safety/rendering, non-mutating scoring, upload rerender, and UI-review validation findings; moved story back to review.
- 2026-05-08: Fixed follow-up review findings for Terraform address/action validation, plan-level unsupported-field reporting, and upload rerender behavior coverage; moved story back to review.
- 2026-05-08: Re-ran code review and moved story back to in-progress for unresolved non-mutating evidence/UI behavior and coverage patch findings.
- 2026-05-08: Fixed latest non-mutating evidence/UI and metadata coverage review findings; moved story back to review.
- 2026-05-08: Re-ran code review and moved story back to in-progress for unresolved real-pipeline metadata propagation and non-mutating upload metadata visibility findings.
- 2026-05-08: Fixed latest real-pipeline metadata propagation and upload metadata visibility findings; moved story back to review.
- 2026-05-08: Re-ran code review and moved story back to in-progress for unresolved non-mutating metadata persistence, upload metadata attribution, and browser-level metadata/rerender coverage findings.
- 2026-05-08: Fixed latest non-mutating metadata persistence, upload metadata attribution, first-mutating plan metadata placement, and browser metadata/rerender coverage findings; moved story back to review.
- 2026-05-08: Re-ran code review and moved story back to in-progress for unresolved explicit empty-evidence scoring and malformed Terraform plan JSON root parser-error findings.
- 2026-05-08: Fixed latest explicit empty-evidence scoring and malformed Terraform plan root parser-error review findings; moved story back to review.
- 2026-05-08: Re-ran code review and moved story back to in-progress for unresolved mixed-plan metadata persistence, generated-config reporting, security validation evidence, and story file-list reconciliation findings.
