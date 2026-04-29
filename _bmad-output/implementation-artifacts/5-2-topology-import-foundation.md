# Story 5.2: Topology import foundation and source registry

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an admin,
I want one topology import framework for supported source types,
so that Terraform, CloudFormation, Kubernetes, Ansible, and future connectors can enrich blast-radius context consistently.

## Acceptance Criteria

1. CLI: `deploywhisper topology import --from <source> --source <uri-or-path>` routes through a shared source registry.
2. Supported source identifiers include `terraform`, `cloudformation`, `kubernetes`, `ansible`, and `custom`.
3. Import result records accepted, skipped, partially parsed, and unsupported resources without storing raw source artifacts.
4. Builds or updates the service topology graph through one normalized topology-change contract.
5. Re-import reports topology diff consistently across source types.
6. Unsupported source types or resources produce explicit warnings instead of failing the whole import.

### Requirement Traceability

- Primary PRD requirements: `CTX-07`, `ADM-03`
- Supporting PRD / NFR / differentiation requirements: `CTX-01`, `CTX-02`, `HIS-08`, `NFR-SEC-01`, `NFR-SEC-03`
- Coverage intent: `Delta`
- Story alignment note: Establish the shared topology import boundary after project/workspace scoping so Terraform, CloudFormation, Kubernetes, Ansible, and custom sources do not duplicate graph, diff, warning, or local-first behavior and all imported context lands in the correct project.

## Tasks / Subtasks

- [x] Implement AC1: shared `deploywhisper topology import --from <source> --source <uri-or-path>` CLI routing (AC: 1)
- [x] Implement AC2: topology source registry with `terraform`, `cloudformation`, `kubernetes`, `ansible`, and `custom` identifiers (AC: 2)
- [x] Implement AC3: import result model for accepted, skipped, partially parsed, and unsupported resources without raw source persistence (AC: 3)
- [x] Implement AC4: normalized topology-change contract consumed by the service topology graph update path (AC: 4)
- [x] Implement AC5: source-agnostic re-import diff behavior (AC: 5)
- [x] Implement AC6: explicit unsupported source/resource warnings that do not fail the whole import (AC: 6)
- [x] Ensure topology imports are project-scoped and cannot bypass the project/workspace boundary introduced in Story 5.1 (AC: 1, 3, 4, 5, 6)
- [x] Add or update automated verification, fixtures, docs, and rollout notes required for this story (AC: 1, 2, 3, 4, 5, 6)

## Dev Notes

- Epic context: Context Moat (2, 15-22 (overlaps Epics 3-4), P1).
- Epic goal: Add lightweight project/workspace isolation, automate topology discovery across supported infrastructure sources, capture deployment outcomes, and build the feedback loop. This epic turns DeployWhisper from "smart on day 1" to "measurably smarter every month" without expanding into enterprise auth or multi-tenant scope.
- Story 5.1 is the prerequisite. Keep project/workspace scoping, project selection, and repository-derived project defaults out of this story except where the topology pipeline must consume the existing project boundary correctly.
- This story is the foundation for the corrected Epic 5 topology scope. Keep source-specific parsing in later connector stories; this story should define the shared registry, normalized import result, topology-change contract, diff behavior, and warnings.
- Epic 5 is the feedback/context moat. Topology freshness, deployment outcomes, and reviewer feedback are first-class context signals that must remain auditable.
- Capture history and feedback in a way that can support later calibration and backtesting without rewriting the persistence model again.
- Outcome and feedback ingestion should be explicit and operator-visible; hidden heuristics will undermine trust.
- Preserve the project-context guardrails: shared analysis core, local-first handling of raw IaC, advisory-first outputs, and deterministic tests over flaky integration assumptions.

### Project Structure Notes

- Likely implementation surfaces: services/topology_service.py, services/report_service.py, api/routes/, models/, ui/routes/, cli/, parsers/, tests/.
- Keep new capabilities in the correct layer instead of duplicating logic across UI, API, CLI, integrations, or docs.
- If this story introduces a new top-level folder or runtime surface, align it with the architecture document before implementation starts.

### References

- [Epics](../planning-artifacts/epics.md)
- [PRD](../planning-artifacts/prd.md)
- [Architecture](../planning-artifacts/architecture.md)
- [Project Context](../project-context.md)
- [Sprint Change Proposal](../planning-artifacts/sprint-change-proposal-2026-04-27-epic-5-project-workspace-foundation.md)

## Dev Agent Record

### Agent Model Used

GPT-5

### Implementation Plan

- Add failing CLI and service regression tests for source-aware topology import, normalized import results, diff reporting, unsupported-source warnings, and project scoping.
- Refactor topology persistence behind a shared import registry and topology-change contract so CLI imports and manual uploads use the same graph update path.
- Update operator docs and complete validation before moving the story to review.

### Debug Log References

- 2026-04-29T00:00:00+05:30: Loaded BMad workflow, project context, story context, sprint status, and existing topology CLI/service/tests.
- 2026-04-29T00:00:00+05:30: Created branch `feature/5-2-topology-import-foundation`.
- 2026-04-29T00:00:00+05:30: `./.venv/bin/python -m unittest -q tests.test_services.test_topology_service tests.test_cli.test_analyze`
- 2026-04-29T00:00:00+05:30: `./.venv/bin/ruff check .`
- 2026-04-29T00:00:00+05:30: `./.venv/bin/ruff format --check .`
- 2026-04-29T00:00:00+05:30: `./.venv/bin/python -m unittest discover -q`
- 2026-04-29T00:00:00+05:30: `bash scripts/ci-local.sh`
- 2026-04-29T00:00:00+05:30: Re-ran `bmad-code-review` after the reviewer fixes; no findings remained.

### Completion Notes List

- Added a shared topology source registry and normalized import contract in `services/topology_service.py`, including `custom`, `terraform`, `cloudformation`, `kubernetes`, and `ansible` identifiers plus warning-only handling for unsupported sources and resources.
- Reworked CLI topology import to use `deploywhisper topology import --from <source> --source <uri-or-path>`, return structured import results, and preserve project/workspace scoping through the Story 5.1 boundary.
- Persisted topology imports as normalized graph metadata without raw source artifacts, added source-agnostic topology diff reporting, and kept manual settings uploads on the same graph update path.
- Fixed the Story 5.2 review findings by restoring strict validation on the legacy manual topology upload/API path and keeping the default-project legacy topology mirror free of the new import metadata envelope.
- Updated regression coverage for CLI, topology service, and context API behavior, including no-op imports for unimplemented connectors, legacy-mirror compatibility, and rejection of invalid manual topology relationships.
- Updated workspace/operator docs to describe the new import command and the local-first, warning-based import posture.
- Validation passed for focused topology tests, repo-wide Ruff check/format check, full `unittest discover -q`, and `scripts/ci-local.sh`. Local CI still skipped Bandit because it is not installed in this environment.

### File List

- README.md
- _bmad-output/implementation-artifacts/5-2-topology-import-foundation.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- cli/analyze.py
- docs/project-workspaces.md
- services/topology_service.py
- tests/test_api/test_context.py
- tests/test_cli/test_analyze.py
- tests/test_services/test_topology_service.py

## Change Log

- 2026-04-29: Implemented the shared topology import foundation with source-registry routing, normalized import results, topology diff reporting, project-scoped persistence, partial-parse warnings, and updated docs/tests.
- 2026-04-29: Fixed Story 5.2 review findings by making manual topology saves fail fast on lossy graphs again and preserving the legacy topology mirror file shape for the default project.
