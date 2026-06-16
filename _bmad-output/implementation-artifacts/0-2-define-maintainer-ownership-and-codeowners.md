# Story 0.2: Define Maintainer Ownership and CODEOWNERS

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a maintainer,
I want maintainer areas and CODEOWNERS documented,
So that reviews route to accountable project owners.

## Acceptance Criteria

1. Given a PR changes a major repository area, When CODEOWNERS evaluates the change, Then the appropriate maintainership area is requested for review. And `MAINTAINERS.md` explains owner responsibilities and known coverage gaps.

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

- [x] [Review][Patch] Add explicit CODEOWNERS and MAINTAINERS coverage for current top-level repo areas such as `evidence/`, `integrations/`, `scripts/`, and `schemas/` [`.github/CODEOWNERS:5`]
- [x] [Review][Patch] Add explicit CODEOWNERS, MAINTAINERS, and guardrail-test coverage for tracked top-level `_bmad/` project configuration area [`.github/CODEOWNERS:4`]

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 0 / Story 0.2 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5

### Debug Log References

- `./.venv/bin/python -m unittest tests.test_infra.test_maintainer_ownership -q` initially failed before implementation because `MAINTAINERS.md` was missing and major repository areas were not explicitly routed in CODEOWNERS.
- `./.venv/bin/python -m unittest tests.test_infra.test_maintainer_ownership -q` passed after adding maintainer ownership docs and CODEOWNERS area coverage.
- `./.venv/bin/ruff check tests/test_infra/test_maintainer_ownership.py` passed.
- `./.venv/bin/ruff format tests/test_infra/test_maintainer_ownership.py` reformatted the new test file.
- `./.venv/bin/python -m unittest tests.test_infra.test_maintainer_ownership tests.test_infra.test_skill_contribution_workflow -q` passed after restoring the explicit `/tests/skill-tests/` CODEOWNERS route required by existing contribution workflow guardrails.
- `./.venv/bin/ruff check .` passed.
- `./.venv/bin/ruff format --check .` passed.
- `./.venv/bin/python -m unittest discover -q` passed with 219 tests run and 1 skipped.
- `bash scripts/ci-local.sh` passed; local Bandit scan was skipped because Bandit is not installed in the environment.
- `./.venv/bin/python -m unittest tests.test_infra.test_maintainer_ownership tests.test_infra.test_skill_contribution_workflow -q` passed after fixing review findings.
- `./.venv/bin/ruff check .` passed after fixing review findings.
- `./.venv/bin/ruff format --check .` passed after fixing review findings.
- `./.venv/bin/python -m unittest discover -q` passed with 219 tests run and 1 skipped after fixing review findings.
- `./.venv/bin/python -m unittest tests.test_infra.test_maintainer_ownership tests.test_infra.test_skill_contribution_workflow -q` passed after adding `_bmad/` ownership coverage.
- `./.venv/bin/ruff check .` passed after adding `_bmad/` ownership coverage.
- `./.venv/bin/ruff format --check .` passed after adding `_bmad/` ownership coverage.
- `./.venv/bin/python -m unittest discover -q` passed with 219 tests run and 1 skipped after adding `_bmad/` ownership coverage.

### Completion Notes List

- Added public `MAINTAINERS.md` with current maintainer, responsibilities, maintainer areas, known coverage gaps, and ownership update process.
- Expanded `.github/CODEOWNERS` so major repository areas route to the current maintainer.
- Added deterministic infrastructure guardrail coverage that verifies CODEOWNERS routes major areas and that `MAINTAINERS.md` explains responsibilities, area ownership, and coverage gaps.
- Resolved review finding by adding explicit ownership coverage for all tracked top-level repository areas.
- Resolved follow-up review finding by adding explicit `_bmad/` ownership coverage.

### File List

- `.github/CODEOWNERS`
- `MAINTAINERS.md`
- `_bmad-output/implementation-artifacts/0-2-define-maintainer-ownership-and-codeowners.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `tests/test_infra/test_maintainer_ownership.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-04: Implemented maintainer ownership documentation, CODEOWNERS area routing, and infra guardrail tests.
