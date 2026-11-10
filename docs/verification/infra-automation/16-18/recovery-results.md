# Story 16.18 operator recovery matrix

Packet 18.3 deterministic contract verification, 2026-11-10. This record covers
the existing application services against an isolated file-backed SQLite database
with synthetic admitted collection, custody, receiver and decision material.
It does not qualify a live receiver, network, actual tool execution, coordinated
database restore, or a restored production credential. Project restore-epoch
invalidation is explicitly distinguished from coordinated database restore.

## Exercised contracts

| Scenario | Verified result |
| --- | --- |
| Disable before dispatch | No delivery callback; prepared intent and held target lock remain readable. |
| Disable then re-enable after dispatch | Original grant cannot be consumed; exactly one attempted delivery and the unknown operation/lock remain. |
| Advance project restore epoch | Unconsumed grant fails current authority; historical operation and lock remain. This is not a database restore exercise. |
| Revoke after consumption | New action admission denies; exact consumed receipt remains readable; authenticated signed failure reconciles the same operation. |
| Authority deadline expiry | New action and repeated dispatch deny; consumed receipt and unknown lock survive. Receiver reads remain possible independently of an expired human idle session. |
| Reviewer membership revocation | New action denies while original receipt and same-operation signed failure reconciliation remain possible. |
| Nonadmin uncertainty break | Denied without breaking the lock, changing the grant, or appending a successful break audit. |
| Audited administrator break | Lock becomes broken, unconsumed grant is invalidated, and both lock/operation audit events persist. No new authorization or replacement delivery is issued. |
| Project epoch revokes runner | Old runner authentication denies; current human health/history reads remain available. |
| Runner rotation then revocation | Both previous and replacement credentials deny; revoked runner history remains visible. |

The fixture shares existing `LifecycleCase`, handoff, receiver callback and runner
enrollment setup; tested operations call real service boundaries. No runtime
behavior was changed and no implementation defect was reproduced. The first test
run found test-adapter mistakes (a nonexistent view field, copied `super()` setup,
and a human idle timeout); these were corrected without changing the service
contracts or weakening the authorization assertions.

## Commands

Python: `3.14.3` in the existing local virtual environment.

- `./.venv/bin/python -m pytest tests/test_infra_automation/test_operator_recovery.py -q --tb=short`
  — **10 passed in 4.99s**.
- `./.venv/bin/python -m ruff format tests/test_infra_automation/test_operator_recovery.py`
  — one new test file formatted.
- `./.venv/bin/python -m ruff check tests/test_infra_automation/test_operator_recovery.py`
  — passed.
- `./.venv/bin/python -m pytest tests/test_infra_automation/test_operator_recovery.py tests/test_infra_automation/test_receiver_reconciliation.py tests/test_infra_automation/test_runner_enrollment.py -q --tb=short`
  — **44 passed, 28 subtests passed in 19.36s**.

The repository-wide `./.venv/bin/python -m ruff format --check .` was also executed
during concurrent implementation. It found four other in-progress files needing
formatting; this is not a final repository-wide formatting pass. Root integration
owns the final broad checks after all packets settle.

## Remaining acceptance

Coordinated backup/restore, interruption and consumed/unconsumed operation races
over an actual restored image remain Packet 18.2 obligations. Real external
receiver/runner qualification, operator pilot, and 30-minute saturation proof
remain explicit acceptance gates. These ten tests do not close all of AC3/AC4 or
the full story by themselves.
