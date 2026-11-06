"""Recognize complete handoff migrations and reject interrupted authority guards."""

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

HEAD = "035_add_infra_handoffs"
CURRENT_HEAD = "039_add_signed_trigger_intake"
PREVIOUS = "034_add_infra_decisions"
MIGRATION = import_module(f"migrations.versions.{HEAD}")


class InfraAutomationHandoffMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "handoff.db"
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

    def fresh_head(self):
        database.engine.dispose()
        self.path.unlink(missing_ok=True)
        command.upgrade(self.config, HEAD)

    def assert_head(self):
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                CURRENT_HEAD,
            )
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_prior_head_upgrade_and_downgrade_preserve_existing_records(self):
        command.upgrade(self.config, PREVIOUS)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT INTO app_settings VALUES ('handoff-migration', 'retained', CURRENT_TIMESTAMP)"
            )
        self.initialize()
        self.initialize()
        self.assert_head()
        with closing(sqlite3.connect(self.path)) as db:
            for table in MIGRATION.TABLES:
                self.assertEqual(
                    db.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0
                )
        command.downgrade(self.config, PREVIOUS)
        with closing(sqlite3.connect(self.path)) as db:
            tables = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertFalse(set(MIGRATION.TABLES) & tables)
            self.assertEqual(
                db.execute(
                    "SELECT value FROM app_settings WHERE key='handoff-migration'"
                ).fetchone()[0],
                "retained",
            )
        self.initialize()
        self.assert_head()

    def test_complete_unversioned_handoff_schema_is_adopted_without_replacing_guards(
        self,
    ):
        self.fresh_head()
        with closing(sqlite3.connect(self.path)) as db, db:
            before = db.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger' ORDER BY name"
            ).fetchall()
            db.execute("DROP TABLE alembic_version")
        self.initialize()
        self.assert_head()
        with closing(sqlite3.connect(self.path)) as db:
            after = dict(
                db.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type='trigger' ORDER BY name"
                ).fetchall()
            )
            previous = dict(before)
            self.assertEqual({name: after[name] for name in previous}, previous)
            current = import_module(f"migrations.versions.{CURRENT_HEAD}")
            added_guards: set[str] = set()
            while current.revision != HEAD:
                added_guards.update(getattr(current, "GUARDS", {}))
                current = import_module(f"migrations.versions.{current.down_revision}")
            self.assertEqual(set(after) - set(previous), added_guards)

    def test_partial_handoff_tables_and_guards_fail_before_create_all(self):
        corruptions = [f"DROP TABLE {table}" for table in MIGRATION.TABLES] + [
            "DROP TRIGGER infra_run_target_scope",
            "DROP TRIGGER infra_grant_transition",
            "DROP INDEX uq_infra_target_held",
        ]
        for versioned in (True, False):
            for corruption in corruptions:
                with self.subTest(versioned=versioned, corruption=corruption):
                    self.fresh_head()
                    with closing(sqlite3.connect(self.path)) as db, db:
                        db.execute(corruption)
                        if not versioned:
                            db.execute("DROP TABLE alembic_version")
                    with (
                        patch.object(
                            database.Base.metadata, "create_all"
                        ) as create_all,
                        self.assertRaisesRegex(
                            RuntimeError, "partial infra automation"
                        ),
                    ):
                        self.initialize()
                    create_all.assert_not_called()

    def test_same_name_permissive_guard_and_nonpartial_lock_index_are_rejected(self):
        for versioned in (True, False):
            for corruption in ("guard", "index"):
                with self.subTest(versioned=versioned, corruption=corruption):
                    self.fresh_head()
                    with closing(sqlite3.connect(self.path)) as db, db:
                        if corruption == "guard":
                            db.execute("DROP TRIGGER infra_run_target_scope")
                            db.execute(
                                "CREATE TRIGGER infra_run_target_scope BEFORE INSERT ON infra_automation_run_targets BEGIN SELECT 1; END"
                            )
                        else:
                            db.execute("DROP INDEX uq_infra_target_held")
                            db.execute(
                                "CREATE UNIQUE INDEX uq_infra_target_held ON infra_automation_target_locks(target_id)"
                            )
                        if not versioned:
                            db.execute("DROP TABLE alembic_version")
                    with self.assertRaisesRegex(
                        RuntimeError, "partial infra automation"
                    ):
                        self.initialize()

    def test_handoff_revision_and_schema_must_agree(self):
        for schema_revision, marker in ((HEAD, PREVIOUS), (PREVIOUS, HEAD)):
            with self.subTest(schema_revision=schema_revision, marker=marker):
                database.engine.dispose()
                self.path.unlink(missing_ok=True)
                command.upgrade(self.config, schema_revision)
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute("UPDATE alembic_version SET version_num=?", (marker,))
                with self.assertRaisesRegex(
                    RuntimeError, "partial infra handoff migration history"
                ):
                    self.initialize()
