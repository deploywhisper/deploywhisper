# WP5 receiver and custody synthetic fault evidence

Current overall WP5 qualification is recorded in [actual saved-plan custody](wp5-real-custody.md). The partial/blocked statements below preserve the earlier synthetic-only run before real qualification.

2026-10-09: **Partial PASS; full WP5 BLOCKED.** This disposable prototype
exercises receiver state transitions and harmless synthetic byte custody only.
It does not execute Terraform/OpenTofu, apply infrastructure, expose application
routes, import the application database, or qualify saved binary plans.

## Reproduce

```sh
./.venv/bin/python -m unittest discover -s tests/test_infra -p test_infra_automation_receiver_qualification.py -q
./.venv/bin/ruff check tests/test_infra/test_infra_automation_receiver_qualification.py tests/fixtures/infra_automation/qualification/16_0/receiver/prototype.py
./.venv/bin/ruff format --check .
./.venv/bin/bandit -q tests/test_infra/test_infra_automation_receiver_qualification.py tests/fixtures/infra_automation/qualification/16_0/receiver/prototype.py
```

Observed: 12 test methods passed, 30 independent tuple-field mutations denied,
6 live-authority mutations denied at both admission and resumed start, and
5 real child-process abrupt exits returned 73. Python 3.14.3, SQLite 3.53.1,
Ruff 0.15.11, Bandit 1.9.4. Repo-wide format check: 313 files already formatted.
These local versions do not establish Python 3.11/Linux release qualification.
Bandit passes with two explicit narrow annotations: importing subprocess and
launching the owned local crash harness with the current interpreter, fixed
case values and a private temporary path, without a shell.

Tests were written before the prototype. Initial red invocation failed while
importing the intentionally absent `receiver/prototype.py`; the execution
wrapper classified the missing path as a setup failure and did not retain a
normal unittest summary/exit code. Verified test-file and interpreter paths,
then implemented the prototype. Final green ran 12 tests in 0.357 seconds. Intermediate
unused-import/format issues were corrected before final checks. This records
an observed test-first failure, not a fabricated numeric red test count.
The acceptance audit found a receiver identity mismatch bug. Tests added before
the fix reproduced admission of an unregistered receiver and malformed receipt
errors: 12 methods, one failure and two errors, exit 1. The fix persists the
configured logical receiver identity, checks it at issue/admission/start and
compares receipt sender with both configuration and stored binding. Final green
passes the nondefault receiver and six malformed receipt regressions.

## Bounded evidence

| Case | Observed outcome |
| --- | --- |
| Canonical binding | SHA-256 over sorted compact JSON; major 1 fixture; each of 30 fields independently mutated rejects old grant, including kind, revision/source/input/scope, report/policy/unit/waves, target/receiver/payload, custody/raw/sanitized digest, deadlines and epochs |
| Unknown contract / advisory apply | Unknown major/kind denied; advisory request cannot authorize apply |
| Live authority | Missing membership, disabled target/feature, unavailable authority, changed authorization/restore epoch deny admission and new/resumed action; shortest deadline expiry denies |
| Custody | Owner-private directory, opaque random handle, readonly finalized bytes, exclusive temporary write + fsync + atomic no-overwrite link, descriptor-based no-follow open; verify owner/mode/device/inode/digest and expiry; metadata persists across reopening |
| Custody attacks | Tampered bytes with restored readonly mode, symlink substitution, replaced inode containing identical bytes, traversal, wrong digest/audience, expiry and overwrite rejected |
| Synthetic exact-plan admission | Raw-local and screened digest differ; unavailable custody blocks; original synthetic bytes admit; replacement before start blocks action; no actual binary-plan qualification |
| Consumption / lost response | BEGIN IMMEDIATE, WAL/FULL, hashed one-use grant and durable stable operation/target lock committed together; duplicate admission recovers same operation |
| Before consumption / after consumption crash | Child dies via os._exit(73); restart recovers or creates same logical admission and performs one harmless counted action, after rechecking live authority |
| After start / after action crash | Counts 0 / 1 respectively; restart reports delivery_unknown, retains target lock and denies another action; signed success with count 0 rejects; count 1 permits terminal reconciliation using the exact durable operation marker without repeating action |
| After completion crash | One fsynced harmless action survives; action_completed persists; dispatch acceptance alone never represents success |
| Registered receiver | Configured logical identity persists across restart; unregistered binding rejects at issue/admission/start; a valid HMAC for the wrong receiver cannot complete or unlock the nondefault bound receiver operation |
| Receipts | HMAC authenticated binding/operation/source/receiver/sequence/state; tampering, replay, signed unrelated operation/binding/source/receiver and unknown state reject; durable completion or independently observed exact synthetic marker is required to release lock; malformed types and unknown fields/states fail closed |
| Cancel / lease expiry / lock break | Cancel and lease expiry retain lock; reasoned synthetic privileged break is audited and blocks new action on the old operation |

The counted action appends a synthetic operation ID to a private temporary
file and fsyncs it. It is not a deployment or proof of universal exactly-once
external effects. A crash after marking action started conservatively loses
retry permission even when the count is zero. Output is durable before local
completion. In this harmless local-action double, the exact fsynced operation
marker independently proves the effect and permits unknown-to-terminal
reconciliation. A signature alone or dispatch acceptance cannot prove it.
Real external uncertainty still requires qualified operator reconciliation.

## Open gates and trust limits

- **BLOCKED:** actual pinned-tool saved binary plan and qualified Linux profile
  from WP4 unavailable to this slice. Harmless bytes cannot satisfy AC6.
- **BLOCKED:** separate collector/receiver OS execution identities, credential
  delivery and least-privilege file grants are unqualified. Strings `collector`
  and `receiver` are scoped logical doubles in one process/user only.
- **BLOCKED:** encryption/storage policy not configured or qualified. Private
  permissions and integrity checks do not establish encryption at rest.
- Single-receiver crash model, not multi-receiver admission/action concurrency
  qualification, remote server/receiver atomicity, authenticated network online
  admission, production key management or target-alias registry implementation.
  Locks are tested against an already canonical target identifier. WP3 owns
  independent-connection fencing contention; this slice does not replace it.
- Same-user host/DB administrators can mutate metadata/files/key material.
  Private store protects the bounded descriptor/path corpus; it does not claim
  protection against malicious host administrators or same-user adversaries.
  Finalization crash durability and cleanup, quotas, secure deletion, real
  provider redaction and full TOCTOU scheduling remain integrated qualification.
- Logical authority/receipt doubles establish deny/recovery shape, not verified
  production identities, governance acceptance or downstream release readiness.

Private temporary directories hold all databases, signing keys, raw byte
fixtures and counted-action files; tests delete them on completion. No raw
plans/state, live secrets, cloud calls or private logs are committed.
**UI validation not applicable.** Story 16.0 and IR-02 remain open.
