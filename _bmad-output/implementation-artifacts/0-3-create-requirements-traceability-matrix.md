# Story 0.3: Create Requirements Traceability Matrix

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a product owner,
I want PRD requirements mapped to epics and implementation artifacts,
So that future planning changes do not silently drift from the finalized PRD.

## Acceptance Criteria

1. Given the finalized PRD requirements, When the traceability matrix is generated, Then every requirement family maps to one or more epics. And gaps, deferred requirements, and cross-cutting requirements are explicitly marked.

### Requirement Traceability

- Primary PRD requirements: Epic 0 coverage: GOV-01..15, NFR-OSS-01..05, DOC-15, DOC-19, DOC-20.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 0 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Add explicit implementation artifact/story-file coverage to the traceability matrix and guardrail test, not just epic coverage [`_bmad-output/planning-artifacts/requirements-traceability-matrix.md:15`]
- [x] [Review][Patch] Verify implementation artifact paths in the traceability matrix resolve to real story files, not just path-shaped strings [`tests/test_infra/test_requirements_traceability_matrix.py:61`]

## Dev Notes

### Epic Context

- Epic: 0. Open Governance, Traceability, and Maintainer Ownership
- Epic goal: Establish the public project foundation needed for open-source trust, contribution, and roadmap accountability.
- Epic coverage: GOV-01..15, NFR-OSS-01..05, DOC-15, DOC-19, DOC-20

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 0 / Story 0.3 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5

### Debug Log References

- `./.venv/bin/python -m unittest tests.test_infra.test_requirements_traceability_matrix -q` initially failed before implementation because `_bmad-output/planning-artifacts/requirements-traceability-matrix.md` was missing.
- `./.venv/bin/python -m unittest tests.test_infra.test_requirements_traceability_matrix -q` passed after adding the matrix.
- `./.venv/bin/ruff format tests/test_infra/test_requirements_traceability_matrix.py` reformatted the new test file.
- `./.venv/bin/ruff check .` passed.
- `./.venv/bin/ruff format --check .` passed.
- `./.venv/bin/python -m unittest discover -q` passed with 223 tests run and 1 skipped.
- `bash scripts/ci-local.sh` passed; local Bandit scan was skipped because Bandit is not installed in the environment.
- `./.venv/bin/python -m unittest tests.test_infra.test_requirements_traceability_matrix -q` passed after fixing review findings.
- `./.venv/bin/ruff check .` passed after fixing review findings.
- `./.venv/bin/ruff format --check .` passed after fixing review findings.
- `./.venv/bin/python -m unittest discover -q` passed with 223 tests run and 1 skipped after fixing review findings.
- `./.venv/bin/python -m unittest tests.test_infra.test_requirements_traceability_matrix -q` passed after adding artifact path existence validation.
- `./.venv/bin/ruff check .` passed after adding artifact path existence validation.
- `./.venv/bin/ruff format --check .` passed after adding artifact path existence validation.
- `./.venv/bin/python -m unittest discover -q` passed with 223 tests run and 1 skipped after adding artifact path existence validation.
- `bmad-code-review` rerun found 0 decision-needed, 0 patch, and 0 deferred findings.
- `./.venv/bin/python -m unittest tests.test_infra.test_requirements_traceability_matrix -q` passed during review rerun.
- `./.venv/bin/ruff check .` passed during review rerun.
- `./.venv/bin/ruff format --check .` passed during review rerun.
- `./.venv/bin/python -m unittest discover -q` passed with 223 tests run and 1 skipped during review rerun.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra --cov=. --cov-report=xml:coverage-api-cli-infra.xml --cov-report=term-missing -q --tb=short` passed with 133 tests after fixing CI-only artifact validation.

### Completion Notes List

- Added `_bmad-output/planning-artifacts/requirements-traceability-matrix.md` with one row per PRD requirement family, epic coverage, coverage status, and explicit gap/deferred/cross-cutting notes.
- Added a gap, deferred, and cross-cutting register that records no open baseline gaps, explicit deferred scope, and cross-cutting requirement families.
- Added deterministic infrastructure guardrails that parse PRD requirement families and verify the traceability matrix exists, covers every PRD family, maps each family to epics, and explicitly uses gap/deferred/cross-cutting language.
- Resolved review finding by adding implementation-artifact/story-file coverage to the matrix and guardrail test.
- Resolved review finding by validating that implementation artifact paths listed in the matrix resolve to real story files.
- Code review rerun completed cleanly with no new findings.
- Fixed CI-only traceability guardrail failure by validating referenced implementation artifacts against committed story files or planned story keys in `sprint-status.yaml`, avoiding dependence on ignored local story files.

### File List

- `_bmad-output/implementation-artifacts/0-3-create-requirements-traceability-matrix.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/planning-artifacts/requirements-traceability-matrix.md`
- `tests/test_infra/test_requirements_traceability_matrix.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-04: Implemented the requirements traceability matrix and deterministic infra guardrail tests.
