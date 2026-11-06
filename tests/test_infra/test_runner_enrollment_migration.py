"""Fail closed on interrupted runner authority migrations before create_all."""

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


class RunnerEnrollmentMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "runner.db"
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

    def test_restart_and_unversioned_head_are_recognized(self):
        command.upgrade(self.config, "head")
        self.initialize()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP TABLE alembic_version")
        self.initialize()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                "039_add_signed_trigger_intake",
            )
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_partial_runner_authority_schema_and_wrong_revision_are_denied(self):
        for sql in (
            "DROP TABLE infra_automation_runner_tasks",
            "DROP TABLE infra_automation_runner_enrollments",
            "DROP TABLE infra_automation_runners",
            "ALTER TABLE infra_automation_runners DROP COLUMN credential_hash",
            "UPDATE alembic_version SET version_num='036_add_receiver_reconciliation'",
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
