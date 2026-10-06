"""Incident scope errors and alias lookup credential-boundary regressions."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from models.tables import Base
from services import incident_service, project_service


class IncidentReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        tempdir = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.engine = create_engine(f"sqlite:///{Path(tempdir) / 'incidents.db'}")
        self.stack.callback(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        for module in (
            "services.project_service",
            "services.incident_service",
            "services.backtesting_service",
        ):
            self.stack.enter_context(patch(f"{module}.SessionLocal", sessions))
        self.project = project_service.create_project(
            project_key="payments", display_name="Payments"
        )
        self.workspace = project_service.create_workspace(
            project_key="payments", workspace_key="prod", display_name="Production"
        )

    def test_direct_ingest_screens_scope_errors_and_preserves_codes(self):
        secret = "Review_Password_ABC"
        for scope, code in (
            (
                {"project_id": self.project.id, "project_key": secret},
                "project_not_found",
            ),
            (
                {"project_id": self.project.id, "workspace_key": secret},
                "workspace_not_found",
            ),
        ):
            with self.subTest(scope=scope), self.assertRaises(ValueError) as raised:
                incident_service.ingest_incident_document(
                    "incident.md", f"# Incident\npassword: {secret}", **scope
                )
            self.assertEqual(raised.exception.code, code)
            self.assertNotIn(secret, str(raised.exception))
            self.assertNotIn(
                project_service.normalize_project_key(secret), str(raised.exception)
            )
            self.assertNotIn(secret, raised.exception.message)

    def test_direct_ingest_selects_only_source_files_for_exact_alias_scope(self):
        # A same-name alias in a sibling workspace must not influence project-only import.
        incident_service.ingest_incident_document(
            incident_service.incident_source_alias("incident.md"),
            "# Existing sibling",
            project_id=self.project.id,
            workspace_id=self.workspace.id,
        )
        statements = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            if (
                statement.lstrip().upper().startswith("SELECT")
                and "incident_records" in statement
            ):
                statements.append((statement, parameters))

        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            imported = incident_service.ingest_incident_document(
                "incident.md", "# New incident", project_id=self.project.id
            )
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        self.assertEqual(imported["source_file"], "incident.md")
        alias_queries = [
            item for item in statements if "incident_records.project_id =" in item[0]
        ]
        self.assertEqual(len(alias_queries), 1)
        statement, parameters = alias_queries[0]
        self.assertNotIn("incident_records.content", statement)
        self.assertNotIn("incident_records.title", statement)
        self.assertIn("incident_records.workspace_id IS NULL", statement)
        self.assertIn(self.project.id, parameters)
