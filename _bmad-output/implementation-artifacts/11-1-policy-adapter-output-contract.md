# Story 11.1: Policy Adapter Output Contract

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform admin,
I want a policy adapter contract,
So that report outputs can be translated into local workflow decisions.

## Acceptance Criteria

1. Given a canonical report exists, When a policy adapter consumes it, Then the adapter can output advisory, warn, soft-block, or hard-block status with reasons. And the canonical report remains unchanged and advisory.

### Requirement Traceability

- Primary PRD requirements: Epic 11 coverage: ADM-07, ADM-09, WRK-07, RSK-07, NFR-SEC-06.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 11 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Reserve scanner-conflict field names from adapter-owned payloads [services/adapter_output_contract.py:261]
- [x] [Review][Patch] Exercise a non-empty frozen scanner-conflict object in the immutability regression [tests/test_services/test_policy_adapter_output_contract.py:55]
- [x] [Review][Patch] Compare the emitted canonical summary with the source summary, not only the untouched source with itself [tests/test_services/test_policy_adapter_output_contract.py:53]
- [x] [Review][Patch] Reject reason text that cannot be serialized as UTF-8 JSON [services/policy_adapter_output_contract.py:39]
- [x] [Review][Patch] Reject reason codes and messages containing no visible characters [services/policy_adapter_output_contract.py:39]
- [x] [Review][Patch] Reject bytes coercion for policy status input [services/policy_adapter_output_contract.py:54]
- [x] [Review][Patch] Reject unordered set input for policy reasons [services/policy_adapter_output_contract.py:55]
- [x] [Review][Patch] Require an actual boolean true for canonical_report_advisory input [services/policy_adapter_output_contract.py:58]
- [x] [Review][Patch] Exercise advisory_only and should_block invariant failures independently [tests/test_services/test_policy_adapter_output_contract.py:95]
- [x] [Review][Patch] Add the changed adapter contract regression file to the story File List [_bmad-output/implementation-artifacts/11-1-policy-adapter-output-contract.md:124]
- [x] [Review][Patch] Reject control characters embedded in otherwise visible policy reason text [services/policy_adapter_output_contract.py:39]

## Dev Notes

### Epic Context

- Epic: 11. Optional Enforcement Adapters
- Epic goal: Expose optional enforcement interpretation without changing the advisory core.
- Epic coverage: ADM-07, ADM-09, WRK-07, RSK-07, NFR-SEC-06

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 11 / Story 11.1 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

Codex (GPT-5)

### Implementation Plan

- Extend the existing immutable workflow-adapter envelope instead of creating a second canonical report shape.
- Represent policy interpretation as a strict, versioned downstream contract with four explicit statuses and required structured reasons.
- Reject non-advisory or blocking canonical summaries while keeping optional policy status separate from core report semantics.
- Regression-lock status coverage, validation, immutability, documentation, and the unchanged advisory report boundary.

### Debug Log References

