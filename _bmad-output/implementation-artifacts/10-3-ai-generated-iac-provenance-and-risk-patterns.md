# Story 10.3: AI-Generated IaC Provenance and Risk Patterns

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a reviewer,
I want AI-generated infrastructure risk patterns detected where possible,
So that plausible but unsafe generated code receives appropriate scrutiny.

## Acceptance Criteria

1. Given provenance or content signals suggest AI-assisted IaC, When analysis runs, Then relevant risk patterns are detected and labeled without overclaiming authorship certainty. And findings still require deterministic evidence for high/critical severity.

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

- [x] [Review][Patch] Scope content-derived provenance and AI-risk labels to the artifact that supplied the signal [services/submission_manifest.py:210]
- [x] [Review][Patch] Do not infer artifact authorship from agent or MCP transport alone [services/ai_iac_risk_service.py:62]
- [x] [Review][Patch] Preserve AI-suggestion review when declared provenance is unknown or conflicts with content signals [services/ai_iac_risk_service.py:72]
- [x] [Review][Patch] Preserve the finding's original domain category when adding the AI-assisted label [services/ai_iac_risk_service.py:181]
- [x] [Review][Patch] Avoid labeling derived or aggregate findings from only the first linked contributor [services/ai_iac_risk_service.py:137]
- [x] [Review][Patch] Make AI-assisted finding labeling idempotent [services/ai_iac_risk_service.py:160]
- [x] [Review][Patch] Map known security flags explicitly instead of broad substring matching [services/ai_iac_risk_service.py:119]
- [x] [Review][Patch] Let an artifact content marker refine caller-declared unknown provenance into a qualified AI-assisted suggestion [services/ai_iac_risk_service.py:70]
- [x] [Review][Patch] Preserve content-derived provenance for accepted artifacts whose parser result fails [services/submission_manifest.py:210]

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 10 / Story 10.3 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5 (Codex)

### Implementation Plan

- Lock provenance qualification and evidence-backed labeling behavior with failing service and intake regression tests.
- Add one shared service for qualified authorship signals and deterministic AI-assisted IaC risk labels.
- Pass audit context through the existing analysis pipeline and persist provenance through the existing submission manifest.
- Document provenance certainty, supported patterns, human review workflow, and current limitations.
- Run focused tests, full regression checks, lint/format validation, and the configured security scan.

### Debug Log References

- Red phase: `./.venv/bin/python -m unittest tests.test_services.test_ai_iac_risk_service tests.test_services.test_intake_service -q` failed as expected because the new service and authorship metadata did not exist.
- Green phase: the same focused suite passed with 26 tests after implementing provenance assessment and deterministic risk labeling.
- Integration phase: focused analysis/intake/service coverage passed with 116 tests, including a real Terraform public-ingress artifact through the shared pipeline.
- Validation: `./.venv/bin/ruff check .` passed.
- Validation: `./.venv/bin/ruff format --check .` passed for all 263 Python files.
- Validation: `./.venv/bin/python -m unittest discover -q` passed.
- Validation: `bash scripts/ci-local.sh` passed across all configured test directories; Bandit reported no issues in touched code.
- Review red phase: focused regressions failed before the reviewer patches, confirming transport inference, batch-tainting, category overwrite, aggregate labeling, non-idempotence, and broad flag mapping were exposed.
- Review green phase: 117 focused analysis, intake, and AI-IaC service tests passed after all seven reviewer patches.
- Review validation: `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q`, and `bash scripts/ci-local.sh` all passed after the review fixes.
- Second-review red phase: 27 focused provenance/intake tests failed on declared-unknown refinement and parser-failed artifact provenance before the patches.
- Second-review green phase: 27 focused tests and 118 combined analysis/intake/provenance tests passed after both patches.
- Second-review validation: repository-wide Ruff check/format passed, root `unittest discover` passed, and `bash scripts/ci-local.sh` passed with 870 tests plus dependency, skills, and Bandit checks.
- UI validation not applicable: no React route, component, browser interaction, keyboard behavior, or accessibility semantics changed.

### Completion Notes List

- Added qualified `human-authored`, `ai-assisted`, and `unknown` provenance with declared/suggested/conflicting/unknown certainty and explicit non-authorship language.
- Explicit declarations and content markers are treated as untrusted provenance signals; agent transport alone does not imply authorship, raw IaC remains local, and content is never interpreted as instructions.
- Labeled artifact-scoped deterministic findings for unsafe defaults, broad IAM permissions, public ingress, and missing environment scoping while preserving their original domain category.
- Reused existing contributors, findings, evidence references, submission manifests, and the Evidence Law runtime gate; provenance alone cannot create a finding.
- Added regression coverage for provenance classification, deterministic-evidence gating, manifest persistence, audit-context propagation, and real shared-pipeline behavior.
- Added the AI-generated/AI-assisted IaC review guide and linked it from the README and agent interface documentation.
- Resolved all seven code-review findings: provenance is artifact-scoped, transport is not authorship, content signals survive conflicting declarations, finding categories remain intact, derived/ambiguous contributors are skipped, labeling is idempotent, and security flags use exact mappings.
- Resolved both second-review findings: content markers now refine caller-declared unknown provenance, and accepted IaC retains provenance signals when parsing fails.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/10-3-ai-generated-iac-provenance-and-risk-patterns.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `docs/ai-safety/agent-api-interface.md`
- `docs/ai-safety/agent-json-output.md`
- `docs/ai-safety/ai-generated-iac-review.md`
- `services/ai_iac_risk_service.py`
- `services/analysis_service.py`
- `services/submission_manifest.py`
- `tests/test_services/test_ai_iac_risk_service.py`
- `tests/test_services/test_analysis_service.py`
- `tests/test_services/test_intake_service.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-07-30: Implemented qualified AI-assisted IaC provenance, deterministic risk-pattern labels, regression coverage, and reviewer documentation; moved story to review.
- 2026-07-30: Resolved all code-review findings, completed focused and full validation, and moved Story 10.3 to done.
- 2026-07-30: Resolved both second-pass code-review findings and completed 870-test local CI validation.
