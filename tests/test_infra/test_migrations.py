"""Migration tests for the evidence-domain schema."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from importlib import reload
from pathlib import Path

import config as config_module
import models.database as database_module
import models.tables as tables_module
from alembic import command
from alembic.config import Config


class MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "migration.db"
        self.database_url = f"sqlite:///{self.db_path}"
        self.previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = self.database_url

    def tearDown(self) -> None:
        if self.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.previous_database_url
        self.tempdir.cleanup()

    def _config(self) -> Config:
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", self.database_url)
        return config

    def _table_columns(self, table_name: str) -> set[str]:
        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            return {
                row[1]
                for row in sqlite_conn.execute(f"PRAGMA table_info({table_name})")
            }
        finally:
            sqlite_conn.close()

    def _table_info(self, table_name: str) -> list[tuple]:
        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            return list(sqlite_conn.execute(f"PRAGMA table_info({table_name})"))
        finally:
            sqlite_conn.close()

    def test_upgrade_head_creates_evidence_schema_on_clean_database(self) -> None:
        command.upgrade(self._config(), "head")

        self.assertIn("finding_id", self._table_columns("evidence_items"))
        self.assertIn("analysis_id", self._table_columns("findings"))
        self.assertIn("analysis_id", self._table_columns("risk_assessments"))
        self.assertIn("analysis_id", self._table_columns("context_snapshots"))
        self.assertIn("report_schema_version", self._table_columns("analysis_reports"))
        self.assertIn("blast_radius_json", self._table_columns("analysis_reports"))
        report_schema_row = next(
            row
            for row in self._table_info("analysis_reports")
            if row[1] == "report_schema_version"
        )
        self.assertIsNone(report_schema_row[4])

    def test_upgrade_head_preserves_existing_analysis_reports(self) -> None:
        command.upgrade(self._config(), "0001_create_analysis_reports")

        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute(
            """
            INSERT INTO analysis_reports (
                risk_score,
                severity,
                recommendation,
                top_risk,
                parse_summary,
                narrative_opening,
                narrative_explanation,
                warnings_json,
                contributors_json,
                analyzed_files_json,
                llm_provider,
                llm_model,
                llm_local_mode,
                assessment_source,
                narrative_source,
                narrative_skills_json,
                source_interface,
                trigger_type,
                trigger_id,
                dashboard_display_duration_seconds,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                42,
                "medium",
                "caution",
                "Broad ingress change",
                "1 parsed, 0 failed, 0 skipped, 1 normalized changes",
                "CAUTION: review the change.",
                "Ingress widened on a shared service.",
                "[]",
                "[]",
                '["plan.json"]',
                "ollama",
                "ollama/llama3",
                "true",
                "heuristic-only",
                "fallback",
                '["terraform"]',
                "api",
                "session",
                "sess-123",
                None,
                "2026-04-20T00:00:00+00:00",
            ),
        )
        sqlite_conn.commit()
        sqlite_conn.close()

        command.upgrade(self._config(), "head")

        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            report_count = sqlite_conn.execute(
                "SELECT COUNT(*) FROM analysis_reports"
            ).fetchone()[0]
            schema_version = sqlite_conn.execute(
                "SELECT report_schema_version FROM analysis_reports LIMIT 1"
            ).fetchone()[0]
            finding_fks = sqlite_conn.execute(
                "PRAGMA foreign_key_list(findings)"
            ).fetchall()
            evidence_fks = sqlite_conn.execute(
                "PRAGMA foreign_key_list(evidence_items)"
            ).fetchall()
        finally:
            sqlite_conn.close()

        self.assertEqual(report_count, 1)
        self.assertEqual(schema_version, "v2")
        self.assertTrue(any(row[2] == "analysis_reports" for row in finding_fks))
        self.assertTrue(any(row[2] == "findings" for row in evidence_fks))

    def test_init_db_upgrades_brownfield_database_without_alembic_version(self) -> None:
        command.upgrade(self._config(), "0001_create_analysis_reports")
        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute(
            """
            CREATE TABLE incident_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title VARCHAR(255) NOT NULL,
                severity VARCHAR(20) NOT NULL,
                source_file VARCHAR(255) NOT NULL,
                incident_date VARCHAR(40),
                content TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
            """
        )
        sqlite_conn.execute("DROP TABLE alembic_version")
        sqlite_conn.commit()
        sqlite_conn.close()

        reload(config_module)
        reload(tables_module)
        reload(database_module)
        database_module.init_db()

        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in sqlite_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            revision = sqlite_conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
        finally:
            sqlite_conn.close()

        self.assertIn("incident_records", tables)
        self.assertIn("findings", tables)
        self.assertIn("evidence_items", tables)
        self.assertEqual(revision, "007_add_blast_radius_payload")

    def test_init_db_repairs_partial_evidence_schema_without_alembic_version(
        self,
    ) -> None:
        command.upgrade(self._config(), "0001_create_analysis_reports")
        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute(
            """
            CREATE TABLE findings (
                finding_id VARCHAR(64) PRIMARY KEY,
                analysis_id INTEGER NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                severity VARCHAR(20) NOT NULL,
                category VARCHAR(80) NOT NULL,
                deterministic BOOLEAN NOT NULL,
                confidence FLOAT NOT NULL,
                evidence_refs_json TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
            """
        )
        sqlite_conn.execute("DROP TABLE alembic_version")
        sqlite_conn.commit()
        sqlite_conn.close()

        reload(config_module)
        reload(tables_module)
        reload(database_module)
        database_module.init_db()

        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in sqlite_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            revision = sqlite_conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
        finally:
            sqlite_conn.close()

        self.assertIn("findings", tables)
        self.assertIn("evidence_items", tables)
        self.assertEqual(revision, "007_add_blast_radius_payload")

    def test_init_db_repairs_current_schema_without_alembic_version(self) -> None:
        command.upgrade(self._config(), "head")
        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute("DROP TABLE alembic_version")
        sqlite_conn.commit()
        sqlite_conn.close()

        reload(config_module)
        reload(tables_module)
        reload(database_module)
        database_module.init_db()

        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            revision = sqlite_conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
            columns = {
                row[1]
                for row in sqlite_conn.execute("PRAGMA table_info(analysis_reports)")
            }
        finally:
            sqlite_conn.close()

        self.assertEqual(revision, "007_add_blast_radius_payload")
        self.assertIn("report_schema_version", columns)
        self.assertIn("blast_radius_json", columns)

    def test_init_db_repairs_empty_alembic_revision_state(self) -> None:
        command.upgrade(self._config(), "0001_create_analysis_reports")
        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute("DELETE FROM alembic_version")
        sqlite_conn.execute("INSERT INTO alembic_version (version_num) VALUES ('')")
        sqlite_conn.commit()
        sqlite_conn.close()

        reload(config_module)
        reload(tables_module)
        reload(database_module)
        database_module.init_db()

        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            revision = sqlite_conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
        finally:
            sqlite_conn.close()

        self.assertEqual(revision, "007_add_blast_radius_payload")


if __name__ == "__main__":
    unittest.main()
