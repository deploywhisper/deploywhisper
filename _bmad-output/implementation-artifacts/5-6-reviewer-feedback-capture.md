# Story 5.6: Reviewer feedback capture

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a reviewer,
I want to rate findings as useful/false-positive/missed,
so that the product learns from my expertise.

## Acceptance Criteria

1. Thumbs up/down on each finding in the UI
2. False positive flag with optional reason
3. False negative note for missed findings
4. Feedback stored in FeedbackEvent table
5. Feedback summary visible to admins

### Requirement Traceability

- Primary PRD requirements: `HIS-05`
- Supporting PRD / NFR / differentiation requirements: `DIF-05`
- Coverage intent: `Delta`
- Story alignment note: Reviewer feedback is the first explicit learning-loop feature and should be stored in an auditable form.

## Tasks / Subtasks

- [x] Implement AC1: Thumbs up/down on each finding in the UI (AC: 1)
- [x] Implement AC2: False positive flag with optional reason (AC: 2)
- [x] Implement AC3: False negative note for missed findings (AC: 3)
- [x] Implement AC4: Feedback stored in FeedbackEvent table (AC: 4)
- [x] Implement AC5: Feedback summary visible to admins (AC: 5)
- [x] Add or update automated verification, fixtures, docs, and rollout notes required for this story (AC: 1, 2, 3, 4, 5)

## Dev Notes

- Epic context: Context Moat (2, 15-22 (overlaps Epics 3-4), P1).
- Epic goal: Automate topology discovery across supported infrastructure sources. Capture deployment outcomes. Build the feedback loop. This epic turns DeployWhisper from "smart on day 1" to "measurably smarter every month".
- This story starts the human-in-the-loop learning loop; the feedback model should support later calibration work directly.
- Epic 5 is the feedback/context moat. Topology freshness, deployment outcomes, and reviewer feedback are first-class context signals that must remain auditable.
- Capture history and feedback in a way that can support later calibration and backtesting without rewriting the persistence model again.
- Outcome and feedback ingestion should be explicit and operator-visible; hidden heuristics will undermine trust.
- Preserve the project-context guardrails: shared analysis core, local-first handling of raw IaC, advisory-first outputs, and deterministic tests over flaky integration assumptions.

### Project Structure Notes

- Likely implementation surfaces: services/topology_service.py, services/report_service.py, api/routes/, models/, ui/routes/, cli/, tests/, ui/components/.
- Keep new capabilities in the correct layer instead of duplicating logic across UI, API, CLI, integrations, or docs.
- If this story introduces a new top-level folder or runtime surface, align it with the architecture document before implementation starts.

### References

- [Epics](../planning-artifacts/epics.md)
- [PRD](../planning-artifacts/prd.md)
- [Architecture](../planning-artifacts/architecture.md)
- [Project Context](../project-context.md)

## Dev Agent Record

### Agent Model Used

GPT-5 (Codex)

### Debug Log References

- `./.venv/bin/python -m unittest -q tests.test_services.test_feedback_service tests.test_infra.test_migrations tests.test_infra.test_container_contract tests.test_ui.test_history_page tests.test_ui.test_settings_page`
- `./.venv/bin/python -m unittest -q tests.test_ui.test_history_page tests.test_ui.test_settings_page tests.test_ui.test_app_shell tests.test_services.test_feedback_service`
- `./.venv/bin/ruff check .`
- `./.venv/bin/ruff format --check .`
- `./.venv/bin/python -m unittest discover -q`
- `bash scripts/ci-local.sh`

### Completion Notes List

- Added migration `012_add_feedback_event_fields` so reviewer feedback can persist `finding_id` and `false_positive_reason` in the existing `feedback_events` table.
- Added shared reviewer-feedback persistence and summary helpers in `services/feedback_service.py` and `models/repositories/feedback_events.py`, including report/finding validation and project-scoped summary aggregation.
- Added reviewer feedback controls to the full history report detail page and the active dashboard review surface, covering thumbs up/down, false-positive reason capture, and missed-finding notes.
- Added an admin-facing reviewer feedback summary card to the settings page for the active project.
- Added rollout documentation in `docs/reviewer-feedback.md` and expanded migration/UI/service regression coverage for the new learning-loop path.
- Validation passed with repo-wide Ruff checks, focused feedback/migration/UI suites, full `unittest discover -q`, and `bash scripts/ci-local.sh`. Local CI still skipped Bandit because it is not installed in this environment.

### File List

- `_bmad-output/implementation-artifacts/5-6-reviewer-feedback-capture.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `docs/reviewer-feedback.md`
- `migrations/versions/012_add_feedback_event_fields.py`
- `models/database.py`
- `models/repositories/feedback_events.py`
- `models/tables.py`
- `services/feedback_service.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_services/test_feedback_service.py`
- `tests/test_ui/test_app_shell.py`
- `tests/test_ui/test_history_page.py`
- `tests/test_ui/test_settings_page.py`
- `ui/components/report_detail_page.py`
- `ui/components/upload_panel.py`
- `ui/routes/history.py`
- `ui/routes/settings.py`

### Change Log

- 2026-04-30: Implemented Story 5.6 reviewer feedback capture across migration, shared service, history/dashboard reviewer UI, admin summary, tests, and rollout documentation.
