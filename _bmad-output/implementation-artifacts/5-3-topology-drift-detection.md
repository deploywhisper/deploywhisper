# Story 5.3: Topology drift detection

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a admin,
I want to know when topology is out of sync,
so that I can trigger a re-import.

## Acceptance Criteria

1. Scheduled drift check (configurable, default daily)
2. Alerts when >10% of resources changed since last import
3. Drift report lists added/removed/modified resources
4. Configurable via settings UI

### Requirement Traceability

- Primary PRD requirements: `CTX-02`, `CTX-07`
- Supporting PRD / NFR / differentiation requirements: `ADM-03`
- Coverage intent: `Delta`
- Story alignment note: Drift detection turns existing freshness warnings into a proactive context-management capability.

## Tasks / Subtasks

- [x] Implement AC1: Scheduled drift check (configurable, default daily) (AC: 1)
- [x] Implement AC2: Alerts when >10% of resources changed since last import (AC: 2)
- [x] Implement AC3: Drift report lists added/removed/modified resources (AC: 3)
- [x] Implement AC4: Configurable via settings UI (AC: 4)
- [x] Add or update automated verification, fixtures, docs, and rollout notes required for this story (AC: 1, 2, 3, 4)

## Dev Notes

- Epic context: Context Moat (2, 15-22 (overlaps Epics 3-4), P1).
- Epic goal: Automate topology discovery across supported infrastructure sources. Capture deployment outcomes. Build the feedback loop. This epic turns DeployWhisper from "smart on day 1" to "measurably smarter every month".
- This story contributes directly to context moat and should build on the shared topology import/source registry contract from Story 5.2 rather than implementing source-specific drift logic.
- Drift checks must work consistently for Terraform, CloudFormation, Kubernetes, Ansible, and custom topology sources as those connectors are added.
- Epic 5 is the feedback/context moat. Topology freshness, deployment outcomes, and reviewer feedback are first-class context signals that must remain auditable.
- Capture history and feedback in a way that can support later calibration and backtesting without rewriting the persistence model again.
- Outcome and feedback ingestion should be explicit and operator-visible; hidden heuristics will undermine trust.
- Preserve the project-context guardrails: shared analysis core, local-first handling of raw IaC, advisory-first outputs, and deterministic tests over flaky integration assumptions.

### Project Structure Notes

- Likely implementation surfaces: services/topology_service.py, services/report_service.py, api/routes/, models/, ui/routes/, cli/, tests/, ui/routes/settings.py.
- Keep new capabilities in the correct layer instead of duplicating logic across UI, API, CLI, integrations, or docs.
- If this story introduces a new top-level folder or runtime surface, align it with the architecture document before implementation starts.

### References

- [Epics](../planning-artifacts/epics.md)
- [PRD](../planning-artifacts/prd.md)
- [Architecture](../planning-artifacts/architecture.md)
- [Project Context](../project-context.md)

## Dev Agent Record

### Agent Model Used

GPT-5

### Implementation Plan

- Add failing regression tests for scheduled drift checks, thresholding, drift report output, and settings-driven configuration.
- Extend the shared topology service with persisted drift state and source-agnostic drift computation over the Story 5.2 import foundation.
- Wire the drift configuration and reporting into the existing settings/admin surfaces, then complete validation before moving the story to review.

### Debug Log References

- 2026-04-29T00:00:00+05:30: Loaded Story 5.3, sprint status, and project context on a clean `develop` worktree.
- 2026-04-29T00:00:00+05:30: Created branch `feature/5-3-topology-drift-detection`.
- 2026-04-29T00:00:00+05:30: `./.venv/bin/python -m unittest -q tests.test_services.test_settings_service tests.test_services.test_topology_service tests.test_ui.test_settings_page`
- 2026-04-29T00:00:00+05:30: `./.venv/bin/ruff check .`
- 2026-04-29T00:00:00+05:30: `./.venv/bin/ruff format --check .`
- 2026-04-29T00:00:00+05:30: `./.venv/bin/python -m unittest discover -q`
- 2026-04-29T00:00:00+05:30: `bash scripts/ci-local.sh`
- 2026-04-29T00:00:00+05:30: Re-ran `bmad-code-review`, fixed the two findings, and revalidated the topology drift scheduler/API surfaces.
- 2026-04-29T00:00:00+05:30: Re-ran `bmad-code-review` after the scheduler/API fixes; no findings remained.

### Completion Notes List

- Added persisted topology drift cadence settings with a default daily interval and shared service helpers for reading and saving the configured schedule.
- Extended the shared topology service with drift status models, resource-level drift comparison, >10% alerting, cached per-project drift snapshots, and due-check execution layered on top of the Story 5.2 import source metadata.
- Exposed the latest topology drift summary and drift cadence selector in the settings page so operators can review scheduled checks and adjust the cadence without leaving the existing topology context workflow.
- Fixed the Story 5.3 review findings by adding a real startup scheduler loop that runs due drift passes in the background, exposing drift payloads through the project context API, and listing added/removed/modified resource names in the settings UI.
- Added deterministic regression coverage for drift interval settings, due scheduled checks, resource-level added/removed/modified drift reports, threshold alerting, manual-topology unavailability, and settings-page visibility.
- Updated workspace docs to describe the per-project topology drift cadence and alert posture.
- Validation passed for the focused drift suites, repo-wide Ruff check/format check, full `unittest discover -q`, and `scripts/ci-local.sh`. Local CI still skipped Bandit because it is not installed in this environment.

### File List

- _bmad-output/implementation-artifacts/5-3-topology-drift-detection.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- api/schemas.py
- app.py
- docs/project-workspaces.md
- services/settings_service.py
- services/topology_service.py
- tests/test_api/test_context.py
- tests/test_services/test_settings_service.py
- tests/test_services/test_topology_service.py
- tests/test_ui/test_settings_page.py
- ui/routes/settings.py

## Change Log

- 2026-04-29: Implemented scheduled topology drift detection with persisted cadence settings, resource-level drift reports, threshold alerts, settings-page controls, and regression coverage.
- 2026-04-29: Fixed Story 5.3 review findings by adding a real background scheduler pass and surfacing drift resource lists through API and settings UI.
