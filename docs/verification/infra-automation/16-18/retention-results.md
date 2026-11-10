# Packet 18.1 implementation and verification

Executed 2026-11-10 on the Story 16.18 feature branch. This closes the implemented
screened-manifest payload removal contract only. It does not qualify whole-artifact
erasure, raw-local custody cleanup, a storage saturation pilot or the whole story.

The typed admin operation is `POST
/api/v1/infra-automation/manifests/{manifest_id}/purge`, with JSON
`expected_run_version` and `reason`. It uses the existing human session,
Origin/CSRF, scoped administrator and reserved transaction boundaries. Exact
same-actor/body retries return the original receipt; a changed request conflicts.

Migration 040 preserves the original manifest identity/digest/provenance and
replaces eligible payload bytes with the reserved empty-list marker only after
inserting its immutable tombstone. All other manifest changes remain forbidden.
Startup validates the effective historical guard and rejects missing or
reinstalled old guards. Downgrade refuses to erase committed removal receipts.

Nonterminal runs, possible external effects, pending/approved decisions, every
handoff and unresolved/broken target locks remain protected. Removal requires
current retention and captured evidence floors, CAS and monotonic run time.
Small payloads that would cost more receipt storage than they reclaim stay
retained with a conflict. Logical quota accounting includes raw receipt bytes,
canonical duplicated scalar and audit fields, a 512-byte bookkeeping allowance
and marker. It never debits the linked report/decision/custody copies that remain.
SQLite file shrinkage is not claimed.

History keeps its compatible report/provenance shape and adds fixed limitations
to existing evidence-status prose when content was removed. Material reads deny
with 409 for validated removal; malformed/digest-corrupt retained data still fails
closed. Collection history projects the existing `stale` status for removed
payloads without reopening execution authority.

## Executed commands

- Red phase: `./.venv/bin/python -m pytest
  tests/test_infra_automation/test_retention.py -q` produced five new failures
  because migration 040 did not exist. The first test file accidentally imported
  a test class and also collected its ten existing tests; this import was changed
  to a module before final verification. Log:
  `/tmp/story16-18-retention-red.log` (ephemeral local output).
- Final focused command: `./.venv/bin/python -m pytest
  tests/test_infra_automation/test_retention.py
  tests/test_models/test_retention_migration.py
  tests/test_api/test_infra_automation_retention.py -q --tb=short`:
  **16 passed, 16 subtests passed, 5.40 seconds**. Six existing Alembic
  configuration deprecation warnings. Log:
  `/tmp/story16-18-retention-final.log`.
- Broader regression command additionally included
  `tests/test_infra_automation/test_preflight_repository.py`,
  `tests/test_infra_automation/test_preflight_service.py`,
  `tests/test_infra_automation/test_collection_views.py` and
  `tests/test_api/test_infra_automation_preflight.py`:
  **64 passed, 109 subtests passed, 27.86 seconds**. This preceded the final
  additional `external_possible` deny and its focused regression. Initial failures
  exposed a legacy unmapped test object, an intentional historical schema fixture
  and the next-head startup check; each was repaired before this passing run.
  Log: `/tmp/story16-18-retention-regressions.log`.
- Scoped `python -m ruff check` passed on the changed retention, manifest reader,
  history adapters, API models/routes and tests; scoped formatting applied.
- `./.venv/bin/python -m bandit -q -r infra_automation/retention.py
  services/infra_automation_retention.py
  migrations/versions/040_add_manifest_retention.py
  models/repositories/infra_automation_reports.py -ll`: passed. An initial static
  SQL-construction finding was removed by expressing the closed column guard
  with a constant-only join; no suppression was added.
- `git diff --check`: passed.
- `./.venv/bin/ruff format --check .` was executed. At that point it reported
  six still-in-progress recovery-lane files requiring formatting; 593 files were
  already formatted. A later check after those edits settled passed:
  **599 files already formatted**. Scoped Ruff and Bandit also passed again on
  the final retention source.

