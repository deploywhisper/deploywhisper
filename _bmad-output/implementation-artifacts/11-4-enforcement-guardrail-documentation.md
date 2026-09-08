# Story 11.4: Enforcement Guardrail Documentation

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a reviewer,
I want docs explaining optional enforcement guardrails,
So that teams understand when not to block automatically.

## Acceptance Criteria

1. Given users read policy adapter docs, When they configure enforcement, Then docs explain Evidence Law, benchmark thresholds, false reassurance, human review, and rollback responsibilities. And docs discourage autonomous approval or remediation.

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

- [x] [Review][Patch] [HIGH] Document that a project-level enforcement mode is inherited by every integration without an override and that deleting an override can expose a blocking project default; the current guide incorrectly implies each integration is always configured directly. [docs/enforcement-guardrails.md:3]
- [x] [Review][Patch] [HIGH] Define fail-safe behavior for unavailable, timed-out, stale, or malformed enforcement decisions so current and future consumers cannot silently convert an operational failure into a passing check. [docs/enforcement-guardrails.md:21]
- [x] [Review][Patch] [MEDIUM] Make benchmark readiness verifiable using the metrics the current runner actually emits, document the calculation and sampling record needed for organization-owned thresholds, and require zero Evidence Law violations rather than treating violations as a configurable tolerance. [docs/enforcement-guardrails.md:53]
- [x] [Review][Patch] [MEDIUM] Clarify that the mode table's per-mode examples do not replace the complete blocking prerequisites; the soft-block row currently appears to authorize blocking once only an exception path exists. [docs/enforcement-guardrails.md:16]
- [x] [Review][Patch] [MEDIUM] Describe observable soft-block and hard-block workflow behavior instead of defining each mode circularly in terms of itself. [docs/enforcement-guardrails.md:18]
- [x] [Review][Patch] [LOW] Remove the contradictory instruction to follow the retired Python UI composition style; project context establishes the React SPA as the only current UI framework. [_bmad-output/implementation-artifacts/11-4-enforcement-guardrail-documentation.md:53]

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
- UI work belongs under `frontend/src/screens/` and `frontend/src/components/`, following the current React SPA theme and component conventions.
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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 11 / Story 11.4 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

OpenAI Codex (GPT-5)

### Implementation Plan

- Lock the required guardrail topics and document discoverability with a failing documentation-contract regression.
- Publish one canonical enforcement guide rather than duplicating safety policy across integration-specific documents.
- Link every current enforcement entry point to the guide and preserve the existing advisory-first runtime contract.
- Run focused documentation coverage, repository smoke tests, quality/security gates, and full local CI before moving the story to review.

### Debug Log References

- RED: `./.venv/bin/python -m pytest tests/test_docs/test_enforcement_guardrails.py -q --tb=short` - expected failure because the guide and entry-point links did not exist (`6 failed, 1 passed`).
- GREEN: the same focused command passed after the guide and links were added (`2 passed, 20 subtests passed`); the expanded self-hosted GitHub App entry-point regression was also confirmed red before its link was added.
- Focused final documentation contracts: `./.venv/bin/python -m pytest tests/test_docs/test_enforcement_guardrails.py tests/test_docs/test_github_action_integration_contract.py tests/test_docs/test_workflow_adapter_output_contract.py -q --tb=short` - `12 passed, 79 subtests passed`.
- Documentation suite: `./.venv/bin/python -m pytest tests/test_docs -q --tb=short` - `25 passed, 138 subtests passed`.
- Required smoke: `./.venv/bin/python -m unittest discover -q` - `416 tests` passed, `1 skipped`.
- Quality gates: `./.venv/bin/ruff check .`, repo-wide `./.venv/bin/ruff format --check .`, and `git diff --check` passed; Ruff reported all 273 files formatted.
- Full local CI: `bash scripts/ci-local.sh` passed Ruff, dependency integrity, Bandit with zero high-severity findings, compileall, skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `930 tests` passing.
- UI validation not applicable: this story changes Markdown documentation and documentation-contract tests only; no React route, component, rendered surface, interaction, keyboard behavior, or accessibility semantics changed.
- Review RED: the strengthened enforcement-contract regression reproduced all missing inheritance, failure-policy, benchmark-verifiability, Evidence Law, and concrete mode-effect guidance (`11 failed, 2 passed, 25 subtests passed`).
- Review GREEN: `./.venv/bin/python -m pytest tests/test_docs/test_enforcement_guardrails.py -q --tb=short` - `2 passed, 36 subtests passed`.
- Review documentation and metadata suite: `./.venv/bin/python -m pytest tests/test_docs tests/test_infra/test_ai_safety_documentation.py tests/test_infra/test_requirements_traceability_matrix.py -q --tb=short` - `39 passed, 226 subtests passed`.
- Review required smoke: `./.venv/bin/python -m unittest discover -q` - `416 tests` passed, `1 skipped`.
- Review full local CI: `bash scripts/ci-local.sh` passed Ruff, dependency integrity, Bandit with zero high-severity findings, compileall, all skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `930 tests` passing.
- Review quality gates: `./.venv/bin/ruff check .`, repo-wide `./.venv/bin/ruff format --check .`, `git diff --check`, and `git diff --cached --check` passed; Ruff reported all 273 files formatted.

### Completion Notes List

- Added a canonical enforcement guardrail guide that explains Evidence Law, organization-owned benchmark thresholds, false reassurance, mandatory human review, rollback responsibility, staged rollout, and break-glass controls.
- Explicitly states that DeployWhisper defines no universal numeric enforcement threshold because the PRD leaves that policy decision open; teams must approve thresholds using representative benchmark evidence before blocking.
- Linked the guide from the README, policy adapter contract, CI guide, GitHub Action guide, GitHub App guide, and self-hosted GitHub App runbook so operators encounter it before configuring required checks.
- Added deterministic documentation regressions for every acceptance-criterion topic and every enforcement entry-point link.
- No runtime, API, persistence, UI, or dependency behavior changed. Implementation is stacked on the verified but unmerged Story 11.3 branch because this story documents that enforcement contract.
- Resolved all six review findings: project-default inheritance and override deletion are explicit; invalid or unavailable decisions cannot become passes; benchmark inputs, calculations, and strict zero Evidence Law violations are documented; mode prerequisites and observable GitHub effects are unambiguous; and stale UI guidance now points to the React SPA conventions.

### File List

- README.md
- _bmad-output/implementation-artifacts/11-4-enforcement-guardrail-documentation.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- docs/ci-advisory-consumption.md
- docs/enforcement-guardrails.md
- docs/github-action.md
- docs/github-app-self-hosted-setup.md
- docs/github-app.md
- docs/workflow-adapter-output-contract.md
- tests/test_docs/test_enforcement_guardrails.py

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-09-07: Added canonical optional-enforcement guardrails, linked all enforcement entry points, added deterministic documentation coverage, completed full validation, and moved the story to review.
- 2026-09-08: Addressed all six code-review findings, strengthened the documentation contract, completed full validation, and moved the story to done.
