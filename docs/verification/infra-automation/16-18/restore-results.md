# Packet 18.2 implementation and verification

Date: 2026-11-10. Python: 3.14.3. These are disposable local synthetic-data
results; they do not establish live operator/custody/receiver qualification or
host-power-loss durability.

## Implemented boundary

- Private offline CLI: `python -m cli.automation_operations --control PATH`
  followed by `initialize`, `backup`, `restore`, `resume`, `status`,
  `recovery-complete`, or `upgrade-copy`. See `--help` and the operator runbook.
- Migration 041 retains the database generation/recovery state and immutable
  restore events. Restored events identify a local operator operation; completion
  records an actually verified fresh human administrator and screened reason.
- Coordinated database/artifact/custody copies use bounded private no-follow
  storage, effective schema/trigger validation, integrity checks and digest-bound
  manifests including empty directories and modes. The control ledger is outside
  every restored root.
- Exclusive operator locking conflicts with participating app/service writers.
  An external monotonic generation considers both current and incoming database
  versions, permanently reserves interrupted generations and prevents repeated
  restore ABA. Multi-root publication has old/new fingerprints and explicit
  resumable crash states. Owned partial-write staging is removed safely.
- Restore invalidates imported sessions, one-use credentials, project epochs,
  runner credentials/enrollments, staged uploads, coordinator ownership and
  available grants. Existing immutable bindings, consumed receipts and locks
  remain unchanged. Current external history absent/different in an older input
  causes conservative refusal **before** generation reservation; it is not erased.
- Recovery-mode startup blocks background automation and topology/backtesting
  schedulers while allowing authorized retained reads and reconciliation.
  Completion requires a fresh global human administrator with full administrative
  authority in every policy project and verified/explicitly broken retained
  operations; it does not issue authorization. Restart after completion before
  running background workers again.

## Commands and actual results

The first regression-first invocation failed during collection because
`infra_automation.operator_recovery` did not exist. Subsequent tests exposed and
corrected exception translation, real migration-trigger constraints, private
directory fixture modes and strict session-token fixtures. The final targeted
command used real Alembic-created current-head databases for every store test:

```text
./.venv/bin/python -m pytest tests/test_infra_automation/test_operator_backup.py tests/test_infra_automation/test_engine_app_lifespan.py tests/test_infra_automation/test_workflow_repository.py -q --tb=short
35 passed, 30 warnings, 14 subtests passed in 21.13s
```

This includes 22 distinct store/operator tests. The warnings concern the existing
Alembic configuration's missing `path_separator` setting.

```text
./.venv/bin/ruff check infra_automation/operator_recovery.py cli/automation_operations.py models/operator_recovery.py migrations/versions/041_add_operator_recovery.py tests/test_infra_automation/test_operator_backup.py app.py config.py services/project_service.py models/database.py models/tables.py
All checks passed!

./.venv/bin/ruff format --check .
602 files already formatted

./.venv/bin/bandit -q -r infra_automation/operator_recovery.py cli/automation_operations.py models/operator_recovery.py migrations/versions/041_add_operator_recovery.py -c pyproject.toml
exit 0; no findings

./.venv/bin/python -m cli.automation_operations --help
exit 0; all seven commands registered
```

Repository search for `RecoveryState(` and `RestoreEvent(` found only the model
declarations; no preexisting direct constructor fixture needed updating. Root
integration owns the broad CI/API/CLI/infra shards, actual v1.4.0 tag-copy upgrade
exercise and qualification refresh. The source hashes at this handoff are in
`restore-source-hashes.json`; later shared integration edits require refresh.

## Remaining acceptance limits

The named lock protocol does not stop an unrelated legacy CLI or remote receiver.
Operators must stop all nonparticipating mutators and declare their complete
storage/journal/key domains. Tooling detects active SQLite writers but does not
claim that this proves remote or filesystem quiescence. Host/DB administrators
remain trusted. Loss/rollback of the outside control ledger is fail-closed;
cross-host recovery requires separately reviewed handling.

Older backups which omit or differ from current external history require a
sufficiently new coordinated backup or separately reviewed manual recovery. The
tool deliberately refuses to manufacture a reconciliation or drop unknown work.
Publication preserves private old roots; operators must account for that storage
and retain them until recovery is qualified. Real disk/power-loss durability,
live custody/receiver restore and credential rotation, restricted-network
exercises, self-service operator pilot and the 30-minute capacity run remain
their explicit acceptance obligations. UI validation is not applicable to this
packet: no rendered surface changed.
