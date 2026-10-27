"""Identity schema upgrade, brownfield recovery, and rollback contracts."""

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


class IdentityMigrationTests(unittest.TestCase):
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

    def tables(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            return {
                r[0]
                for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }

    def test_fresh_has_only_three_identity_tables_and_no_default_account(self):
        command.upgrade(self.config, "head")
        self.assertEqual(
            {name for name in self.tables() if name.startswith("identity_")},
            {"identity_accounts", "identity_sessions", "identity_credentials"},
        )
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM identity_accounts").fetchone()[0], 0
            )
            self.assertEqual(
                db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                "033_add_infra_preflight",
            )
            for table in ("identity_sessions", "identity_credentials"):
                self.assertEqual(
                    db.execute(f"PRAGMA foreign_key_list({table})").fetchone()[2],
                    "identity_accounts",
                )
            columns = {r[1] for r in db.execute("PRAGMA table_info(identity_sessions)")}
            self.assertTrue(
                {
                    "security_profile",
                    "trusted_origin",
                    "authentication_version",
                    "expires_at",
                    "revoked_at",
                }
                <= columns
            )

    def test_upgrade_rollback_reupgrade_preserves_legacy_state(self):
        command.upgrade(self.config, "028_add_narrative_guidance_payload")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT INTO app_settings VALUES ('legacy-test', 'preserve', CURRENT_TIMESTAMP)"
            )
        command.upgrade(self.config, "head")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT INTO app_settings VALUES ('identity.login_limits.v1', '{}', CURRENT_TIMESTAMP)"
            )
        command.downgrade(self.config, "028_add_narrative_guidance_payload")
        self.assertFalse(any(name.startswith("identity_") for name in self.tables()))
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(
                db.execute(
                    "SELECT value FROM app_settings WHERE key='legacy-test'"
                ).fetchone()[0],
                "preserve",
            )
            self.assertIsNone(
                db.execute(
                    "SELECT value FROM app_settings WHERE key='identity.login_limits.v1'"
                ).fetchone()
            )
        command.upgrade(self.config, "head")
        reload(config)
        reload(database)
        database.init_db()

    def test_unversioned_complete_schema_is_recognized(self):
        command.upgrade(self.config, "head")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP TABLE alembic_version")
        reload(config)
        reload(database)
        database.init_db()
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(
                db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                "033_add_infra_preflight",
            )

    def test_unversioned_partial_identity_fails_closed(self):
        command.upgrade(self.config, "head")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP TABLE alembic_version")
            db.execute("DROP TABLE identity_credentials")
        reload(config)
        reload(database)
        with self.assertRaisesRegex(RuntimeError, "partial identity"):
            database.init_db()

    def test_versioned_partial_identity_fails_closed(self):
        command.upgrade(self.config, "head")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP TABLE identity_credentials")
        reload(config)
        reload(database)
        with self.assertRaisesRegex(RuntimeError, "partial identity"):
            database.init_db()
