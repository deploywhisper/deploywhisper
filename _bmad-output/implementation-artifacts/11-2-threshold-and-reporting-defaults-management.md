# Story 11.2: Threshold and Reporting Defaults Management

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform admin,
I want configurable thresholds and reporting defaults,
So that teams can tune adapter behavior without changing core code.

## Acceptance Criteria

1. Given thresholds are configured per project or integration, When adapter output is generated, Then thresholds are applied only to adapter interpretation. And the original evidence, findings, and severity remain auditable.

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

- [x] [Review][Patch] Normalize adapter metadata project keys with the canonical project-key normalizer before comparing them with resolved settings [services/policy_adapter_output_contract.py:138]
- [x] [Review][Patch] Validate GET/DELETE integration query values consistently with PUT and return the policy-settings error contract [api/routes/settings.py:438]
- [x] [Review][Decision] Clarify the Story 11.2 runtime boundary before claiming production integration — Resolved by retaining the reusable configured-generation service boundary, correcting overstated runtime wording, and leaving integration activation to Story 11.3.
- [x] [Review][Patch] Reject unknown canonical severities instead of silently applying the reporting default [services/policy_adapter_output_contract.py:163]
- [x] [Review][Patch] Validate persisted policy-setting payload scope against its storage key before returning it [services/settings_service.py:233]

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 11 / Story 11.2 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

Codex (GPT-5)

### Implementation Plan

- Reuse the existing policy-adapter contract and application settings repository instead of changing canonical scoring or adding persistence tables.
- Model strict severity thresholds plus an advisory/warn reporting default, with integration overrides inheriting project and built-in defaults.
- Add one configured generation service that resolves project key or ID, validates integration scope, applies settings only to policy interpretation, and records the applied snapshot for audit.
- Expose admin-only, explicitly project-scoped GET/PUT/DELETE management endpoints and keep generated API types and operator documentation aligned.
- Regression-lock precedence, reset behavior, RBAC, explicit scope, project-ID resolution, threshold validation, and canonical report immutability.

### Debug Log References

- RED: focused policy/settings/API/docs pytest collection failed because `PolicyAdapterSettings` and the management behavior did not exist.
- GREEN: initial focused suite passed 41 tests and 46 subtests after adding thresholds, persistence, API management, and immutable applied-settings output.
- Review RED: an internal review found that stored settings lacked a configured runtime generation path, overrides could not be reset, and `project_id` scope was not verified; new tests first failed because the runtime service and delete behavior did not exist.
- Review GREEN: added `build_configured_policy_adapter_output`, inherited-default deletion, project-ID resolution, and scope guards; focused suite passed 45 tests and 48 subtests.
- Final review RED/GREEN: missing project scope initially returned 200 for GET/PUT/DELETE; explicit-scope validation changed all three to deterministic `400 missing_project_scope`, and the regression passed with 3 subtests.
- Final focused regression: `./.venv/bin/python -m pytest tests/test_services/test_policy_adapter_service.py tests/test_services/test_policy_adapter_output_contract.py tests/test_services/test_settings_service.py tests/test_api/test_settings.py tests/test_docs/test_workflow_adapter_output_contract.py -q --tb=short` — 46 passed, 51 subtests passed.
- Required affected GitHub shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -q --tb=short` — 381 passed, 94 subtests passed.
- Affected services/docs shard: `./.venv/bin/python -m pytest tests/test_services tests/test_docs -q --tb=short` — 928 passed, 373 subtests passed.
- Required smoke: `./.venv/bin/python -m unittest discover -q` — 399 passed, 1 skipped; the final broader CI run superseded this after the last route guard.
- Static/security validation: `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, and targeted Bandit over the changed service/API modules — passed; 272 files already formatted.
- Final full local CI: `bash scripts/ci-local.sh` — passed, including Ruff, repo-wide formatting, dependency validation, Bandit, compile checks, skill harnesses, and 905 tests.
- Generated API types from the current in-process FastAPI OpenAPI document with `openapi-typescript`; the policy-adapter GET/PUT/DELETE contract is present in `frontend/src/api/schema.d.ts`.
- Independent internal re-review: zero remaining high or medium findings after runtime wiring, reset behavior, project-ID validation, and explicit project-scope fixes.
- BMad review fixes: canonicalized metadata/resolved/settings project keys before scope comparison and aligned GET/DELETE integration query validation with the write contract and `invalid_policy_adapter_settings` error envelope.
- BMad re-review fixes: clarified that the configured-generation service is the Story 11.2 boundary rather than an already activated integration, rejected unknown canonical severities, and rejected persisted settings whose payload scope disagrees with their storage key.
- Review regression suite: `./.venv/bin/python -m pytest tests/test_services/test_policy_adapter_service.py tests/test_services/test_policy_adapter_output_contract.py tests/test_services/test_settings_service.py tests/test_api/test_settings.py tests/test_docs/test_workflow_adapter_output_contract.py -q --tb=short` — 50 passed, 57 subtests passed.
- Post-review full local CI: `bash scripts/ci-local.sh` — passed, including Ruff, repo-wide formatting, dependency validation, Bandit, compile checks, skill harnesses, and 908 tests.
- UI validation not applicable: no React route, rendered surface, browser interaction, keyboard behavior, or accessibility semantics changed; only generated API type declarations were refreshed.

### Completion Notes List

- Added strict frozen policy settings for medium/high/critical defaults, optional disabled thresholds, and advisory/warn below-threshold reporting behavior.
- Persisted project defaults and integration-specific overrides through the existing application settings repository, with integration -> project -> built-in resolution and DELETE-based reset to inheritance.
- Added one reusable configured-generation service that resolves adapter project key or ID, applies the correct integration settings, and rejects cross-project or cross-integration use.
- Kept policy decisions separate from the canonical advisory report and attached the resolved settings snapshot to the policy envelope for auditability.
- Added admin-only GET/PUT/DELETE API management with explicit project scope and refreshed generated OpenAPI TypeScript declarations.
- Documented built-in defaults, precedence, reset semantics, runtime usage, and the unchanged canonical evidence/findings/severity boundary.

### File List

- `_bmad-output/implementation-artifacts/11-2-threshold-and-reporting-defaults-management.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `api/routes/settings.py`
- `api/schemas.py`
- `docs/workflow-adapter-output-contract.md`
- `frontend/src/api/schema.d.ts`
- `services/policy_adapter_output_contract.py`
- `services/policy_adapter_service.py`
- `services/policy_adapter_settings.py`
- `services/settings_service.py`
- `tests/test_api/test_settings.py`
- `tests/test_docs/test_workflow_adapter_output_contract.py`
- `tests/test_services/test_policy_adapter_output_contract.py`
- `tests/test_services/test_policy_adapter_service.py`
- `tests/test_services/test_settings_service.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-08-06: Added project/integration threshold and reporting-default management, configured adapter interpretation, reset/inheritance behavior, explicit scope/RBAC safeguards, docs, generated API types, and full regression coverage; moved story to review.
- 2026-08-06: Resolved all BMad review findings, added canonical project-key and integration-query regressions, passed full local CI, and marked the story done.
- 2026-08-06: Resolved re-review findings for runtime-boundary wording, unknown canonical severities, and persisted scope integrity; retained Story 11.3 as the integration-activation boundary.
