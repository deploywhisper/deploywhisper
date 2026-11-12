# Data lifecycle for self-hosted deployments

## Supported scope

The packaged application defaults to SQLite. InfraFlow execution and its coordinated recovery protocol require singleton SQLite; do not point that engine at PostgreSQL. PostgreSQL is a future scale path, not a current v1.5 automation baseline (architecture ADR14 and section25). The repository supplies no PostgreSQL driver in its dependency locks; the conditional guidance below does not claim a tested PostgreSQL application deployment.

For a deployment bound to an external recovery ledger, use [the coordinated operator procedure](../infra-automation/operations.md). Copying only SQLite would omit artifact/custody roots, recovery generation and authorization invalidation. Retain the external ledger outside snapshots and never reconstruct a lost deployed ledger from a backup.

## Inventory and quiescence

Record the exact image digest/source revision, Alembic revision, configured database location, artifact/custody roots, custom skills and operational configuration. Keep secrets in their existing private store, separately from publicly shareable inventory. Stop the app and every CLI/worker/writer before coordinated backup or restore. Check that no maintenance or migration process remains. Budget space for the snapshot, restored copy, retained old roots and failed private staging directories.

Backups contain sensitive reports, incident/context data and account records. Use a private destination with encryption/access controls appropriate to that data. Define an operator retention schedule and restoration test interval before deleting older copies. Never upload databases, real state or saved plans as CI evidence.

## SQLite backup and restore

For InfraFlow, follow `python -m cli.automation_operations ... backup`, `restore`, `resume` and `complete` in the linked runbook. Those commands verify the schema, coordinated manifests and current retained history, invalidate stale authority, and require explicit recovery completion. An older snapshot missing current purge receipts or uncertain external work is refused.

For a legacy, unbound core-analysis installation, quiesce all writers and use SQLite's backup API into a fresh private path, rather than copying a live `.db` while ignoring WAL. An operator can inspect a copy with:

```python
import sqlite3
with sqlite3.connect("file:/private/backup/app.db?mode=ro", uri=True) as db:
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    print(db.execute("SELECT version_num FROM alembic_version").fetchone())
```

Validate restored data in an isolated directory with the matching application version before replacing a live path. Keep the original intact until report reads, project scope, authentication and core analysis have passed. Do not transplant these legacy steps onto a recovery-bound installation. SQLite integrity checks alone do not prove application-level history or credential safety.

## Upgrade and rollback

Preserve a coordinated pre-upgrade snapshot and exact prior image. Test the immutable copy first; record source digest, before/after revision and integrity/FK checks. The InfraFlow `upgrade-copy` procedure supports the documented v1.4.0 revision028 input and current head; it never upgrades the live source. On ordinary failure it cleans only its own unpublished copy. Ambiguous published output and power-loss remnants require inspection.

A package downgrade is not a database downgrade. Do not run destructive Alembic downgrade as a routine rollback. Recover with the matching previous image and its coordinated snapshot only after evaluating retained newer audit, purge and external-operation history. Otherwise retain the current state for an investigated recovery.

## Retention, logs and maintenance

Use supported report/history deletion and policy APIs under current permissions. Do not delete database rows directly or equate expiry with removal: decisions, audit identity and uncertain external work remain protected. InfraFlow screened-manifest purge retains digest tombstones and removal audit receipts; backups may still contain older sensitive material and need their own retention controls.

Collect only bounded diagnostic logs needed for investigation; screen them before sharing. Restrict log access and rotation/retention at the host or container logging driver. Provider credentials, session cookies, `.env` contents, raw infrastructure state and saved plans must not appear in support bundles.

Run integrity and foreign-key checks on private copies. Plan SQLite compaction/checkpoints as maintenance with disk headroom and participating writers quiesced; never remove live `-wal`/`-shm` files. Backup first and verify application reads afterward. Maintenance must not bypass immutable-history guards or release unknown target locks.

## PostgreSQL operator path — conditional, not qualified here

If an independently supported core deployment supplies a compatible PostgreSQL driver and migrations, use matching server/client tools and private service/password files, never passwords embedded in command lines. A custom-format `pg_dump` archive can be inspected/restored with `pg_restore`; cluster-global roles require separate handling. Restore to a fresh isolated database, check warnings and validate application/schema/data before cutover. Follow the official [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html) and [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html) procedures for the deployed version.

This conditional procedure is not proof of PostgreSQL compatibility or a reason to enable InfraFlow on PostgreSQL. Story12.7 is a documentation contract; it does not authorize adding PostgreSQL automation. Any future declaration of PostgreSQL support requires a compatible driver, supported schema and actual operational qualification. See the [scope audit](../verification/operations/scope-and-verification.md) and [executed SQLite roundtrip](../verification/operations/core-roundtrip-results.json).
