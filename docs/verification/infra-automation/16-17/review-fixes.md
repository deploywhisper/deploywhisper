# Story 16.17 review findings — fixes and validation

Scope: resolve CR17-1 and CR17-2 from the formal review of `51bb952`.
Both findings are resolved. All final required validation commands passed; story status is `review`.

## CR17-1: retain checked machine time across business rollback

`_check_clock` now advances the existing shared clock and registers its checked
observation in the authorized operation. `authorized_session` places business
writes behind a materialized savepoint inside its existing `BEGIN IMMEDIATE`.
Successful effects commit with the clock atomically. On rejection, filesystem
compensation runs while ownership is retained, the business savepoint rolls
back, and only registered deny-only observations commit under the same outer
SQLite reservation. Success cleanup callbacks do not run for that rejected
operation. No second connection or released-lock interval is introduced.

The new tests cover:

- Actual signed admission and engine starts on two different runs: a later
  successful effect prevents an earlier effect on the other run.
- Key expiry denial, then a backwards clock step with no later signed request:
  the checked time survives, and stale authority remains denied.
- Ordinary business failure after a checked observation: business writes vanish
  while the clock remains.
- Raw SQL changes plus an ORM flush error: unrelated data rolls back while the
  observation persists. An independent connection cannot acquire the SQLite
  write reservation during either clock write.
- Observation-storage failure: the operation fails, business writes vanish,
  successful cleanup is skipped, and no durable clock observation is claimed.
- Swallowed inner savepoint failures followed by outer success: the maximum
  operation-local observation survives the inner rollback, rejects smaller
  subsequent checks and is reapplied before outer commit. No current HTTP path
  catching this sequence was identified; these tests qualify supported nested
  operation composition.
- Lost physical SQLite reservation: stale savepoint handles are cancelled at
  the connection before invalidating the session. Replacement-writer data and
  files survive; no clock observation is retained without the original lock.
- Outer COMMIT failure after release of the nested savepoint: the entire outer
  transaction rolls back without publishing business data or a clock update.

A process/storage failure before durable commit cannot create a retained
observation. External errors remain bounded and fail closed; these tests do not
claim otherwise. The existing key, principal, scope and effect guards remain in
place. No schema migration or dependency was added.

Red/green: three initial regression tests failed on the reviewed code. All nine
clock regressions now pass. Independent clock/savepoint review found no
introduced defect. Full local CI exposed the pre-existing replacement-writer
regression test as an incompatibility with the initial savepoint implementation.
That path is repaired and the combined clock, project-authorization and report-
authorization selection passes 69 tests / 165 subtests. An independent final
selection passes all nine clock tests plus that replacement-cleanup regression.
The earlier local-CI failure is retained, and all broad final commands were
restarted on the repaired source.

## CR17-2: publish the actual signing-header contract

All five signed operations now have documentation-only OpenAPI metadata declaring
all four required headers, their bounded formats, and exact-byte HMAC, nonce,
clock-skew and authority semantics. Runtime authentication still verifies the raw
body and reserves its nonce before JSON parsing. The custom HMAC protocol is not
misrepresented as a bearer API key.

OpenAPI tests first failed on all five operations, then passed after the fix.
They assert required signing metadata and missing-header rejection before the
parser. Generated TypeScript types now require every signing header. Additional
TypeScript checks verify that missing headers fail compilation.

## Validation

Final command results, exit codes, source hashes and retained log hashes are
recorded in `review-fixes-results.json` after completion. Initial runs that
reached the workstation's live Ollama service were interrupted and retained as
`/tmp/story16-17-fix-*-initial-live-model.log`. Final broad runs set
`LLM_API_BASE=http://127.0.0.1:1`, matching CI's lack of an optional local model
service. Provider adapter tests still use their own controlled fixtures.

The first complete API shard, root unittest run and first local-CI attempt caught a sprint metadata
mismatch from the review update (header date November 7, YAML field November 4).
Both fields are now November 7. The documentation selection passes 10 tests /
72 subtests. Those initial failures are retained in the `*-sprint-date-failure.log`
files; all three full commands were restarted after the correction.

Validation runs are isolated: root unittest uses the main workspace; local CI
uses `/tmp/deploywhisper-story16-17-fixes-ci`; exact API/CLI/infra and automation
pytest API/CLI/infra shard runs in `/tmp/deploywhisper-story16-17-fixes-shards`;
the automation shard uses `/tmp/deploywhisper-story16-17-fixes-automation`.
All validation directories have identical runtime, test, generated-contract and qualification
record bytes. Independent databases/artifact directories avoid parallel test
interference. Tests run to completion; an interrupted initial run is not claimed
as a passing run.

Production-runtime coverage uses a disposable container from the existing app
image with Python 3.11, a read-only source mount and no network. Clock and signed
API selections pass 27 tests. The original running app is untouched and healthy.

Collection qualification was rerun against the changed runtime: all 49 checks
pass, and the isolation/collection integrity selection passes 9 tests / 86
subtests. Qualification remains restricted to the recorded offline ARM64,
OpenTofu profile. Existing production TLS, live-runner browser and broader
collector/delivery gates remain open under their owning stories.

UI validation not applicable: no React screen, rendered UI, interaction or
accessibility semantics changed. Generated types are covered by generation,
TypeScript checking, frontend tests and the production asset build. No Compose
browser acceptance or wider production-support claim is made by this fix.

Mypy retains 317 pre-existing diagnostics, with none in the three changed runtime
files. Scoped Bandit has zero findings at all severity/confidence levels.
Repository-wide lint/format and full local CI are required before story status
advancement. No public push, PR, credential setup or release is part of this task.

## Final results

- Root unittest: **1932 tests, 3 skips, exit0**.
- Full local CI: **3402 tests across all ten directories, exit0**.
- Exact API/CLI/infra pytest: **799 passed, 1 skipped, 2,433 subtests, exit0**.
- Exact automation pytest: **1,108 passed, 1 skipped, 3,236 subtests, exit0**.
- Production Python3.11.17: **27 tests passed**.
- Frontend: **479 tests +2 compatibility checks, typecheck/build pass**.
- Qualification: **49 checks pass; integrity9 tests /86 subtests pass**.
- Ruff lint/repository formatting and scoped Bandit pass. Mypy retains317 existing diagnostics, none in the changed runtime files.

No finding from this review remains open. The next BMad handoff is code review;
public GitHub writes and release publication were not performed.

## Changed files in the review-fix workstream

- `_bmad-output/implementation-artifacts/16-17-signed-trigger-intake-and-cli.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/project-context.md`
- `api/routes/infra_automation_triggers.py`
- `docs/infra-automation/triggers.md`
- `docs/verification/infra-automation/16-14/results.json`
- `docs/verification/infra-automation/16-17/formal-code-review.md`
- `docs/verification/infra-automation/16-17/review-fixes-results.json`
- `docs/verification/infra-automation/16-17/review-fixes.md`
- `frontend/src/api/schema.d.ts`
- `services/infra_automation_trigger_authority.py`
- `services/project_service.py`
- `tests/test_api/test_infra_automation_triggers.py`
- `tests/test_infra_automation/test_trigger_clock.py`
