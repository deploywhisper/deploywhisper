"""Synthetic private-store recovery proofs; never a live operator exercise."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from infra_automation.operator_recovery import RecoveryError, RecoveryStore


class OperatorBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.db = self.base / "app.db"
        from alembic import command
        from alembic.config import Config
        from unittest.mock import patch
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from datetime import datetime, timezone, timedelta
        from models.tables import (
            Project,
            IdentityAccount,
            IdentitySession,
            IdentityCredential,
            InfraAutomationPolicy,
        )
        from infra_automation.lifecycle import AutomationSettings

        cfg = Config("alembic.ini")
        with patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{self.db}"}):
            command.upgrade(cfg, "head")
        engine = create_engine(f"sqlite:///{self.db}")
        now = datetime.now(timezone.utc)
        try:
            with Session(engine) as db:
                db.add(Project(id=100, project_key="recovery", display_name="Recovery"))
                db.add(
                    IdentityAccount(
                        id="operator",
                        username="operator",
                        password_verifier="synthetic",
                        authentication_version=1,
                        created_at=now,
                    )
                )
                db.flush()
                db.add(
                    IdentitySession(
                        id="old-session",
                        principal_id="operator",
                        token_hash="a" * 64,
                        csrf_hash="b" * 64,
                        audience="human",
                        security_profile="https",
                        trusted_origin="https://recovery.invalid",
                        authentication_version=1,
                        created_at=now,
                        last_seen_at=now,
                        expires_at=now + timedelta(hours=1),
                    )
                )
                db.add(
                    IdentityCredential(
                        id="old-setup",
                        token_hash="c" * 64,
                        purpose="recovery",
                        principal_id="operator",
                        created_at=now,
                        expires_at=now + timedelta(hours=1),
                    )
                )
                db.add(
                    InfraAutomationPolicy(
                        project_id=100,
                        settings_json=AutomationSettings(
                            enabled=True
                        ).model_dump_json(),
                        version=1,
                        authorization_epoch=1,
                        restore_epoch=1,
                        created_at=now,
                        updated_at=now,
                    )
                )
                db.commit()
        finally:
            engine.dispose()
        os.chmod(self.db, 0o600)
        self.roots = {}
        for role in ("artifacts", "custody"):
            root = self.base / role
            root.mkdir(mode=0o700)
            payload = root / "synthetic.txt"
            payload.write_text(role)
            payload.chmod(0o600)
            self.roots[role] = root
        self.store = RecoveryStore(self.base / "control")
        self.store.initialize(self.db, self.roots)

    def backup(self):
        path = self.base / "backup"
        self.store.backup(path)
        return path

    def test_backup_is_complete_and_private(self):
        path = self.backup()
        self.assertEqual((path / "custody/synthetic.txt").read_text(), "custody")
        self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        manifest = json.loads((path / "manifest.json").read_text())
        self.assertEqual(
            manifest["installation_id"], self.store.status()["installation_id"]
        )
        self.assertTrue(manifest["files"])

    def test_live_participant_denies_backup_and_restore(self):
        backup = self.backup()
        with self.store.participate():
            with self.assertRaises(RecoveryError):
                self.store.backup(self.base / "another")
            with self.assertRaises(RecoveryError):
                self.store.restore(backup)

    def test_restore_invalidates_sessions_and_bumps_past_both_databases(self):
        backup = self.backup()
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE identity_accounts SET authentication_version=50")
            connection.execute(
                "UPDATE infra_automation_policies SET version=version+1, authorization_epoch=authorization_epoch+1,restore_epoch=60"
            )
        result = self.store.restore(backup)
        self.assertGreater(result["generation"], 60)
        self.assertEqual(result["phase"], "reconciliation_required")
        with sqlite3.connect(self.db) as connection:
            self.assertIsNotNone(
                connection.execute(
                    "SELECT revoked_at FROM identity_sessions"
                ).fetchone()[0]
            )
            self.assertIsNotNone(
                connection.execute(
                    "SELECT consumed_at FROM identity_credentials"
                ).fetchone()[0]
            )
            self.assertGreater(
                connection.execute(
                    "SELECT authentication_version FROM identity_accounts"
                ).fetchone()[0],
                50,
            )
            self.assertFalse(
                json.loads(
                    connection.execute(
                        "SELECT settings_json FROM infra_automation_policies"
                    ).fetchone()[0]
                )["enabled"]
            )
        with self.assertRaises(RecoveryError):
            self.store.assert_ready(effects=True)
        self.store.assert_ready(effects=False)

    def test_repeated_restore_cannot_reuse_a_generation(self):
        backup = self.backup()
        first = self.store.restore(backup)["generation"]
        second = self.store.restore(backup)["generation"]
        self.assertGreater(second, first)

    def test_corrupt_or_extra_backup_content_denies_without_reservation(self):
        backup = self.backup()
        before = self.store.status()["generation"]
        (backup / "custody/synthetic.txt").write_text("changed")
        with self.assertRaises(RecoveryError):
            self.store.restore(backup)
        self.assertEqual(self.store.status()["generation"], before)

    def test_symlink_and_public_custody_denied(self):
        (self.roots["custody"] / "link").symlink_to(self.db)
        with self.assertRaises(RecoveryError):
            self.store.backup(self.base / "bad")

    def test_missing_ledger_never_reinitializes_imported_authority(self):
        (self.store.control / "ledger.json").unlink()
        with self.assertRaises(RecoveryError):
            self.store.assert_ready()
        with self.assertRaises(RecoveryError):
            self.store.initialize(self.db, self.roots)

    def test_crash_reservation_blocks_startup_and_resume_uses_same_operation(self):
        backup = self.backup()
        from unittest.mock import patch

        with patch.object(
            self.store, "_stage", side_effect=OSError("synthetic disk failure")
        ):
            with self.assertRaises(RecoveryError):
                self.store.restore(backup)
        reserved = self.store.status()
        self.assertEqual(reserved["phase"], "restore_reserved")
        with self.assertRaises(RecoveryError):
            self.store.assert_ready()
        resumed = self.store.resume()
        self.assertEqual(resumed["generation"], reserved["generation"])
        self.assertEqual(resumed["phase"], "reconciliation_required")

    def test_backup_overlap_rejected(self):
        with self.assertRaises(RecoveryError):
            self.store.backup(self.roots["custody"] / "backup")

    def test_business_errors_keep_identity_with_and_without_configuration(self):
        from dataclasses import replace
        from unittest.mock import patch
        import config
        from infra_automation.lifecycle import LifecycleError
        from infra_automation.operator_recovery import participating_operation

        for control in ("", str(self.store.control)):
            with patch.object(
                config,
                "settings",
                replace(config.settings, recovery_control_path=control),
            ):
                for status in (409, 422, 429):
                    error = LifecycleError(status)
                    with self.assertRaises(LifecycleError) as raised:
                        with participating_operation():
                            raise error
                    self.assertIs(raised.exception, error)

    def test_partial_write_and_fsync_failures_remove_owned_staging(self):
        from unittest.mock import patch
        from infra_automation.operator_recovery import _write

        target = self.base / "atomic.json"
        _write(target, b"original")
        for operation in ("os.write", "os.fsync"):
            with patch(
                "infra_automation.operator_recovery." + operation,
                side_effect=OSError("synthetic no space"),
            ):
                with self.assertRaises(RecoveryError):
                    _write(target, b"replacement", replace=True)
            self.assertEqual(target.read_bytes(), b"original")
            self.assertEqual(list(self.base.glob(".pending-*")), [])

    def test_directory_entry_bound_includes_empty_directories(self):
        from unittest.mock import patch

        for number in range(4):
            (self.roots["custody"] / f"empty-{number}").mkdir(mode=0o700)
        with patch("infra_automation.operator_recovery.MAX_FILES", 3):
            with self.assertRaises(RecoveryError):
                self.store.backup(self.base / "bounded")

    def test_resume_requires_the_reserved_backup_digest(self):
        from unittest.mock import patch

        backup = self.backup()
        with patch.object(self.store, "_stage", side_effect=OSError("crash")):
            with self.assertRaises(RecoveryError):
                self.store.restore(backup)
        manifest_path = backup / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["generation"] += 1
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(RecoveryError):
            self.store.resume()

    def test_publication_interruption_resumes_without_generation_reuse(self):
        from unittest.mock import patch

        original = os.rename
        backup = self.backup()

        # Fail after moving the database aside, before installing its replacement.
        def rename(source, destination, *args, **kwargs):
            if Path(source).name.startswith(".restore-new-"):
                raise OSError("synthetic process interruption")
            return original(source, destination, *args, **kwargs)

        with patch("infra_automation.operator_recovery.os.rename", side_effect=rename):
            with self.assertRaises(RecoveryError):
                self.store.restore(backup)
        generation = self.store.status()["generation"]
        with self.assertRaises(RecoveryError):
            self.store.assert_ready()
        result = self.store.resume()
        self.assertEqual(result["generation"], generation)
        self.assertEqual(result["phase"], "reconciliation_required")

    def test_corrupt_published_target_blocks_resume(self):
        from unittest.mock import patch

        original = os.rename
        backup = self.backup()
        count = 0

        def rename(source, destination, *args, **kwargs):
            nonlocal count
            count += 1
            if count == 3:
                raise OSError("synthetic process interruption")
            return original(source, destination, *args, **kwargs)

        with patch("infra_automation.operator_recovery.os.rename", side_effect=rename):
            with self.assertRaises(RecoveryError):
                self.store.restore(backup)
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE identity_accounts SET username='changed'")
        with self.assertRaises(RecoveryError):
            self.store.resume()

    def test_complete_requires_fresh_global_and_project_admin(self):
        from dataclasses import replace
        from datetime import datetime, timezone, timedelta
        import hashlib
        from unittest.mock import patch
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from models.tables import IdentitySession, IdentityAccount
        from models.repositories.project_memberships import upsert_membership
        from services.identity_service import IdentityService
        from services import project_service as authorization
        import config

        self.store.restore(self.backup())
        engine = create_engine(f"sqlite:///{self.db}")
        factory = sessionmaker(engine, expire_on_commit=False)
        self.addCleanup(engine.dispose)
        now = datetime.now(timezone.utc)
        token, csrf = "a" * 43, "b" * 43
        with factory.begin() as db:
            account = db.get(IdentityAccount, "operator")
            account.is_admin = True
            db.add(
                IdentitySession(
                    id="fresh",
                    principal_id=account.id,
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    csrf_hash=hashlib.sha256(csrf.encode()).hexdigest(),
                    audience="human",
                    security_profile="https",
                    trusted_origin="https://recovery.invalid",
                    authentication_version=account.authentication_version,
                    created_at=now,
                    last_seen_at=now,
                    expires_at=now + timedelta(hours=1),
                )
            )
        identity = IdentityService(
            factory, security_profile="https", trusted_origin="https://recovery.invalid"
        )
        settings = replace(
            config.settings,
            recovery_control_path=str(self.store.control),
            database_url=f"sqlite:///{self.db}",
            identity_profile="https",
            identity_origin="https://recovery.invalid",
            authorization_profile="verified",
        )
        with (
            patch.object(config, "settings", settings),
            authorization.credential_context(
                identity, token, csrf_token=csrf, mutation=True
            ),
        ):
            with self.assertRaises(authorization.TrustedAuthorizationError):
                self.store.complete("Operator checked retained operations.")
            self.assertEqual(self.store.status()["phase"], "reconciliation_required")
            with factory.begin() as db:
                upsert_membership(
                    db,
                    principal_id="operator",
                    project_id=100,
                    workspace_id=None,
                    role="admin",
                )
            # Membership provisioning in this fixture does not mint a new session;
            # the existing session remains bound to current account auth version.
            result = self.store.complete("Operator checked retained operations.")
            self.assertEqual(result["phase"], "ready")
            self.store.assert_ready(effects=True)
            with sqlite3.connect(self.db) as db:
                self.assertEqual(
                    db.execute(
                        "SELECT actor_id FROM infra_automation_restore_events WHERE event='completed'"
                    ).fetchone(),
                    ("operator",),
                )

    def _interrupt_completion(self, *, committed):
        from unittest.mock import patch

        save = self.store._save

        def interrupted(value):
            if not committed and value["phase"] == "completing":
                save(value)
                raise OSError("Synthetic interruption before completion commit")
            if committed and value["phase"] == "ready":
                raise OSError("Synthetic interruption after completion commit")
            return save(value)

        # Reuse the actual fresh-global-admin/permission setup and complete call.
        with patch.object(self.store, "_save", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.test_complete_requires_fresh_global_and_project_admin()
        self.assertEqual(self.store.status()["phase"], "completing")
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE identity_sessions SET expires_at='1970-01-01 00:00:00'")

    def _business_rows(self):
        with sqlite3.connect(self.db) as db:
            names = [
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            ]
            return {
                name: db.execute(f'SELECT * FROM "{name}"').fetchall() for name in names
            }

    def test_resume_committed_completion_needs_no_expired_session(self):
        self._interrupt_completion(committed=True)
        before = self._business_rows()
        result = self.store.resume()
        self.assertEqual(result["phase"], "ready")
        self.assertEqual(self._business_rows(), before)
        self.store.assert_ready(effects=True)
        with sqlite3.connect(self.db) as db:
            self.assertFalse(
                json.loads(
                    db.execute(
                        "SELECT settings_json FROM infra_automation_policies WHERE project_id=100"
                    ).fetchone()[0]
                )["enabled"]
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM infra_automation_restore_events WHERE event='completed'"
                ).fetchone()[0],
                1,
            )

    def test_resume_uncommitted_completion_reopens_only_read_recovery(self):
        self._interrupt_completion(committed=False)
        before = self._business_rows()
        self.assertEqual(self.store.resume()["phase"], "reconciliation_required")
        self.assertEqual(self._business_rows(), before)
        self.store.assert_ready(effects=False)
        with self.assertRaises(RecoveryError):
            self.store.assert_ready(effects=True)

    def test_resume_cannot_publish_ready_without_committed_completion_proof(self):
        self._interrupt_completion(committed=False)
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE infra_automation_recovery_state SET phase='ready'")
        before = self._business_rows()
        with self.assertRaises(RecoveryError):
            self.store.resume()
        self.assertEqual(self.store.status()["phase"], "completing")
        self.assertEqual(self._business_rows(), before)

    def test_empty_nested_directories_and_modes_survive_restore(self):
        empty = self.roots["custody"] / "journal" / "empty"
        empty.parent.mkdir(mode=0o700)
        empty.mkdir(mode=0o700)
        backup = self.backup()
        empty.rmdir()
        self.store.restore(backup)
        self.assertTrue(empty.is_dir())
        self.assertEqual(empty.stat().st_mode & 0o777, 0o700)

    def test_missing_security_guard_blocks_backup_and_restore(self):
        backup = self.backup()
        before = self.store.status()["generation"]
        with sqlite3.connect(self.db) as db:
            db.execute("DROP TRIGGER infra_automation_attempts_immutable")
        with self.assertRaises(RecoveryError):
            self.store.backup(self.base / "missing-guard")
        with self.assertRaises(RecoveryError):
            self.store.restore(backup)
        self.assertEqual(self.store.status()["generation"], before)

    def test_ledger_duplicate_keys_and_boolean_version_deny(self):
        path = self.store.control / "ledger.json"
        original = path.read_bytes()
        path.write_bytes(original[:-1] + b',"version":1}')
        with self.assertRaises(RecoveryError):
            self.store.status()
        value = json.loads(original)
        value["version"] = True
        path.write_text(json.dumps(value))
        with self.assertRaises(RecoveryError):
            self.store.status()

    def test_unconfigured_startup_cannot_ignore_a_bound_database(self):
        from dataclasses import replace
        from unittest.mock import patch
        import config
        from infra_automation.operator_recovery import assert_startup_allowed

        with patch.object(
            config,
            "settings",
            replace(
                config.settings,
                database_url=f"sqlite:///{self.db}",
                recovery_control_path="",
            ),
        ):
            with self.assertRaises(RecoveryError):
                assert_startup_allowed()

    def test_disabled_recovery_imports_without_fcntl(self):
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.modules['fcntl']=None; import infra_automation.operator_recovery as recovery; import services.identity_service; import services.infra_automation_policy; assert recovery.fcntl is None",
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_recovery_startup_serves_without_background_effects(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        import app

        async def scenario():
            with (
                patch(
                    "infra_automation.operator_recovery.assert_startup_allowed",
                    return_value={"phase": "reconciliation_required"},
                ),
                patch("app.init_db"),
                patch(
                    "app._start_engine_coordinator", new_callable=AsyncMock
                ) as engine,
                patch(
                    "app._topology_drift_scheduler_loop", new_callable=AsyncMock
                ) as drift,
            ):
                async with app.lifespan(SimpleNamespace(state=SimpleNamespace())):
                    engine.assert_not_called()
                    drift.assert_not_called()

        asyncio.run(scenario())

    def test_sqlite_managed_metadata_reads_preserve_wal_locks_and_revocation(self):
        import subprocess
        import sys
        from datetime import datetime, timezone, timedelta
        import hashlib
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from models.tables import IdentitySession
        from services.identity_service import IdentityService, IdentityError
        from infra_automation.operator_recovery import _connect

        # Keep a WAL connection alive, as the app's pool does. A different
        # process probes the actual kernel byte-range lock, not a mocked close.
        parent = sqlite3.connect(self.db)
        self.addCleanup(parent.close)
        self.assertEqual(parent.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        parent.execute("SELECT 1 FROM identity_accounts").fetchone()
        probe = "import os,fcntl,sys; fd=os.open(sys.argv[1],os.O_RDWR)\ntry: fcntl.lockf(fd,fcntl.LOCK_EX|fcntl.LOCK_NB,510,0x40000002,os.SEEK_SET); print('released')\nexcept BlockingIOError: print('held')\nfinally: os.close(fd)"

        def lock_state():
            result = subprocess.run(
                [sys.executable, "-c", probe, str(self.db)],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            return result.stdout.strip()

        self.assertEqual(lock_state(), "held")
        with _connect(self.db) as connection:
            connection.execute(
                "SELECT generation FROM infra_automation_recovery_state"
            ).fetchone()
        self.assertEqual(lock_state(), "held")
        engine = create_engine(f"sqlite:///{self.db}")
        self.addCleanup(engine.dispose)
        factory = sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(timezone.utc)
        token = "a" * 43
        with factory.begin() as db:
            db.add(
                IdentitySession(
                    id="wal-current",
                    principal_id="operator",
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    csrf_hash="b" * 64,
                    audience="human",
                    security_profile="https",
                    trusted_origin="https://recovery.invalid",
                    authentication_version=1,
                    created_at=now,
                    last_seen_at=now,
                    expires_at=now + timedelta(hours=1),
                )
            )
        identity = IdentityService(
            factory, security_profile="https", trusted_origin="https://recovery.invalid"
        )
        self.assertEqual(identity.resolve_session(token).authentication_version, 1)
        writer = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('BEGIN IMMEDIATE'); c.execute('UPDATE identity_accounts SET authentication_version=authentication_version+1'); c.execute(\"UPDATE identity_sessions SET revoked_at='2026-01-01'\");c.commit();c.close()"
        subprocess.run(
            [sys.executable, "-c", writer, str(self.db)],
            capture_output=True,
            timeout=15,
            check=True,
        )
        self.assertEqual(
            parent.execute(
                "SELECT authentication_version FROM identity_accounts"
            ).fetchone()[0],
            2,
        )
        for _ in range(3):
            with self.assertRaises(IdentityError) as denied:
                identity.resolve_session(token)
            self.assertEqual(denied.exception.status_code, 401)

    def test_sqlite_connection_validation_denies_unsafe_paths_without_creation(self):
        from infra_automation.operator_recovery import _connect

        link = self.base / "database-link"
        link.symlink_to(self.db)
        with self.assertRaises(RecoveryError):
            with _connect(link):
                self.fail("Symlink database accepted")
        self.db.chmod(0o644)
        with self.assertRaises(RecoveryError):
            with _connect(self.db):
                self.fail("Public database accepted")
        missing = self.base / "missing.db"
        with self.assertRaises(OSError):
            with _connect(missing):
                self.fail("Missing database created")
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