Coverage includes real scoped service/API denial, CAS, exact replay,
concurrent retries producing one receipt/audit, rollback after audit failure,
pending/approved decision and held/broken lock fixtures, possible external effects,
backward time, accounting floors, Unicode reason copies, cleanup while new-work
capacity checks are unavailable, irreversible marker/tombstone guards and actual
039-to-040 migrations with effective-trigger tamper detection.

UI validation not applicable to this packet: no React file, browser interaction
or rendered design was changed. Generated API types and the required exact
API/CLI/infra shard, repository smoke/full CI and final repository-wide formatting
remain the integration owner's combined verification obligations. Fixtures are
explicitly synthetic; these tests do not establish live receiver or custody
qualification.

## Review correction: original intake replay after removal

The independent review found that the default manifest content reader rejected
an exact retry of the original admitted preflight after retention. A real API
regression reproduced the old path's 409 at an explicitly injected server time
equal to the removal clock floor. The corrected manifest admission lookup accepts
validated removal metadata and checks the original digest plus retained original
byte length. An exact original request returns its existing failed/terminal run;
it does not restore bytes, create a manifest, change run version/accounting or add
an audit event. Changed content still returns 409.

The analogous synthetic collected-manifest lookup uses the same identity helper,
while preserving private attempt/fence/lease, envelope freshness and live-run
checks before lookup. A removed terminal task cannot gain collector authority by
replaying metadata.

Executed final correction verification: `./.venv/bin/python -m pytest
tests/test_api/test_infra_automation_retention.py
tests/test_infra_automation/test_retention.py
tests/test_models/test_retention_migration.py
tests/test_infra_automation/test_preflight_repository.py
tests/test_infra_automation/test_preflight_service.py -q --tb=short`:
**39 passed, 61 subtests passed, 20.25 seconds**. Scoped Ruff and Bandit passed.
The repo-wide format check was rerun and found one concurrent recovery-lane file
still changing; 601 other files were formatted. Logs are the ephemeral local
`/tmp/story16-18-retention-replay-{red,green,final}.log` files.

## Integrated correction: migration 032 counter guard

The composed-app exercise exposed a gap in the earlier fixture proof: metadata
creation plus selected guards omitted migration 032's monotonic retained-byte
guard. The real app rejected the service's quota debit, rolling back purge with
503. Earlier metadata-only passing tests did not establish that this operation
worked against the complete migrated application schema.

Migration 040 now replaces only the original run guard's byte-monotonicity
clause. Every original identity, version, cancellation, effect and clock clause
is preserved. Its exception requires an immutable exact tombstone for the old
run version, version increment exactly one, the published removal marker,
unchanged terminal state/cancellation facts, no possible external effect or
protected work, matching receipt timestamps, the snapshot floor and an exact
persisted `reclaimed_bytes` debit. That positive integer is bounded below the
original payload size; SQLite type checks also reject fractional values. The
new scalar is included in quota accounting with its maximum decimal width.
Once the run version advances, the receipt cannot justify another debit.

Effective startup validation now checks both migration 032's run guard and
migration 033's manifest guard against the complete 040 schema. Missing or
reinstalled historical versions fail closed. The API test fixture also executes
Alembic through head 041 before seeding synthetic records, instead of relying
only on `Base.metadata.create_all`.

Red proof: installing the original 032 guard after the actual migrated fixture
reproduced the real purge 503. Final focused proof passed **19 tests and 19
subtests in 8.13 seconds**, including actual migrated API purge/replay and
concurrent SQL probes rejecting a fractional tombstone, incorrect debit amount,
version jump, state change, effect flag and timestamp change. The legitimate
debit succeeds; an additional debit against its spent receipt fails. Source was
then frozen for the composed-app rerun. Logs:
`/tmp/story16-18-retention-run-guard-{red,green,final}.log`.

The final broader retention/API/migration/preflight repository/service command
passed **45 tests and 67 subtests in 23.79 seconds** after the additional
effective-032 startup tamper check. Scoped Ruff/Bandit, whitespace and the
repository-wide format check (**602 files**) passed. Broader log:
`/tmp/story16-18-retention-run-guard-broad.log`.
