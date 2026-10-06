"""Source alias queries preserve scope without loading incident documents."""

from __future__ import annotations

import unittest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from models.database import Base
from models import tables
from models.repositories import incident_records, incident_ingestion_sources


class IncidentSourceAliasQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            for project_id, workspace_id, source_file in (
                (1, None, "root.md"),
                (1, None, "root.md"),
                (1, 10, "workspace.md"),
                (1, 20, "other-workspace.md"),
                (2, None, "other-project.md"),
            ):
                session.add(
                    tables.IncidentRecord(
                        project_id=project_id,
                        workspace_id=workspace_id,
                        source_file=source_file,
                        title="Safe",
                        content="large document" * 1000,
                    )
                )
            for project_id, workspace_id, source_file in (
                (1, None, "root.md"),
                (1, 10, "workspace.md"),
                (1, 20, "other-workspace.md"),
                (2, None, "other-project.md"),
            ):
                session.add(
                    tables.IncidentIngestionSource(
                        project_id=project_id,
                        workspace_id=workspace_id,
                        source_file=source_file,
                        status="removed",
                    )
                )
            session.commit()

    def test_alias_queries_are_distinct_scoped_and_do_not_hydrate_documents(
        self,
    ) -> None:
        queries = []
        event.listen(
            self.engine,
            "before_cursor_execute",
            lambda conn, cursor, statement, parameters, context, executemany: (
                queries.append(statement)
            ),
        )
        for repository, helper in (
            (incident_records, "list_incident_source_files"),
            (incident_ingestion_sources, "list_incident_ingestion_source_files"),
        ):
            with (
                self.subTest(repository=repository.__name__),
                Session(self.engine) as session,
            ):
                query = getattr(repository, helper)
                self.assertEqual(
                    query(session, project_id=1, workspace_id=None), ["root.md"]
                )
                self.assertEqual(
                    query(session, project_id=1, workspace_id=10), ["workspace.md"]
                )
                self.assertEqual(
                    set(
                        query(
                            session, project_id=1, workspace_id=None, project_wide=True
                        )
                    ),
                    {"root.md", "workspace.md", "other-workspace.md"},
                )
                self.assertFalse(session.identity_map)
        self.assertTrue(queries)
        self.assertTrue(
            all(
                "content" not in sql and "failure_summaries_json" not in sql
                for sql in queries
            )
        )
