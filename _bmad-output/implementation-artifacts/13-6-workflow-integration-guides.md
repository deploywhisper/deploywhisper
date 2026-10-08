# Story 13.6: Workflow Integration Guides

Status: ready-for-dev

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform admin,
I want setup guides for workflow integrations,
So that I can configure GitHub, GitLab, future Jenkins/Atlantis/GitOps/chat, and local workflow delivery safely.

## Acceptance Criteria

1. Given a supported workflow integration exists, When users read its guide, Then setup, permissions, secrets, troubleshooting, limitations, report schema behavior, and advisory/enforcement boundaries are documented. And UI/CLI/API surfaces link to docs where practical.

### Requirement Traceability

- Primary PRD requirements: Epic 13 coverage: DOC-01..27, NFR-DOC-01..06, DOC-related requirements across all epics.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 13 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [ ] Implement and verify acceptance criterion 1. (AC: 1)
- [ ] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [ ] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [ ] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [ ] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 13 / Story 13.6 definition.
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

## Release Baseline Reconciliation — 2026-10-07

Status remains `ready-for-dev`. Existing baseline credit: Action/App/self-hosted and enforcement integration guides exist. Remaining acceptance: Audit all story-required workflow coverage, links and contracts; preserve the external Action runtime boundary. No incomplete task is marked complete by release publication. See `../planning-artifacts/sprint-change-proposal-2026-10-07-v1.4.0-status-reconciliation.md`. UI validation is required only if subsequent implementation touches a browser surface; this reconciliation is documentation-only.
