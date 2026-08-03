# Story 10.5: AI Safety Documentation

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a user of AI coding agents,
I want documented safe review workflows,
So that agents use DeployWhisper as an advisory reviewer, not an approver.

## Acceptance Criteria

1. Given AI-agent documentation is read, When users configure agent workflows, Then docs show safe invocation, output interpretation, human review expectations, prompt-injection risks, and forbidden auto-approval patterns. And examples remain self-hosted/local-first.

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

- [x] [Review][Patch] Distinguish `analysis.submit` from `report.read` in the MCP-equivalent response documentation so consumers do not validate the submit path against the read-operation example. [docs/ai-safety/mcp-server.md:45]
- [x] [Review][Patch] Restore the bounded `meta.output_limits` contract in the canonical MCP-equivalent example and regression coverage, or explicitly mark the payload as abbreviated. [docs/ai-safety/mcp-server.md:45]
- [x] [Review][Patch] Strengthen documentation regressions to verify operation values, bounded-response metadata, per-guide local-first guardrails, and internal relative link targets instead of relying on globally aggregated prose keywords. [tests/test_infra/test_ai_safety_documentation.py:34]
- [x] [Review][Patch] Clarify that HTTP consumers must validate both `data.schema_version` and `meta.interface_schema_version`; the general review workflow currently names only `schema_version`. [docs/ai-safety/reviewing-ai-generated-iac.md:41]
- [x] [Review][Patch] Warn that generated agent JSON may contain sensitive findings and context and must not be committed or broadly shared without review. [docs/ai-safety/reviewing-ai-generated-iac.md:14]
- [x] [Review][Patch] Label the `report.read` JSON payload as an abbreviated data example rather than a complete response, because it intentionally omits stable `AgentAnalysisData` fields. [docs/ai-safety/mcp-server.md:52]
- [x] [Review][Patch] Extend the MCP documentation regression to require truncation metadata and its human-review guidance, not only output-limit field names. [tests/test_infra/test_ai_safety_documentation.py:82]
- [x] [Review][Patch] Verify README and CI navigation as actual Markdown links with existing targets so malformed canonical navigation cannot pass path-substring checks. [tests/test_infra/test_ai_safety_documentation.py:144]
- [x] [Review][Patch] Preserve legacy section anchors in both compatibility guides so existing deep links continue to land on the intended canonical guidance. [docs/ai-safety/agent-api-interface.md:1]
- [x] [Review][Patch] Document that `artifact_paths` requires exactly one safe repository-relative value per upload in matching order. [docs/ai-safety/mcp-server.md:38]
- [x] [Review][Patch] Synchronize the machine-readable sprint `last_updated` value with the updated header and Story 10.5 completion date. [_bmad-output/implementation-artifacts/sprint-status.yaml:38]

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 10 / Story 10.5 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

Codex (GPT-5)

### Implementation Plan

- Lock the PRD's four canonical AI-safety document paths with a focused infrastructure regression test.
- Reuse and cross-link the existing agent JSON, HTTP agent-interface, provenance, and prompt-injection guidance rather than changing runtime behavior.
- Document one self-hosted, local-first review workflow covering safe invocation, output interpretation, human decision gates, untrusted-input risks, and forbidden automation.
- Preserve earlier documentation URLs as concise compatibility links and update current navigation to the canonical guides.

### Debug Log References

