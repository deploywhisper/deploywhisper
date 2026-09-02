# Story 11.3: Integration-Level Enforcement Settings

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform admin,
I want enforcement mode configured per integration,
So that teams can adopt warnings before blocking.

## Acceptance Criteria

1. Given GitHub, CI, or future integrations are configured, When enforcement settings are changed, Then each integration can use advisory, warn, soft-block, or hard-block mode. And defaults preserve advisory-first behavior.

### Requirement Traceability

- Primary PRD requirements: Epic 11 coverage: ADM-07, ADM-09, WRK-07, RSK-07, NFR-SEC-06.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 11 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Follow-ups (AI)

- [x] [AI-Review][HIGH] Make GitHub check-run delivery best-effort on neutral-skip and successful-analysis paths while preserving handled webhook results and persisted report references.
- [x] [AI-Review][LOW] Emit explicit skipped-analysis guidance for sensitive-only, unsupported-only, and mixed rejected artifact sets.

### Review Findings

- [x] [Review][Patch] Add a combined GitHub webhook regression proving an enforcement-decision failure remains bounded when the fallback failure check cannot be delivered. [tests/test_services/test_github_app_service.py:435]
- [x] [Review][Patch] Implement and verify the GitHub Action/CI enforcement consumer in `deploywhisper/analyze-action` using the canonical `github-action` integration key, validated v1 decision contract, auditable outputs, and configured blocking exit behavior.
- [x] [Review][Patch] Treat a missing integer check-run ID as a delivery failure so a malformed GitHub success response cannot silently discard a soft/hard enforcement signal. [integrations/github/app_service.py:888]
- [x] [Review][Patch] Return project-scope failures as failed results with the original machine-readable project code and a separate check-delivery code when both failures occur. [integrations/github/app_service.py:668]
- [x] [Review][Patch] Preserve an existing or inherited enforcement mode in the shared settings service when non-HTTP callers omit the new field. [services/settings_service.py:218]
- [x] [Review][Patch] Describe unknown future intake rejection states without incorrectly claiming that no changed artifacts were available. [integrations/github/app_service.py:852]
- [x] [Review][Patch] Standardize the GitHub Action integration identifier as `github-action` across runtime, documentation, and executable contract examples. [docs/github-action.md:70]
- [x] [Review][Patch] Synchronize both sprint-status `last_updated` values with the Story 11.3 completion date. [_bmad-output/implementation-artifacts/sprint-status.yaml:2]
- [x] [Review][Patch] Remove the contradictory instruction to follow the retired Python UI composition style; project context establishes the React SPA as the only current UI framework. [_bmad-output/implementation-artifacts/11-3-integration-level-enforcement-settings.md:78]
- [x] [Review][Patch] Make GitHub project-scope failure check-run delivery best-effort so a secondary GitHub API failure cannot escape the handled webhook result. [integrations/github/app_service.py:681]
- [x] [Review][Defer] Best-effort handle GitHub check-run creation failures on neutral-skip and successful-analysis paths [integrations/github/app_service.py:421] — deferred, pre-existing
- [x] [Review][Defer] Distinguish sensitive-only and unsupported-only skipped PR artifacts in GitHub guidance [integrations/github/app_service.py:414] — deferred, pre-existing
- [x] [Review][Patch] [MEDIUM] Do not claim that a canonical advisory report exists in GitHub check text when analysis was skipped or failed before report persistence; `_check_run_text()` currently appends that sentence even when both `details_url` and `enforcement` are absent. [integrations/github/app_service.py:822]
- [x] [Review][Patch] [MEDIUM] Give malformed integration identifiers and internal enforcement-decision invariant failures distinct machine-readable API error codes; both paths currently emit `invalid_policy_adapter_output` despite representing caller input versus server-contract failures. [api/routes/analyses.py:1038]
- [x] [Review][Patch] [MEDIUM] Reject blank or otherwise invalid `integration` query values as client errors before enforcement-decision construction; whitespace currently reaches `AdapterMetadata`, is caught with internal invariant failures, and returns HTTP 500 instead of a bounded 4xx response. [api/routes/analyses.py:1028]
- [x] [Review][Patch] [LOW] Add a legacy integration-scoped storage regression proving persisted settings without `enforcement_mode` load as advisory, matching the documented backward-compatibility guarantee already covered only for project-scoped storage. [tests/test_services/test_settings_service.py:246]
- [x] [Review][Patch] [MEDIUM] Preserve the resolved inherited project enforcement mode when a backward-compatible client creates its first integration override without `enforcement_mode`; the current source check falls back to the request model's `advisory` default and silently downgrades enforcement. [api/routes/settings.py:529]
- [x] [Review][Patch] [MEDIUM] Return a server-error contract when the enforcement-decision endpoint encounters internally generated adapter or decision invariant failures; the new route currently reports every `ValueError` as client-side `400 invalid_policy_adapter_output`. [api/routes/analyses.py:1063]
- [x] [Review][Patch] [MEDIUM] Use enforcement-specific fallback guidance when analysis succeeds but enforcement validation fails; the check summary says the analysis completed, while `_check_run_text()` currently says it could not complete. [integrations/github/app_service.py:585]
- [x] [Review][Patch] [MEDIUM] Expand enforcement-decision regression coverage across raw policy statuses, including raw statuses below the configured ceiling, so the no-upward-escalation invariant and advisory-first built-in decision path cannot drift. [tests/test_services/test_policy_adapter_service.py:108]
- [x] [Review][Patch] [HIGH] Expose the capped enforcement decision through a shared external API contract so CI and future adapters can consume `configured_mode`, `effective_status`, and `should_block` without reimplementing policy logic. [api/routes/analyses.py:96]
- [x] [Review][Patch] [HIGH] Handle policy-setting integrity and enforcement-contract failures after successful GitHub analysis instead of crashing before a check run is posted. [integrations/github/app_service.py:553]
- [x] [Review][Patch] [MEDIUM] Preserve an existing enforcement mode when backward-compatible clients omit the newly added field during a settings update. [api/routes/settings.py:529]
- [x] [Review][Patch] [MEDIUM] Stop using the enforcement-error fallback copy for neutral no-supported-artifact checks, where analysis was intentionally skipped rather than failing. [integrations/github/app_service.py:416]
- [x] [Review][Patch] [MEDIUM] Add full GitHub webhook regressions for advisory, warn, and soft-block decisions, including emitted conclusion, summary, and guidance text. [tests/test_services/test_github_app_service.py:123]
- [x] [Review][Patch] [MEDIUM] Add API regressions for built-in advisory mode and reset inheritance so the new response/default contract cannot drift. [tests/test_api/test_settings.py:92]
- [x] [Review][Patch] [LOW] Lock operator-facing branch-protection guidance and the canonical `github` integration key with an executable documentation regression. [docs/github-app.md:65]

