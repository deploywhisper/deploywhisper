# Story 16.11 review fix — 2026-11-03

Scope: the single P2 finding from `code-review-2026-11-03.md`.

## Correction and regression

`GithubInfraAutomationAdapter._tag_protected` now accumulates rule types across
all qualified applicable rulesets before requiring both update and deletion
restrictions. Identity, active tag target, applicability, bypass restrictions,
rule-list bounds and complete bounded enumeration are still enforced. No new
dependency, wire contract, constructor field or production delivery port.

The new regression failed before the fix for both ruleset orders, then passed
with the fix. It exercises dispatch acceptance with split protections in either
order and 18 rejection cases: for either rule contribution, missing rules,
unrelated rules, branch targeting, evaluate/disabled enforcement, bypass actors,
nonmatching or excluded tags and unsupported pattern semantics. Every rejection
asserts no POST and no possible dispatch. Existing annotated-tag and single-rule
protection regressions remain intact.

An independent read-only reviewer reported no findings. The two tag-protection
tests passed independently with 26 subtests.

## Verification

- `./.venv/bin/python -m unittest tests.test_infra_automation.test_github_adapter tests.test_infra_automation.test_target_transport -q` — 47 tests passed.
- `./.venv/bin/python -m pytest tests/test_infra_automation/test_github_adapter.py tests/test_infra_automation/test_target_transport.py -q` — 47 tests and 270 subtests passed.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` — 709 passed, 1 skipped, 2,316 subtests passed (262.96 seconds).
- `./.venv/bin/mypy --follow-imports=silent --ignore-missing-imports infra_automation/github_contracts.py infra_automation/target_transport.py integrations/github/infra_automation_adapter.py` — no issues in 3 source files.
- `./.venv/bin/bandit -q integrations/github/infra_automation_adapter.py infra_automation/github_contracts.py infra_automation/target_transport.py --severity-level medium --confidence-level medium` — passed.
- `./.venv/bin/ruff check .` — passed.
- `./.venv/bin/ruff format --check .` — 477 files already formatted.
- `git diff --check` — passed before final documentation updates; final result recorded below.

The first sandboxed root run completed 1,486 tests with 10 failures, 93 errors
and 2 skips; local CI stopped at infra-automation (729 tests, the same 10 failures
and 93 errors). These were worker termination/process-tree checks, outside the
adapter path. Process inspection via `ps` was denied in the sandbox. A failing
representative test,
`tests.test_infra_automation.test_engine_cancellation.EngineCancellationTests.test_blocking_handler_does_not_block_tick_or_second_claim`,
passed outside the sandbox in 3.223 seconds. No lifecycle code was changed.

Unrestricted broad reruns were interrupted because the default local Ollama
endpoint caused live inference calls. The final broad reruns use the process-only
environment override `LLM_API_BASE=http://127.0.0.1:1` to keep unmocked narrative
calls on the unavailable-provider/degraded path without a live model. Provider
unit tests still supply their own mocks/configuration. No settings file or
repository defaults changed. Final results are recorded below; the review action item is resolved.

Scratch logs: `/tmp/story16-11-review-fix-{unittest,ci-local,shard}.log`.
The results recorded here are the durable evidence; scratch logs are local only.

## Boundaries

UI validation not applicable: no rendered UI or browser behavior changed.
An optional Linux image check could not run because Docker commands failed in
this session; no new Linux qualification is claimed. Host verification uses the
existing environment. No live GitHub dispatch was performed. The live sandbox
qualification and Packets 2–5 remain outstanding; story status stays in progress.

## Final broad results

Both final commands ran outside the sandbox with only the test-process
`LLM_API_BASE=http://127.0.0.1:1` override described above:

- `./.venv/bin/python -m unittest discover -q` — exit 0, 1,486 tests,
  2 existing skips, 628.908 seconds.
- `bash scripts/ci-local.sh` — exit 0, 2,932 tests across all 10 directories,
  2 existing skips. Infra-automation passed all 729 tests, including the new
  regression, and services passed all 1,232 tests. Repository lint/format,
  dependency consistency, the configured security gate, compileall, skill matrix
  and prompt-injection checks passed as part of the script.

| Directory | Tests | Result |
| --- | ---: | --- |
| analysis | 69 | passed |
| API | 324 | passed |
| CLI | 102 | passed |
| docs | 51 | passed |
| infra | 284 | passed, 1 existing skip |
| infra-automation | 729 | passed |
| LLM | 76 | passed, 1 existing skip |
| models | 22 | passed |
| parsers | 43 | passed |
| services | 1,232 | passed |

Final scratch logs are `/tmp/story16-11-review-fix-unittest-offline.log` and
`/tmp/story16-11-review-fix-ci-local-offline.log`. The initial restricted failures
are retained separately rather than overwritten. The generated Bandit report
was moved to `/tmp/story16-11-review-fix-bandit-report.json`; its medium report
contains the existing B104 sample-address finding in
`services/sample_incident_pack.py`. Touched source files have no medium/high
findings; the configured high/high repository gate passes.

Final `git diff --check` passed. No new dependencies or abstractions were added.
The story review checkbox is resolved; whole-story status remains in progress.
BMad next step remains Packet 1 sandbox qualification in `bmad-dev-story`, then
its later packets and review. No commit or push was performed.
