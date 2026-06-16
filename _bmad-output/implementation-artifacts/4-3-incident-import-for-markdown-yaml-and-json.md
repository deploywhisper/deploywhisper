# Story 4.3: Incident Import for Markdown, YAML, and JSON

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform admin,
I want to import incident records from simple files,
So that organization memory can be added without integrating a ticketing system first.

## Acceptance Criteria

1. Given markdown, YAML, or JSON incident files are provided, When import runs, Then incident metadata, root cause, trigger change, affected services, rollback path, and prevention notes are stored under the correct project. And invalid records produce actionable errors.
2. Given an imported incident is missing required scope, source, or redaction metadata, When validation runs, Then the record is rejected with field-level errors. And no partial incident index entry is created.

### Requirement Traceability

- Primary PRD requirements: Epic 4 coverage: INC-01..12, CTX-03..04, HIS-05..07, HIS-09, ADM-04, RSK-12, DOC-23.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 4 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Implement and verify acceptance criterion 2. (AC: 2)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Invalid project/workspace scope errors escape the field-level validation contract [services/incident_import_service.py:116] — AC2 requires missing or invalid scope metadata to be rejected with field-level errors and no partial incident entry. The importer only converts a missing project into `IncidentImportValidationError`; unknown/conflicting `project_id`, `project_key`, `workspace_id`, or `workspace_key` currently raise raw `ProjectResolutionError` from `resolve_project_reference` / `ingest_incident_document` after record validation.
- [x] [Review][Patch] String redaction booleans are persisted with the wrong value [services/incident_import_service.py:297] — AC1 requires redaction metadata to be stored accurately. `bool(contains_sensitive_data)` turns any non-empty string, including `"false"`, into `True`, corrupting imported redaction metadata when operators quote YAML values or provide string JSON values.
- [x] [Review][Patch] Required list fields can import malformed data instead of actionable field errors [services/incident_import_service.py:260] — AC1 requires affected services and prevention notes to be stored, and invalid records to produce actionable errors. `prevention_notes` accepts any non-empty dict and then stores no notes, while list values such as `null` are stringified into `"None"` rather than rejected as invalid service/note values.

## Dev Notes

### Epic Context

- Epic: 4. Day-Zero Risk Patterns and Incident Memory
- Epic goal: Give new installs useful memory immediately and grow organization-specific learning over time.
- Epic coverage: INC-01..12, CTX-03..04, HIS-05..07, HIS-09, ADM-04, RSK-12, DOC-23

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 4 / Story 4.3 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- RED: `./.venv/bin/python -m unittest tests.test_services.test_incident_import_service -q` failed before implementation with `ModuleNotFoundError: No module named 'services.incident_import_service'`.
- GREEN: `./.venv/bin/python -m unittest tests.test_services.test_incident_import_service -q` passed 3 tests.
- Formatting: `./.venv/bin/ruff format tests/test_services/test_incident_import_service.py` reformatted the new focused test file.
- Lint: `./.venv/bin/ruff check .` passed.
- Format check: `./.venv/bin/ruff format --check .` passed.
- Static security check: `./.venv/bin/bandit -r services/ -x tests/ --severity-level high --confidence-level high` passed with no high-severity findings.
- Full regression: `./.venv/bin/python -m unittest discover -q` passed 414 tests with 1 skipped.
- Whitespace check: `git diff --check` passed.
- UI validation not applicable; this story added a service-layer import path and documentation without changing UI routes, retired Python UI components, browser interaction, keyboard behavior, or accessibility semantics.
- Review fix focused regression: `./.venv/bin/python -m unittest tests.test_services.test_incident_import_service -q` passed 5 tests.
- Review fix lint: `./.venv/bin/ruff check .` passed.
- Review fix format check: `./.venv/bin/ruff format --check .` passed.
- Review fix static security check: `./.venv/bin/bandit -r services/ -x tests/ --severity-level high --confidence-level high` passed with no high-severity findings.
- Review fix full regression: `./.venv/bin/python -m unittest discover -q` passed 414 tests with 1 skipped.
- Review fix whitespace check: `git diff --check` passed.
- Re-review focused regression: `./.venv/bin/python -m unittest tests.test_services.test_incident_import_service -q` passed 5 tests.
- Re-review lint: `./.venv/bin/ruff check .` passed.
- Re-review format check: `./.venv/bin/ruff format --check .` passed.
- Re-review whitespace check: `git diff --check` passed.

### Completion Notes List

- Added a project-scoped incident import service for Markdown, YAML, and JSON files.
- Normalized imported incident data into the existing incident record storage path so metadata, root cause, trigger change, affected services, rollback path, prevention notes, source metadata, and redaction metadata are persisted as incident content under the correct project.
- Added batch validation with source-file and field-level errors; invalid batches are rejected before any incident records are persisted.
- Documented the import contract and required fields for operators and future surfaces.
- Fixed code-review findings by converting invalid project/workspace scope into import field errors before persistence, preserving string redaction booleans accurately, and rejecting malformed service/note collections without coercion.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/4-3-incident-import-for-markdown-yaml-and-json.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `docs/incident-import.md`
- `services/incident_import_service.py`
- `tests/test_services/test_incident_import_service.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-21: Implemented incident file import for Markdown, YAML, and JSON with validation and docs.
- 2026-05-21: Resolved Story 4.3 code-review findings and reran focused plus full validation.
- 2026-05-21: Re-ran code review; no remaining findings; moved story to done.
