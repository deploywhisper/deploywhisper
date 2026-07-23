# Story 9.3: Skill Test Harness

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a maintainer,
I want every verified/core Skill tested against deterministic scenarios,
So that Skills do not add ungrounded guidance.

## Acceptance Criteria

1. Given a Skill declares test scenarios, When the harness runs, Then expected triggers, outputs, evidence assumptions, and safety constraints are verified. And verified/core trust levels require passing tests.

### Requirement Traceability

- Primary PRD requirements: Epic 9 coverage: SKL-01..09, ADM-05, DOC-13, NFR-OSS-05.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 9 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Count coverage categories only when their scenarios actually pass [services/skill_test_harness_service.py:244]
- [x] [Review][Patch] Match full-path triggers exactly like the runtime resolver [services/skill_test_harness_service.py:216]
- [x] [Review][Patch] Do not report a synthetic suite-coverage sentinel as a failed declared scenario [services/skill_test_harness_service.py:300]
- [x] [Review][Patch] Keep suite-level coverage failures out of the public declared-scenarios list [services/skill_test_harness_service.py:340]
- [x] [Review][Patch] Do not assume every future built-in Skill requires verified/core gating [tests/test_services/test_skill_test_harness_service.py:293]

## Dev Notes

### Epic Context

- Epic: 9. Skills Ecosystem
- Epic goal: Grow community knowledge safely through non-executable, tested, versioned Skills.
- Epic coverage: SKL-01..09, ADM-05, DOC-13, NFR-OSS-05

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 9 / Story 9.3 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

OpenAI Codex (GPT-5.4)

### Debug Log References