- RED: `./.venv/bin/python -m pytest tests/test_services/test_policy_adapter_output_contract.py tests/test_docs/test_workflow_adapter_output_contract.py -q --tb=short` — collection failed because `services.policy_adapter_output_contract` did not exist.
- GREEN: the same focused command passed with 6 tests and 20 subtests after adding the contract and documentation.
- RED immutability regression: the canonical scanner-conflict collection remained a mutable list through the adapter envelope.
- GREEN/refactor: added a frozen scanner-conflict summary tuple and reran the combined adapter suite — 29 tests and 46 subtests passed.
- Affected CI shard: `./.venv/bin/python -m pytest tests/test_services tests/test_docs -q --tb=short` — 918 passed, 349 subtests passed.
- Required smoke: `./.venv/bin/python -m unittest discover -q` — 396 passed, 1 skipped.
- Static/security validation: `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, and `./.venv/bin/python -m bandit -q -r services/adapter_output_contract.py services/policy_adapter_output_contract.py` — passed; 269 files already formatted.
- Full local CI: `bash scripts/ci-local.sh` — passed, including Ruff, repo-wide formatting, dependency validation, Bandit, compile checks, skill harnesses, and 895 tests.
- Review RED: the combined adapter-contract suite failed because scanner-conflict `finding_id` was still accepted in `adapter_payload`; 27 tests and 32 subtests otherwise passed.
- Review GREEN: reserved every scanner-conflict model field, added a real non-empty conflict fixture, verified nested field immutability and source-to-output equality, and reran the focused suite — 29 tests and 47 subtests passed.
- Review affected shard: `./.venv/bin/python -m pytest tests/test_services tests/test_docs -q --tb=short` — 918 passed, 350 subtests passed.
- Review closure validation: unittest smoke passed with 396 tests and 1 skip; Ruff, format check, targeted Bandit, diff checks, and `bash scripts/ci-local.sh` all passed; full local CI ran 895 tests.
- Second-review RED: `./.venv/bin/python -m pytest tests/test_services/test_policy_adapter_output_contract.py -q --tb=short` reproduced all coercion, visibility, and serialization gaps with 6 failures; 5 tests and 8 subtests otherwise passed.
- Second-review GREEN: `./.venv/bin/python -m pytest tests/test_services/test_policy_adapter_output_contract.py tests/test_services/test_adapter_output_contract.py tests/test_docs/test_workflow_adapter_output_contract.py -q --tb=short` — 30 passed, 55 subtests passed.
- Second-review affected shard: `./.venv/bin/python -m pytest tests/test_services tests/test_docs -q --tb=short` — 919 passed, 358 subtests passed.
- Second-review closure validation: unittest smoke passed with 396 tests and 1 skip; Ruff, format check, targeted Bandit, diff checks, and `bash scripts/ci-local.sh` all passed; full local CI ran 896 tests.
- Third-review RED: `./.venv/bin/python -m pytest tests/test_services/test_policy_adapter_output_contract.py -q --tb=short` reproduced embedded control-character acceptance with 3 failures; 5 tests and 14 subtests otherwise passed.
- Third-review GREEN: the combined policy, adapter, and documentation contract suite passed with 30 tests and 58 subtests after rejecting all non-printable reason characters.
- Third-review affected shard: `./.venv/bin/python -m pytest tests/test_services tests/test_docs -q --tb=short` — 919 passed, 361 subtests passed.
- Third-review closure validation: unittest smoke passed with 396 tests and 1 skip; Ruff, format check, targeted Bandit, diff checks, and `bash scripts/ci-local.sh` all passed; full local CI ran 896 tests.
- Local mypy was unavailable in `.venv`; the configured GitHub mypy step is non-blocking. No dependency was added solely for local validation.
- UI validation not applicable: Story 11.1 changes service contracts and documentation only; no React route, rendered surface, browser interaction, keyboard behavior, or accessibility semantics changed.

### Completion Notes List

- Added `PolicyAdapterOutputContract`, `PolicyAdapterStatus`, and `PolicyAdapterReason` as strict frozen Pydantic contracts.
- Supported `advisory`, `warn`, `soft-block`, and `hard-block` interpretations with at least one nonblank structured reason.
- Reused the Story 5.6 `AdapterOutputContract` and immutable canonical `ShareSummary` instead of duplicating analysis or severity logic.
- Rejected policy output when the nested canonical summary is not advisory or claims DeployWhisper should block.
- Rejected embedded control characters in policy reason codes and messages before they reach logs or rendered integration output.
- Preserved canonical report values for every policy status and closed the remaining nested scanner-conflict immutability gap.
- Documented construction, ownership boundaries, versioning, and the distinction between optional local policy decisions and canonical advisory semantics.

### File List

- `_bmad-output/implementation-artifacts/11-1-policy-adapter-output-contract.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `docs/workflow-adapter-output-contract.md`
- `services/adapter_output_contract.py`
- `services/policy_adapter_output_contract.py`
- `tests/test_docs/test_workflow_adapter_output_contract.py`
- `tests/test_services/test_adapter_output_contract.py`
- `tests/test_services/test_policy_adapter_output_contract.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-08-03: Added the optional policy-adapter output contract, strengthened canonical immutability, documented the boundary, completed full validation, and moved the story to review.
- 2026-08-03: Resolved all code-review findings, added scanner-conflict shadow and immutability regressions, reran full validation, and marked the story done.
- 2026-08-03: Closed the second review with strict ordered inputs, UTF-8-visible structured reasons, literal advisory semantics, independent invariant regressions, and another full local CI pass.
- 2026-08-03: Closed the third review by rejecting embedded control characters in policy reasons and rerunning focused, affected-shard, security, smoke, and full-CI validation.
