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

### Review Findings

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 11 / Story 11.3 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

OpenAI Codex (GPT-5)

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

### Completion Notes List

- Added project/integration `enforcement_mode` persistence and API exposure for `advisory`, `warn`, `soft-block`, and `hard-block`, with advisory defaults and backward-compatible loading of Story 11.2 settings.
- Added a shared immutable enforcement decision that preserves raw policy status, caps effective status at the explicit integration mode, and keeps canonical reports advisory/non-blocking.
- Routed GitHub App checks through the shared policy/enforcement path: advisory/warn remain non-blocking, soft-block maps to `action_required`, and hard-block maps to `failure`; summaries expose raw, configured, and effective statuses.
- Updated integration/operator documentation and the generated TypeScript API schema. The external `deploywhisper/analyze-action` repository remains the owner of its runtime implementation and can consume this shared contract without changing the canonical analysis response.
- Implementation is stacked on the unmerged Story 11.2 branch because Story 11.3 directly extends its policy settings/output services.
- Resolved all seven code-review findings: added the external capped-decision endpoint, safe GitHub failure results, legacy PUT preservation, accurate skipped-analysis guidance, full mode/default/reset regressions, and executable operator-documentation coverage.

### File List

- README.md
- _bmad-output/implementation-artifacts/11-3-integration-level-enforcement-settings.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- api/routes/settings.py
- api/routes/analyses.py
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
- tests/test_docs/test_workflow_adapter_output_contract.py
- tests/test_services/test_github_app_service.py
- tests/test_services/test_policy_adapter_service.py
- tests/test_services/test_settings_service.py

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-08-11: Added advisory-first integration enforcement settings, shared capped decisions, GitHub check enforcement, deterministic regression coverage, API schema generation, and operator documentation; moved story to review.
- 2026-08-12: Resolved all seven code-review findings, regenerated the API client contract, completed full validation, and moved the story to done.
