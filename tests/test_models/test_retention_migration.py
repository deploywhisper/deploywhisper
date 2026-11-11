"""Retention migrations retain historical guards and reject interrupted schemas."""

from __future__ import annotations

from importlib import import_module
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from models import database


class RetentionMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.url = f"sqlite:///{Path(self.temp.name) / 'retention.db'}"
        self.env = self.enterContext(patch.dict(os.environ, {"DATABASE_URL": self.url}))
        self.config = Config("alembic.ini")
        self.config.set_main_option("sqlalchemy.url", self.url)
        command.upgrade(self.config, "039_add_signed_trigger_intake")
        command.upgrade(self.config, "040_add_manifest_retention")
        self.engine = create_engine(self.url)
        self.addCleanup(self.engine.dispose)

    def test_prior_head_upgrade_and_effective_guards_survive_restart_checks(self):
        for _ in range(2):
            with self.engine.begin() as db:
                tables = set(inspect(db).get_table_names())
                self.assertTrue(
                    database._infra_automation_schema_complete(
                        db, tables, "033_add_infra_preflight"
                    )
                )
                self.assertTrue(
                    database._infra_automation_schema_complete(
                        db, tables, "032_add_infra_automation_engine"
                    )
                )
                self.assertTrue(
                    database._infra_automation_schema_complete(
                        db, tables, "040_add_manifest_retention"
                    )
                )
                self.assertEqual(
                    db.exec_driver_sql("PRAGMA foreign_key_check").all(), []
                )

    def test_missing_or_original_reinstalled_guard_fails_closed(self):
        migration = import_module("migrations.versions.040_add_manifest_retention")
        original = import_module("migrations.versions.033_add_infra_preflight")
        override = next(iter(migration.OVERRIDES))
        for replacement in (None, original.GUARDS[override]):
            with self.subTest(replacement=replacement), self.engine.begin() as db:
                db.exec_driver_sql(f"DROP TRIGGER IF EXISTS {override}")
                if replacement:
                    db.exec_driver_sql(f"CREATE TRIGGER {override} {replacement}")
                with self.assertRaisesRegex(RuntimeError, "partial infra"):
                    database._infra_automation_schema_complete(
                        db,
                        set(inspect(db).get_table_names()),
                        "033_add_infra_preflight",
                    )
                db.exec_driver_sql(f"DROP TRIGGER IF EXISTS {override}")
                db.exec_driver_sql(
                    f"CREATE TRIGGER {override} {migration.OVERRIDES[override]}"
                )

    def test_partial_table_or_missing_receipt_guard_fails_closed(self):
        with self.engine.begin() as db:
            db.exec_driver_sql("DROP TRIGGER infra_retention_no_delete")
            with self.assertRaisesRegex(RuntimeError, "partial infra"):
                database._infra_automation_schema_complete(
                    db, set(inspect(db).get_table_names()), "040_add_manifest_retention"
                )

    def test_original_run_counter_guard_cannot_be_reinstalled_after_retention(self):
        original = import_module("migrations.versions.032_add_infra_automation_engine")
        with self.engine.begin() as db:
            db.exec_driver_sql("DROP TRIGGER infra_automation_runs_immutable")
            db.exec_driver_sql(
                "CREATE TRIGGER infra_automation_runs_immutable "
                + original.GUARDS["infra_automation_runs_immutable"]
            )
            with self.assertRaisesRegex(RuntimeError, "partial infra"):
                database._infra_automation_schema_complete(
                    db,
                    set(inspect(db).get_table_names()),
                    "032_add_infra_automation_engine",
                )
