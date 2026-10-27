"""Copied legacy DB upgrade, rollback and fail-closed automation schema checks."""

from __future__ import annotations

from contextlib import closing
from importlib import reload
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config

import config
import models.database as database

HEAD = "032_add_infra_automation_engine"
PREVIOUS = "031_add_infra_workflows"
TABLES = (
    "infra_automation_runs",
    "infra_automation_attempts",
    "infra_automation_coordinator_lease",
    "infra_automation_run_requests",
)


class InfraAutomationEngineMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "copy.db"
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

    def test_copied_v140_and_prior_head_upgrade_preserves_records(self):
        for baseline in ("028_add_narrative_guidance_payload", PREVIOUS):
            with self.subTest(baseline=baseline):
                if self.path.exists():
                    self.path.unlink()
                command.upgrade(self.config, baseline)
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute(
                        "INSERT INTO app_settings VALUES ('synthetic-retained', 'value', CURRENT_TIMESTAMP)"
                    )
                    if baseline == PREVIOUS:
                        db.execute(
                            "INSERT INTO identity_accounts VALUES ('human','synthetic','human','verifier',1,1,1,CURRENT_TIMESTAMP,NULL)"
                        )
                        db.execute(
                            "INSERT INTO projects (id,project_key,display_name,is_default,created_at,updated_at,authorization_required) VALUES (100,'synthetic','Synthetic',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1)"
                        )
                        db.execute(
                            "INSERT INTO project_memberships VALUES ('membership','human',100,NULL,'admin',1,7,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                        )
                source = self.path.with_name("source.db")
                shutil.copy2(self.path, source)
                # Migration runs against the copied synthetic DB, never an operator DB.
                copied_bytes = source.read_bytes()
                self.path.unlink()
                shutil.copy2(source, self.path)
                self.initialize()
                self.assertEqual(source.read_bytes(), copied_bytes)
                with closing(sqlite3.connect(self.path)) as db:
                    self.assertEqual(
                        db.execute(
                            "SELECT version_num FROM alembic_version"
                        ).fetchone()[0],
                        HEAD,
                    )
                    self.assertEqual(
                        db.execute(
                            "SELECT value FROM app_settings WHERE key='synthetic-retained'"
                        ).fetchone()[0],
                        "value",
                    )
                    for table in TABLES:
                        self.assertEqual(
                            db.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0
                        )
                    self.assertEqual(
                        db.execute("PRAGMA foreign_key_check").fetchall(), []
                    )
                    if baseline == "028_add_narrative_guidance_payload":
                        self.assertEqual(
                            db.execute(
                                "SELECT count(*) FROM identity_accounts"
                            ).fetchone()[0],
                            0,
                        )
                    if baseline == PREVIOUS:
                        self.assertEqual(
                            db.execute(
                                "SELECT authorization_version FROM project_memberships"
                            ).fetchone()[0],
                            7,
                        )
                database.engine.dispose()

    def test_downgrade_reupgrade_and_unversioned_recognition(self):
        command.upgrade(self.config, "head")
        command.downgrade(self.config, PREVIOUS)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertFalse(
                set(TABLES)
                & {
                    r[0]
                    for r in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            )
        command.upgrade(self.config, "head")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP TABLE alembic_version")
        self.initialize()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                HEAD,
            )

    def test_partial_tables_triggers_constraints_fail_closed_before_create_all(self):
        corruptions = [f"DROP TABLE {table}" for table in TABLES] + [
            "DROP TRIGGER infra_engine_output_immutable",
            "DROP TRIGGER infra_engine_run_revision_scope",
            "DROP TRIGGER infra_automation_runs_immutable",
            "ALTER TABLE infra_automation_runs DROP COLUMN version",
            "UPDATE alembic_version SET version_num='031_add_infra_workflows'",
        ]
        for versioned in (True, False):
            for corruption in corruptions:
                if not versioned and corruption.startswith("UPDATE alembic"):
                    continue
                with self.subTest(versioned=versioned, corruption=corruption):
                    database.engine.dispose()
                    if self.path.exists():
                        self.path.unlink()
                    command.upgrade(self.config, "head")
                    with closing(sqlite3.connect(self.path)) as db, db:
                        if corruption.startswith("ALTER TABLE"):
                            db.execute("PRAGMA writable_schema=ON")
                            db.execute(
                                "UPDATE sqlite_master SET sql=replace(sql,'retained_bytes >= length(snapshot_bytes)','retained_bytes >= 0') WHERE name='infra_automation_runs'"
                            )
                        else:
                            db.execute(corruption)
                        if not versioned:
                            db.execute("DROP TABLE alembic_version")
                    with self.assertRaisesRegex(
                        RuntimeError, "partial infra automation"
                    ):
                        self.initialize()

    def test_orphan_automation_table_without_baseline_is_not_adopted(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE infra_automation_runs (id TEXT)")
        with self.assertRaisesRegex(RuntimeError, "partial infra automation"):
            self.initialize()
