# Story 3.1: Verdict-First Report Header

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a reviewer,
I want the verdict, Evidence Law status, confidence, and top risk visible immediately,
So that I can orient quickly before drilling into detail.

## Acceptance Criteria

1. Given an analysis report is displayed, When the result page loads, Then verdict, advisory posture, Evidence Law status, confidence, top risk, and next action are visible above the fold. And the copy avoids implying automatic approval or blocking.

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

- [x] [Review][Patch] Compute Evidence Law status from linked deterministic evidence, not only finding booleans [ui/formatters/report_header.py:32]

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 3 / Story 3.1 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5.4

### Debug Log References

- Created feature branch `feature/3-1-verdict-first-report-header` from `develop`.
- Red-phase focused UI route test initially failed because the report detail header did not explicitly render the verdict-first signals by name.
- Implemented shared report header signal helpers and rendered them in both saved report detail headers and the dashboard verdict card.
- Red-phase review-finding tests failed for severe reports without linked deterministic evidence, then passed after Evidence Law status was derived from linked evidence items.

### Completion Notes List

- Added verdict-first header signals for verdict, advisory posture, Evidence Law status, confidence, top risk, and next action above the detailed report sections.
- Kept copy advisory-first: the UI states that the verdict is not an approval or automatic block and frames the next action as a human review step.
- Added deterministic formatter coverage for Evidence Law status and next-action copy, route rendering coverage for saved report detail, and Playwright coverage for the dashboard verdict card.
- Fixed the review finding by requiring severe findings to reference deterministic evidence items before the header reports Evidence Law as satisfied, and by flagging severe reports without visible severe findings for review.
- No separate documentation update was required; the story changed user-visible report copy only, and the copy is covered by UI tests.
- Validation results:
  - `./.venv/bin/python -m unittest tests.test_ui.test_history_page.HistoryPageRenderingTests.test_history_detail_route_renders_verdict_first_header -q` - red-phase failed before implementation, then passed after implementation.
  - `./.venv/bin/python -m unittest tests.test_ui.test_verdict_card tests.test_ui.test_history_page.HistoryPageRenderingTests.test_history_detail_route_renders_verdict_first_header -q` - passed, 5 tests.
  - `./.venv/bin/python -m unittest tests.test_ui.test_verdict_card -q` - red-phase failed for the review finding before the fix, then passed after the fix.
  - `./.venv/bin/python -m unittest tests.test_ui.test_verdict_card tests.test_ui.test_history_page.HistoryPageRenderingTests.test_history_detail_route_renders_verdict_first_header -q` - passed, 7 tests.
  - `APP_PORT=18080 npm run test:ui-review` - passed, 1 Playwright test.
  - `./.venv/bin/ruff check .` - passed.
  - `./.venv/bin/ruff format --check .` - passed after formatting `ui/formatters/report_header.py`.
  - `git diff --check` - passed.
  - `./.venv/bin/python -m pip check` - passed, no broken requirements.
  - `./.venv/bin/bandit -r api/ analysis/ services/ parsers/ llm/ models/ cli/ ui/ evidence/ --severity-level high --confidence-level high -x tests/` - passed, no high issues.
  - `./.venv/bin/python -m unittest discover -q` - passed, 354 tests, 1 skipped.

### File List

- `_bmad-output/implementation-artifacts/3-1-verdict-first-report-header.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `tests/e2e/report_review.keyboard.spec.js`
- `tests/test_ui/test_history_page.py`
- `tests/test_ui/test_verdict_card.py`
- `ui/components/report_detail_page.py`
- `ui/components/verdict_card.py`
- `ui/formatters/report_header.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-13: Implemented verdict-first report header signals and moved story to review.
- 2026-05-13: Code review found one Evidence Law status patch item; story moved back to in-progress.
- 2026-05-13: Fixed Evidence Law linked-evidence review finding and moved story back to review.
- 2026-05-13: Re-ran BMad code review cleanly and marked story done.
