# Story 3.5: Context Completeness and TODO Panel

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform admin,
I want report-level context completeness and TODOs,
So that I know what data would improve future analysis.

## Acceptance Criteria

1. Given context sources are missing, stale, incomplete, or conflicting, When the report renders, Then context completeness state and TODOs are visible near the relevant findings and summary. And TODOs link to connector or documentation guidance where practical.

### Requirement Traceability

- Primary PRD requirements: Epic 3 coverage: REV-01..10, HIS-03, RSK-04..06, RSK-09..10, NFR-XAI-01..05, UX-DR1..10.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 3 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Story artifact is ignored and untracked, so normal closeout would omit the Dev Agent Record and review status [.gitignore:225]

## Dev Notes

### Epic Context

- Epic: 3. Report and Review Experience
- Epic goal: Make the report experience fast, inspectable, and honest.
- Epic coverage: REV-01..10, HIS-03, RSK-04..06, RSK-09..10, NFR-XAI-01..05, UX-DR1..10

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 3 / Story 3.5 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5.4

### Debug Log References

- Red regression check: `./.venv/bin/python -m unittest tests.test_ui.test_context_completeness_panel.ContextCompletenessPanelRenderingTests.test_context_panel_links_todos_to_guidance tests.test_ui.test_history_page.HistoryPageRenderingTests.test_history_detail_route_renders_dedicated_report_page -q` failed as expected before implementation on missing TODO guidance links and missing summary-adjacent context callout.
- Focused regression rerun: `./.venv/bin/python -m unittest tests.test_ui.test_context_completeness_panel tests.test_ui.test_history_page.HistoryPageRenderingTests.test_history_detail_route_renders_dedicated_report_page -q` passed, `Ran 8 tests`.
- Affected UI unittest suite: `./.venv/bin/python -m unittest tests.test_ui.test_context_completeness_panel tests.test_ui.test_history_page -q` passed, `Ran 49 tests`.
- Lint: `./.venv/bin/ruff check .` passed.
- Format check: `./.venv/bin/ruff format --check .` passed, `271 files already formatted`.
- Full unittest: `./.venv/bin/python -m unittest discover -q` passed, `Ran 400 tests` with `skipped=1`.
- Security scan: `./.venv/bin/bandit -r app.py api services ui tests/e2e/seeded_server.py --severity-level high --confidence-level high -q` passed with no high/high findings.
- Dependency audit: `./.venv/bin/python -m pip_audit -r requirements.txt` passed, `No known vulnerabilities found`.
- Local CI: `bash scripts/ci-local.sh` passed, including Ruff, format, pip check, Bandit, parser skill scenarios, and unittest discovery.
- Browser validation: `APP_PORT=18092 npm run test:ui-review` passed, `3 passed`.
- VoiceOver validation: not run locally per project directive that this system should not run the voiceover test.
- Review finding fix: `git ls-files --error-unmatch _bmad-output/implementation-artifacts/3-5-context-completeness-and-todo-panel.md` passed after force-adding the ignored story artifact.
- Review finding verification: `git diff --check`, `./.venv/bin/ruff format --check .`, `./.venv/bin/ruff check .`, and `./.venv/bin/python -m unittest tests.test_ui.test_context_completeness_panel tests.test_ui.test_history_page -q` all passed after resolving the reviewer finding.

### Completion Notes List

- Added summary-adjacent context completeness rendering for report review and upload/report result surfaces so missing, stale, incomplete, or low-confidence context is visible before findings.
- Added deterministic TODO guidance links for topology management, incident context, evidence model, and report schema guidance.
- Extended seeded browser-review data and Playwright assertions to cover the visible context follow-up callout and guidance links.
- Updated README report-review documentation to mention context TODOs alongside confidence and uncertainty cues.
- Resolved the code-review finding by force-adding the ignored Story 3.5 artifact so the Dev Agent Record and review status are included in closeout.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/3-5-context-completeness-and-todo-panel.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `tests/e2e/report_review.keyboard.spec.js`
- `tests/e2e/seeded_server.py`
- `tests/test_ui/test_context_completeness_panel.py`
- `tests/test_ui/test_history_page.py`
- `ui/components/context_completeness_panel.py`
- `ui/components/report_detail_page.py`
- `ui/components/upload_panel.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-19: Implemented summary-adjacent context completeness TODO panel with guidance links, regression tests, browser validation, and documentation update.
- 2026-05-19: Resolved code-review finding for ignored/untracked story artifact and verified repository state plus focused UI tests.
- 2026-05-19: Clean code-review rerun completed and story moved to done for Git Flow closeout.
