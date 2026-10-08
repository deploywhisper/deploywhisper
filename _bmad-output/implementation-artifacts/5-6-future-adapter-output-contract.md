# Story 5.6: Future Adapter Output Contract

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a DeployWhisper user,
I want GitLab, Jenkins, Atlantis, GitOps, chat, and other adapters to consume one report contract,
So that new workflow integrations do not redesign the core.

## Acceptance Criteria

1. Given future adapters are implemented, When they consume DeployWhisper output, Then they use canonical report summaries and adapter metadata. And adapter-specific formatting cannot mutate canonical severity or Evidence Law status.

### Requirement Traceability

- Primary PRD requirements: Epic 5 coverage: WRK-01..10, REV-05..08, ADM-07, DOC-08.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 5 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Decision] Require project scope via either `project_key` or `project_id`; keep workspace scope optional via either `workspace_key` or `workspace_id`.
- [x] [Review][Patch] Deep-freeze adapter metadata and payload maps so reserved canonical fields cannot be added after validation [services/adapter_output_contract.py:52]
- [x] [Review][Patch] Derive reserved adapter field names from canonical summary fields; current manual set omits `headline` [services/adapter_output_contract.py:14]
- [x] [Review][Patch] Forbid unknown top-level `AdapterMetadata` fields so typos and reserved names are not silently ignored [services/adapter_output_contract.py:34]
- [x] [Review][Patch] Reuse the existing typed `ShareSummary` contract instead of maintaining a second partial canonical summary shape [services/adapter_output_contract.py:76]

#### Re-review Findings (2026-05-29)

- [x] [Review][Patch] Tuple-wrapped adapter payload entries bypass deep-freeze [services/adapter_output_contract.py:42]
- [x] [Review][Patch] Conflicting project/workspace key and ID scope identifiers are accepted despite the contract's either/or wording [services/adapter_output_contract.py:108]
- [x] [Review][Patch] Non-serializable adapter payload values pass validation and fail only during JSON emission [services/adapter_output_contract.py:171]
- [x] [Review][Patch] Adapter payload reserved-field validation only checks top-level keys, allowing nested canonical field shadowing [services/adapter_output_contract.py:221]
- [x] [Review][Patch] Dev Agent Record lacks command-level validation evidence despite Story 5.6 being marked done [_bmad-output/implementation-artifacts/5-6-future-adapter-output-contract.md:87]

#### Second Re-review Findings (2026-05-29)

- [x] [Review][Patch] Metadata `extra` allows non-finite floats that serialize as `null` [services/adapter_output_contract.py:16]
- [x] [Review][Patch] Project and workspace IDs are coercive, allowing booleans, strings, and floats to become integer IDs [services/adapter_output_contract.py:60]
- [x] [Review][Patch] Adapter payload reserved-field validation omits canonical nested finding and context fields [services/adapter_output_contract.py:220]
- [x] [Review][Patch] `contract_version` accepts blank or unsupported schema versions on direct model construction [services/adapter_output_contract.py:170]

## Dev Notes

### Epic Context

- Epic: 5. Workflow-Native Delivery
- Epic goal: Deliver the report in real review workflows without duplicating analysis logic.
- Epic coverage: WRK-01..10, REV-05..08, ADM-07, DOC-08

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 5 / Story 5.6 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5.4 Codex

### Debug Log References

- Red phase: `./.venv/bin/python -m unittest tests.test_services.test_adapter_output_contract -q` failed with `ModuleNotFoundError: No module named 'services.adapter_output_contract'`.
- Red phase: `./.venv/bin/python -m unittest tests.test_docs.test_workflow_adapter_output_contract -q` failed before the guide/link existed.
- Green/refactor: Added `services.adapter_output_contract` with immutable canonical summary fields, adapter metadata, and reserved-field validation for adapter payloads and metadata extras.
- UI validation not applicable: story changed service contract helpers and documentation only; no retired Python UI route, component, browser interaction, keyboard behavior, or accessibility semantics changed.
- Code review remediation: required project scope by key or ID, kept workspace scope optional by key or ID, reused typed `ShareSummary`, derived reserved adapter fields from model fields, forbade unknown metadata fields, and deep-froze adapter-owned maps.
- Re-review remediation: rejected non-JSON adapter payload containers/values before contract construction, recursively blocked nested canonical-field shadowing, enforced exactly one project scope identifier and at most one workspace scope identifier, and added command-level validation evidence.
- Second re-review remediation: rejected non-finite metadata extra numbers, changed project/workspace IDs to strict positive integers, added canonical finding/context model fields to recursive reserved-field checks, and fixed direct `AdapterOutputContract` construction to `contract_version="v1"`.

### Completion Notes List

- Added a service-layer future adapter output contract that wraps canonical `ShareSummary` output with explicit `AdapterMetadata`.
- Preserved canonical severity, recommendation, advisory posture, and Evidence Law status/detail as frozen core summary fields.
- Rejected adapter-specific payloads or metadata extras that shadow canonical fields, preventing adapter formatting from rewriting severity or Evidence Law status.
- Documented the workflow adapter output contract and linked it from CI advisory consumption guidance.
- Added deterministic service and documentation regression coverage.
- Validation passed: `./.venv/bin/python -m unittest tests.test_services.test_adapter_output_contract tests.test_docs.test_workflow_adapter_output_contract -q` — 14 tests OK.
- Validation passed: `./.venv/bin/python -m unittest tests.test_services.test_adapter_output_contract tests.test_docs.test_workflow_adapter_output_contract -q` — 17 tests OK.
- Validation passed: `./.venv/bin/ruff check .` — All checks passed.
- Validation passed: `./.venv/bin/ruff format --check .` — 286 files already formatted.
- Validation passed: `./.venv/bin/python -m unittest discover -q` — 447 tests OK, 1 skipped.
- Validation passed: `bash scripts/ci-local.sh` — Ruff, format, dependency check, Bandit, parser scenarios, and unittest passed; unittest result 447 tests OK, 1 skipped.
- Resolved all Story 5.6 code review findings before moving the story to done.
- Resolved all Story 5.6 re-review findings and reran focused plus broad validation.
- Resolved all Story 5.6 second re-review findings and reran focused tests, Ruff, full unittest, and local CI.

### File List

- `_bmad-output/implementation-artifacts/5-6-future-adapter-output-contract.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `docs/ci-advisory-consumption.md`
- `docs/workflow-adapter-output-contract.md`
- `services/adapter_output_contract.py`
- `tests/test_docs/test_workflow_adapter_output_contract.py`
- `tests/test_services/test_adapter_output_contract.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-29: Implemented future adapter output contract, documentation, and regression coverage.
- 2026-05-29: Resolved code review findings for project scope, metadata strictness, immutable adapter maps, derived reserved fields, and typed `ShareSummary` reuse.
- 2026-05-29: Resolved re-review findings for JSON-safe payload validation, recursive canonical shadow checks, scope identifier conflicts, and command-level validation evidence.
- 2026-05-29: Resolved second re-review findings for finite metadata extras, strict ID typing, nested canonical finding/context shadow checks, and fixed v1 contract version validation.

## Course Correction — 2026-10-07

Status reconciled to `done` against merged delivery [PR #78](https://github.com/deploywhisper/deploywhisper/pull/78), the completed task/review-fix records above, and the accepted v1.4.0 baseline in `docs/verification/v1.4.0-release.json`. This is administrative closeout of existing delivery, not a claim that a new implementation review or application test run occurred today. Historical review attempts remain intact. See `../planning-artifacts/sprint-change-proposal-2026-10-07-v1.4.0-status-reconciliation.md`.
