"""A partial reconciliation issuer schema must never become implicit authority."""

from __future__ import annotations

from importlib import import_module, reload
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config

import config
import models.database as database


class ReceiverRecoveryMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve() / "recovery.db"
        self.env = patch.dict(
            os.environ, {"DATABASE_URL": "sqlite:///" + str(self.path)}
        )
        self.env.start()
        self.cfg = Config("alembic.ini")
        self.cfg.set_main_option("sqlalchemy.url", "sqlite:///" + str(self.path))
        self.migration = import_module("migrations.versions.042_add_receiver_recovery")
        self.addCleanup(self.cleanup)

    def cleanup(self):
        database.engine.dispose()
        self.env.stop()
        reload(config)
        reload(database)
        self.temp.cleanup()

    def initialize(self):
        reload(config)
        reload(database)
        database.init_db()

    def test_upgrade_restart_and_unversioned_adoption_mint_no_credentials(self):
        command.upgrade(self.cfg, "041_add_operator_recovery")
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO app_settings VALUES ('receiver-recovery-proof','retained',CURRENT_TIMESTAMP)"
            )
        self.initialize()
        with sqlite3.connect(self.path) as db:
            guards = dict(
                db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'")
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM infra_automation_receiver_recovery_credentials"
                ).fetchone()[0],
                0,
            )
            db.execute("DROP TABLE alembic_version")
        self.initialize()
        with sqlite3.connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                self.migration.revision,
            )
            self.assertEqual(
                db.execute(
                    "SELECT value FROM app_settings WHERE key='receiver-recovery-proof'"
                ).fetchone()[0],
                "retained",
            )
            self.assertEqual(
                dict(
                    db.execute(
                        "SELECT name,sql FROM sqlite_master WHERE type='trigger'"
                    )
                ),
                guards,
            )
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_each_missing_guard_denies_before_metadata_repair(self):
        for guard in self.migration.GUARDS:
            with self.subTest(guard=guard):
                self.initialize()
                with sqlite3.connect(self.path) as db:
                    db.execute(f'DROP TRIGGER "{guard}"')
                with patch.object(database.Base.metadata, "create_all") as repair:
                    with self.assertRaisesRegex(
                        RuntimeError, "partial infra automation"
                    ):
                        self.initialize()
                    repair.assert_not_called()
                # Restore this exact guard before probing the next one.
                with sqlite3.connect(self.path) as db:
                    db.execute(
                        f'CREATE TRIGGER "{guard}" {self.migration.GUARDS[guard]}'
                    )

    def test_false_old_revision_cannot_hide_current_issuer_table(self):
        self.initialize()
        with sqlite3.connect(self.path) as db:
            db.execute(
                "UPDATE alembic_version SET version_num='041_add_operator_recovery'"
            )
        with patch.object(database.Base.metadata, "create_all") as repair:
            with self.assertRaisesRegex(RuntimeError, "partial receiver recovery"):
                self.initialize()
            repair.assert_not_called()

    def test_empty_downgrade_preserves_all_older_immutability_guards(self):
        command.upgrade(self.cfg, "041_add_operator_recovery")
        with sqlite3.connect(self.path) as db:
            before = dict(
                db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'")
            )
        command.upgrade(self.cfg, self.migration.revision)
        command.downgrade(self.cfg, "041_add_operator_recovery")
        with sqlite3.connect(self.path) as db:
            self.assertEqual(
                dict(
                    db.execute(
                        "SELECT name,sql FROM sqlite_master WHERE type='trigger'"
                    )
                ),
                before,
            )
            self.assertIsNone(
                db.execute(
                    "SELECT name FROM sqlite_master WHERE name='infra_automation_receiver_recovery_credentials'"
                ).fetchone()
            )