## Dev Notes

### Epic Context

- Epic: 11. Optional Enforcement Adapters
- Epic goal: Expose optional enforcement interpretation without changing the advisory core.
- Epic coverage: ADM-07, ADM-09, WRK-07, RSK-07, NFR-SEC-06

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
- UI work belongs under `frontend/src/screens/` and `frontend/src/components/`, following the current React SPA component and theme conventions.
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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 11 / Story 11.3 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

OpenAI Codex (GPT-5)

### Implementation Plan

- Preserve successful analysis and handled-webhook results when GitHub check delivery fails, while returning a bounded `partial` status and `github_check_run_failed` code without exposing upstream details.
- Derive skipped-analysis guidance only from aggregate intake statuses so sensitive, unsupported, mixed, and empty artifact sets are explicit without disclosing filenames or contents.
- Lock both paths with focused regressions before running the required repository validation gates.

### Debug Log References

- RED: `./.venv/bin/python -m pytest tests/test_services/test_settings_service.py tests/test_services/test_policy_adapter_service.py tests/test_api/test_settings.py tests/test_services/test_github_app_service.py -q --tb=short` - expected failure (`9 failed, 61 passed, 17 subtests passed`) before enforcement settings and decisions existed.
- GREEN: the same focused command - `66 passed, 21 subtests passed`.
- Expanded regression: policy settings/output, analyses/settings APIs, GitHub App, and contract docs - `191 passed, 113 subtests passed`.
- Generated API contract: temporary local app plus `OPENAPI_URL=http://127.0.0.1:18133/api/v1/openapi.json npm run ui:gen-api` - passed.
- Full local CI: `bash scripts/ci-local.sh` - passed Ruff check/format, dependency integrity, Bandit high-confidence gate (0 high findings), compileall, skill scenarios, prompt-injection gate, and every backend/docs test directory; final services directory reported `915 tests` passing.
- Required smoke: `./.venv/bin/python -m unittest discover -q` - `408 tests` passed, `1 skipped`.
- CI-parity shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` - `389 passed, 103 subtests passed`.
- Generated-client verification: `npm --prefix frontend run build` - passed; `npm --prefix frontend test` - `55 passed`.
- UI validation not applicable: no React route, component, rendered surface, interaction, keyboard behavior, or accessibility semantics changed; only generated API type declarations changed.
- Review RED: five focused regressions reproduced the missing external decision endpoint, legacy PUT reset, GitHub enforcement exception, skipped-analysis copy, and documentation gaps (`5 failed`).
- Review GREEN: focused analyses/settings/GitHub suites passed after fixes; documentation contract rerun reported `3 passed, 26 subtests passed`.
- Review full local CI: `bash scripts/ci-local.sh` - Ruff, formatting, dependency integrity, Bandit, compileall, all skill/prompt gates, and `919 tests` passed.
- Review required smoke: `./.venv/bin/python -m unittest discover -q` - `411 tests` passed, `1 skipped`.
- Review CI-parity shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` - `392 passed, 109 subtests passed`.
- Review generated-client verification: OpenAPI schema regenerated from the local app; frontend production build passed; Vitest reported `55 passed`.
- Remote CI correction: the first PR API/CLI/infra run found a stale mirrored sprint-status header date; after aligning it with `last_updated`, the focused metadata regression and full shard were rerun.
- Review rerun RED: `./.venv/bin/python -m pytest tests/test_services/test_github_app_service.py tests/test_services/test_policy_adapter_service.py -q --tb=short` reproduced the inaccurate enforcement fallback guidance (`2 failed, 30 passed, 22 subtests passed`).
- Review rerun GREEN: the same focused command passed after the fix (`30 passed, 22 subtests passed`).
- Review rerun quality gates: `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, and `git diff --check` passed; Ruff reported all 272 files formatted.
- Review rerun CI-parity shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` - `392 passed, 109 subtests passed`.
- Review rerun full local CI: `bash scripts/ci-local.sh` - passed Ruff check/format, dependency integrity, Bandit high-confidence gate (0 high findings), compileall, all skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `920 tests` passing.
- Second review rerun RED: focused settings/analyses API regressions reproduced the inherited-mode downgrade and client-error misclassification (`2 failed, 118 passed, 33 subtests passed`).
- Second review rerun GREEN: `./.venv/bin/python -m pytest tests/test_api/test_settings.py tests/test_api/test_analyses.py -q --tb=short` - `120 passed, 33 subtests passed`.
- Second review required smoke: `./.venv/bin/python -m unittest discover -q` - `413 tests` passed, `1 skipped`.
- Second review CI-parity shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` - `394 passed, 109 subtests passed`.
- Second review full local CI: `bash scripts/ci-local.sh` - passed Ruff check/format, dependency integrity, Bandit high-confidence gate, compileall, all skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `920 tests` passing.
- Third review rerun RED: focused analyses/settings-service regressions reproduced invalid integration identifiers returning HTTP 500 (`2 failed, 134 passed, 28 subtests passed`); the legacy integration-storage regression passed immediately.
- Third review rerun GREEN: `./.venv/bin/python -m pytest tests/test_api/test_analyses.py tests/test_services/test_settings_service.py -q --tb=short` - `134 passed, 30 subtests passed`.
- Third review required smoke: `./.venv/bin/python -m unittest discover -q` - `414 tests` passed, `1 skipped`.
- Third review CI-parity shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` - `395 passed, 111 subtests passed`.
- Third review full local CI: `bash scripts/ci-local.sh` - passed Ruff check/format, dependency integrity, Bandit high-confidence gate, compileall, all skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `921 tests` passing.
- Fourth review RED: focused GitHub App and analyses API regressions reproduced misleading no-report guidance and the shared client/server error code (`5 failed, 127 passed, 27 subtests passed`).
- Fourth review GREEN: `./.venv/bin/python -m pytest tests/test_services/test_github_app_service.py tests/test_api/test_analyses.py -q --tb=short` - `130 passed, 29 subtests passed`.
- Fourth review required smoke: `./.venv/bin/python -m unittest discover -q` - `414 tests` passed, `1 skipped`.
- Fourth review CI-parity shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` - `395 passed, 111 subtests passed`.
- Fourth review full local CI: `bash scripts/ci-local.sh` - passed Ruff check/format, dependency integrity, Bandit high-confidence gate, compileall, all skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `921 tests` passing.
- Deferred-finding RED: `./.venv/bin/python -m pytest tests/test_services/test_github_app_service.py -q --tb=short` reproduced generic skipped-analysis copy and uncaught check-run delivery failures (`6 failed, 26 passed, 6 subtests passed`).
- Deferred-finding GREEN: the same focused command passed after the fixes (`29 passed, 9 subtests passed`).
- Deferred-finding quality gates: `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, and `git diff --check` passed; Ruff reported all 272 files formatted.
- Deferred-finding required smoke: `./.venv/bin/python -m unittest discover -q` - `414 tests` passed, `1 skipped`.
- Deferred-finding CI-parity shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` - `395 passed, 111 subtests passed`.
- Deferred-finding full local CI: `bash scripts/ci-local.sh` - passed Ruff check/format, dependency integrity, Bandit high-confidence gate with zero high findings, compileall, all skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `924 tests` passing.
- UI validation not applicable for the deferred findings: no React route, component, rendered surface, browser interaction, keyboard behavior, or accessibility semantics changed.
- Sixth review RED: `./.venv/bin/python -m pytest tests/test_services/test_github_app_service.py -q --tb=short` reproduced the unhandled project-scope/check-delivery failure (`1 failed, 29 passed, 9 subtests passed`).
- Sixth review GREEN: the same focused GitHub App suite passed after the bounded partial-result fix (`30 passed, 9 subtests passed`).
- Sixth review quality gates: `./.venv/bin/ruff check .`, repo-wide `./.venv/bin/ruff format --check .`, and `git diff --check` passed; Ruff reported all 272 files formatted.
- Sixth review required smoke: `./.venv/bin/python -m unittest discover -q` passed.
- Sixth review full local CI: `bash scripts/ci-local.sh` passed Ruff check/format, dependency integrity, Bandit with zero high-severity findings, compileall, skill and prompt-injection gates, and every backend/docs test directory; `925 tests` passed.
- UI validation not applicable for the sixth review: no React route, component, rendered surface, browser interaction, keyboard behavior, or accessibility semantics changed.
- Seventh review focused regression: `./.venv/bin/python -m pytest tests/test_services/test_github_app_service.py -q --tb=short` - `31 passed, 11 subtests passed`, including both enforcement-failure/check-delivery combinations.
- Seventh review quality gates: `./.venv/bin/ruff check .`, repo-wide `./.venv/bin/ruff format --check .`, and `git diff --check` passed; Ruff reported all 272 files formatted.
- Seventh review required smoke: `./.venv/bin/python -m unittest discover -q` - `414 tests` passed, `1 skipped`.
- Seventh review full local CI: `bash scripts/ci-local.sh` passed Ruff check/format, dependency integrity, Bandit with zero high-severity findings, compileall, skill and prompt-injection gates, and every backend/docs test directory; `926 tests` passed.
- UI validation not applicable for the seventh review: no React route, component, rendered surface, browser interaction, keyboard behavior, or accessibility semantics changed.
- Eighth review RED: focused regressions reproduced missing check-run ID acceptance, project failures reported as success, lost primary project codes on compounded failures, shared-service enforcement downgrades, and misleading unknown intake guidance (`5 failed`).
- Eighth review app GREEN: focused settings/GitHub App/API suites passed (`87 passed, 30 subtests passed`); GitHub Action contract and adapter-contract suites passed (`31 passed, 54 subtests passed`).
- Eighth review CI-parity shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` - `395 passed, 111 subtests passed`.
- Eighth review required smoke: `./.venv/bin/python -m unittest discover -q` - `414 tests` passed, `1 skipped`.
- Eighth review full local CI: `bash scripts/ci-local.sh` passed Ruff check/format, dependency integrity, Bandit with zero high-severity findings, compileall, skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `930 tests` passing.
- External action validation in `/tmp/analyze-action`: `python3 -m unittest discover -s tests -q` passed `62 tests`; compileall, non-repository `run_action.py --help`, and `git diff --check` passed.
- UI validation not applicable for the eighth review: no React route, component, rendered surface, browser interaction, keyboard behavior, or accessibility semantics changed.