- RED: `./.venv/bin/python -m unittest tests.test_services.test_skill_test_harness_service -q` — failed with 30 missing coverage/trust result errors, proving the existing harness did not expose Story 9.3's required contract.
- RED integration: focused API/CLI pytest run — failed because the test-results API omitted coverage and trust decisions and the CLI returned success for an unsatisfied verified/core trust gate.
- GREEN focused: `./.venv/bin/python -m pytest tests/test_services/test_skill_test_harness_service.py tests/test_api/test_skills.py tests/test_cli/test_analyze.py -q --tb=short` — 100 tests and 28 subtests passed.
- Skill catalog: `./.venv/bin/python cli.py skill test` — all 28 built-in verified/core Skill suites passed with complete trigger, output, evidence-assumption, and safety-constraint coverage.
- CI parity, services: the first exact shard found two new test fixtures missing the required contributor evidence summary; after fixing those fixtures, `./.venv/bin/python -m pytest tests/test_services --cov=. --cov-report=xml:/tmp/coverage-services.xml --cov-report=term-missing -v --tb=short` passed 838 tests and 171 subtests.
- CI parity, API/CLI/infra: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra --cov=. --cov-report=xml:/tmp/coverage-api-cli-infra.xml --cov-report=term-missing -v --tb=short` passed 339 tests and 15 subtests.
- FULL: `bash scripts/ci-local.sh` — Ruff lint and repo-wide formatting, dependency validation, Bandit high/high gate, compileall, all 28 Skill suites, and explicit per-directory discovery passed; 838 Python tests passed.
- REVIEW RED: the three reviewer regressions failed before the patch, proving that failed scenarios could claim coverage, full-path trigger matching diverged from runtime behavior, and the synthetic coverage sentinel leaked into declared-scenario failures.
- REVIEW GREEN focused: `./.venv/bin/python -m pytest tests/test_services/test_skill_test_harness_service.py tests/test_api/test_skills.py tests/test_cli/test_analyze.py -q --tb=short` — 102 tests and 28 subtests passed.
- REVIEW CI parity, services: `COVERAGE_FILE=/tmp/deploywhisper-story-9-3-review-services.coverage ./.venv/bin/python -m pytest tests/test_services --cov=. --cov-report=xml:/tmp/coverage-services-review.xml --cov-report=term-missing -v --tb=short` — 840 tests and 171 subtests passed.
- REVIEW CI parity, API/CLI/infra: `COVERAGE_FILE=/tmp/deploywhisper-story-9-3-review-api-cli-infra.coverage ./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra --cov=. --cov-report=xml:/tmp/coverage-api-cli-infra-review.xml --cov-report=term-missing -v --tb=short` — 339 tests and 15 subtests passed.
- REVIEW FULL: `bash scripts/ci-local.sh` — all quality gates and 840 Python tests passed.
- RE-REVIEW RED: `./.venv/bin/python -m pytest tests/test_services/test_skill_test_harness_service.py -q --tb=short` — failed because incomplete verified coverage still added a synthetic second scenario.
- RE-REVIEW GREEN focused: `./.venv/bin/python -m pytest tests/test_services/test_skill_test_harness_service.py tests/test_api/test_skills.py tests/test_cli/test_analyze.py -q --tb=short` — 102 tests and 28 subtests passed.
- RE-REVIEW CI parity, services: `COVERAGE_FILE=/tmp/deploywhisper-story-9-3-rereview-services.coverage ./.venv/bin/python -m pytest tests/test_services --cov=. --cov-report=xml:/tmp/coverage-services-rereview.xml --cov-report=term-missing -v --tb=short` — 840 tests and 171 subtests passed.
- RE-REVIEW CI parity, API/CLI/infra: `COVERAGE_FILE=/tmp/deploywhisper-story-9-3-rereview-api-cli-infra.coverage ./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra --cov=. --cov-report=xml:/tmp/coverage-api-cli-infra-rereview.xml --cov-report=term-missing -v --tb=short` — 339 tests and 15 subtests passed.
- RE-REVIEW FULL: after applying the required Ruff formatting, `bash scripts/ci-local.sh` passed all quality gates and 840 Python tests.

### Completion Notes List

- Added explicit suite coverage decisions for expected triggers, expected guidance outputs, evidence assumptions, and negative-selection safety constraints.
- Added a trust-level requirement result: verified/core Skills now require complete deterministic coverage and every declared scenario to pass; incomplete high-trust suites become failing results with actionable reasons.
- Preserved experimental/deprecated behavior: scenarios still execute and failures remain nonzero, while incomplete coverage alone does not claim those trust levels are invalid.
- Exposed coverage and trust decisions through the public test-results API and JSON CLI, and made human-readable CLI output explain trust-gate failures.
- Added negative safety scenarios for the seven foundational core Skills that previously had only positive selection scenarios.
- Updated authoring, harness, and registry API documentation with the completed Story 9.3 contract.
- Resolved all three code-review findings: coverage now derives only from passing scenarios, full-path trigger matching mirrors runtime resolution, and synthetic coverage failures are not described as failed declared scenarios.
- Resolved the fresh code-review findings: trust-gate failures now affect suite status without entering the declared-scenarios list, and catalog assertions derive enforcement from each Skill's trust level.
- UI validation not applicable: no React route, component, browser interaction, keyboard behavior, or accessibility semantics changed.

### File List

- `_bmad-output/implementation-artifacts/9-3-skill-test-harness.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `api/schemas.py`
- `cli/analyze.py`
- `docs/skills/authoring-guide.md`
- `docs/skills/registry-api.md`
- `docs/skills/test-harness.md`
- `services/skill_test_harness_service.py`
- `tests/skill-tests/ansible/non-match.json`
- `tests/skill-tests/cloudformation/non-match.json`
- `tests/skill-tests/docker/non-match.json`
- `tests/skill-tests/git/non-match.json`
- `tests/skill-tests/jenkins/non-match.json`
- `tests/skill-tests/kubernetes/non-match.json`
- `tests/skill-tests/terraform/non-match.json`
- `tests/test_api/test_skills.py`
- `tests/test_cli/test_analyze.py`
- `tests/test_services/test_skill_test_harness_service.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-07-23: Completed Story 9.3 with deterministic coverage classification, verified/core trust enforcement, public API/CLI results, negative safety fixtures, and CI-parity regression coverage.
- 2026-07-23: Addressed code review findings — 3 items resolved and verified with focused, shard-level, and full local CI coverage.
- 2026-07-23: Addressed fresh code review findings — 2 additional items resolved and verified through focused, shard-level, and full local CI coverage.
