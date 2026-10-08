# Story 6.2: Benchmark Runner

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a maintainer,
I want a benchmark runner that uses the same analysis core,
So that benchmark results reflect actual product behavior.

## Acceptance Criteria

1. Given a benchmark corpus exists, When the runner executes scenarios, Then it records pass/fail, findings, evidence coverage, Evidence Law violations, latency, and unsupported scenarios. And it does not use a separate scoring path.

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

- [x] [Review][Patch] Runtime artifact reads can bypass corpus containment after validation [services/benchmark_runner_service.py:88]
- [x] [Review][Patch] Unsupported evidence coverage can credit stale selectors after artifact content changes [services/benchmark_runner_service.py:542]
- [x] [Review][Patch] CloudFormation JSON selector scoping can bind logical IDs outside top-level Resources [services/benchmark_runner_service.py:303]
- [x] [Review][Patch] Kubernetes document separators with comments can collapse multi-document selector scope [services/benchmark_runner_service.py:329]
- [x] [Review][Patch] Benchmark error payload summaries omit run-level pass/fail counters [cli/analyze.py:836]
- [x] [Review][Patch] Top-level inline CloudFormation `Resources` maps never match expected selectors [services/benchmark_runner_service.py:318]
- [x] [Review][Patch] CloudFormation YAML selector scoping can bind nested keys inside another resource [services/benchmark_runner_service.py:321]
- [x] [Review][Patch] Duplicate Jenkins stage names ignore parser occurrence order during selector matching [services/benchmark_runner_service.py:388]
- [x] [Review][Patch] Artifact-local selector matching misses supported tools without hard-coded matchers [services/benchmark_runner_service.py:256]
- [x] [Review][Patch] `benchmark run` can still traceback instead of JSON on post-validation load failures [cli/analyze.py:834]
- [x] [Review][Patch] Unscoped parser fallback can still false-pass same-file selectors on the wrong resource [services/benchmark_runner_service.py:267]
- [x] [Review][Patch] One observed evidence item can satisfy multiple distinct expected evidence IDs [services/benchmark_runner_service.py:334]
- [x] [Review][Patch] Non-UTF-8 corpus JSON still escapes structured error handling [services/benchmark_corpus_service.py:247]
- [x] [Review][Patch] YAML resource scoping can attribute selectors from the wrong section or document [services/benchmark_runner_service.py:267]
- [x] [Review][Patch] CloudFormation inline YAML resources can miss valid selector coverage [services/benchmark_runner_service.py:216]
- [x] [Review][Patch] Duplicate Kubernetes kind/name documents can scope evidence to the wrong occurrence [services/benchmark_runner_service.py:301]
- [x] [Review][Patch] Duplicate Ansible task names can scope evidence to the wrong occurrence [services/benchmark_runner_service.py:247]
- [x] [Review][Patch] Same-file selector matching can false-pass evidence and finding coverage [services/benchmark_runner_service.py:207]
- [x] [Review][Patch] Unsupported multi-artifact finding coverage is not tied to the matched artifact [services/benchmark_runner_service.py:312]
- [x] [Review][Patch] Deterministic benchmark profile makes supported scenarios permanently insufficient-context [services/analysis_service.py:491]
- [x] [Review][Patch] Evidence coverage matches raw selectors against summarized evidence text, causing false coverage misses [services/benchmark_runner_service.py:193]
- [x] [Review][Patch] Unsupported scenarios can report full finding coverage without any observed finding [services/benchmark_runner_service.py:305]
- [x] [Review][Patch] Warn expectations pass when the actual verdict is stop, hiding over-severity regressions [services/benchmark_runner_service.py:144]
- [x] [Review][Patch] Failed unsupported scenarios are counted as unsupported instead of failed in the summary [services/benchmark_runner_service.py:482]
- [x] [Review][Patch] Supported parse failures are still scored as unsupported, which can false-pass broken scenarios [services/benchmark_runner_service.py:420]
- [x] [Review][Patch] Benchmark runs are not explicitly isolated from ambient topology/narrative service behavior [services/benchmark_runner_service.py:346]
- [x] [Review][Patch] Evidence coverage can falsely pass selector-level expectations [services/benchmark_runner_service.py:198]
- [x] [Review][Patch] Finding coverage can falsely pass with the wrong finding [services/benchmark_runner_service.py:173]
- [x] [Review][Patch] `benchmark run` exits successfully even when the benchmark result fails [cli/analyze.py:831]
- [x] [Review][Patch] Scenario execution failures are counted as unsupported inputs [services/benchmark_runner_service.py:299]
- [x] [Review][Patch] Benchmark runner bypasses the shared analysis artifact builder [services/benchmark_runner_service.py:321]
- [x] [Review][Patch] Unsupported and partial-parse reporting ignores the submission manifest [services/benchmark_runner_service.py:325]
- [x] [Review][Patch] `benchmark run` can traceback instead of returning structured JSON for invalid corpus inputs [cli/analyze.py:831]
- [x] [Review][Patch] Benchmark runner docs omit the `--path`, error, local-first, and advisory CLI contract [docs/benchmarks/corpus.md:25]

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 6 / Story 6.2 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Red test: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_runner_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_scenario_results -q` failed before implementation because `services.benchmark_runner_service` and `benchmark run` did not exist.
- Focused regression after implementation: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_runner_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_scenario_results -q` passed, 4 tests.
- `./.venv/bin/ruff check .` passed.
- `./.venv/bin/ruff format --check .` passed, 290 files already formatted.
- `./.venv/bin/bandit -q -r services/analysis_service.py services/benchmark_corpus_service.py services/benchmark_runner_service.py cli/analyze.py` passed.
- `./.venv/bin/python cli.py benchmark validate-corpus` passed, 3 valid scenarios.
- Initial implementation CLI smoke: `./.venv/bin/python cli.py benchmark run` produced `passed=true`, 3 passed scenarios, 0 failed scenarios, 0 unsupported scenarios before review-fix strict matching was added.
- Review fix focused regression: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_runner_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_scenario_results tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_exits_nonzero_for_failed_result -q` passed, 8 tests.
- Review fix CLI verification: `./.venv/bin/python cli.py benchmark run` exited `1` with `passed=false`, 0 passed scenarios, 3 failed scenarios, 0 unsupported scenarios, proving the runner now reports current benchmark gaps honestly instead of false-green coverage.
- `./.venv/bin/python -m unittest discover -q` passed, 447 tests, 1 skipped.
- `bash scripts/ci-local.sh` passed.
- Shared-core review fix focused regression: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_runner_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_scenario_results tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_exits_nonzero_for_failed_result tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_invalid_corpus_as_json -q` passed, 10 tests.
- Shared-core review fix CLI verification: `./.venv/bin/python cli.py benchmark validate-corpus` passed with 3 valid scenarios, and `./.venv/bin/python cli.py benchmark run` exited `1` with structured JSON, `passed=false`, 0 passed scenarios, 3 failed scenarios, 0 unsupported scenarios.
- Shared-core review fix quality checks: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed, 290 files already formatted; `./.venv/bin/bandit -q -r services/analysis_service.py services/benchmark_corpus_service.py services/benchmark_runner_service.py cli/analyze.py` passed.
- Shared-core review fix full validation: `./.venv/bin/python -m unittest discover -q` passed, 447 tests, 1 skipped; `bash scripts/ci-local.sh` passed.
- Reviewer findings fix focused regression: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_runner_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_scenario_results tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_exits_nonzero_for_failed_result tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_invalid_corpus_as_json -q` passed, 12 tests.
- Reviewer findings fix quality checks: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed, 290 files already formatted; `./.venv/bin/bandit -q -r analysis/risk_engine.py analysis/risk_scorer.py services/analysis_service.py services/benchmark_runner_service.py tests/test_services/test_benchmark_runner_service.py` passed.
- Reviewer findings fix CLI verification: `./.venv/bin/python cli.py benchmark run` exited `1` with structured JSON, `passed=false`, 0 passed scenarios, 3 failed scenarios, 0 unsupported scenarios, and deterministic benchmark-profile latency.
- Reviewer findings fix full validation: `./.venv/bin/python -m unittest discover -q` passed, 447 tests, 1 skipped.
- Reviewer findings fix local CI: `bash scripts/ci-local.sh` passed.
- UI validation not applicable; no UI route/component/rendered surface changed.
- Rerun code review verification: `./.venv/bin/python cli.py benchmark run` exited `1` with structured JSON, `passed=false`, 0 passed scenarios, 3 failed scenarios, 0 unsupported scenarios. All bundled scenarios reported `actual_verdict="insufficient_context"` and `evidence_coverage=0.0`, confirming new patch findings.
- Final reviewer-finding fix focused regression: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_runner_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_scenario_results tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_exits_nonzero_for_failed_result tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_invalid_corpus_as_json -q` passed, 15 tests.
- Final reviewer-finding fix CLI verification: `./.venv/bin/python cli.py benchmark run` exited `1` with structured JSON, `passed=false`, 0 passed scenarios, 3 failed scenarios, 0 unsupported scenarios. Supported scenarios now report `actual_verdict="warn"` and `evidence_coverage=1.0`; remaining failures are explicit expected-finding coverage misses.
- Final reviewer-finding fix quality checks: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed, 290 files already formatted; `./.venv/bin/bandit -q -r analysis/risk_engine.py analysis/risk_scorer.py services/analysis_service.py services/benchmark_runner_service.py tests/test_services/test_benchmark_runner_service.py` passed.
- Final reviewer-finding fix full validation: `./.venv/bin/python -m unittest discover -q` passed, 447 tests, 1 skipped.
- Final reviewer-finding fix local CI: `bash scripts/ci-local.sh` passed.
- Rerun code review layers: Acceptance Auditor approved Story 6.2; Blind Hunter and Edge Case Hunter found two patch findings covering same-file selector false passes and unsupported multi-artifact attribution. One low CLI shape-test concern was dismissed because explicit CLI pass/fail and invalid-corpus tests already cover exit behavior while bundled corpus failure remains an allowed honest benchmark outcome.
- Latest reviewer-finding fix focused regression: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_runner_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_scenario_results tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_exits_nonzero_for_failed_result tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_invalid_corpus_as_json -q` passed, 17 tests.
- Latest reviewer-finding fix quality checks: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed, 290 files already formatted; `./.venv/bin/bandit -q -r analysis/risk_engine.py analysis/risk_scorer.py services/analysis_service.py services/benchmark_runner_service.py tests/test_services/test_benchmark_runner_service.py` passed.
- Latest reviewer-finding fix CLI verification: `./.venv/bin/python cli.py benchmark run` exited `1` with structured JSON, `passed=false`, 0 passed scenarios, 3 failed scenarios, 0 unsupported scenarios. Supported scenarios report `actual_verdict="warn"` and `evidence_coverage=1.0`; remaining failures are explicit expected-finding coverage misses.
- Latest reviewer-finding fix full validation: `./.venv/bin/python -m unittest discover -q` passed, 447 tests, 1 skipped.
- Latest reviewer-finding fix local CI: `bash scripts/ci-local.sh` passed.
- Latest rerun reviewer-finding fix focused regression: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_runner_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_scenario_results tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_exits_nonzero_for_failed_result tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_invalid_corpus_as_json tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_loader_failure_as_json tests.test_cli.test_analyze.AnalyzeCliTests.test_github_init_command_uses_shared_init_service -q` passed, 20 tests.
- Latest rerun reviewer-finding fix quality checks: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed, 290 files already formatted; `./.venv/bin/bandit -q -r analysis/risk_engine.py analysis/risk_scorer.py services/analysis_service.py services/benchmark_runner_service.py cli/analyze.py tests/test_services/test_benchmark_runner_service.py tests/test_cli/test_analyze.py` passed.
- Latest rerun reviewer-finding fix CLI verification: `./.venv/bin/python cli.py benchmark run` exited `1` with structured JSON, `passed=false`, 0 passed scenarios, 3 failed scenarios, 0 unsupported scenarios. Supported scenarios report `actual_verdict="warn"` and `evidence_coverage=1.0`; remaining failures are explicit expected-finding coverage misses.
- Latest rerun reviewer-finding fix full validation: `./.venv/bin/python -m unittest discover -q` passed, 447 tests, 1 skipped.
- Latest rerun reviewer-finding fix local CI: `bash scripts/ci-local.sh` passed, including Ruff, format, pip check, Bandit, parser golden coverage, and full unit discovery.
- Edge-case reviewer-finding fix focused regression: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_runner_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_scenario_results tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_exits_nonzero_for_failed_result tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_invalid_corpus_as_json tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_loader_failure_as_json tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_non_utf8_corpus_json_as_json -q` passed, 22 tests.
- Edge-case reviewer-finding fix quality checks: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed, 290 files already formatted; `./.venv/bin/bandit -q -r analysis/risk_engine.py analysis/risk_scorer.py services/analysis_service.py services/benchmark_corpus_service.py services/benchmark_runner_service.py cli/analyze.py tests/test_services/test_benchmark_runner_service.py tests/test_cli/test_analyze.py` passed.
- Edge-case reviewer-finding fix CLI verification: `./.venv/bin/python cli.py benchmark run` exited `1` with structured JSON, `passed=false`, 0 passed scenarios, 3 failed scenarios, 0 unsupported scenarios. Stricter one-to-one evidence matching now reports partial evidence coverage where bundled expectations require multiple evidence selectors from fewer observed evidence items.
- Edge-case reviewer-finding fix full validation: `./.venv/bin/python -m unittest discover -q` passed, 447 tests, 1 skipped.
- Edge-case reviewer-finding fix local CI: `bash scripts/ci-local.sh` passed, including Ruff, format, pip check, Bandit, parser golden coverage, and full unit discovery.
- Latest bmad-code-review rerun layers: Acceptance Auditor reported no Story 6.2 AC violations; Blind Hunter and Edge Case Hunter surfaced one actionable YAML scoping patch plus several dismissed findings already covered by corpus validation, status-based summary counts, deterministic benchmark scope, or intentionally conservative one-to-one matching.
- Latest bmad-code-review patch fix focused regression: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_runner_service -q` passed, 19 tests.
- Latest bmad-code-review patch fix quality checks: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed, 290 files already formatted; `./.venv/bin/bandit -q -r analysis/risk_engine.py analysis/risk_scorer.py services/analysis_service.py services/benchmark_corpus_service.py services/benchmark_runner_service.py cli/analyze.py tests/test_services/test_benchmark_runner_service.py tests/test_cli/test_analyze.py` passed.
- Latest bmad-code-review patch fix CLI verification: `./.venv/bin/python cli.py benchmark run` exited `1` with structured JSON, `passed=false`, 0 passed scenarios, 3 failed scenarios, 0 unsupported scenarios. Evidence Law was satisfied and remaining failures are explicit missing expected coverage IDs.
- Latest bmad-code-review patch fix full validation: `./.venv/bin/python -m unittest discover -q` passed, 447 tests, 1 skipped.
- Latest bmad-code-review patch fix local CI: `bash scripts/ci-local.sh` passed, including Ruff, format, pip check, Bandit, parser golden coverage, and full unit discovery.
- Final bmad-code-review rerun layers: Acceptance Auditor reported no Story 6.2 AC violations; Blind Hunter findings for artifact containment and verdict normalization were dismissed as covered by validated corpus loading and intentional benchmark verdict mapping; Edge Case Hunter findings for inline CloudFormation YAML, duplicate Kubernetes kind/name, and duplicate Ansible task names were fixed.
- Final bmad-code-review patch fix focused regression: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_runner_service -q` passed, 22 tests.
- Final bmad-code-review patch fix quality checks: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed, 290 files already formatted; `./.venv/bin/bandit -q -r analysis/risk_engine.py analysis/risk_scorer.py services/analysis_service.py services/benchmark_corpus_service.py services/benchmark_runner_service.py cli/analyze.py tests/test_services/test_benchmark_runner_service.py tests/test_cli/test_analyze.py` passed.
- Final bmad-code-review patch fix CLI verification: `./.venv/bin/python cli.py benchmark run` exited `1` with structured JSON, `passed=false`, 0 passed scenarios, 3 failed scenarios, 0 unsupported scenarios. Evidence Law was satisfied and remaining failures are explicit missing expected coverage IDs.
- Final bmad-code-review patch fix full validation: `./.venv/bin/python -m unittest discover -q` passed, 447 tests, 1 skipped.
- Final bmad-code-review patch fix local CI: `bash scripts/ci-local.sh` passed, including Ruff, format, pip check, Bandit, parser golden coverage, and full unit discovery.
- Rerun bmad-code-review layers: Acceptance Auditor reported no Story 6.2 AC violations; Blind Hunter and Edge Case Hunter produced actionable hardening findings for runtime artifact containment, unsupported selector credit, CloudFormation JSON scoping, Kubernetes comment separators, loader path checks, and CLI error summary shape. The recurring corpus-containment concern was fixed defensively even though normal execution already validates the corpus before loading.
- Rerun bmad-code-review patch fix focused regression: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_runner_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_scenario_results tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_exits_nonzero_for_failed_result tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_invalid_corpus_as_json tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_loader_failure_as_json tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_non_utf8_corpus_json_as_json -q` passed, 31 tests.
- Rerun bmad-code-review patch fix quality checks: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed, 290 files already formatted; `./.venv/bin/bandit -q -r analysis/risk_engine.py analysis/risk_scorer.py services/analysis_service.py services/benchmark_corpus_service.py services/benchmark_runner_service.py cli/analyze.py tests/test_services/test_benchmark_runner_service.py tests/test_cli/test_analyze.py` passed.
- Rerun bmad-code-review patch fix CLI verification: `./.venv/bin/python cli.py benchmark run` exited `1` with structured JSON, `passed=false`, 0 passed scenarios, 3 failed scenarios, 0 unsupported scenarios. Evidence Law was satisfied and remaining failures are explicit expected coverage misses.
- Rerun bmad-code-review patch fix full validation: `./.venv/bin/python -m unittest discover -q` passed, 447 tests, 1 skipped.
- Rerun bmad-code-review patch fix local CI: `bash scripts/ci-local.sh` passed, including Ruff, format, pip check, Bandit, parser golden coverage, and full unit discovery.
- Reviewer findings fix focused regression: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_runner_service -q` passed, 29 tests.
- Reviewer findings fix CLI regression: `./.venv/bin/python -m unittest tests.test_services.test_benchmark_runner_service tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_scenario_results tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_exits_nonzero_for_failed_result tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_invalid_corpus_as_json tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_loader_failure_as_json tests.test_cli.test_analyze.AnalyzeCliTests.test_benchmark_run_command_reports_non_utf8_corpus_json_as_json -q` passed, 34 tests.
- Reviewer findings fix quality checks: `./.venv/bin/ruff check .` passed; `./.venv/bin/ruff format --check .` passed, 290 files already formatted; `./.venv/bin/bandit -q -r parsers/cloudformation_parser.py services/benchmark_runner_service.py tests/test_services/test_benchmark_runner_service.py` passed.
- Reviewer findings fix CLI verification: `./.venv/bin/python cli.py benchmark run` exited `1` with structured JSON, `passed=false`, 0 passed scenarios, 3 failed scenarios, 0 unsupported scenarios. Evidence Law was satisfied and remaining failures are explicit expected coverage misses.
- Reviewer findings fix full validation: `./.venv/bin/python -m unittest discover -q` passed, 447 tests, 1 skipped.
- Reviewer findings fix local CI: `bash scripts/ci-local.sh` passed, including Ruff, format, pip check, Bandit, parser golden coverage, migration checks, and full unit discovery.
- UI validation not applicable; no UI route/component/rendered surface changed.

### Completion Notes List

- Added a benchmark runner service that validates and loads the corpus, replays each scenario through the shared parse/evidence/scoring/finding/Evidence Law path, and records pass/fail, findings, coverage, Evidence Law violations, latency, and unsupported reasons.
- Exposed a public context-completeness helper from the analysis service so benchmark execution can reuse the same context signal without importing private helpers.
- Added the `benchmark run` CLI command with optional `--path` and JSON output.
- Updated benchmark documentation with runner usage and output fields.
- Added deterministic service and CLI regression coverage, including tests for expected unsupported scenarios and verifying the runner calls the shared `evaluate_parse_batch` evaluator once per scenario.
- Fixed review findings by requiring selector-level evidence coverage, expected finding/title/evidence-ref matching, nonzero CLI exit on failed benchmark results, and separate execution-error reporting that does not inflate unsupported counts.
- Fixed shared-core review findings by routing benchmark execution through `build_analysis_artifacts`, carrying submission-manifest coverage into benchmark results, preserving partial input warnings without counting mixed scenarios as fully unsupported, returning structured JSON for invalid corpus CLI inputs, and documenting the full local-first advisory `benchmark run` contract.
- Fixed rerun review findings by treating accepted parser failures as failed/partial benchmark runs rather than unsupported passes, and by running benchmarks through an explicit deterministic profile that skips ambient topology, incident lookup, narrative generation, and LLM scoring assists while preserving the shared parser/evidence/scoring/finding path.
- Fixed final rerun review findings by scoring deterministic benchmark context against enabled dimensions only, matching expected evidence selectors against raw artifact text, emitting observed unsupported findings, requiring exact benchmark verdict matches, and counting failed unsupported expectations as failed outcomes.
- Fixed latest review findings by limiting selector matching to each observed evidence item plus its parser-local change text, and by requiring unsupported synthetic findings to carry only evidence refs from the matched unsupported artifact.
- Fixed latest rerun review findings by allowing unscoped parser evidence selectors to match the artifact body when no tool-specific scoped extractor exists, returning structured JSON for post-validation benchmark loader failures, and keeping the touched CLI tests Bandit-clean.
- Fixed edge-case reviewer findings by adding scoped CloudFormation and Ansible selector matching, enforcing one-to-one observed-to-expected evidence coverage, and returning structured benchmark JSON for non-UTF-8 corpus JSON files.
- Fixed latest bmad-code-review finding by constraining CloudFormation selector extraction to the top-level `Resources` mapping and selecting Kubernetes documents by parsed `metadata.name` instead of any nested `name:` field.
- Fixed final bmad-code-review findings by matching inline CloudFormation resource YAML and using parser change occurrence order to disambiguate duplicate Kubernetes and Ansible resources without changing parser resource IDs.
- Fixed rerun bmad-code-review findings by defensively rechecking artifact and scenario paths at execution/load time, requiring unsupported selector credit against current artifact text, scoping CloudFormation JSON selectors to top-level `Resources`, accepting Kubernetes document separators with comments, and preserving run-level summary counters in CLI error JSON.
- Fixed reviewer findings by loading CloudFormation templates through the shared CloudFormation SafeLoader before matching direct `Resources` entries, covering top-level inline resource maps and avoiding nested-resource key matches, and by using parser occurrence order for duplicate Jenkins stage selector scope.

### File List

- `services/analysis_service.py`
- `analysis/risk_engine.py`
- `analysis/risk_scorer.py`
- `services/benchmark_corpus_service.py`
- `services/benchmark_runner_service.py`
- `parsers/cloudformation_parser.py`
- `cli/analyze.py`
- `docs/benchmarks/corpus.md`
- `tests/test_services/test_benchmark_runner_service.py`
- `tests/test_cli/test_analyze.py`
- `_bmad-output/implementation-artifacts/6-2-benchmark-runner.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-06-01: Implemented benchmark runner service and CLI, added deterministic tests, updated docs, and validated full local unit suite.
- 2026-06-02: Fixed review findings for strict expected evidence/finding matching, failed-result CLI exit status, and execution-error classification; validated with focused regressions and full local CI.
- 2026-06-02: Fixed shared-core review findings for artifact-builder reuse, manifest-based partial/unsupported reporting, invalid-corpus JSON errors, and benchmark runner documentation; validated with focused regressions, full unit suite, and local CI.
- 2026-06-02: Fixed rerun review findings for supported parser-failure classification and deterministic benchmark-profile isolation; validated with focused regressions, Ruff, Bandit, CLI smoke, and full unit suite.
- 2026-06-02: Fixed final reviewer findings for deterministic context scoring, selector coverage, unsupported finding coverage, exact verdict matching, and failed unsupported summary counts; validated with focused regressions, Ruff, Bandit, full unit suite, and local CI.
- 2026-06-02: Fixed latest reviewer findings for evidence-local selector matching and artifact-specific unsupported finding attribution; validated with focused regressions, Ruff, Bandit, full unit suite, and local CI.
- 2026-06-02: Fixed latest rerun reviewer findings for unscoped parser selector matching and post-validation benchmark loader JSON errors; validated with focused regressions, Ruff, Bandit, full unit suite, CLI smoke, and local CI.
- 2026-06-02: Fixed edge-case reviewer findings for scoped CloudFormation/Ansible selector matching, one-to-one evidence coverage, and non-UTF-8 corpus JSON error handling; validated with focused regressions, Ruff, Bandit, full unit suite, CLI smoke, and local CI.
- 2026-06-02: Fixed final bmad-code-review edge findings for inline CloudFormation YAML and duplicate Kubernetes/Ansible occurrence scoping; validated with focused regressions, Ruff, Bandit, full unit suite, CLI smoke, and local CI.
- 2026-06-02: Fixed rerun bmad-code-review findings for runtime corpus containment, unsupported selector credit, CloudFormation JSON scoping, Kubernetes comment separators, and CLI error summary counters; validated with focused regressions, Ruff, Bandit, full unit suite, CLI smoke, and local CI.
- 2026-06-03: Fixed rerun reviewer findings for top-level inline CloudFormation `Resources` maps, nested CloudFormation YAML key scoping, and duplicate Jenkins stage occurrence scoping; validated with focused regressions, Ruff, Bandit, full unit suite, CLI smoke, and local CI.

## Course Correction — 2026-10-07

Status reconciled to `done` against merged delivery [PR #80](https://github.com/deploywhisper/deploywhisper/pull/80), the completed task/review-fix records above, and the accepted v1.4.0 baseline in `docs/verification/v1.4.0-release.json`. This is administrative closeout of existing delivery, not a claim that a new implementation review or application test run occurred today. Historical review attempts remain intact. See `../planning-artifacts/sprint-change-proposal-2026-10-07-v1.4.0-status-reconciliation.md`.
