# Story 6.1: Benchmark Corpus v1

Status: review

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a maintainer,
I want a public benchmark corpus,
So that risk detection quality is measurable and inspectable.

## Acceptance Criteria

1. Given benchmark scenarios are added, When corpus validation runs, Then each scenario includes artifacts, expected findings, expected evidence, expected verdict rationale, labels, and licensing metadata. And unsafe or non-public samples are rejected.

### Requirement Traceability

- Primary PRD requirements: Epic 6 coverage: BEN-01..11, INC-09..11, HIS-04, HIS-06..07, NFR-PERF-01..05, DOC-14, DOC-27.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 6 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Validator does not scan all scenario text for unsafe or non-public content [services/benchmark_corpus_service.py:237]
- [x] [Review][Patch] Nested scenario fields accept whitespace-only evidence and metadata text [services/benchmark_corpus_service.py:71]
- [x] [Review][Patch] Validator accepts evidence selectors that are not present in referenced artifacts [services/benchmark_corpus_service.py:345]

## Dev Notes

### Epic Context

- Epic: 6. Benchmarks, Calibration, and Honest Failure Reporting
- Epic goal: Prove trust claims with measurable, repeatable evidence.
- Epic coverage: BEN-01..11, INC-09..11, HIS-04, HIS-06..07, NFR-PERF-01..05, DOC-14, DOC-27

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 6 / Story 6.1 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5.4 Codex

### Debug Log References

- Red phase: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_corpus_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_validate_corpus_command_reports_public_corpus_status -q` failed because `services.benchmark_corpus_service` and `benchmark validate-corpus` did not exist.
- Green phase: added `services.benchmark_corpus_service`, bundled `benchmarks/corpus/v1`, and CLI `benchmark validate-corpus` command.
- Focused validation: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_corpus_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_validate_corpus_command_reports_public_corpus_status -q` passed, 5 tests OK.
- Corpus validation: `./.venv/bin/python cli.py benchmark validate-corpus` passed with `valid=true`, 3 scenarios, and no errors.
- Lint/security/regression validation:
  - `./.venv/bin/ruff check .` passed.
  - `./.venv/bin/ruff format --check .` passed.
  - `./.venv/bin/bandit -q -r services/benchmark_corpus_service.py cli/analyze.py` passed.
  - `./.venv/bin/python -m unittest discover -q` passed: 447 tests OK, 1 skipped.
- Review-fix red phase: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_corpus_service.BenchmarkCorpusServiceTests.test_validation_rejects_unsafe_nested_scenario_text tests.test_services.test_benchmark_corpus_service.BenchmarkCorpusServiceTests.test_validation_rejects_whitespace_only_nested_text -q` failed against the reviewed implementation, reproducing both patch findings.
- Review-fix focused validation:
  - `./.venv/bin/python -m unittest tests.test_services.test_benchmark_corpus_service.BenchmarkCorpusServiceTests.test_validation_rejects_unsafe_nested_scenario_text tests.test_services.test_benchmark_corpus_service.BenchmarkCorpusServiceTests.test_validation_rejects_whitespace_only_nested_text -q` passed, 2 tests OK.
  - `./.venv/bin/python -m unittest tests.test_services.test_benchmark_corpus_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_validate_corpus_command_reports_public_corpus_status -q` passed, 7 tests OK.
- Review-fix corpus/lint/security/regression validation:
  - `./.venv/bin/ruff check .` passed.
  - `./.venv/bin/ruff format --check .` passed.
  - `./.venv/bin/bandit -q -r services/benchmark_corpus_service.py cli/analyze.py` passed.
  - `./.venv/bin/python cli.py benchmark validate-corpus` passed with `valid=true`, 3 scenarios, and no errors.
  - `./.venv/bin/python -m unittest discover -q` passed: 447 tests OK, 1 skipped.
- Selector review-fix red phase: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_corpus_service.BenchmarkCorpusServiceTests.test_validation_rejects_evidence_selector_missing_from_artifact -q` failed against the reviewed implementation, reproducing the selector validation finding.
- Selector review-fix focused validation:
  - `./.venv/bin/python -m unittest tests.test_services.test_benchmark_corpus_service.BenchmarkCorpusServiceTests.test_validation_rejects_evidence_selector_missing_from_artifact tests.test_services.test_benchmark_corpus_service.BenchmarkCorpusServiceTests.test_bundled_v1_corpus_is_public_and_valid -q` passed, 2 tests OK.
  - `./.venv/bin/python -m unittest tests.test_services.test_benchmark_corpus_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_validate_corpus_command_reports_public_corpus_status -q` passed, 8 tests OK.
