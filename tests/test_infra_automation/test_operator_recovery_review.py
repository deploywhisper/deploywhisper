"""Formal-review regressions use private synthetic stores and real Alembic guards."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from infra_automation import operator_recovery as recovery
from tests.test_infra_automation import test_operator_backup as backup_tests


class Interrupted(BaseException):
    """Model a process interruption without treating it as an ordinary error."""


class RecoveryReviewTests(unittest.TestCase):
    setUp = backup_tests.OperatorBackupTests.setUp
    backup = backup_tests.OperatorBackupTests.backup

    def unbound(self):
        from alembic import command
        from alembic.config import Config
        from uuid import uuid4

        suffix = uuid4().hex
        database = self.base / ("unbound-" + suffix + ".db")
        with patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{database}"}):
            command.upgrade(Config("alembic.ini"), "head")
        with sqlite3.connect(database) as target:
            target.execute("ATTACH DATABASE ? AS fixture", (str(self.db),))
            target.execute(
                "INSERT INTO identity_accounts SELECT * FROM fixture.identity_accounts"
            )
        database.chmod(0o600)
        return recovery.RecoveryStore(self.base / ("new-control-" + suffix)), database

    def binding(self, database):
        with sqlite3.connect(database) as db:
            return db.execute(
                "SELECT installation_id,generation,phase FROM infra_automation_recovery_state"
            ).fetchall()

    def test_initial_binding_failure_resumes_same_durable_intent(self):
        for error in (OSError, Interrupted):
            with self.subTest(error=error):
                store, database = self.unbound()
                with patch.object(store, "_save", side_effect=error("after commit")):
                    with self.assertRaises((recovery.RecoveryError, Interrupted)):
                        store.initialize(database, self.roots)
                intent = store.status()
                self.assertEqual(intent["phase"], "initializing")
                self.assertEqual(len(self.binding(database)), 1)
                with self.assertRaises(recovery.RecoveryError):
                    store.assert_ready()
                lock = (store.control / "lifecycle.lock").stat().st_ino
                result = store.resume()
                self.assertEqual(result["installation_id"], intent["installation_id"])
                self.assertEqual(result["generation"], intent["generation"])
                self.assertEqual(result["phase"], "ready")
                self.assertEqual((store.control / "lifecycle.lock").stat().st_ino, lock)
                # An actual lost deployed ledger never authorizes another initialization.
                (store.control / "ledger.json").unlink()
                with self.assertRaises(recovery.RecoveryError):
                    store.resume()
                with self.assertRaises(recovery.RecoveryError):
                    store.initialize(database, self.roots)
                import shutil

                shutil.rmtree(store.control)
                database.unlink()

    def test_published_initial_intent_survives_error_before_binding(self):
        from infra_automation.receiver_custody import _publish_directory

        store, database = self.unbound()

        def interrupted(*args):
            _publish_directory(*args)
            raise Interrupted("after exclusive control publication")

        with patch(
            "infra_automation.receiver_custody._publish_directory",
            side_effect=interrupted,
        ):
            with self.assertRaises(Interrupted):
                store.initialize(database, self.roots)
        self.assertEqual(self.binding(database), [])
        self.assertEqual(store.status()["phase"], "initializing")
        with self.assertRaises(recovery.RecoveryError):
            store.assert_ready()
        with patch.object(recovery, "configured_store", return_value=store):
            with self.assertRaises(recovery.RecoveryError):
                recovery.assert_startup_allowed()
            with self.assertRaises(recovery.RecoveryError):
                with store.participate():
                    self.fail("Initializing control admitted a normal participant")
        with store._lock(exclusive=True):
            inode = (store.control / "lifecycle.lock").stat().st_ino
            with self.assertRaises(recovery.RecoveryError):
                store.initialize(database, self.roots)
            self.assertEqual((store.control / "lifecycle.lock").stat().st_ino, inode)
        self.assertEqual(store.resume()["phase"], "ready")
        self.assertEqual(len(self.binding(database)), 1)

    def test_prepublication_failure_has_no_binding_and_retry_is_safe(self):
        store, database = self.unbound()
        with patch(
            "infra_automation.receiver_custody._publish_directory",
            side_effect=Interrupted("before control publication"),
        ):
            with self.assertRaises(Interrupted):
                store.initialize(database, self.roots)
        self.assertFalse(store.control.exists())
        self.assertEqual(self.binding(database), [])
        self.assertEqual(store.initialize(database, self.roots)["phase"], "ready")

    def test_prebinding_schema_failure_keeps_intent_and_initialize_retry(self):
        store, database = self.unbound()
        schema = store._schema

        def failed(connection):
            if store.control.exists():
                raise OSError("before binding")
            schema(connection)

        with patch.object(store, "_schema", side_effect=failed):
            with self.assertRaises(recovery.RecoveryError):
                store.initialize(database, self.roots)
        intent = store.status()
        self.assertEqual(self.binding(database), [])
        self.assertEqual(
            store.initialize(database, self.roots)["installation_id"],
            intent["installation_id"],
        )

    def test_parent_fsync_failure_after_control_publication_resumes(self):
        store, database = self.unbound()
        sync = os.fsync

        def failed(descriptor):
            if store.control.exists():
                raise OSError("control parent sync failed")
            return sync(descriptor)

        with patch.object(recovery.os, "fsync", side_effect=failed):
            with self.assertRaises(recovery.RecoveryError):
                store.initialize(database, self.roots)
        self.assertEqual(self.binding(database), [])
        self.assertEqual(store.resume()["phase"], "ready")

    def pending_initialization(self):
        from infra_automation.receiver_custody import _publish_directory

        store, database = self.unbound()

        def interrupted(*args):
            _publish_directory(*args)
            raise Interrupted("published intent")

        with patch(
            "infra_automation.receiver_custody._publish_directory",
            side_effect=interrupted,
        ):
            with self.assertRaises(Interrupted):
                store.initialize(database, self.roots)
        return store, database

    def test_unbound_intent_denies_replaced_database_inode(self):
        store, database = self.pending_initialization()
        replacement = self.base / "replacement.db"
        with (
            sqlite3.connect(database) as source,
            sqlite3.connect(replacement) as target,
        ):
            source.backup(target)
        replacement.chmod(0o600)
        replacement.replace(database)
        with self.assertRaises(recovery.RecoveryError):
            store.resume()
        self.assertEqual(self.binding(database), [])

    def test_unbound_intent_denies_advanced_database_generation(self):
        store, database = self.pending_initialization()
        with sqlite3.connect(database) as db:
            db.execute(
                "UPDATE identity_accounts SET authentication_version=authentication_version+1"
            )
        with self.assertRaises(recovery.RecoveryError):
            store.resume()
        self.assertEqual(self.binding(database), [])

    def test_bound_intent_denies_different_installation_and_missing_schema_guard(self):
        store, database = self.unbound()
        with patch.object(store, "_save", side_effect=OSError("after binding")):
            with self.assertRaises(recovery.RecoveryError):
                store.initialize(database, self.roots)
        path = store.control / "ledger.json"
        intent = json.loads(path.read_text())
        changed = {**intent, "installation_id": "f" * 32}
        path.write_text(json.dumps(changed))
        with self.assertRaises(recovery.RecoveryError):
            store.resume()
        path.write_text(json.dumps(intent))
        with sqlite3.connect(database) as db:
            db.execute("DROP TRIGGER infra_retention_no_delete")
        with self.assertRaises(recovery.RecoveryError):
            store.resume()

    def test_initialization_after_ready_publication_can_be_resumed(self):
        store, database = self.unbound()
        save = store._save

        def interrupted(value):
            save(value)
            raise Interrupted("after ready ledger publication")

        with patch.object(store, "_save", side_effect=interrupted):
            with self.assertRaises(Interrupted):
                store.initialize(database, self.roots)
        binding = self.binding(database)
        self.assertEqual(store.resume()["phase"], "ready")
        self.assertEqual(self.binding(database), binding)

    def test_process_exit_at_initialization_boundaries_preserves_one_intent(self):
        import subprocess
        import sys

        program = """
