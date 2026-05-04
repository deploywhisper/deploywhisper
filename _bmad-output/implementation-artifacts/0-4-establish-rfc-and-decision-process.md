# Story 0.4: Establish RFC and Decision Process

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a maintainer,
I want major design decisions to use a public RFC process,
So that architecture, roadmap, and governance changes remain auditable.

## Acceptance Criteria

1. Given a change affects architecture, governance, security, or roadmap scope, When maintainers propose it, Then the RFC process defines required sections, review expectations, and decision recording. And accepted decisions link back to relevant PRD or architecture sections.

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 0 / Story 0.4 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5

### Debug Log References

- `./.venv/bin/python -m unittest tests.test_infra.test_rfc_decision_process.RfcDecisionProcessTests.test_rfc_process_and_template_exist -v` failed before implementation because `docs/rfcs/README.md` and `docs/rfcs/0000-template.md` were missing.
- `./.venv/bin/python -m unittest tests.test_infra.test_rfc_decision_process.RfcDecisionProcessTests -q` passed after adding the RFC process, template, and governance link.
- `./.venv/bin/python -m unittest tests.test_infra.test_governance_files -q` passed after updating `GOVERNANCE.md`.
- `./.venv/bin/ruff check .` passed.
- `./.venv/bin/ruff format --check .` passed.
- `./.venv/bin/python -m unittest discover -q` passed with 225 tests run and 1 skipped.
- `bash scripts/ci-local.sh` passed; local Bandit scan was skipped because Bandit is not installed in the environment.
- `bmad-code-review` found 0 decision-needed, 0 patch, and 0 deferred findings.
- `./.venv/bin/python -m unittest tests.test_infra.test_rfc_decision_process.RfcDecisionProcessTests -q` passed during code review.
- `./.venv/bin/python -m unittest tests.test_infra.test_governance_files -q` passed during code review.

### Completion Notes List

- Added a public RFC process under `docs/rfcs/README.md` defining when major architecture, governance, security, and roadmap changes require an RFC.
- Added `docs/rfcs/0000-template.md` with required sections for summary, motivation, PRD and architecture links, design, security/privacy, compatibility, alternatives, review plan, and decision record.
- Updated `GOVERNANCE.md` to point major decisions to the published RFC process and require accepted RFCs to link back to PRD or architecture sections.
- Added deterministic infrastructure guardrails that verify the RFC process, template, review expectations, decision states, and governance cross-link remain present.
- Code review completed cleanly with no new findings.

### File List

- `GOVERNANCE.md`
- `_bmad-output/implementation-artifacts/0-4-establish-rfc-and-decision-process.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `docs/rfcs/0000-template.md`
- `docs/rfcs/README.md`
- `tests/test_infra/test_rfc_decision_process.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-04: Implemented the public RFC process, RFC template, governance cross-link, and deterministic RFC guardrail tests.
