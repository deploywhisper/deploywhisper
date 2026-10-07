# Story 10.1: Agent JSON CLI Mode

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a DeployWhisper user,
I want stable JSON output from the CLI,
So that I can consume deployment-risk analysis without scraping human text.

## Acceptance Criteria

1. Given the CLI runs with `--agent-json`, When analysis completes, Then output includes schema version, verdict, advisory-only status, evidence, findings, confidence, uncertainty, context TODOs, and verification guidance. And output explicitly states it is not deployment approval.

### Requirement Traceability

- Primary PRD requirements: Epic 10 coverage: AIA-01..10, RSK-11, AIA-related NFR-SEC requirements, DOC-24.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 10 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Isolate and lock the nested v1 agent contract so shared API schema evolution cannot silently change evidence, findings, or confidence output; add direct builder coverage for workspace scope and empty collections. [services/agent_interface_service.py:47]
- [x] [Review][Patch] Deduplicate verification guidance by normalized text rather than exact casing so equivalent instructions are not repeated. [services/agent_interface_service.py:87]

## Dev Notes

### Epic Context

- Epic: 10. AI Infrastructure Safety and Agent-Native Review
- Epic goal: Serve AI coding agents safely without letting them bypass human judgment.
- Epic coverage: AIA-01..10, RSK-11, AIA-related NFR-SEC requirements, DOC-24

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 10 / Story 10.1 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

Codex (GPT-5)

### Implementation Plan

- Preserve the default CLI JSON contract and run the shared analysis core exactly once.
- Add an architecture-owned agent interface adapter with strict Pydantic models and an independently versioned v1 output contract.
- Derive evidence, findings, verdict, confidence, uncertainty, scope, Evidence Law status, context TODOs, and verification guidance from the canonical analysis response.
- Lock immutable advisory and human-decision guardrails with CLI and service regressions.
- Document the agent schema, safe consumption rules, and operational-error behavior.

### Debug Log References

- RED: `./.venv/bin/python -m pytest tests/test_cli/test_analyze.py::AnalyzeCliTests::test_analyze_agent_json_emits_stable_advisory_contract -q --tb=short` — failed because `--agent-json` was not recognized.
- GREEN: the focused agent contract regression passed after implementation.
- Focused agent coverage: agent success contract, structured operational error, and verification-guidance aggregation — 3 passed.
- Full affected CLI/service coverage after review fixes: `./.venv/bin/python -m pytest tests/test_services/test_agent_interface_service.py tests/test_cli/test_analyze.py -q --tb=short` — 88 passed.
- CI-parity shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` — 349 passed, 19 subtests passed.
- Full local CI after review fixes: `bash scripts/ci-local.sh` — passed, including Ruff, format, dependency validation, Bandit, compile checks, Skill harnesses, and 858 tests.
- Required smoke: `./.venv/bin/python -m unittest discover -q` — 360 passed, 1 skipped.
- Manual CLI sanity: `./.venv/bin/python cli.py analyze --help` — documented `--agent-json` successfully.
- UI validation not applicable: Story 10.1 changes only the CLI/service contract and documentation; no React or browser-visible surface changed.

### Completion Notes List

- Added `deploywhisper analyze --agent-json` without changing default CLI JSON or operational error envelopes.
- Added a strict v1 agent contract with report schema version, explicit project/workspace scope, verdict, Evidence Law status, canonical evidence and findings, confidence ledger, uncertainty, context TODOs, and deduplicated verification guidance.
- Added immutable `advisory_only=true`, `deployment_approval=false`, `human_decision_required=true`, and explicit non-approval wording so agents cannot interpret the result as deployment approval.
- Reused the existing canonical `AnalysisRunData` and shared analysis/persistence path; the agent mode performs no duplicate analysis and introduces no dependency or persistence change.
- Added deterministic success, failure, exact-shape, shared-core call-count, and guidance aggregation coverage.
- Isolated every nested v1 evidence, finding, context-source, and confidence-ledger field behind strict agent-owned models so additive API schema changes cannot alter the agent contract.
- Added direct builder regressions for exact nested keys, workspace scope, empty collections, and immutable approval guardrails; guidance deduplication now ignores equivalent casing and whitespace.
- Documented agent invocation, schema evolution, human review requirements, forbidden autonomous approval/deployment/remediation behavior, and operational-error interpretation.

### File List

- `_bmad-output/implementation-artifacts/10-1-agent-json-cli-mode.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `README.md`
- `cli/analyze.py`
- `docs/ai-safety/agent-json-output.md`
- `docs/ci-advisory-consumption.md`
- `services/agent_interface_service.py`
- `tests/test_cli/test_analyze.py`
- `tests/test_services/test_agent_interface_service.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-07-28: Implemented and verified the stable advisory `--agent-json` CLI contract; moved Story 10.1 to review.
- 2026-07-28: Resolved all code-review findings, reran focused and full validation, and moved Story 10.1 to done.