import json, os, sys
from infra_automation.operator_recovery import RecoveryStore
from infra_automation import receiver_custody
store = RecoveryStore(sys.argv[1])
boundary = sys.argv[4]
if boundary in {'before-control', 'after-control'}:
    publish = receiver_custody._publish_directory
    def interrupted(*args):
        if boundary == 'after-control':
            publish(*args)
        os._exit(42)
    receiver_custody._publish_directory = interrupted
else:
    save = store._save
    def interrupted(value):
        if boundary == 'after-ledger':
            save(value)
        os._exit(42)
    store._save = interrupted
store.initialize(sys.argv[2], json.loads(sys.argv[3]))
"""
        for boundary in (
            "before-control",
            "after-control",
            "after-binding",
            "after-ledger",
        ):
            with self.subTest(boundary=boundary):
                store, database = self.unbound()
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        program,
                        str(store.control),
                        str(database),
                        json.dumps(
                            {key: str(path) for key, path in self.roots.items()}
                        ),
                        boundary,
                    ],
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(result.returncode, 42, result.stderr.decode())
                if boundary == "before-control":
                    self.assertFalse(store.control.exists())
                    self.assertEqual(self.binding(database), [])
                    resumed = store.initialize(database, self.roots)
                else:
                    intent = store.status()
                    if boundary != "after-ledger":
                        with self.assertRaises(recovery.RecoveryError):
                            store.assert_ready()
                    resumed = store.resume()
                    self.assertEqual(
                        resumed["installation_id"], intent["installation_id"]
                    )
                    self.assertEqual(resumed["generation"], intent["generation"])
                self.assertEqual(resumed["phase"], "ready")
                self.assertEqual(len(self.binding(database)), 1)

    def test_reserved_database_root_denies_before_any_binding(self):
        store, database = self.unbound()
        reserved = self.base / "reserved"
        reserved.mkdir(mode=0o700)
        with self.assertRaises(recovery.RecoveryError):
            store.initialize(database, {**self.roots, "database": reserved})
        self.assertFalse(store.control.exists())
        self.assertEqual(self.binding(database), [])

    def test_reserved_role_in_existing_ledger_denies_before_restore_reservation(self):
        backup = self.backup()
        path = self.store.control / "ledger.json"
        value = json.loads(path.read_text())
        value["roots"]["database"] = str(self.base / "reserved")
        path.write_text(json.dumps(value))
        before = path.read_bytes()
        with self.assertRaises(recovery.RecoveryError):
            self.store.restore(backup)
        self.assertEqual(path.read_bytes(), before)

    def test_complete_package_file_boundary_includes_manifest(self):
        custody = self.roots["custody"]
        # Two existing payloads + 4091 = 4093; DB + two roles + manifest = 4097.
        for number in range(4091):
            path = custody / f"file-{number:04}"
            path.touch(mode=0o600)
        with self.assertRaises(recovery.RecoveryError):
            self.store.backup(self.base / "too-many")
        self.assertFalse((self.base / "too-many").exists())
        (custody / "file-4090").unlink()
        backup = self.backup()
        self.assertEqual(len(recovery._walk(backup)), 4096)
        self.assertEqual(self.store.restore(backup)["phase"], "reconciliation_required")

    def test_complete_package_depth_includes_role_prefix(self):
        nested = self.roots["custody"]
        for _ in range(32):
            nested = nested / "d"
            nested.mkdir(mode=0o700)
        with self.assertRaises(recovery.RecoveryError):
            self.store.backup(self.base / "too-deep")
        self.assertFalse((self.base / "too-deep").exists())
        nested.rmdir()
        backup = self.backup()
        self.store._verify_backup(backup, self.store.status())

    def test_complete_package_metadata_limit_is_checked_before_publication(self):
        for number in range(3000):
            path = self.roots["custody"] / (f"{number:04}-" + "x" * 225)
            path.touch(mode=0o600)
        with self.assertRaises(recovery.RecoveryError):
            self.store.backup(self.base / "metadata-large")
        self.assertFalse((self.base / "metadata-large").exists())

    def test_complete_package_byte_budget_includes_manifest(self):
        baseline = self.backup()
        size = sum(
            len(raw) for raw, _ in recovery._walk(baseline).values() if raw is not None
        )
        with patch.object(recovery, "MAX_BYTES", size - 1):
            with self.assertRaises(recovery.RecoveryError):
                self.store.backup(self.base / "byte-large")
        self.assertFalse((self.base / "byte-large").exists())
        with patch.object(recovery, "MAX_BYTES", size):
            self.store.backup(self.base / "byte-exact")
            self.store._verify_backup(self.base / "byte-exact", self.store.status())


class UpgradeReviewTests(unittest.TestCase):
    def setUp(self):
        from alembic import command
        from alembic.config import Config

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.source, self.output = self.base / "source.db", self.base / "output.db"
        with patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{self.source}"}):
            command.upgrade(Config("alembic.ini"), "028_add_narrative_guidance_payload")
        self.source.chmod(0o400)
        self.original = self.source.read_bytes()

    def test_failed_migration_cleans_only_owned_unpublished_copy_and_sidecars(self):
        foreign = self.base / ".upgrade-foreign"
        foreign.write_bytes(b"foreign")
        foreign.chmod(0o600)

        def failed(cfg, revision):
            path = Path(
                cfg.get_main_option("sqlalchemy.url").removeprefix("sqlite:///")
            )
            for suffix in ("-journal", "-wal", "-shm"):
                sidecar = Path(str(path) + suffix)
                sidecar.write_bytes(b"synthetic SQLite sidecar")
                sidecar.chmod(0o600)
            raise RuntimeError("synthetic migration interruption")

        previous_url = os.environ.get("DATABASE_URL")
        for _ in range(3):
            with patch("alembic.command.upgrade", side_effect=failed):
                with self.assertRaises(RuntimeError):
                    recovery.upgrade_database_copy(self.source, self.output)
            self.assertEqual(self.source.read_bytes(), self.original)
            self.assertFalse(self.output.exists())
            self.assertEqual(list(self.base.glob(".upgrade-*")), [foreign])
            self.assertEqual(os.environ.get("DATABASE_URL"), previous_url)
        self.assertEqual(
            recovery.upgrade_database_copy(self.source, self.output),
            {"schema_revision": recovery.REVISION},
        )
        self.assertEqual(list(self.base.glob(".upgrade-*")), [foreign])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_partial_database_copy_failure_cleans_owned_copy(self):
        connect = sqlite3.connect
        source_path = self.source.as_uri()

        class FailedCopy:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, *args):
                return self.connection.execute(*args)

            def backup(self, destination):
                destination.execute("CREATE TABLE partial_copy (id INTEGER)")
                destination.commit()
                raise OSError("synthetic interruption after copying some pages")

            def close(self):
                self.connection.close()

        def interrupted(path, *args, **kwargs):
            connection = connect(path, *args, **kwargs)
            return (
                FailedCopy(connection)
                if str(path).startswith(source_path)
                else connection
            )

        with patch.object(recovery.sqlite3, "connect", side_effect=interrupted):
            with self.assertRaises(recovery.RecoveryError):
                recovery.upgrade_database_copy(self.source, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.base.glob(".upgrade-*")), [])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_schema_validation_failure_cleans_owned_copy(self):
        with patch.object(
            recovery.RecoveryStore, "_schema", side_effect=recovery.RecoveryError
        ):
            with self.assertRaises(recovery.RecoveryError):
                recovery.upgrade_database_copy(self.source, self.output)
        self.assertEqual(list(self.base.glob(".upgrade-*")), [])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_publish_failure_cleans_owned_copy_and_never_existing_output(self):
        link = os.link

        def failed(source, destination, *args, **kwargs):
            if Path(destination) == self.output:
                raise OSError("publish failed")
            return link(source, destination, *args, **kwargs)

        with patch.object(recovery.os, "link", side_effect=failed):
            with self.assertRaises(recovery.RecoveryError):
                recovery.upgrade_database_copy(self.source, self.output)
        self.assertEqual(list(self.base.glob(".upgrade-*")), [])
        self.output.write_bytes(b"foreign output")
        self.output.chmod(0o600)
        with self.assertRaises(recovery.RecoveryError):
            recovery.upgrade_database_copy(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), b"foreign output")

    def test_copy_interruption_cleans_owned_copy(self):
        connect = recovery._connect

        def failed(path):
            if Path(path).name.startswith(".upgrade-"):
                raise Interrupted("copy connection interrupted")
            return connect(path)

        with patch.object(recovery, "_connect", side_effect=failed):
            with self.assertRaises(Interrupted):
                recovery.upgrade_database_copy(self.source, self.output)
        self.assertEqual(list(self.base.glob(".upgrade-*")), [])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_ambiguous_successful_publication_retains_output(self):
        link = os.link

        def interrupted(source, destination, *args, **kwargs):
            result = link(source, destination, *args, **kwargs)
            if Path(destination) == self.output:
                raise Interrupted("publication completed before interruption")
            return result

        with patch.object(recovery.os, "link", side_effect=interrupted):
            with self.assertRaises(Interrupted):
                recovery.upgrade_database_copy(self.source, self.output)
        self.assertTrue(self.output.exists())
        with sqlite3.connect(self.output) as db:
            self.assertEqual(
                db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                recovery.REVISION,
            )
        self.assertEqual(self.source.read_bytes(), self.original)


class RetentionRestoreReviewTests(unittest.TestCase):
    def setUp(self):
        from tests.test_api.test_infra_automation_retention import (
            RetentionMigratedApiTests,
        )

        self.retention = RetentionMigratedApiTests()
        self.addCleanup(self.retention.doCleanups)
        self.retention.setUp()
        self.fixture = self.retention.fixture
        self.database = Path(self.fixture.engine.url.database).resolve()
        self.database.chmod(0o600)
        self.base = self.database.parent
        self.roots = {}
        for role in ("artifacts", "custody"):
            root = self.base / ("review-" + role)
            root.mkdir(mode=0o700)
            self.roots[role] = root
        self.store = recovery.RecoveryStore(self.base / "review-control")
        self.store.initialize(self.database, self.roots)

    def purge(self):
        from services import infra_automation_retention as retention

        with patch.object(retention, "_now", return_value=self.retention.future):
            response = self.fixture.client.post(
                self.retention.path,
                json=self.retention.body,
                headers=self.fixture.headers(),
            )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def test_real_api_removal_denies_old_backup_without_reservation(self):
        backup = self.base / "before-purge"
        self.store.backup(backup)
        receipt = self.purge()
        before = self.store.status()
        with self.assertRaises(recovery.RecoveryError):
            self.store.restore(backup)
        self.assertEqual(self.store.status(), before)
        with sqlite3.connect(self.database) as db:
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM infra_automation_retention_tombstones"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM infra_automation_audit WHERE event_type='automation_manifest_content_removed'"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                db.execute(
                    "SELECT artifacts_bytes,digest FROM infra_automation_artifact_manifests WHERE id=?",
                    (receipt["manifest_id"],),
                ).fetchone(),
                (b"[]", receipt["original_digest"]),
            )

    def test_backup_after_removal_restores_receipt_marker_and_audit(self):
        receipt = self.purge()
        backup = self.base / "after-purge"
        self.store.backup(backup)
        self.assertEqual(self.store.restore(backup)["phase"], "reconciliation_required")
        with sqlite3.connect(self.database) as db:
            self.assertEqual(
                db.execute(
                    "SELECT artifacts_bytes,digest FROM infra_automation_artifact_manifests WHERE id=?",
                    (receipt["manifest_id"],),
                ).fetchone(),
                (b"[]", receipt["original_digest"]),
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM infra_automation_retention_tombstones"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM infra_automation_audit WHERE event_type='automation_manifest_content_removed'"
                ).fetchone()[0],
                1,
            )

    def test_modified_receipts_audits_markers_and_digests_deny_before_reservation(self):
        self.purge()
        backup = self.base / "receipt-candidates"
        self.store.backup(backup)
        database = backup / "database.sqlite"
        original_database = database.read_bytes()
        manifest_path = backup / "manifest.json"
        original_manifest = json.loads(manifest_path.read_text())
        before = self.store.status()
        cases = (
            (
                "infra_automation_retention_tombstones",
                "DELETE FROM infra_automation_retention_tombstones",
            ),
            (
                "infra_automation_retention_tombstones",
                "UPDATE infra_automation_retention_tombstones SET request_digest='sha256:' || printf('%064d',1)",
            ),
            (
                "infra_automation_audit",
                "DELETE FROM infra_automation_audit WHERE event_type='automation_manifest_content_removed'",
            ),
            (
                "infra_automation_audit",
                "UPDATE infra_automation_audit SET reason='Different removal' WHERE event_type='automation_manifest_content_removed'",
            ),
            (
                "infra_automation_artifact_manifests",
                "UPDATE infra_automation_artifact_manifests SET artifacts_bytes=x'7265737572726563746564'",
            ),
            (
                "infra_automation_artifact_manifests",
                "UPDATE infra_automation_artifact_manifests SET digest='sha256:' || printf('%064d',1)",
            ),
        )
        for table, mutation in cases:
            with self.subTest(mutation=mutation):
                database.write_bytes(original_database)
                with sqlite3.connect(database) as db:
                    # Alter only the synthetic candidate, then restore every exact
                    # migration guard; schema validity alone must not admit it.
                    guards = db.execute(
                        "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
                        (table,),
                    ).fetchall()
                    for name, _ in guards:
                        db.execute(f'DROP TRIGGER "{name}"')
                    db.execute(mutation)
                    for _, sql in guards:
                        db.execute(sql)
                with recovery._connect(database) as db:
                    self.store._schema(db)
                    self.store._integrity(db)
                raw = database.read_bytes()
                manifest = json.loads(json.dumps(original_manifest))
                manifest["files"]["database.sqlite"].update(
                    size=len(raw), digest=recovery._digest(raw)
                )
                manifest_path.write_bytes(recovery._canonical(manifest))
                with self.assertRaises(recovery.RecoveryError):
                    self.store.restore(backup)
                self.assertEqual(self.store.status(), before)


class ExternalHistoryReviewTests(unittest.TestCase):
    def test_older_snapshot_cannot_regress_consumed_external_work_or_release_lock(self):
        from tests.test_infra_automation.test_receiver_recovery import (
            ReceiverRecoveryTests,
        )

        fixture = ReceiverRecoveryTests()
        fixture.defer_consumption = True
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        backup = fixture.base / "before-consumption"
        fixture.store.backup(backup)
        sent = fixture.sent[0]
        fixture.handoffs.consume(sent.message_bytes, sent.grant_token, fixture.receiver)
        before = fixture.store.status()
        with sqlite3.connect(fixture.dbpath) as db:
            locks = db.execute("SELECT * FROM infra_automation_target_locks").fetchall()
            handoffs = db.execute("SELECT * FROM infra_automation_handoffs").fetchall()
        self.assertTrue(locks)
        with self.assertRaises(recovery.RecoveryError):
            fixture.store.restore(backup)
        self.assertEqual(fixture.store.status(), before)
        with sqlite3.connect(fixture.dbpath) as db:
            self.assertEqual(
                db.execute("SELECT * FROM infra_automation_target_locks").fetchall(),
                locks,
            )
            self.assertEqual(
                db.execute("SELECT * FROM infra_automation_handoffs").fetchall(),
                handoffs,
            )
