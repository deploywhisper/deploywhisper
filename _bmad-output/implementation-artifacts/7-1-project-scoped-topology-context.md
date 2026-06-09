# Story 7.1: Project-Scoped Topology Context

Status: review

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a reviewer,
I want blast radius computed from project-scoped topology,
So that affected services and dependencies are meaningful.

## Acceptance Criteria

1. Given topology exists for a project/workspace, When analysis computes blast radius, Then affected services, dependencies, ownership, freshness, and context source are included in the report. And stale, missing, incomplete, or conflicting topology is explicit.

### Requirement Traceability

- Primary PRD requirements: Epic 7 coverage: CTX-01..13, ADM-03, PRJ-09, NFR-PERF-05, DOC-09.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 7 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] API report schema drops topology context fields [api/schemas.py:910]
- [x] [Review][Patch] Downstream topology edges are rendered as service dependencies [analysis/blast_radius.py:17]
- [x] [Review][Patch] Legacy blast-radius payloads default to missing topology context [analysis/blast_radius.py:49]
- [x] [Review][Patch] Singular owner accepts malformed non-string values without a partial-parse warning [services/topology_service.py:787]
- [x] [Review][Patch] Freshness rendering can crash on non-numeric persisted age_days values [ui/components/blast_radius_graph.py:103]
- [x] [Review][Patch] Malformed entries inside `owners` lists are stringified and reported as real owners [services/topology_service.py:810]
- [x] [Review][Patch] Legacy topology with missing source or freshness metadata can be classified as current [analysis/blast_radius.py:74]
- [x] [Review][Patch] Whitespace-padded downstream service ids can drop transitive blast-radius services [analysis/blast_radius.py:225]
- [x] [Review][Patch] Invalid topology `updated_at` can still serialize context state as current [analysis/blast_radius.py:83]
- [x] [Review][Patch] Negative persisted freshness age renders impossible stale text [ui/components/blast_radius_graph.py:103]
- [x] [Review][Patch] Partial persisted API context dictionaries can omit expected source/freshness keys [api/schemas.py:938]
- [x] [Review][Patch] Malformed persisted blast-radius additive fields can break API/UI report loading [api/schemas.py:914]
- [x] [Review][Patch] Partial or non-scalar topology source metadata is classified as current [analysis/blast_radius.py:67]
- [x] [Review][Patch] Duplicate downstream edges render duplicate dependency labels [analysis/blast_radius.py:275]
- [x] [Review][Patch] Stale/conflicting report states lack direct regression coverage [analysis/blast_radius.py:155]
- [x] [Review][Patch] Report schema docs omit the explicit state/limitation contract [docs/schemas/report-v2.md:260]
- [x] [Review][Patch] Malformed nested additive-field values can still break API/UI report loading [api/schemas.py:973]
- [x] [Review][Patch] Future topology timestamps are treated as fresh current context [analysis/blast_radius.py:151]
- [x] [Review][Patch] Legacy topology file source path is not propagated into blast-radius context source [services/topology_service.py:490]
- [x] [Review][Patch] Legacy context-state contract documents `unknown` but emits `null` [docs/schemas/report-v2.md:440]
- [x] [Review][Patch] Freshness `age_days` computation lacks deterministic shared-core coverage [analysis/blast_radius.py:151]
- [x] [Review][Patch] Explicit legacy `context_state: null` still serializes as `null` instead of `unknown` [api/schemas.py:991]

## Dev Notes

### Epic Context

- Epic: 7. Context Moat
- Epic goal: Improve deployment-risk judgment with richer project-scoped context.
- Epic coverage: CTX-01..13, ADM-03, PRJ-09, NFR-PERF-05, DOC-09

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 7 / Story 7.1 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5.4 Codex

### Debug Log References

