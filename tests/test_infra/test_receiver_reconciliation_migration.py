"""Receiver migration restart and fail-closed brownfield recognition."""

from __future__ import annotations

from contextlib import closing
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

HEAD = "036_add_receiver_reconciliation"
CURRENT_HEAD = "042_add_receiver_recovery"
PREVIOUS = "035_add_infra_handoffs"


class ReceiverReconciliationMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "receiver.db"
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

    def test_restart_recognizes_current_head_without_recreating_table(self):
        command.upgrade(self.config, HEAD)
        self.initialize()
        self.initialize()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                CURRENT_HEAD,
            )
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_unversioned_complete_schema_preserves_immutable_guards(self):
        command.upgrade(self.config, HEAD)
        with closing(sqlite3.connect(self.path)) as db, db:
            before = db.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name"
            ).fetchall()
            db.execute("DROP TABLE alembic_version")
        self.initialize()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                CURRENT_HEAD,
            )
            after = dict(
                db.execute(
                    "SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name"
                ).fetchall()
            )
            current = import_module(f"migrations.versions.{CURRENT_HEAD}")
            overrides: dict[str, str] = {}
            while current.revision != HEAD:
                overrides = {**getattr(current, "OVERRIDES", {}), **overrides}
                current = import_module(f"migrations.versions.{current.down_revision}")
            for name, sql in before:
                expected = (
                    f"CREATE TRIGGER {name} {overrides[name]}"
                    if name in overrides
                    else sql
                )
                self.assertEqual(after[name], expected)

    def test_partial_receiver_guard_denies_before_create_all(self):
        command.upgrade(self.config, HEAD)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP TRIGGER infra_external_fact_no_update")
        with patch.object(database.Base.metadata, "create_all") as create_all:
            with self.assertRaisesRegex(RuntimeError, "partial infra automation"):
                self.initialize()
            create_all.assert_not_called()

    def test_upgrade_downgrade_preserves_prior_records(self):
        command.upgrade(self.config, PREVIOUS)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT INTO app_settings VALUES ('receiver-proof','retained',CURRENT_TIMESTAMP)"
            )
        self.initialize()
        command.downgrade(self.config, PREVIOUS)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute(
                    "SELECT value FROM app_settings WHERE key='receiver-proof'"
                ).fetchone()[0],
                "retained",
            )
            self.assertIsNone(
                db.execute(
                    "SELECT name FROM sqlite_master WHERE name='infra_automation_external_facts'"
                ).fetchone()
            )
        self.initialize()
