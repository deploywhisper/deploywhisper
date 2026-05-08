# Story 1.6: Project Model Documentation

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a user deploying DeployWhisper,
I want project modeling guidance,
So that I can map monorepos, multi-repos, Terraform workspaces, Kubernetes clusters, and platform teams correctly.

## Acceptance Criteria

1. Given users read project model docs, When they compare deployment patterns, Then the docs explain recommended project/workspace mappings for common infrastructure setups. And examples remain self-hosted and do not assume a SaaS control plane.

### Requirement Traceability

- Primary PRD requirements: Epic 1 coverage: PRJ-01..10, HIS-08, NFR-SEC-07, DOC-22.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 1 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Use the canonical DOC-22 project model path from planning artifacts [`docs/concepts/project-model.md:1`]
- [x] [Review][Patch] Ensure docs regression tests are discovered by `python -m unittest discover -q` [`tests/test_docs/__init__.py:1`]
- [x] [Review][Patch] Resolve cwd-sensitive docs test pathing [`tests/test_docs/test_project_model_documentation.py:9`]
- [x] [Review][Patch] Strengthen regression coverage for actual mapping guidance and self-hosted/no-SaaS posture [`tests/test_docs/test_project_model_documentation.py:16`]
- [x] [Review][Patch] Cover the new README and workspace documentation links [`tests/test_docs/test_project_model_documentation.py:62`]
- [x] [Review][Patch] Document the GitHub project-key override needed for shared multi-repo project mapping [`docs/concepts/project-model.md:30`]
- [x] [Review][Patch] Document that invalid `DEPLOYWHISPER_GITHUB_PROJECT_KEY` values fail instead of falling back to repo-derived keys [`docs/concepts/project-model.md:58`]
- [x] [Review][Patch] Validate recommended-mappings table structure and columns in docs regression tests [`tests/test_docs/test_project_model_documentation.py:73`]
- [x] [Review][Patch] Make link regression tests assert the intended README/workspace entry points, not only repeated href presence [`tests/test_docs/test_project_model_documentation.py:59`]
- [x] [Review][Patch] Cover the README Project Workspaces link added by this story [`README.md:508`]
- [x] [Review][Patch] Make invalid GitHub override docs assertion meaning-sensitive instead of newline-sensitive [`tests/test_docs/test_project_model_documentation.py:58`]
- [x] [Review][Patch] Make recommended-mappings table parsing tolerant of harmless Markdown separator/header formatting [`tests/test_docs/test_project_model_documentation.py:91`]
- [x] [Review][Patch] Align Project Workspaces GitHub override docs with fail-fast invalid override behavior [`docs/project-workspaces.md:45`]
- [x] [Review][Patch] Update README documentation index to the current 2026-05-01 implementation readiness report [`README.md:506`]
- [x] [Review][Patch] Relax project-model docs table regression parsing so valid formatting and additional rows do not fail CI [`tests/test_docs/test_project_model_documentation.py:124`]

## Dev Notes

### Epic Context

