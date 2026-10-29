"""Membership migrations preserve legacy data and reject partial authority schema."""

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

HEAD = "034_add_infra_decisions"
PREVIOUS = "029_add_identity_lifecycle"


class ProjectMembershipMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "migration.db"
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

    def test_fresh_head_has_empty_membership_and_audit_and_default_false_markers(self):
        command.upgrade(self.config, "head")
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(
                db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                HEAD,
            )
            for table in ("project_memberships", "project_authorization_audit"):
                self.assertEqual(
                    db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0
                )
            for table in ("projects", "analysis_reports"):
                marker = next(
                    row
                    for row in db.execute(f"PRAGMA table_info({table})")
                    if row[1] == "authorization_required"
                )
                self.assertEqual(marker[3:5], (1, "0"))
            foreign_keys = list(
                db.execute("PRAGMA foreign_key_list(project_memberships)")
            )
            self.assertTrue(
                any(
                    row[2:5] == ("project_workspaces", "project_id", "project_id")
                    for row in foreign_keys
                )
            )
            self.assertTrue(
                any(
                    row[2:5] == ("project_workspaces", "workspace_id", "id")
                    for row in foreign_keys
                )
            )

    def test_upgrade_downgrade_reupgrade_preserves_identity_and_legacy_data(self):
        command.upgrade(self.config, PREVIOUS)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT INTO app_settings VALUES ('legacy-test', 'preserve', CURRENT_TIMESTAMP)"
            )
            db.execute(
                "INSERT INTO identity_accounts VALUES ('human','synthetic','human','verifier',1,1,1,CURRENT_TIMESTAMP,NULL)"
            )
        command.upgrade(self.config, HEAD)
        command.downgrade(self.config, PREVIOUS)
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(
                db.execute(
                    "SELECT value FROM app_settings WHERE key='legacy-test'"
                ).fetchone()[0],
                "preserve",
            )
            self.assertEqual(
                db.execute("SELECT id FROM identity_accounts").fetchone()[0], "human"
            )
            self.assertNotIn(
                "authorization_required",
                {r[1] for r in db.execute("PRAGMA table_info(projects)")},
            )
        command.upgrade(self.config, HEAD)
        self.initialize()

    def test_unversioned_complete_schema_recognized(self):
        command.upgrade(self.config, "head")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP TABLE alembic_version")
        self.initialize()
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(
                db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                HEAD,
            )

    def test_partial_current_head_or_unversioned_schema_fails_closed(self):
        for versioned in (True, False):
            for table in ("project_memberships", "project_authorization_audit"):
                with self.subTest(versioned=versioned, table=table):
                    if self.path.exists():
                        self.path.unlink()
                    command.upgrade(self.config, "head")
                    with closing(sqlite3.connect(self.path)) as db, db:
                        db.execute(f"DROP TABLE {table}")
                        if not versioned:
                            db.execute("DROP TABLE alembic_version")
                    with self.assertRaisesRegex(
                        RuntimeError, "partial project authorization"
                    ):
                        self.initialize()
                    database.engine.dispose()

    def test_missing_marker_and_role_constraint_fail_closed(self):
        for corruption in (
            "ALTER TABLE projects DROP COLUMN authorization_required",
            "PRAGMA writable_schema=ON",
        ):
            with self.subTest(corruption=corruption):
                if self.path.exists():
                    self.path.unlink()
                command.upgrade(self.config, "head")
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute(corruption)
                    if corruption.startswith("PRAGMA"):
                        db.execute(
                            "UPDATE sqlite_master SET sql=replace(sql, 'authorization_version > 0', 'authorization_version >= 0') WHERE name='project_memberships'"
                        )
                with self.assertRaisesRegex(
                    RuntimeError, "partial project authorization"
                ):
                    self.initialize()
                database.engine.dispose()
