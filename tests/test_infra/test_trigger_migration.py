"""Signed authority schema recovery rejects incomplete replay fences."""

from __future__ import annotations

from contextlib import closing
from importlib import reload
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


class TriggerMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "triggers.db"
        self.env = patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{self.path}"})
        self.env.start()
        self.config = Config("alembic.ini")
        self.config.set_main_option("sqlalchemy.url", f"sqlite:///{self.path}")

    def tearDown(self):
        database.engine.dispose()
        self.env.stop()
        reload(config)
        reload(database)
        self.temp.cleanup()

    def initialize(self):
        reload(config)
        reload(database)
        database.init_db()

    def test_restart_and_missing_history_preserve_empty_authority(self):
        command.upgrade(self.config, "head")
        self.initialize()
        with closing(sqlite3.connect(self.path)) as db, db:
            before = dict(
                db.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
            )
            db.execute("DROP TABLE alembic_version")
        self.initialize()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                "039_add_signed_trigger_intake",
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM identity_accounts").fetchone()[0], 0
            )
            self.assertEqual(
                dict(
                    db.execute(
                        "SELECT name, sql FROM sqlite_master WHERE type='trigger'"
                    )
                ),
                before,
            )
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_partial_signed_authority_denies_before_create_all(self):
        for sql in (
            "DROP TABLE infra_automation_trigger_clock",
            "DROP TABLE infra_automation_trigger_nonces",
            "DROP TABLE infra_automation_run_origins",
            "DROP TRIGGER infra_trigger_clock_monotonic",
            "DROP TRIGGER infra_trigger_nonce_no_update",
            "ALTER TABLE infra_automation_run_origins DROP COLUMN operation_digest",
            "UPDATE alembic_version SET version_num='038_add_declared_unit_maps'",
        ):
            with self.subTest(sql=sql):
                database.engine.dispose()
                self.path.unlink(missing_ok=True)
                command.upgrade(self.config, "head")
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute(sql)
                with patch.object(database.Base.metadata, "create_all") as create_all:
                    with self.assertRaisesRegex(RuntimeError, "partial infra"):
                        self.initialize()
                    create_all.assert_not_called()

    def test_clock_cannot_rewind_or_be_erased(self):
        command.upgrade(self.config, "head")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT INTO infra_automation_trigger_clock VALUES(1,'2026-11-05 12:00:00')"
            )
        for sql in (
            "UPDATE infra_automation_trigger_clock SET last_seen_at='2026-11-05 11:59:59'",
            "DELETE FROM infra_automation_trigger_clock",
            "INSERT OR REPLACE INTO infra_automation_trigger_clock VALUES(1,'2026-11-05 11:59:59')",
        ):
            with self.subTest(sql=sql), closing(sqlite3.connect(self.path)) as db:
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql)
        with self.assertRaisesRegex(RuntimeError, "Retained signed authority"):
            command.downgrade(self.config, "038_add_declared_unit_maps")