- Selector review-fix corpus/lint/security/regression validation:
  - `./.venv/bin/ruff check .` passed.
  - `./.venv/bin/ruff format --check .` passed.
  - `./.venv/bin/bandit -q -r services/benchmark_corpus_service.py cli/analyze.py` passed.
  - `./.venv/bin/python cli.py benchmark validate-corpus` passed with `valid=true`, 3 scenarios, and no errors.
  - `./.venv/bin/python -m unittest discover -q` passed: 447 tests OK, 1 skipped.
- UI validation not applicable: no UI route, retired Python UI component, rendered page, browser interaction, keyboard behavior, or accessibility semantics changed.

### Completion Notes List

- Added public benchmark corpus v1 with three synthetic scenarios covering Terraform public SSH exposure, Kubernetes zero-replica rollout risk, and Jenkins production auto-apply workflow risk.
- Added deterministic corpus validation that enforces scenario artifacts, expected findings, expected evidence, expected verdict rationale, labels, public licensing metadata, and safety metadata.
- Added unsafe/non-public rejection for disallowed licenses, non-public sample flags, unsafe safety declarations, secret-like artifact content, non-public markers, path traversal, missing artifacts, duplicate IDs, and unknown evidence references.
- Hardened artifact scanning so rejected escaping paths are reported but never read during safety scans.
- Hardened scenario metadata scanning so unsafe and non-public markers are rejected across all nested scenario strings, including expected findings and expected evidence.
- Hardened nested required text validation so artifact metadata, expected evidence, expected findings, license metadata, manifest scenario paths, and evidence ID references reject whitespace-only values.
- Hardened expected evidence validation so each selector must be present in its referenced artifact, and aligned the Terraform benchmark fixture formatting with its selectors.
- Added `python cli.py benchmark validate-corpus` so maintainers can run corpus validation from the existing CLI surface.
- Added service and CLI regression tests plus benchmark corpus documentation.
- No new dependencies were introduced.

### File List

- `_bmad-output/implementation-artifacts/6-1-benchmark-corpus-v1.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `benchmarks/corpus/v1/manifest.json`
- `benchmarks/corpus/v1/scenarios/jenkins-prod-auto-apply/artifacts/Jenkinsfile`
- `benchmarks/corpus/v1/scenarios/jenkins-prod-auto-apply/scenario.json`
- `benchmarks/corpus/v1/scenarios/kubernetes-zero-replicas/artifacts/deployment.yaml`
- `benchmarks/corpus/v1/scenarios/kubernetes-zero-replicas/scenario.json`
- `benchmarks/corpus/v1/scenarios/terraform-public-ssh/artifacts/main.tf`
- `benchmarks/corpus/v1/scenarios/terraform-public-ssh/scenario.json`
- `cli/analyze.py`
- `docs/benchmarks/corpus.md`
- `services/benchmark_corpus_service.py`
- `tests/test_cli/test_analyze.py`
- `tests/test_services/test_benchmark_corpus_service.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-06-01: Implemented public benchmark corpus v1, deterministic corpus validation, CLI validation command, docs, and regression coverage.
- 2026-06-01: Fixed review findings for nested unsafe/non-public scenario text scanning and whitespace-only nested metadata validation.
- 2026-06-01: Fixed review finding for expected evidence selectors that were not verified against referenced artifacts.
