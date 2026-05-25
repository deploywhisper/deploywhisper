# Story 5.2: CLI Project-Aware Advisory Output

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a CLI user,
I want project-aware analysis output,
So that local and CI workflows can consume the same core report.

## Acceptance Criteria

1. Given a user runs the CLI with artifacts and optional project/workspace key, When analysis completes, Then output includes verdict, Evidence Law status, top findings, uncertainty, report schema version, and advisory posture. And deterministic output remains available without narrative.

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

- [x] [Review][Patch] Treat unsatisfied Evidence Law as requiring human attention [services/analysis_service.py:944]
- [x] [Review][Patch] Preserve omitted-detail Evidence Law status for compact summaries [services/analysis_service.py:920]
- [x] [Review][Patch] Assert the full advisory contract on the project/workspace CLI path [tests/test_cli/test_analyze.py:1005]
- [x] [Review][Patch] Correct docs for actual Evidence Law surfaces and verdict banner format [docs/project-workspaces.md:31]
- [x] [Review Rerun][Patch] Assert Evidence Law detail on the project/workspace CLI path [tests/test_cli/test_analyze.py:1005]
- [x] [Review Rerun][Patch] Fold unsatisfied Evidence Law into the advisory attention contract [services/report_service.py:3477]
- [x] [Review Rerun][Patch] Normalize share-summary finding confidence and compact Evidence Law attention handling [services/analysis_service.py:782]
- [x] [Review Rerun][Patch] Prove scoped CLI advisory output remains deterministic when narrative is unavailable [tests/test_cli/test_analyze.py:1005]

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 5 / Story 5.2 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Red test confirmed missing first-class Evidence Law output: `./.venv/bin/python -m unittest tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_share_summary_returns_thread_ready_markdown_and_json_payload tests.test_cli.test_analyze.AnalyzeCliTests.test_analyze_command_preserves_advisory_output_for_high_risk_results -q`
- Focused green regression run: `./.venv/bin/python -m unittest tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_share_summary_returns_thread_ready_markdown_and_json_payload tests.test_api.test_analyses.AnalysesApiTests.test_create_analysis_returns_structured_result tests.test_cli.test_analyze.AnalyzeCliTests.test_analyze_command_preserves_advisory_output_for_high_risk_results tests.test_cli.test_analyze.AnalyzeCliTests.test_analyze_command_accepts_project_workspace_key -q`
- Repo validation: `./.venv/bin/ruff check .`; `./.venv/bin/ruff format --check .`; `./.venv/bin/bandit -r api/ services/ cli/ --severity-level high --confidence-level high -x tests/`; `./.venv/bin/python -m unittest discover -q`
- Review rerun validation: `./.venv/bin/python -m unittest tests.test_services.test_report_service.ReportServiceTests.test_report_advisory_builder_requires_attention_for_evidence_law_gap tests.test_services.test_report_service.ReportServiceTests.test_report_advisory_builder_normalizes_false_like_boolean_strings tests.test_services.test_report_service.ReportServiceTests.test_report_advisory_builder_ignores_non_finite_boolean_signals -q`; `./.venv/bin/python -m unittest tests.test_cli.test_analyze.AnalyzeCliTests.test_analyze_command_accepts_project_workspace_key -q`; `./.venv/bin/python -m unittest discover -q`; `bash scripts/ci-local.sh` all passed.
- Review rerun hardening validation: `./.venv/bin/python -m unittest tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_share_summary_can_mark_evidence_detail_omitted tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_share_summary_normalizes_malformed_finding_confidence tests.test_services.test_analysis_service.AnalysisServiceTests.test_build_share_summary_requires_attention_for_unsatisfied_evidence_law tests.test_cli.test_analyze.AnalyzeCliTests.test_analyze_command_accepts_project_workspace_key tests.test_services.test_report_service.ReportServiceTests.test_report_advisory_builder_requires_attention_for_evidence_law_gap -q`; `./.venv/bin/ruff check services/analysis_service.py tests/test_services/test_analysis_service.py tests/test_cli/test_analyze.py docs/ci-advisory-consumption.md docs/schemas/report-v2.md _bmad-output/implementation-artifacts/5-2-cli-project-aware-advisory-output.md`; `./.venv/bin/ruff format --check services/analysis_service.py tests/test_services/test_analysis_service.py tests/test_cli/test_analyze.py`; `./.venv/bin/python -m unittest discover -q`; `bash scripts/ci-local.sh` all passed.

### Completion Notes List

- Added first-class `evidence_law_status` and `evidence_law_detail` fields to the shared advisory JSON payload used by CLI and API analysis responses.
- Included Evidence Law status in markdown and plain-text share summaries while preserving the advisory-only `should_block=false` posture.
- Added deterministic CLI coverage for project/workspace keyed analysis output and high-risk advisory output without relying on narrative availability.
- Updated operator/schema docs for the CLI/API advisory contract. UI validation not applicable; no UI route, NiceGUI component, rendered page, browser interaction, keyboard behavior, or accessibility semantics changed.
- BMad code review follow-ups resolved: unsatisfied Evidence Law now forces human-review guidance, compact summaries can surface omitted evidence detail, project/workspace CLI coverage asserts the advisory contract, and docs no longer overstate list/detail Evidence Law fields.
- BMad code review rerun follow-up resolved: project/workspace CLI coverage now asserts the Evidence Law detail field as part of the advisory contract.
- BMad code review rerun follow-up resolved: unsatisfied Evidence Law now also sets advisory attention and an uncertainty flag for CI consumers that branch on `data.advisory.requires_attention`.
- BMad code review rerun follow-up resolved: share-summary finding confidence is finite-safe, compact omitted-detail Evidence Law summaries no longer force human-review guidance by themselves, and scoped CLI coverage now exercises unavailable narrative output.

### File List

- `api/schemas.py`
- `docs/ci-advisory-consumption.md`
- `docs/project-workspaces.md`
- `docs/schemas/report-v2.md`
- `services/analysis_service.py`
- `services/report_service.py`
- `tests/test_api/test_analyses.py`
- `tests/test_cli/test_analyze.py`
- `tests/test_services/test_analysis_service.py`
- `tests/test_services/test_report_service.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-25: Implemented CLI/API project-aware advisory output with first-class Evidence Law status in shared summaries.
- 2026-05-25: Addressed BMad code review findings and marked story ready for closure.
- 2026-05-25: Reran BMad code review and tightened project/workspace CLI Evidence Law detail coverage.
- 2026-05-25: Reran BMad code review and aligned Evidence Law gaps with advisory attention output.
- 2026-05-25: Reran BMad code review and hardened compact Evidence Law summaries plus malformed finding confidence handling.