### Completion Notes List

- Added project/integration `enforcement_mode` persistence and API exposure for `advisory`, `warn`, `soft-block`, and `hard-block`, with advisory defaults and backward-compatible loading of Story 11.2 settings.
- Added a shared immutable enforcement decision that preserves raw policy status, caps effective status at the explicit integration mode, and keeps canonical reports advisory/non-blocking.
- Routed GitHub App checks through the shared policy/enforcement path: advisory/warn remain non-blocking, soft-block maps to `action_required`, and hard-block maps to `failure`; summaries expose raw, configured, and effective statuses.
- Updated integration/operator documentation and the generated TypeScript API schema. The external `deploywhisper/analyze-action` runtime now consumes the shared enforcement contract without changing the canonical analysis response.
- Implementation is stacked on the unmerged Story 11.2 branch because Story 11.3 directly extends its policy settings/output services.
- Resolved all seven code-review findings: added the external capped-decision endpoint, safe GitHub failure results, legacy PUT preservation, accurate skipped-analysis guidance, full mode/default/reset regressions, and executable operator-documentation coverage.
- Resolved both findings from the Story 11.3 review rerun: enforcement-validation failures now describe the completed analysis accurately, and the decision suite locks every raw-status/configured-mode pairing against upward escalation plus the built-in advisory path.
- Resolved both findings from the second review rerun: legacy integration overrides retain inherited project enforcement when the field is omitted, and internal enforcement-decision validation failures return a sanitized server-error response.
- Resolved both findings from the third review rerun: policy integration identifiers now use shared boundary normalization before decision construction, and legacy integration-scoped storage has explicit advisory-default coverage.
- Resolved both findings from the fourth review rerun: GitHub checks only mention a canonical report when one exists, and the external enforcement-decision API now distinguishes malformed integration input from internal decision-validation failures with stable error codes.
- The fifth review rerun found no Story 11.3 patch or decision gap; two pre-existing GitHub App reliability/copy issues were recorded in deferred work without expanding this story's scope.
- Resolved both fifth-review deferrals at user request: skipped and successful analyses now survive GitHub check-run delivery failures with bounded partial results, and rejected artifact sets receive explicit sensitive/unsupported/mixed guidance without exposing artifact details.
- Resolved both sixth-review findings: story guidance now points only to the current React SPA conventions, and project-scope failures preserve handled webhook results when GitHub check-run delivery also fails.
- Resolved both seventh-review findings: compounded enforcement/check-delivery failures now have explicit regression coverage, and sprint completion timestamps are internally consistent.
- Resolved every eighth-review finding: the standalone action now enforces the validated `github-action` decision, malformed check-run responses fail explicitly, project and delivery failures remain separately machine-readable, shared service updates preserve enforcement, and all integration keys/guidance are consistent.