- 2026-06-09: Started bmad-dev-story implementation on `feature/7-1-project-scoped-topology-context`.
- 2026-06-09: Existing topology loading was already project/workspace scoped; Story 7.1 gap was that blast-radius report payloads did not carry topology source, freshness, dependency, ownership, or explicit context-state metadata.
- 2026-06-09: Added RED regressions for enriched blast-radius output and topology owner preservation; initial focused run failed on missing `context_source`, `context_state`, and dropped ownership fields.
- 2026-06-09: Implemented topology owner preservation, enriched `ImpactNode` / `BlastRadiusResult`, rendered topology source/freshness/owners/dependencies in the blast-radius panel text equivalent, and documented the additive report schema fields.
- 2026-06-09: Validation passed: focused blast-radius/topology/report/UI regressions (8 tests); topology/blast-radius/UI suites (27 tests); docs/persistence regressions (3 tests); touched-file `py_compile`; touched-file Ruff; `./.venv/bin/ruff check .`; `./.venv/bin/ruff format --check .`; production Bandit; `APP_PORT=18109 npm run test:ui-review` (4 tests); `./.venv/bin/python -m unittest discover -q` (463 tests, 1 skipped).
- 2026-06-09: Fixed code-review findings by preserving enriched blast-radius fields in API schemas, calculating dependencies from upstream topology edges, treating absent legacy context state as unknown, validating singular `owner`, and guarding malformed `freshness.age_days` rendering.
- 2026-06-09: Review-fix validation passed: focused review regressions (16 tests); impacted analysis/topology/API/report/docs/UI suites (105 tests); touched-file `py_compile`; touched-file Ruff; `./.venv/bin/ruff check .`; `./.venv/bin/ruff format --check .`; `git diff --check`; production Bandit; `./.venv/bin/python -m unittest discover -q` (466 tests, 1 skipped); `APP_PORT=18109 npm run test:ui-review` (4 tests).
- 2026-06-09: Fixed follow-up code-review findings by filtering malformed list owner entries, requiring topology source/freshness metadata for current context state, normalizing topology service/downstream IDs, treating invalid `updated_at` as incomplete context, guarding negative freshness ages, and normalizing partial persisted API context dictionaries.
- 2026-06-09: Follow-up review-fix validation passed: focused review regressions (19 tests); impacted analysis/topology/API/report/docs/UI suites (111 tests); touched-file `py_compile`; touched-file Ruff; `./.venv/bin/ruff check .`; `./.venv/bin/ruff format --check .`; `git diff --check`; production Bandit; `./.venv/bin/python -m unittest discover -q` (468 tests, 1 skipped); `APP_PORT=18109 npm run test:ui-review` (4 tests).
- 2026-06-09: Fixed final code-review findings by normalizing malformed persisted blast-radius additive fields in analysis/API schemas, requiring scalar complete topology source metadata, deduplicating downstream dependency metadata, adding direct stale/conflicting report-state regressions, and documenting context-state/limitation labels.
- 2026-06-09: Final review-fix validation passed: targeted review regressions (24 tests); impacted analysis/topology/API/report/docs/UI suites (119 tests); touched-file `py_compile`; `./.venv/bin/ruff check .`; `./.venv/bin/ruff format --check .`; `git diff --check`; production Bandit; `./.venv/bin/python -m unittest discover -q` (470 tests, 1 skipped); `APP_PORT=18109 npm run test:ui-review` (4 tests).
- 2026-06-09: Fixed latest code-review findings by sanitizing malformed nested persisted context fields, treating future topology timestamps as invalid freshness, propagating legacy topology file source paths into context source metadata, keeping legacy context state at `unknown`, and adding deterministic freshness `age_days` coverage with an injected clock.
- 2026-06-09: Latest review-fix validation passed: focused review regressions (29 tests); impacted analysis/topology/API/report/docs/UI suites (123 tests); touched-file `py_compile`; touched-file Ruff check/format; `./.venv/bin/ruff check .`; `./.venv/bin/ruff format --check .`; `git diff --check`; production Bandit; `./.venv/bin/python -m unittest discover -q` (471 tests, 1 skipped); `APP_PORT=18109 npm run test:ui-review` (4 tests).
- 2026-06-09: Fixed rerun code-review finding by normalizing explicit persisted `context_state: null` to `unknown` in shared blast-radius and API report schemas.
- 2026-06-09: Rerun review-fix validation passed: focused schema regressions (21 tests); direct model repro (`unknown`/`unknown`); impacted analysis/API/report/docs/UI suites (101 tests); touched-file `py_compile`; touched-file Ruff check/format; `./.venv/bin/ruff check .`; `./.venv/bin/ruff format --check .`; `git diff --check`; production Bandit; `./.venv/bin/python -m unittest discover -q` (472 tests, 1 skipped); `APP_PORT=18109 npm run test:ui-review` (4 tests).

### Completion Notes List

- Enriched blast-radius report payloads with context source, freshness, context state, context limitations, affected-service dependencies, and owners.
- Preserved valid `owner` / `owners` values through project/workspace-scoped topology save/import normalization and dropped malformed owner values with partial-parse warnings.
- Updated the report blast-radius panel text equivalent so reviewers can see topology source, freshness, affected-service ownership, and true upstream dependencies.
- Preserved enriched blast-radius topology context through API response schemas and fresh-analysis fallback payloads.
- Kept legacy persisted blast-radius payloads from being falsely labeled as missing topology context.
- Guarded report UI freshness rendering against malformed persisted `age_days` values.
- Normalized malformed/partial persisted topology context so reviewers do not see fabricated owners, impossible freshness text, or falsely current context state.
- Hardened legacy persisted blast-radius payload handling across API/UI report loading and documented the explicit topology context-state contract.
- Hardened nested persisted topology context payloads and future freshness handling so malformed or temporally impossible topology context remains explicit instead of breaking report loading or being labeled current.
- Normalized explicit legacy `context_state: null` values to `unknown` across shared analysis and API schema loading.
- Updated the report schema documentation for the additive blast-radius context fields.

### File List

- `_bmad-output/implementation-artifacts/7-1-project-scoped-topology-context.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `analysis/blast_radius.py`
- `api/schemas.py`
- `docs/schemas/report-v2.md`
- `services/topology_service.py`
- `tests/test_analysis/test_blast_radius.py`
- `tests/test_api/test_analyses.py`
- `tests/test_services/test_report_service.py`
- `tests/test_services/test_topology_service.py`
- `tests/test_ui/test_blast_radius_panel.py`
- `ui/components/blast_radius_graph.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-06-09: Implemented Story 7.1 project-scoped topology context enrichment and moved story to review after focused, full unittest, lint, static-analysis, documentation, and UI validation.
- 2026-06-09: Fixed Story 7.1 review findings and moved story back to review after focused, full unittest, lint, static-analysis, documentation, and UI validation.
- 2026-06-09: Fixed follow-up Story 7.1 review findings and moved story back to review after targeted regression, impacted-suite, full unittest, lint, static-analysis, and UI validation.
- 2026-06-09: Fixed final Story 7.1 review findings and moved story back to review after targeted regression, impacted-suite, full unittest, lint, static-analysis, and UI validation.
- 2026-06-09: Fixed latest Story 7.1 review findings and moved story back to review after targeted regression, impacted-suite, full unittest, lint, static-analysis, and UI validation.
- 2026-06-09: Fixed rerun Story 7.1 review finding and moved story back to review after targeted regression, impacted-suite, full unittest, lint, static-analysis, and UI validation.
