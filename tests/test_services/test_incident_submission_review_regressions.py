"""Incident submission credential context survives aliases and text projection."""

from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from models.tables import Base, IncidentRecord
from services import incident_import_service as imports
from services import incident_service as incidents
from services import project_service as projects


class IncidentSubmissionReviewRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        engine = create_engine(f"sqlite:///{Path(directory) / 'submission.db'}")
        self.stack.callback(engine.dispose)
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False)
        for module in (projects, imports, incidents):
            self.stack.enter_context(
                patch.object(module, "SessionLocal", self.sessions)
            )
        self.stack.enter_context(
            patch.object(imports, "invalidate_backtesting_snapshot")
        )
        self.stack.enter_context(
            patch.object(incidents, "invalidate_backtesting_snapshot")
        )
        self.project = projects.create_project(
            project_key="submission", display_name="Submission"
        )
        self.secret = "OpaqueReview/Value!"

    def _file(
        self, source: str, text: str, *, declared: bool = False
    ) -> imports.IncidentImportFile:
        document = {
            "title": text,
            "severity": "high",
            "incident_date": "2026-10-01",
            "root_cause": text,
            "trigger_change": "Deployment",
            "affected_services": ["api"],
            "rollback_path": "Restore config",
            "prevention_notes": [text],
            "source": {"system": "manual", "reference": "INC-12"},
            "redaction": {"status": "none", "contains_sensitive_data": False},
        }
        if declared:
            document["connector"] = {"password": self.secret}
        return imports.IncidentImportFile(
            source_file=source, content=json.dumps(document)
        )

    def _assert_safe_records(self, *forbidden: str) -> None:
        listed = incidents.get_incident_records(project_id=self.project.id)
        self.assertTrue(listed)
        with self.sessions() as session:
            rows = session.scalars(select(IncidentRecord)).all()
            self.assertTrue(rows)
            stored = "\n".join(row.title + "\n" + row.content for row in rows)
        for value in forbidden:
            self.assertNotIn(value, stored)
            self.assertNotIn(value, json.dumps(listed))

    def test_filename_only_credentials_screen_own_and_sibling_content_and_keep_alias(
        self,
    ) -> None:
        for operation in (
            imports.import_incident_files,
            imports.reindex_incident_files,
        ):
            for filename in (
                f"password='{self.secret}'.json",
                f"https://user:{quote(self.secret, safe='')}@example.invalid/incident.json",
                quote(f"password='{self.secret}'", safe="") + ".json",
            ):
                with self.subTest(operation=operation.__name__, filename=filename):
                    files = [
                        self._file(filename, self.secret),
                        self._file("sibling.json", self.secret),
                    ]
                    first = operation(files, project_id=self.project.id)
                    self.assertNotIn(self.secret, first.model_dump_json())
                    second = operation(files, project_id=self.project.id)
                    self._assert_safe_records(self.secret)
                    if hasattr(first, "records"):
                        self.assertEqual(
                            first.records[0]["source_file"],
                            second.records[0]["source_file"],
                        )
                        self.assertIn("[REDACTED]", first.records[0]["source_file"])

    def test_filename_only_credentials_screen_normalized_scope_errors(self) -> None:
        file = self._file(f"password='{self.secret}'.json", "Safe incident")
        normalized = projects.normalize_project_key(self.secret)
        for operation in (
            imports.import_incident_files,
            imports.reindex_incident_files,
        ):
            with (
                self.subTest(operation=operation.__name__),
                self.assertRaises(ValueError) as raised,
            ):
                operation([file], project_id=self.project.id, project_key=self.secret)
            self.assertNotIn(self.secret, str(raised.exception))
            self.assertNotIn(normalized, str(raised.exception))

    def test_encoded_narratives_are_screened_in_storage_and_list_output(self) -> None:
        encoded = self.secret
        for _ in range(5):
            encoded = quote(encoded, safe="")
        for operation in (
            imports.import_incident_files,
            imports.reindex_incident_files,
        ):
            with self.subTest(operation=operation.__name__):
                result = operation(
                    [self._file("encoded.json", encoded, declared=True)],
                    project_id=self.project.id,
                )
                self.assertNotIn(encoded, result.model_dump_json())
                self._assert_safe_records(self.secret, encoded)

    def test_healthy_encoded_prose_keeps_exact_content(self) -> None:
        text = "Read rollout%2Fchecklist; traffic is 50% and route%2520name is public."
        result = imports.import_incident_files(
            [self._file("healthy.json", text)], project_id=self.project.id
        )
        self.assertEqual(result.records[0]["title"], text)
        with self.sessions() as session:
            row = session.scalars(select(IncidentRecord)).one()
            self.assertIn(text, row.content)

    def test_numeric_credential_echoes_screened_before_text_projection(self) -> None:
        for operation in (
            imports.import_incident_files,
            imports.reindex_incident_files,
        ):
            for number in (739241, 739241.25):
                for suffix in (".json", ".yaml", ".md"):
                    with self.subTest(
                        operation=operation.__name__, number=number, suffix=suffix
                    ):
                        document = json.loads(
                            self._file("numeric.json", "Safe").content
                        )
                        document["connector"] = {"password": number, "token": "high"}
                        for field in (
                            "title",
                            "root_cause",
                            "trigger_change",
                            "rollback_path",
                        ):
                            document[field] = number
                        document["source"] = {"system": number, "reference": number}
                        content = (
                            json.dumps(document)
                            if suffix == ".json"
                            else yaml.safe_dump(document)
                        )
                        if suffix == ".md":
                            content = "---\n" + content + "---\n"
                        result = operation(
                            [
                                imports.IncidentImportFile(
                                    source_file="numeric" + suffix, content=content
                                )
                            ],
                            project_id=self.project.id,
                        )
                        self.assertNotIn(str(number), result.model_dump_json())
                        self._assert_safe_records(str(number))
                        with self.sessions() as session:
                            rows = session.scalars(select(IncidentRecord)).all()
                            self.assertTrue(all(row.severity == "high" for row in rows))
                            self.assertTrue(
                                all(
                                    "Redaction status: redacted" in row.content
                                    for row in rows
                                )
                            )
                            self.assertTrue(
                                all("Severity: high" in row.content for row in rows)
                            )

    def test_filename_numeric_credentials_screen_sibling_text_and_source_status(
        self,
    ) -> None:
        number = 739241
        for operation in (
            imports.import_incident_files,
            imports.reindex_incident_files,
        ):
            with self.subTest(operation=operation.__name__):
                sensitive = self._file("password='739241'.json", "Safe declaration")
                sibling = json.loads(self._file("sibling.json", "Safe").content)
                sibling["title"] = number
                sibling["root_cause"] = number
                operation(
                    [
                        sensitive,
                        imports.IncidentImportFile(
                            source_file="sibling.json", content=json.dumps(sibling)
                        ),
                    ],
                    project_id=self.project.id,
                )
                self._assert_safe_records(str(number))
                status = incidents.get_incident_ingestion_status(
                    project_id=self.project.id
                )
                source = next(
                    item
                    for item in status.sources
                    if item.import_source == "sibling.json"
                )
                self.assertEqual(source.title, "[REDACTED]")
                self.assertEqual(source.redaction_status, "redacted")

    def test_healthy_numeric_text_and_required_empty_fields_keep_existing_behavior(
        self,
    ) -> None:
        for number in (0, 739241, 739241.25):
            with self.subTest(number=number):
                document = json.loads(self._file("healthy-number.json", "Safe").content)
                document["title"] = number
                document["root_cause"] = number
                result = imports.import_incident_files(
                    [
                        imports.IncidentImportFile(
                            source_file="healthy-number.json",
                            content=json.dumps(document),
                        )
                    ],
                    project_id=self.project.id,
                )
                self.assertEqual(result.records[0]["title"], str(number))
                self.assertEqual(result.records[0]["severity"], "high")
                status = incidents.get_incident_ingestion_status(
                    project_id=self.project.id
                )
                source = next(
                    item
                    for item in status.sources
                    if item.import_source == "healthy-number.json"
                )
                self.assertEqual(source.redaction_status, "none")
        for missing in (None, "", [], {}):
            with self.subTest(missing=missing):
                document = json.loads(self._file("missing.json", "Safe").content)
                document["title"] = missing
                with self.assertRaises(imports.IncidentImportValidationError):
                    imports.import_incident_files(
                        [
                            imports.IncidentImportFile(
                                source_file="missing.json", content=json.dumps(document)
                            )
                        ],
                        project_id=self.project.id,
                    )
