# WP3 disposable SQLite qualification

Responsible contributor: Codex persistence qualification agent, 2026-10-09.
Scope: Story 16.0 AC4 only. This prototype imports no application database,
defines no migration and delivers no production automation behavior. Public
acceptance, independent review and the remaining story gates stay open.

The harness uses private temporary file-backed SQLite databases and two spawned
processes synchronized at the claim boundary. Each independently opens the
existing schema before contention. One version-0 claim wins; the other observes
the committed version and denies. The first prototype run exposed concurrent
schema initialization contention; schema preparation now occurs once before
contenders start, matching the supported single-instance migration boundary.

## Selected semantics

- WAL with `synchronous=FULL` (numeric 2), `busy_timeout=0`; short
  `BEGIN IMMEDIATE` transactions commit CAS claim, attempt/fence and audit
  together. Four SQLITE_BUSY observations allow three 10ms pauses; exhaustion
  raises an explicit Busy outcome with no action committed. Other SQL errors
  propagate. A held independent connection tests both exhausted budget and
  successful retry after release inside the budget.
  Initial connection/PRAGMA configuration has a separate bounded 30ms SQLite
  timeout because first-reader WAL recovery can contend. Connections close
  explicitly; transaction contention uses the zero-timeout application budget.
- CAS state version plus unique `(job,attempt)` and `(job,fence)` constraints
  protect ownership. Attempts/fences increase across local retry. Coordinator
  generation is durable and invalidates old workers even before lease expiry.
- Every heartbeat/log/upload/completion checks synthetic job ID, owner,
  attempt, fence, generation, auth epoch, restore epoch, active running state
  and unexpired lease. Wrong token fields, expired leases, old generation and
  revoked/restored epochs deny. This one-job scope double is not the production
  principal/project/workspace/run/step permission matrix (WP2/16.12).
- Output commits in its own transaction before a succeeding completion can
  commit. Completion without output denies. Completed attempts reject further
  mutation. Persisted outputs survive an abrupt child exit before completion;
  restart can complete the same unexpired local attempt.
- Lease expiry only reclaims declared local idempotent work. Expired external
  work becomes `delivery_unknown` and retains its target lock. Subsequent claims
  deny; no automatic action retry is available. Lease and epoch checks do not
  prove or undo remote action effects; WP5 owns receiver reconciliation.

## Evidence and reproduction

[Screened results](wp3-sqlite-results.json) record SQLite 3.53.1, actual selected
PRAGMAs and seven corpus snapshots with audit-event timelines and checkpointed
database SHA-256 digests. Digests identify this observed disposable state;
reproduction may select a different winning process and hence different bytes.
Only harmless event names and synthetic state are published. Databases, WAL,
raw process output and temporary directories are not retained in the repository.

```sh
./.venv/bin/python -m unittest discover -s tests/test_infra -p test_infra_automation_sqlite_qualification.py -q
./.venv/bin/python -m pytest tests/test_infra/test_infra_automation_sqlite_qualification.py -q
./.venv/bin/python tests/fixtures/infra_automation/qualification/16_0/sqlite/prototype.py
./.venv/bin/ruff check tests/test_infra/test_infra_automation_sqlite_qualification.py tests/fixtures/infra_automation/qualification/16_0/sqlite/prototype.py
./.venv/bin/bandit -q tests/fixtures/infra_automation/qualification/16_0/sqlite/prototype.py
./.venv/bin/ruff format --check .
```

Tests were written before the prototype; the initial missing-prototype red
attempt was rejected by the execution tool's missing-path detector. The first
readable run was red (9 tests, one process pickling/import error); registered
fixture import support fixed that. The final targeted results are **11 unittest
tests passed; pytest 11 passed, 5 subtests passed**. Scoped Ruff lint and Bandit
passed without suppressions. Repo-wide format verification initially found
two concurrently edited receiver files; the final rerun passed (313 files).
Tests reside in the existing `tests/test_infra` discovery lane. UI validation
not applicable.

Closing connections exposed a second real red: simultaneous first-reader WAL
opening could fail during synchronous PRAGMA configuration and break the race
barrier. The separate bounded connection configuration timeout addresses that
boundary; final unittest and pytest runs passed after that change.

Crash probes use real child `os._exit(73)`, with no graceful close: precommit
rolls the claim back; postcommit preserves owner/fence; output-before-success
preserves output and running state. Restart tests assert each observed state.
Tests also reject duplicate attempt/fence constraints and all four stale
mutation types after generation overlap and lease reclaim.

## Limits

This is a macOS local-file synthetic microspike under Python 3.14, not a
production SQLite profile, 10-run capacity measurement, HA, physical power-loss,
disk corruption, network filesystem, backup-restore procedure or host-administrator
tamper qualification. Lease times are injected logical values; production clock
policy and SQLite deployment/upgrade compatibility still need qualification.
Only a single synthetic job/target is modeled; cross-target alias collision,
real memberships, worker/process execution, receiver outcome reconciliation,
load and integrated recovery remain downstream. No exactly-once external effect
claim follows from a unique SQL row or committed claim.
