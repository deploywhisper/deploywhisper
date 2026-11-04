# Story 16.12 review repairs

Date: 2026-11-04. Scope: R1–R4 from [the BMad review](code-review.md). All four findings are resolved. Fresh focused and full regression verification passed; Story 16.12 is ready for re-review.

| Finding | Repair | Regression evidence |
| --- | --- | --- |
| R1 — encoded credential retention | Reuse `redact_text` with task/runner values and bearer prefixes across accumulated logs, upload fields, operation metadata and administrative audit reasons. No new decoder. | Original encoded-token repro fails before the fix. URL/nested URL/encoded-prefix corpus, chunk joins, harmless encodings, and 18 enrollment/rotate/revoke reason cases prove rejection without retained state or audit changes. |
| R2 — stale clock after parsing | Refresh live authority after parsing/screening, around every operation and after audit/projection; roll back the savepoint if authority expires. Final authority reads are bracketed by another clock read, and stored fractional credential deadlines use the advertised whole-second floor. | Original delayed-heartbeat repro fails before the fix. All five operations are tested across parsing, screening, effects, audits, projection and final validation with lease/credential/coordinator expiry; retained sequence/state/evidence/quota/audit snapshots remain unchanged on rejection. |
| R3 — historical rows exhaust capacity | Count only unexpired active credentials and unexpired unconsumed pending enrollment. Retain all history. Recheck expired-credential rotation and concurrent allocation under the reserved transaction. | 106 historical/current records remain readable; expired pending enrollment releases capacity; 100 active credentials still cap admission; concurrent final-slot allocation has one winner; expired rotation cannot overbook. |
| R4 — missing health pagination | Reuse existing `_page`/`_binding` and `CursorStore`, with immutable creation-audit sequence as insertion watermark. Return typed closed `data.items` and `data.cursor`; default25/max100, finite scoped cursors and current authorization on each page. | Default/max size, stable ordering, later/backdated insertion exclusion, history beyond100, tamper/expiry/changed limit/principal/project/workspace/membership rejection, disabled-policy history and HTTP session revocation. |

Implementation files: `infra_automation/runner/claims.py`, `services/infra_automation_runner_tasks.py`, `services/infra_automation_runners.py`, `models/repositories/infra_automation_runners.py`, and `api/routes/infra_automation_runner_admin.py`. Existing redaction, attempt, cursor and audit infrastructure was reused; no dependency or migration was added.

New regression files: `tests/test_infra_automation/test_runner_review_security.py` and `tests/test_infra_automation/test_runner_health.py`. Existing enrollment and HTTP tests were updated, and all direct health/constructor consumers were searched.

## Completed focused verification

- Combined runner/protocol/client/enrollment/attempt/authorization/sensitive-default/review-security/health/API/migration suite: **82 passed, 617 subtests**, 55.37 seconds.
- Independent final repair review: **38 passed, 188 subtests**, with no unresolved actionable findings in R1–R4.
- Repo-wide Ruff check and format check (517 files), targeted Bandit and `git diff --check` passed during implementation.
- UI validation not applicable: no rendered or browser-interaction surface changed.

## Broader verification

The exact `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` passed: **734 passed, one skipped, 2,353 subtests**, 558.03 seconds. Fresh `./.venv/bin/python -m unittest discover -q` passed **1,636 tests, three skips**, in 811.105 seconds. Full `bash scripts/ci-local.sh` completed with **exit 0, no retries**. All ten directories passed: analysis69, API343, CLI102, docs51, infra290, automation855, LLM76, models22, parsers43 and services1,232 — 3,083 test executions, with three existing skips. The script also passed dependency consistency, repository lint/format, Bandit, compilation, skill tests and prompt-injection tests.

The named reference-capacity and production collection/isolation qualifications remain unclaimed. A refreshed diagnostic benchmark does not change those release gates.

Final-source Linux diagnostic: 100 warmups, 1,000 measured claims and 20 processes, zero failures; p50 54.82 ms / p95 99.63 ms / p99 150.39 ms. Source hashes remained unchanged; actual 4-CPU/7-GiB limits were recorded, with full CI running concurrently. This remains explicitly unqualified reference capacity.

Final checks after integration: `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .` (517 files), touched-code Bandit and `git diff --check` passed. Story/sprint status is review, and R1–R4 action items are checked off. Changes remain on `feature/16-12-runner-enrollment-attempt-protocol`; no commit or push was requested by this repair task.
