# Story 1.1: Project and Workspace Records

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform admin,
I want first-class project and workspace records,
So that analysis, reports, and future context can be scoped before shared usage expands.

## Acceptance Criteria

1. Given a self-hosted DeployWhisper instance, When an admin creates projects and workspaces, Then project and workspace/environment records are represented with stable keys, display names, descriptions, and timestamps. And migrations only add the entities needed for project/workspace selection and lookup.
2. Given a duplicate, missing, or invalid project key is submitted, When project or workspace validation runs, Then the user receives an explicit error and no partial project/workspace record is created.

### Requirement Traceability

- Primary PRD requirements: Epic 1 coverage: PRJ-01..10, HIS-08, NFR-SEC-07, DOC-22.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 1 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Implement and verify acceptance criterion 2. (AC: 2)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Duplicate workspace creation can raise an uncaught database `IntegrityError` instead of the explicit duplicate-key error contract [services/project_service.py:222]
- [x] [Review][Patch] Explicit workspace list calls validate the requested project only after `ensure_default_project()` can mutate the database [services/project_service.py:251]
- [x] [Review][Patch] Workspace API routes return `400` for `project_not_found` instead of the existing project-aware `404` contract [api/routes/projects.py:65]
- [x] [Review][Patch] Workspace persistence and API expose an unused `is_default` field outside Story 1.1's represented-record scope [migrations/versions/014_add_project_workspace_records.py:29]
- [x] [Review][Patch] Brownfield migration repair can stamp revision `014` without verifying the full `project_workspaces` schema contract [models/database.py:216]
- [x] [Review][Patch] Omitted `project_key` workspace listing returns all project workspaces instead of the default project's workspaces [services/project_service.py:255]
- [x] [Review][Patch] Explicit blank workspace list project key is treated as omitted and can still create the default project [services/project_service.py:255]
- [x] [Review][Patch] Brownfield workspace schema validation does not verify required non-null column semantics before stamping revision `014` [models/database.py:177]
- [x] [Review][Patch] Brownfield init can skip a stray partial `project_workspaces` table when baseline tables are absent [models/database.py:220]
- [x] [Review][Patch] Workspace creation maps every `IntegrityError` to a duplicate workspace key error [services/project_service.py:230]
- [x] [Review][Patch] Concurrent duplicate project creation can raise uncaught database `IntegrityError` instead of the explicit duplicate project-key error contract [services/project_service.py:204]
- [x] [Review][Patch] Workspace creation can surface raw foreign-key `IntegrityError` if the project disappears between validation and insert [services/project_service.py:259]
- [x] [Review][Patch] Brownfield workspace schema validation does not verify `id` primary-key or workspace column type compatibility before stamping revision `014` [models/database.py:177]
- [x] [Review][Patch] Workspace migration file is untracked and would be omitted from commit/push unless explicitly added [migrations/versions/014_add_project_workspace_records.py]

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 1 / Story 1.1 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-05-04: Added failing service/API coverage for workspace creation, duplicate keys, invalid keys, and no partial record creation; confirmed failures before implementation.
- 2026-05-04: Added `ProjectWorkspace` persistence, migration `014_add_project_workspace_records`, repository/service helpers, API schemas/routes, CLI workspace subcommands, and project-workspaces documentation updates.
- 2026-05-04: Updated migration repair and container contract tests for the new migration head.
- 2026-05-05: Fixed code-review findings for workspace duplicate race handling, explicit lookup side effects, project-not-found API status, unused workspace default state, and brownfield schema validation.
- 2026-05-05: Fixed code-review rerun findings for default-only workspace listing, blank explicit project-key validation, non-null workspace schema validation, stray workspace-table detection, and narrowed integrity-error translation.
- 2026-05-05: Fixed remaining code-review findings for duplicate project insert races, workspace foreign-key insert races, and primary-key/type validation for brownfield workspace schemas.
- 2026-05-05: Fixed code-review rerun finding by explicitly staging the new workspace migration file for commit inclusion.

### Completion Notes List

- Project records continue to use the existing project service/repository/API path.
- Workspace/environment records are now first-class project-local rows with stable keys, display names, optional descriptions, optional environment labels, timestamps, and duplicate protection per project.
- Invalid or duplicate workspace requests fail before insertion, preserving the no-partial-record guarantee.
- Admin creation/listing is available through API and CLI; docs now list the new workspace endpoints and CLI commands.
- Code-review follow-up now translates database duplicate races into explicit workspace validation errors, keeps explicit workspace reads side-effect-free, returns `404` for unknown project-scoped workspace routes, removes unused workspace default state, and verifies the full workspace schema before brownfield revision stamping.
- Code-review rerun follow-up now scopes omitted workspace listings to the default project, treats blank explicit project keys as invalid input, rejects nullable/stray workspace schemas during brownfield startup, and only rewrites unique workspace-key integrity failures as duplicate-key validation errors.
- Remaining review follow-up now translates duplicate project insert races to the explicit project-key validation contract, maps workspace project foreign-key races to `project_not_found`, and rejects brownfield workspace tables with a missing primary key or incompatible reflected column types.
- Code-review rerun follow-up now has the `014_add_project_workspace_records` migration staged so Git closeout includes the migration required by the story.

### File List

- `api/routes/projects.py`
- `api/schemas.py`
- `cli/analyze.py`
- `docs/project-workspaces.md`
- `migrations/versions/014_add_project_workspace_records.py`
- `models/database.py`
- `models/repositories/projects.py`
- `models/tables.py`
- `services/project_service.py`
- `tests/test_api/test_projects.py`
- `tests/test_cli/test_analyze.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_services/test_project_service.py`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-04: Implemented first-class workspace records with API/CLI surfaces, migration support, docs, and regression coverage.
- 2026-05-05: Addressed code-review findings for project/workspace race handling and stricter brownfield workspace schema validation.
- 2026-05-05: Addressed code-review rerun finding by staging the workspace migration file for Git closeout.