- RED: `./.venv/bin/python -m pytest tests/test_infra/test_ai_safety_documentation.py::AiSafetyDocumentationTests::test_required_ai_safety_documents_exist -q --tb=short` — failed with the three missing canonical paths before implementation.
- GREEN: `./.venv/bin/python -m pytest tests/test_infra/test_ai_safety_documentation.py -q --tb=short` — 6 passed, 21 subtests passed.
- Focused safety suite: `./.venv/bin/python -m pytest tests/test_infra/test_ai_safety_documentation.py tests/test_llm/test_prompt_injection.py tests/test_infra/test_prompt_injection_release_gate.py -q --tb=short` — 17 passed, 117 subtests passed.
- CI-parity shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` — 373 passed, 40 subtests passed.
- Required smoke: `./.venv/bin/python -m unittest discover -q` — 392 passed, 1 skipped.
- Full local CI: `bash scripts/ci-local.sh` — passed, including Ruff, repo-wide format check, dependency validation, Bandit, compile checks, skill harnesses, and 891 tests.
- Initial independent verification was superseded by the adversarial code-review rerun, which found five documentation-contract and test-adequacy gaps.
- Review fixes: `./.venv/bin/python -m pytest tests/test_infra/test_ai_safety_documentation.py -q --tb=short` — 9 passed, 57 subtests passed.
- Review CI-parity shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` — 376 passed, 76 subtests passed.
- Review smoke: `./.venv/bin/python -m unittest discover -q` — 395 passed, 1 skipped.
- Review full local CI: `bash scripts/ci-local.sh` — passed, including Ruff, repo-wide format check, dependency validation, Bandit, compile checks, skill harnesses, and 891 tests.
- Second-review documentation regression: `./.venv/bin/python -m pytest tests/test_infra/test_ai_safety_documentation.py -q --tb=short` — 8 passed, 63 subtests passed.
- Second-review CI-parity shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -q --tb=short` — 375 passed, 82 subtests passed.
- Second-review smoke: `./.venv/bin/python -m unittest discover -q` — 394 passed, 1 skipped.
- Second-review static checks: `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .` — passed; 267 files already formatted.
- Second-review full local CI: `bash scripts/ci-local.sh` — passed, including Ruff, repo-wide format check, dependency validation, Bandit, compile checks, skill harnesses, and 891 tests.
- Third-review RED regression: `./.venv/bin/python -m pytest tests/test_infra/test_ai_safety_documentation.py -q --tb=short` — failed on all three newly identified contract gaps before implementation.
- Third-review documentation regression: `./.venv/bin/python -m pytest tests/test_infra/test_ai_safety_documentation.py -q --tb=short` — 10 passed, 72 subtests passed.
- Third-review CI-parity shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -q --tb=short` — 377 passed, 91 subtests passed.
- Third-review smoke: `./.venv/bin/python -m unittest discover -q` — 396 passed, 1 skipped.
- Third-review static checks: `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .` — passed; 267 files already formatted.
- Third-review full local CI: `bash scripts/ci-local.sh` — passed, including Ruff, repo-wide format check, dependency validation, Bandit, compile checks, skill harnesses, and 891 tests.
- UI validation not applicable: Story 10.5 changes documentation and its deterministic contract test only; no React route, rendered surface, browser interaction, keyboard behavior, or accessibility semantics changed.

### Completion Notes List

- Added the four canonical PRD safety guides for reviewing AI-generated IaC, agent JSON, the MCP-equivalent self-hosted interface, and prompt-injection threats.
- Documented safe local invocation, schema and error interpretation, Evidence Law checks, uncertainty handling, human review responsibilities, prompt isolation, redaction, tool restrictions, and explicit forbidden auto-approval patterns.
- Kept examples self-hosted at `localhost` and preserved the local-first raw-artifact boundary; no runtime service or public contract changed.
- Replaced superseded guides with compatibility links, refreshed README/CI navigation, and added deterministic documentation coverage.
- Resolved all five code-review findings by documenting operation-specific HTTP metadata, restoring bounded-response fields, clarifying dual schema validation, protecting generated JSON artifacts, and regression-locking per-guide safety and internal links.
- Resolved all three findings from the second adversarial review by accurately labeling the abbreviated MCP payload, locking truncation and human-review guidance, and validating README/CI navigation as real links with existing targets.
- Resolved all three findings from the third adversarial review by preserving legacy fragment navigation, documenting ordered one-to-one artifact paths, and synchronizing sprint update metadata.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/10-5-ai-safety-documentation.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `docs/ai-safety/agent-api-interface.md`
- `docs/ai-safety/agent-json-output.md`
- `docs/ai-safety/ai-generated-iac-review.md`
- `docs/ai-safety/mcp-server.md`
- `docs/ai-safety/prompt-injection-testing.md`
- `docs/ai-safety/reviewing-ai-generated-iac.md`
- `docs/ci-advisory-consumption.md`
- `docs/security/prompt-injection-threat-model.md`
- `tests/test_infra/test_ai_safety_documentation.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-07-31: Added and regression-locked the canonical self-hosted AI-safety documentation set; moved the story to review.
- 2026-08-03: Resolved all adversarial review findings, strengthened documentation-contract coverage, completed full validation, and moved the story to done.
- 2026-08-03: Resolved all second-review findings, reran focused and full validation, and retained done status.
- 2026-08-03: Resolved all third-review findings with regression-first coverage, completed full validation, and retained done status.
