"""Migration tests for the evidence-domain schema."""

from __future__ import annotations

import json
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

    def _table_sql(self, table_name: str) -> str:
        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            row = sqlite_conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).fetchone()
        finally:
            sqlite_conn.close()
        return str(row[0] if row else "")

    def _foreign_keys(self, table_name: str) -> list[dict]:
        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            return [
                {
                    "constrained_columns": [row[3]],
                    "referred_table": row[2],
                    "referred_columns": [row[4]],
                    "ondelete": row[6],
                }
                for row in sqlite_conn.execute(f"PRAGMA foreign_key_list({table_name})")
            ]
        finally:
            sqlite_conn.close()

    def _foreign_key_groups(self, table_name: str) -> list[dict]:
        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            grouped: dict[int, dict] = {}
            rows = sqlite_conn.execute(f"PRAGMA foreign_key_list({table_name})")
            for row in rows:
                group = grouped.setdefault(
                    row[0],
                    {
                        "constrained_columns": [],
                        "referred_table": row[2],
                        "referred_columns": [],
                        "ondelete": row[6],
                    },
                )
                group["constrained_columns"].append(row[3])
                group["referred_columns"].append(row[4])
            return list(grouped.values())
        finally:
            sqlite_conn.close()

    def _unique_constraint_columns(self, table_name: str) -> set[tuple[str, ...]]:
        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            unique_columns: set[tuple[str, ...]] = set()
            for index_row in sqlite_conn.execute(f"PRAGMA index_list({table_name})"):
                is_unique = bool(index_row[2])
                if not is_unique:
                    continue
                columns = tuple(
                    column_row[2]
                    for column_row in sqlite_conn.execute(
                        f"PRAGMA index_info({index_row[1]})"
                    )
                )
                unique_columns.add(columns)
            return unique_columns
        finally:
            sqlite_conn.close()

    def _create_project_workspace_table(
        self,
        *,
        id_definition: str = "id INTEGER PRIMARY KEY AUTOINCREMENT",
        workspace_key_definition: str = "workspace_key VARCHAR(120) NOT NULL",
    ) -> None:
        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            sqlite_conn.execute(
                f"""
                CREATE TABLE project_workspaces (
                    {id_definition},
                    project_id INTEGER NOT NULL,
                    {workspace_key_definition},
                    display_name VARCHAR(255) NOT NULL,
                    description TEXT,
                    environment VARCHAR(80),
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(project_id, workspace_key)
                )
                """
            )
            sqlite_conn.execute(
                "CREATE INDEX ix_project_workspaces_project_id "
                "ON project_workspaces (project_id)"
            )
            sqlite_conn.execute(
                "CREATE INDEX ix_project_workspaces_workspace_key "
                "ON project_workspaces (workspace_key)"
            )
            sqlite_conn.execute("DROP TABLE alembic_version")
            sqlite_conn.commit()
        finally:
            sqlite_conn.close()

    def test_upgrade_head_creates_evidence_schema_on_clean_database(self) -> None:
        command.upgrade(self._config(), "head")

        self.assertIn("finding_id", self._table_columns("evidence_items"))
        self.assertIn("artifact", self._table_columns("evidence_items"))
        self.assertIn("location", self._table_columns("evidence_items"))
        self.assertIn("resource", self._table_columns("evidence_items"))
        self.assertIn("operation", self._table_columns("evidence_items"))
        self.assertIn("project_id", self._table_columns("evidence_items"))
        self.assertIn("project_key", self._table_columns("evidence_items"))
        self.assertIn("workspace_id", self._table_columns("evidence_items"))
        self.assertIn("workspace_key", self._table_columns("evidence_items"))
        self.assertIn("source_kind", self._table_columns("evidence_items"))
        self.assertIn("determinism_level", self._table_columns("evidence_items"))
        self.assertIn("redaction_status", self._table_columns("evidence_items"))
        self.assertIn("analysis_id", self._table_columns("findings"))
        self.assertIn("explanation", self._table_columns("findings"))
        self.assertIn("guidance_json", self._table_columns("findings"))
        self.assertIn("evidence_classification", self._table_columns("findings"))
        self.assertIn(
            "evidence_classification IN",
            self._table_sql("findings"),
        )
        self.assertIn("analysis_id", self._table_columns("risk_assessments"))
        self.assertIn("analysis_id", self._table_columns("context_snapshots"))
        self.assertIn("project_id", self._table_columns("analysis_reports"))
        self.assertIn("workspace_id", self._table_columns("analysis_reports"))
        self.assertIn("project_key", self._table_columns("projects"))
        self.assertIn("workspace_key", self._table_columns("project_workspaces"))
        self.assertIn("environment", self._table_columns("project_workspaces"))
        self.assertNotIn("is_default", self._table_columns("project_workspaces"))
        self.assertIn("title", self._table_columns("incident_records"))
        self.assertIn("analysis_id", self._table_columns("incident_records"))
        self.assertIn("payload_json", self._table_columns("topology_versions"))
        self.assertIn("deployed_at", self._table_columns("deployment_outcomes"))
        self.assertIn("linked_incident_id", self._table_columns("deployment_outcomes"))
        self.assertIn("finding_id", self._table_columns("feedback_events"))
        self.assertIn("false_positive_reason", self._table_columns("feedback_events"))
        self.assertIn("report_schema_version", self._table_columns("analysis_reports"))
        self.assertIn("blast_radius_json", self._table_columns("analysis_reports"))
        self.assertIn("rollback_plan_json", self._table_columns("analysis_reports"))
        self.assertIn("incident_matches_json", self._table_columns("analysis_reports"))
        self.assertIn("narrative_degraded", self._table_columns("analysis_reports"))
        self.assertIn(
            "narrative_failure_notice", self._table_columns("analysis_reports")
        )
        self.assertIn("share_password_hash", self._table_columns("analysis_reports"))
        self.assertIn("share_password_salt", self._table_columns("analysis_reports"))
        self.assertIn("share_redact_filenames", self._table_columns("analysis_reports"))
        self.assertIn(
            "submission_manifest_json", self._table_columns("analysis_reports")
        )
        self.assertIn(
            "submission_manifest_fallback_json",
            self._table_columns("analysis_reports"),
        )
        self.assertIn(
            ("project_id", "id"),
            self._unique_constraint_columns("project_workspaces"),
        )
        report_fks = self._foreign_keys("analysis_reports")
        self.assertTrue(
            any(
                foreign_key["referred_table"] == "project_workspaces"
                and foreign_key["constrained_columns"] == ["workspace_id"]
                for foreign_key in report_fks
            )
        )
        for table_name in (
            "incident_records",
            "deployment_outcomes",
            "feedback_events",
            "topology_versions",
        ):
            grouped_fks = self._foreign_key_groups(table_name)
            self.assertTrue(
                any(
                    foreign_key["referred_table"] == "project_workspaces"
                    and foreign_key["constrained_columns"]
                    == ["project_id", "workspace_id"]
                    and foreign_key["referred_columns"] == ["project_id", "id"]
                    for foreign_key in grouped_fks
                ),
                f"{table_name} should enforce workspace/project consistency",
            )
        report_schema_row = next(
            row
            for row in self._table_info("analysis_reports")
            if row[1] == "report_schema_version"
        )
        self.assertIsNone(report_schema_row[4])
        share_redact_row = next(
            row
            for row in self._table_info("analysis_reports")
            if row[1] == "share_redact_filenames"
        )
        self.assertIsNone(share_redact_row[4])
        submission_manifest_row = next(
            row
            for row in self._table_info("analysis_reports")
            if row[1] == "submission_manifest_json"
        )
        self.assertIsNone(submission_manifest_row[4])
        submission_manifest_fallback_row = next(
            row
            for row in self._table_info("analysis_reports")
            if row[1] == "submission_manifest_fallback_json"
        )
        self.assertIsNone(submission_manifest_fallback_row[4])

    def test_learning_context_scope_rejects_cross_project_workspace_rows(
        self,
    ) -> None:
        command.upgrade(self._config(), "head")

        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute("PRAGMA foreign_keys = ON")
        try:
            first_project_id = sqlite_conn.execute(
                "SELECT id FROM projects WHERE project_key = ? LIMIT 1",
                ("unassigned",),
            ).fetchone()[0]
            sqlite_conn.execute(
                """
                INSERT INTO projects (
                    project_key,
                    display_name,
                    is_default,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "platform",
                    "Platform",
                    0,
                    "2026-05-06T00:00:00+00:00",
                    "2026-05-06T00:00:00+00:00",
                ),
            )
            other_project_id = sqlite_conn.execute(
                "SELECT id FROM projects WHERE project_key = ? LIMIT 1",
                ("platform",),
            ).fetchone()[0]
            sqlite_conn.execute(
                """
                INSERT INTO project_workspaces (
                    project_id,
                    workspace_key,
                    display_name,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    other_project_id,
                    "prod",
                    "Production",
                    "2026-05-06T00:00:00+00:00",
                    "2026-05-06T00:00:00+00:00",
                ),
            )
            workspace_id = sqlite_conn.execute(
                "SELECT id FROM project_workspaces WHERE workspace_key = ? LIMIT 1",
                ("prod",),
            ).fetchone()[0]

            with self.assertRaises(sqlite3.IntegrityError):
                sqlite_conn.execute(
                    """
                    INSERT INTO topology_versions (
                        project_id,
                        workspace_id,
                        source_type,
                        payload_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        first_project_id,
                        workspace_id,
                        "manual",
                        "{}",
                        "2026-05-06T00:00:00+00:00",
                    ),
                )
        finally:
            sqlite_conn.close()

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
            share_password_hash = sqlite_conn.execute(
                "SELECT share_password_hash FROM analysis_reports LIMIT 1"
            ).fetchone()[0]
            share_redact_filenames = sqlite_conn.execute(
                "SELECT share_redact_filenames FROM analysis_reports LIMIT 1"
            ).fetchone()[0]
            submission_manifest = sqlite_conn.execute(
                "SELECT submission_manifest_json FROM analysis_reports LIMIT 1"
            ).fetchone()[0]
            submission_manifest_fallback = sqlite_conn.execute(
                "SELECT submission_manifest_fallback_json FROM analysis_reports LIMIT 1"
            ).fetchone()[0]
            project_key = sqlite_conn.execute(
                """
                SELECT projects.project_key
                FROM analysis_reports
                JOIN projects ON projects.id = analysis_reports.project_id
                LIMIT 1
                """
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
        self.assertIsNone(share_password_hash)
        self.assertEqual(share_redact_filenames, 0)
        self.assertEqual(submission_manifest, "{}")
        self.assertEqual(submission_manifest_fallback, "[]")
        self.assertEqual(project_key, "unassigned")
        self.assertTrue(any(row[2] == "analysis_reports" for row in finding_fks))
        self.assertTrue(any(row[2] == "findings" for row in evidence_fks))

    def test_upgrade_head_backfills_finding_context_for_existing_findings(
        self,
    ) -> None:
        command.upgrade(self._config(), "018_add_evidence_identity_fields")

        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            sqlite_conn.execute(
                """
                INSERT INTO analysis_reports (
                    id,
                    project_id,
                    risk_score,
                    severity,
                    recommendation,
                    top_risk,
                    report_schema_version,
                    parse_summary,
                    narrative_opening,
                    narrative_explanation,
                    warnings_json,
                    contributors_json,
                    analyzed_files_json,
                    submission_manifest_json,
                    submission_manifest_fallback_json,
                    blast_radius_json,
                    rollback_plan_json,
                    share_redact_filenames,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    1,
                    42,
                    "medium",
                    "caution",
                    "Legacy inferred finding",
                    "v2",
                    "1 parsed file",
                    "CAUTION",
                    "Review the finding.",
                    "[]",
                    "[]",
                    '["plan.json"]',
                    "{}",
                    "[]",
                    "{}",
                    "{}",
                    0,
                    "2026-05-08T00:00:00+00:00",
                ),
            )
            sqlite_conn.execute(
                """
                INSERT INTO findings (
                    finding_id,
                    analysis_id,
                    title,
                    description,
                    severity,
                    category,
                    deterministic,
                    confidence,
                    uncertainty_note,
                    evidence_refs_json,
                    skill_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "finding-legacy",
                    1,
                    "Legacy inferred finding",
                    "Legacy model-assisted finding.",
                    "medium",
                    "cross-tool interaction",
                    0,
                    0.55,
                    "Confidence uses the heuristic floor.",
                    "[]",
                    None,
                    "2026-05-08T00:00:00+00:00",
                ),
            )
            sqlite_conn.executemany(
                """
                INSERT INTO findings (
                    finding_id,
                    analysis_id,
                    title,
                    description,
                    severity,
                    category,
                    deterministic,
                    confidence,
                    uncertainty_note,
                    evidence_refs_json,
                    skill_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        "finding-heuristic",
                        1,
                        "Legacy heuristic finding",
                        "Legacy heuristic-backed finding.",
                        "medium",
                        "cross-tool interaction",
                        0,
                        0.55,
                        "Confidence uses the heuristic floor.",
                        '["ev-heuristic"]',
                        None,
                        "2026-05-08T00:00:00+00:00",
                    ),
                    (
                        "finding-external",
                        1,
                        "Legacy scanner finding",
                        "Legacy scanner-backed finding.",
                        "medium",
                        "scanner",
                        0,
                        0.7,
                        None,
                        '["ev-external"]',
                        None,
                        "2026-05-08T00:00:00+00:00",
                    ),
                    (
                        "finding-user",
                        1,
                        "Legacy user-context finding",
                        "Legacy user-context-backed finding.",
                        "medium",
                        "operator context",
                        0,
                        0.7,
                        None,
                        '["ev-user"]',
                        None,
                        "2026-05-08T00:00:00+00:00",
                    ),
                    (
                        "finding-mixed",
                        1,
                        "Legacy mixed finding",
                        "Legacy mixed-support finding.",
                        "high",
                        "cross-tool interaction",
                        0,
                        0.55,
                        None,
                        '["ev-mixed-heuristic", "ev-mixed-deterministic"]',
                        None,
                        "2026-05-08T00:00:00+00:00",
                    ),
                    (
                        "finding-shared-ref",
                        1,
                        "Legacy shared-reference finding",
                        "Legacy finding with evidence referenced only by JSON.",
                        "medium",
                        "cross-tool interaction",
                        0,
                        0.55,
                        None,
                        '["ev-mixed-deterministic"]',
                        None,
                        "2026-05-08T00:00:00+00:00",
                    ),
                    (
                        "finding-escaped-ref",
                        1,
                        "Legacy escaped-reference finding",
                        "Legacy finding with escaped evidence reference JSON.",
                        "medium",
                        "cross-tool interaction",
                        0,
                        0.55,
                        None,
                        json.dumps(['ev-"quoted"']),
                        None,
                        "2026-05-08T00:00:00+00:00",
                    ),
                    (
                        "finding-malformed-ref",
                        1,
                        "Legacy malformed-reference finding",
                        "Legacy finding with malformed evidence reference JSON.",
                        "medium",
                        "cross-tool interaction",
                        0,
                        0.55,
                        None,
                        '["ev-malformed"',
                        None,
                        "2026-05-08T00:00:00+00:00",
                    ),
                ),
            )
            sqlite_conn.executemany(
                """
                INSERT INTO evidence_items (
                    evidence_id,
                    analysis_id,
                    finding_id,
                    source_type,
                    source_ref,
                    artifact,
                    location,
                    resource,
                    operation,
                    source_kind,
                    determinism_level,
                    redaction_status,
                    summary,
                    severity_hint,
                    deterministic,
                    confidence,
                    related_change_ids_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        "ev-heuristic",
                        1,
                        "finding-heuristic",
                        "heuristic",
                        "heuristic://interaction#payments",
                        "",
                        "",
                        "payments",
                        "modify",
                        "heuristic",
                        "heuristic",
                        "none",
                        "Heuristic overlap",
                        "medium",
                        0,
                        0.55,
                        "[]",
                        "2026-05-08T00:00:00+00:00",
                    ),
                    (
                        "ev-external",
                        1,
                        "finding-external",
                        "external_scanner",
                        "scanner://scan.json#CVE-1",
                        "",
                        "",
                        "CVE-1",
                        "scan",
                        "external_scanner",
                        "deterministic",
                        "none",
                        "Scanner result",
                        "medium",
                        1,
                        0.7,
                        "[]",
                        "2026-05-08T00:00:00+00:00",
                    ),
                    (
                        "ev-user",
                        1,
                        "finding-user",
                        "user_context",
                        "user_context://note#prod-freeze",
                        "",
                        "",
                        "prod-freeze",
                        "note",
                        "user_context",
                        "deterministic",
                        "none",
                        "Operator supplied context",
                        "medium",
                        1,
                        0.7,
                        "[]",
                        "2026-05-08T00:00:00+00:00",
                    ),
                    (
                        "ev-mixed-heuristic",
                        1,
                        "finding-mixed",
                        "heuristic",
                        "heuristic://interaction#payments",
                        "",
                        "",
                        "payments",
                        "modify",
                        "heuristic",
                        "heuristic",
                        "none",
                        "Heuristic overlap",
                        "medium",
                        0,
                        0.55,
                        "[]",
                        "2026-05-08T00:00:00+00:00",
                    ),
                    (
                        'ev-"quoted"',
                        1,
                        "finding-mixed",
                        "artifact",
                        "terraform://plan.json#aws_security_group.quoted?action=modify",
                        "plan.json",
                        "plan.json#aws_security_group.quoted",
                        "aws_security_group.quoted",
                        "modify",
                        "artifact",
                        "deterministic",
                        "none",
                        "Deterministic quoted evidence",
                        "medium",
                        1,
                        1.0,
                        "[]",
                        "2026-05-08T00:00:00+00:00",
                    ),
                    (
                        "ev-mixed-deterministic",
                        1,
                        "finding-mixed",
                        "artifact",
                        "terraform://plan.json#aws_security_group.main?action=modify",
                        "plan.json",
                        "plan.json#aws_security_group.main",
                        "aws_security_group.main",
                        "modify",
                        "artifact",
                        "deterministic",
                        "none",
                        "Deterministic plan evidence",
                        "high",
                        1,
                        1.0,
                        "[]",
                        "2026-05-08T00:00:00+00:00",
                    ),
                ),
            )
            sqlite_conn.commit()
        finally:
            sqlite_conn.close()

        command.upgrade(self._config(), "head")

        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            rows = sqlite_conn.execute(
                """
                SELECT finding_id, explanation, guidance_json, evidence_classification
                FROM findings
                WHERE finding_id IN (
                    'finding-legacy',
                    'finding-heuristic',
                    'finding-external',
                    'finding-user',
                    'finding-mixed',
                    'finding-shared-ref',
                    'finding-escaped-ref',
                    'finding-malformed-ref'
                )
                """
            ).fetchall()
        finally:
            sqlite_conn.close()

        context_by_finding = {row[0]: row[1:] for row in rows}
        self.assertEqual(
            context_by_finding["finding-legacy"][0],
            "Legacy model-assisted finding.",
        )
        self.assertEqual(context_by_finding["finding-legacy"][1], "[]")
        self.assertEqual(context_by_finding["finding-legacy"][2], "model_inferred")
        self.assertEqual(context_by_finding["finding-heuristic"][2], "derived")
        self.assertEqual(context_by_finding["finding-external"][2], "external")
        self.assertEqual(context_by_finding["finding-user"][2], "user_provided")
        self.assertEqual(context_by_finding["finding-mixed"][2], "deterministic")
        self.assertEqual(
            context_by_finding["finding-shared-ref"][2],
            "deterministic",
        )
        self.assertEqual(
            context_by_finding["finding-escaped-ref"][2],
            "deterministic",
        )
        self.assertEqual(
            context_by_finding["finding-malformed-ref"][2],
            "model_inferred",
        )

    def test_downgrade_to_011_removes_feedback_event_fields(self) -> None:
        command.upgrade(self._config(), "head")

        command.downgrade(self._config(), "011_add_deployment_outcome_fields")

        columns = self._table_columns("feedback_events")
        self.assertNotIn("finding_id", columns)
        self.assertNotIn("false_positive_reason", columns)

    def test_downgrade_to_012_removes_incident_analysis_reference(self) -> None:
        command.upgrade(self._config(), "head")

        command.downgrade(self._config(), "012_add_feedback_event_fields")

        columns = self._table_columns("incident_records")
        self.assertNotIn("analysis_id", columns)

    def test_downgrade_to_010_drops_incident_records_when_011_created_it(self) -> None:
        command.upgrade(self._config(), "head")

        command.downgrade(self._config(), "010_add_project_workspaces")

        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in sqlite_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            marker = sqlite_conn.execute(
                "SELECT value FROM app_settings WHERE key = ? LIMIT 1",
                ("migration:011:created_incident_records",),
            ).fetchone()
        finally:
            sqlite_conn.close()

        self.assertNotIn("incident_records", tables)
        self.assertIsNone(marker)

    def test_downgrade_to_010_preserves_preexisting_incident_records(self) -> None:
        command.upgrade(self._config(), "010_add_project_workspaces")

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
        sqlite_conn.commit()
        sqlite_conn.close()

        command.upgrade(self._config(), "head")
        command.downgrade(self._config(), "010_add_project_workspaces")

        sqlite_conn = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in sqlite_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            marker = sqlite_conn.execute(
                "SELECT value FROM app_settings WHERE key = ? LIMIT 1",
                ("migration:011:created_incident_records",),
            ).fetchone()
        finally:
            sqlite_conn.close()

        self.assertIn("incident_records", tables)
        self.assertIsNone(marker)

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
        self.assertIn("projects", tables)
        self.assertIn("topology_versions", tables)
        self.assertEqual(revision, "021_add_incident_matches_payload")

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
        self.assertIn("projects", tables)
        self.assertEqual(revision, "021_add_incident_matches_payload")

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

        self.assertEqual(revision, "021_add_incident_matches_payload")
        self.assertIn("report_schema_version", columns)
        self.assertIn("blast_radius_json", columns)
        self.assertIn("project_id", columns)
        self.assertIn("workspace_id", columns)
        self.assertIn("submission_manifest_json", columns)
        self.assertIn("submission_manifest_fallback_json", columns)

    def test_init_db_accepts_current_incident_matches_revision(self) -> None:
        command.upgrade(self._config(), "head")

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

        self.assertEqual(revision, "021_add_incident_matches_payload")

    def test_init_db_rejects_partial_report_workspace_scope_schema(self) -> None:
        command.upgrade(self._config(), "014_add_project_workspace_records")
        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute(
            "ALTER TABLE analysis_reports ADD COLUMN workspace_id INTEGER"
        )
        sqlite_conn.execute("DROP TABLE alembic_version")
        sqlite_conn.commit()
        sqlite_conn.close()

        reload(config_module)
        reload(tables_module)
        reload(database_module)

        with self.assertRaisesRegex(
            RuntimeError, "partial analysis report workspace scope schema"
        ):
            database_module.init_db()

    def test_init_db_rejects_partial_submission_manifest_schema(self) -> None:
        command.upgrade(self._config(), "016_scope_learning_context_records")
        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute(
            "ALTER TABLE analysis_reports ADD COLUMN submission_manifest_json TEXT"
        )
        sqlite_conn.execute("DROP TABLE alembic_version")
        sqlite_conn.commit()
        sqlite_conn.close()

        reload(config_module)
        reload(tables_module)
        reload(database_module)

        with self.assertRaisesRegex(RuntimeError, "partial submission manifest schema"):
            database_module.init_db()

    def test_init_db_rejects_pre_016_submission_manifest_column(self) -> None:
        command.upgrade(self._config(), "015_add_report_workspace_scope")
        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute(
            "ALTER TABLE analysis_reports ADD COLUMN submission_manifest_json TEXT"
        )
        sqlite_conn.execute("DROP TABLE alembic_version")
        sqlite_conn.commit()
        sqlite_conn.close()

        reload(config_module)
        reload(tables_module)
        reload(database_module)

        with self.assertRaisesRegex(RuntimeError, "partial submission manifest schema"):
            database_module.init_db()

    def test_init_db_rejects_incomplete_finding_context_schema(self) -> None:
        command.upgrade(self._config(), "018_add_evidence_identity_fields")
        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute("ALTER TABLE findings ADD COLUMN explanation TEXT")
        sqlite_conn.execute("ALTER TABLE findings ADD COLUMN guidance_json TEXT")
        sqlite_conn.execute(
            "ALTER TABLE findings ADD COLUMN evidence_classification INTEGER"
        )
        sqlite_conn.execute("DROP TABLE alembic_version")
        sqlite_conn.commit()
        sqlite_conn.close()

        reload(config_module)
        reload(tables_module)
        reload(database_module)

        with self.assertRaisesRegex(RuntimeError, "partial finding context schema"):
            database_module.init_db()

    def test_init_db_rejects_incomplete_finding_classification_constraint(
        self,
    ) -> None:
        command.upgrade(self._config(), "018_add_evidence_identity_fields")
        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute("PRAGMA foreign_keys=OFF")
        sqlite_conn.execute("ALTER TABLE findings RENAME TO findings_old")
        sqlite_conn.execute(
            """
            CREATE TABLE findings (
                id INTEGER NOT NULL,
                finding_id VARCHAR(80) NOT NULL,
                analysis_id INTEGER NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                explanation TEXT NOT NULL DEFAULT '',
                guidance_json TEXT NOT NULL DEFAULT '[]',
                severity VARCHAR(20) NOT NULL,
                category VARCHAR(100) NOT NULL,
                deterministic BOOLEAN NOT NULL,
                confidence FLOAT NOT NULL,
                uncertainty_note TEXT,
                evidence_classification VARCHAR(30) NOT NULL DEFAULT 'deterministic',
                evidence_refs_json TEXT NOT NULL,
                skill_id VARCHAR(120),
                created_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                CONSTRAINT ck_findings_evidence_classification
                    CHECK (evidence_classification != '')
            )
            """
        )
        sqlite_conn.execute("DROP TABLE findings_old")
        sqlite_conn.execute("DROP TABLE alembic_version")
        sqlite_conn.commit()
        sqlite_conn.close()

        reload(config_module)
        reload(tables_module)
        reload(database_module)

        with self.assertRaisesRegex(RuntimeError, "partial finding context schema"):
            database_module.init_db()

    def test_init_db_rejects_partial_incident_analysis_link_schema(self) -> None:
        command.upgrade(self._config(), "011_add_deployment_outcome_fields")
        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute(
            "ALTER TABLE incident_records ADD COLUMN analysis_id INTEGER"
        )
        sqlite_conn.execute("DROP TABLE alembic_version")
        sqlite_conn.commit()
        sqlite_conn.close()

        reload(config_module)
        reload(tables_module)
        reload(database_module)

        with self.assertRaisesRegex(
            RuntimeError, "partial incident-analysis link schema"
        ):
            database_module.init_db()

    def test_init_db_rejects_partial_project_workspace_schema(self) -> None:
        command.upgrade(self._config(), "013_add_incident_analysis_reference")
        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute(
            """
            CREATE TABLE project_workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                workspace_key VARCHAR(120) NOT NULL
            )
            """
        )
        sqlite_conn.execute("DROP TABLE alembic_version")
        sqlite_conn.commit()
        sqlite_conn.close()

        reload(config_module)
        reload(tables_module)
        reload(database_module)

        with self.assertRaisesRegex(RuntimeError, "partial project workspace schema"):
            database_module.init_db()

    def test_init_db_rejects_nullable_project_workspace_required_columns(self) -> None:
        command.upgrade(self._config(), "013_add_incident_analysis_reference")
        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute(
            """
            CREATE TABLE project_workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                workspace_key VARCHAR(120),
                display_name VARCHAR(255),
                description TEXT,
                environment VARCHAR(80),
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(project_id, workspace_key)
            )
            """
        )
        sqlite_conn.execute(
            "CREATE INDEX ix_project_workspaces_project_id "
            "ON project_workspaces (project_id)"
        )
        sqlite_conn.execute(
            "CREATE INDEX ix_project_workspaces_workspace_key "
            "ON project_workspaces (workspace_key)"
        )
        sqlite_conn.execute("DROP TABLE alembic_version")
        sqlite_conn.commit()
        sqlite_conn.close()

        reload(config_module)
        reload(tables_module)
        reload(database_module)

        with self.assertRaisesRegex(RuntimeError, "partial project workspace schema"):
            database_module.init_db()

    def test_init_db_rejects_project_workspace_schema_without_primary_key(
        self,
    ) -> None:
        command.upgrade(self._config(), "013_add_incident_analysis_reference")
        self._create_project_workspace_table(id_definition="id INTEGER NOT NULL")

        reload(config_module)
        reload(tables_module)
        reload(database_module)

        with self.assertRaisesRegex(RuntimeError, "partial project workspace schema"):
            database_module.init_db()

    def test_init_db_rejects_project_workspace_schema_with_wrong_key_type(
        self,
    ) -> None:
        command.upgrade(self._config(), "013_add_incident_analysis_reference")
        self._create_project_workspace_table(
            workspace_key_definition="workspace_key INTEGER NOT NULL"
        )

        reload(config_module)
        reload(tables_module)
        reload(database_module)

        with self.assertRaisesRegex(RuntimeError, "partial project workspace schema"):
            database_module.init_db()

    def test_init_db_rejects_stray_project_workspace_table_without_baseline(
        self,
    ) -> None:
        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute(
            """
            CREATE TABLE project_workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                workspace_key VARCHAR(120) NOT NULL
            )
            """
        )
        sqlite_conn.commit()
        sqlite_conn.close()

        reload(config_module)
        reload(tables_module)
        reload(database_module)

        with self.assertRaisesRegex(RuntimeError, "partial project workspace schema"):
            database_module.init_db()

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

        self.assertEqual(revision, "021_add_incident_matches_payload")


if __name__ == "__main__":
    unittest.main()