- Epic: 1. Project, Workspace, and RBAC Foundation
- Epic goal: Make DeployWhisper project-aware before reports, incidents, topology, scanner imports, and feedback become harder to migrate.
- Epic coverage: PRJ-01..10, HIS-08, NFR-SEC-07, DOC-22

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 1 / Story 1.6 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-05-07: Started implementation on `feature/1-6-project-model-documentation`; sprint status moved to in-progress.
- 2026-05-07: Red phase confirmed `./.venv/bin/python -m unittest tests.test_docs.test_project_model_documentation -q` failed because the project model guide was missing.
- 2026-05-07: Green phase passed `./.venv/bin/python -m unittest tests.test_docs.test_project_model_documentation -q`.
- 2026-05-07: Validation passed `./.venv/bin/ruff check .`.
- 2026-05-07: Validation passed `./.venv/bin/ruff format --check .`.
- 2026-05-07: Validation passed `./.venv/bin/python -m unittest discover -q` with 289 tests run and 1 skipped.
- 2026-05-07: Fixed all Story 1.6 review findings: moved guide to canonical DOC-22 path, added GitHub multi-repo override guidance, and strengthened docs tests.
- 2026-05-07: Review-fix validation passed `./.venv/bin/python -m unittest tests.test_docs.test_project_model_documentation -q` with 2 tests run.
- 2026-05-07: Review-fix validation passed `./.venv/bin/ruff check .`.
- 2026-05-07: Review-fix validation passed `./.venv/bin/ruff format --check .`.
- 2026-05-07: Review-fix validation passed `./.venv/bin/python -m unittest discover -q` with 291 tests run and 1 skipped.
- 2026-05-07: Fixed re-review findings: documented invalid GitHub override failure behavior, parsed recommended-mapping table structure in tests, and asserted exact documentation entry-point links.
- 2026-05-07: Re-review fix validation passed `./.venv/bin/python -m unittest tests.test_docs.test_project_model_documentation -q` with 2 tests run.
- 2026-05-07: Re-review fix validation passed `./.venv/bin/ruff check .`.
- 2026-05-07: Re-review fix validation passed `./.venv/bin/ruff format --check .`.
- 2026-05-07: Re-review fix validation passed `./.venv/bin/python -m unittest discover -q` with 291 tests run and 1 skipped.
- 2026-05-07: Fixed latest re-review findings: README Project Workspaces link coverage, whitespace-normalized invalid GitHub override assertion, and tolerant recommended-mapping table parsing.
- 2026-05-07: Latest re-review fix validation passed `./.venv/bin/python -m unittest tests.test_docs.test_project_model_documentation -q` with 2 tests run.
- 2026-05-07: Latest re-review fix validation passed `./.venv/bin/ruff check .`.
- 2026-05-07: Latest re-review fix validation passed `./.venv/bin/ruff format --check .`.
- 2026-05-07: Latest re-review fix validation passed `./.venv/bin/python -m unittest discover -q` with 291 tests run and 1 skipped.
- 2026-05-07: Final Story 1.6 closeout review found no accepted findings; story status moved to done.
- 2026-05-07: Fixed follow-up re-review findings for Project Workspaces GitHub override docs, README readiness link, and tolerant docs table regression parsing.
- 2026-05-07: Follow-up finding validation passed `./.venv/bin/python -m unittest tests.test_docs.test_project_model_documentation -q` with 2 tests run.
- 2026-05-07: Follow-up finding validation passed `./.venv/bin/ruff check .`.
- 2026-05-07: Follow-up finding validation passed `./.venv/bin/ruff format --check .`.
- 2026-05-07: Follow-up finding validation passed `./.venv/bin/python -m unittest discover -q` with 292 tests run and 1 skipped.
- 2026-05-07: Follow-up finding validation passed `bash scripts/ci-local.sh`; Bandit was not installed, so the script skipped the local Bandit scan.

### Completion Notes List

- Added a project modeling guide covering common self-hosted setup patterns and recommended project/workspace mappings.
- Linked the guide from project workspace documentation and the README documentation index.
- Added deterministic docs regression coverage for the required guide sections and self-hosted pattern language.
- Resolved review findings by using the canonical DOC-22 docs path, documenting GitHub multi-repo override behavior, and ensuring docs regression tests run under standard discovery.
- Resolved re-review findings by documenting invalid GitHub override behavior and tightening docs tests for table structure plus intended entry-point links.
- Resolved latest re-review findings by asserting the README workspace entry point, making invalid override coverage meaning-based, and allowing harmless Markdown table formatting changes.
- Completed closeout after final review triage left no accepted findings.
- Resolved follow-up re-review findings by aligning the Project Workspaces GitHub override note with fail-fast runtime behavior, updating the README readiness report link, and relaxing docs table parsing while preserving required mapping coverage.

### File List

- `README.md`
- `docs/concepts/project-model.md`
- `docs/project-workspaces.md`
- `tests/test_docs/__init__.py`
- `tests/test_docs/test_project_model_documentation.py`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/1-6-project-model-documentation.md`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-07: Implemented project modeling documentation and verification coverage; story moved to review.
- 2026-05-07: Fixed Story 1.6 code-review findings and revalidated.
- 2026-05-07: Fixed Story 1.6 re-review findings and revalidated.
- 2026-05-07: Fixed latest Story 1.6 re-review findings and revalidated focused docs checks, lint, formatting, and full unittest discovery.
- 2026-05-07: Closed Story 1.6 after final review triage accepted no findings.
