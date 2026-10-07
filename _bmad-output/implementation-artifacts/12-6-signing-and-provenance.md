# Story 12.6: Signing and Provenance

Status: in-progress

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a DeployWhisper user,
I want release artifacts signed with provenance or attestations where practical,
So that I can verify artifact origin before self-hosted deployment.

## Acceptance Criteria

1. Given release signing or provenance is enabled, When artifacts are published, Then signatures, provenance or attestations, verification commands, and known limitations are documented. And unsigned or unverifiable artifacts are explicitly labeled.

### Requirement Traceability

- Primary PRD requirements: Epic 12 coverage: ADM-01..02, NFR-SEC-01..07, NFR-OPS-01..06, GOV-06..07, DOC-11, DOC-12.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 12 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [ ] Implement and verify acceptance criterion 1. (AC: 1)
- [ ] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [ ] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [ ] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [ ] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

## Dev Notes

### Epic Context

- Epic: 12. Security and Supply Chain Hardening
- Epic goal: Make the project trustworthy to install, operate, and contribute to.
- Epic coverage: ADM-01..02, NFR-SEC-01..07, NFR-OPS-01..06, GOV-06..07, DOC-11, DOC-12

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 12 / Story 12.6 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

Codex; signed-release workflow implementation and independent read-only review.

### Debug Log References

Signing implementation tracked by `spec-gh-131-review-and-signed-releases.md`; actual release publication and reviewer policy require the pending user decisions.

### Completion Notes List

- Started user-requested real source/image provenance, strict verification and safe release delivery. Existing releases have no uploaded assets and are not retroactively altered.
- Hosted signed preview will establish cryptographic evidence before choosing a new public version. Story remains in-progress until published delivery is verified.

### File List

- `.github/workflows/release.yml`
- `.github/workflows/release-artifacts.yml`
- `scripts/release_artifacts.py`
- `scripts/release_policy.py`
- `Dockerfile`
- `tests/test_infra/test_release_artifacts.py`
- `tests/test_infra/test_release_workflow.py`
- `docs/security/release-artifacts.md`
- `docs/security/release-integrity.md`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-10-07: Began real artifact signing/provenance and safe release-pipeline implementation under the user-requested Scorecard remediation.
