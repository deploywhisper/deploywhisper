# Story 13.8: Release Notes and Upgrade Notes

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a self-hosted operator,
I want release and upgrade notes,
So that I know what changed and what action is required.

## Acceptance Criteria

1. Given a user-visible release is prepared, When release notes are written, Then they include changes, migration notes, compatibility notes, schema changes, operational impacts, and known issues. And upgrade instructions are available where needed.

### Requirement Traceability

- Primary PRD requirements: Epic 13 coverage: DOC-01..27, NFR-DOC-01..06, DOC-related requirements across all epics.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 13 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

## Dev Notes

### Epic Context

- Epic: 13. Documentation and User Enablement
- Epic goal: Make the product self-service for users, operators, integrators, and contributors.
- Epic coverage: DOC-01..27, NFR-DOC-01..06, DOC-related requirements across all epics

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
- UI work belongs under `frontend/src/screens/` and `frontend/src/components/`, following the React SPA theme/UI primitives and approved design mockup. Validate any browser-facing change against the Compose-built FastAPI app, not Vite.
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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 13 / Story 13.8 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

_To be filled during implementation._

### Debug Log References

_To be filled during implementation._

### Completion Notes List

_To be filled during implementation._

### File List

_To be filled during implementation._

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.

## Course Correction — 2026-10-07

Status reconciled to `done` against merged delivery [PR #153](https://github.com/deploywhisper/deploywhisper/pull/153), the release acceptance mapping below, and the accepted v1.4.0 baseline in `docs/verification/v1.4.0-release.json`. This is administrative closeout of existing delivery, not a claim that a new implementation review or application test run occurred today. Historical review attempts remain intact. See `../planning-artifacts/sprint-change-proposal-2026-10-07-v1.4.0-status-reconciliation.md`.

### Release acceptance mapping

AC1 is satisfied by `docs/releases/v1.4.0.md` (changes, migration 028, compatibility, operational impact, upgrade steps and known issues), `CHANGELOG.md`, and the published release. Existing release infrastructure was reused; no new abstraction or runtime behavior was introduced. Documentation coverage is validated by the release preparation reviews and published acceptance record in `spec-v1-4-0-signed-release.md`, PR #153 and `docs/verification/v1.4.0-release.json`. This pass adds the documented registry/governance follow-ups to the repository release notes. Historical release verification: local CI 1,845 tests; tagged suite 1,844 passed plus 1 optional skip and 1,318 subtests; composed browser 17/17. These are retained historical results, not reruns in this documentation reconciliation. UI validation not applicable to this documentation-only change.

Affected artifacts: `docs/releases/v1.4.0.md`, `CHANGELOG.md`, `docs/verification/v1.4.0-release.json`, `spec-v1-4-0-signed-release.md`; review and publication evidence is retained there. The original generated placeholder Dev Agent Record above is historical; this acceptance mapping supersedes its pending content.