### File List

- README.md
- _bmad-output/implementation-artifacts/deferred-work.md
- _bmad-output/implementation-artifacts/11-3-integration-level-enforcement-settings.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- api/routes/settings.py
- api/routes/analyses.py
- api/routes/github_app.py
- api/schemas.py
- docs/ci-advisory-consumption.md
- docs/github-action.md
- docs/github-app-self-hosted-setup.md
- docs/github-app.md
- docs/workflow-adapter-output-contract.md
- frontend/src/api/schema.d.ts
- integrations/github/app_service.py
- services/policy_adapter_service.py
- services/policy_adapter_settings.py
- services/settings_service.py
- tests/test_api/test_settings.py
- tests/test_api/test_analyses.py
- tests/test_api/test_github_app.py
- tests/test_docs/test_github_action_integration_contract.py
- tests/test_docs/test_workflow_adapter_output_contract.py
- tests/test_services/test_adapter_output_contract.py
- tests/test_services/test_github_app_service.py
- tests/test_services/test_policy_adapter_service.py
- tests/test_services/test_settings_service.py
- External repository `deploywhisper/analyze-action`: `README.md`, `action.yml`, `action_runtime.py`, `tests/test_action_runtime.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-08-11: Added advisory-first integration enforcement settings, shared capped decisions, GitHub check enforcement, deterministic regression coverage, API schema generation, and operator documentation; moved story to review.
- 2026-08-12: Resolved all seven code-review findings, regenerated the API client contract, completed full validation, and moved the story to done.
- 2026-08-13: Resolved both findings from the code-review rerun and expanded enforcement-decision regression coverage across the complete status matrix.
- 2026-08-13: Resolved the second review rerun findings for inherited enforcement preservation and internal error classification, with focused and full-CI regression evidence.
- 2026-08-13: Resolved the third review rerun findings for invalid integration input classification and legacy integration-storage coverage.
- 2026-08-14: Resolved the fourth review rerun findings for no-report GitHub guidance and distinct enforcement-decision error codes.
- 2026-08-14: Fifth review rerun passed Story 11.3 acceptance and recorded two pre-existing GitHub App issues as deferred work.
- 2026-08-14: Addressed both deferred fifth-review findings with red-green regressions and full local CI; moved Story 11.3 back to review.
- 2026-08-17: Addressed all sixth-review findings with a focused red-green regression and full local CI; moved Story 11.3 to done.
- 2026-08-18: Addressed all seventh-review findings with compounded-failure regressions, synchronized sprint metadata, and full local CI; retained done status.
- 2026-08-18: Addressed all eighth-review findings across the app and standalone action repositories, completed CI enforcement consumption, and retained done status after full validation.
