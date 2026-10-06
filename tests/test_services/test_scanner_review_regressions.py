"""Persisted scanner credential regressions from the Story 12.3 re-review."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote, urlsplit

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from models.database import Base
from models.tables import ExternalScannerEvidence, ScannerImport
import services.project_service as projects
import services.scanner_import_service as scanners


class ScannerReviewRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        engine = create_engine(
            f"sqlite:///{Path(temporary.name) / 'scanner-review.db'}"
        )
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False)
        for module in (projects, scanners):
            replacement = patch.object(module, "SessionLocal", self.sessions)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.project = projects.create_project(
            project_key="scanner-review", display_name="Scanner Review"
        )

    def _file(self, *, secret: str, label: str) -> scanners.ScannerImportFile:
        return scanners.ScannerImportFile(
            source_file="review.sarif",
            content=json.dumps(
                {
                    "version": "2.1.0",
                    "password": secret,
                    "runs": [
                        {
                            "tool": {
                                "driver": {
                                    "name": label,
                                    "rules": [
                                        {
                                            "id": label,
                                            "shortDescription": {"text": label},
                                        }
                                    ],
                                }
                            },
                            "results": [
                                {
                                    "ruleId": label,
                                    "level": "warning",
                                    "message": {"text": "Public bucket policy"},
                                    "locations": [
                                        {
                                            "physicalLocation": {
                                                "artifactLocation": {"uri": "main.tf"},
                                                "region": {"startLine": 12},
                                            }
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ),
        )

    def test_encoded_labels_are_screened_before_storage_without_changing_identity(
        self,
    ) -> None:
        secret = "SynthValue/Case!"
        encoded = secret
        for _ in range(5):
            encoded = quote(encoded, safe="")
        file = self._file(secret=secret, label=encoded)
        original = scanners._parse_sarif(file)[0]
        expected_digest = hashlib.blake2b(
            json.dumps(
                original.identity, sort_keys=True, separators=(",", ":")
            ).encode(),
            digest_size=16,
            person=b"dw-sarif-src",
        ).hexdigest()
        first = scanners.import_sarif_file(file, project_id=self.project.id)
        with self.sessions() as session:
            stored = session.scalars(select(ExternalScannerEvidence)).one()
            imported = session.scalars(select(ScannerImport)).one()
            for value in (stored.tool_name, stored.rule_id, stored.rule_name):
                self.assertEqual(value, "[REDACTED]")
            self.assertEqual(json.loads(imported.tool_names_json), ["[REDACTED]"])
            self.assertEqual(stored.source_file, "review.sarif")
            self.assertEqual(stored.artifact_uri, "main.tf")
            self.assertEqual(urlsplit(stored.source_ref).path, f"/{expected_digest}")
        second = scanners.import_sarif_file(file, project_id=self.project.id)
        self.assertEqual(first.evidence[0].id, second.evidence[0].id)
        self.assertEqual(first.evidence[0].source_ref, second.evidence[0].source_ref)
        listed = scanners.list_external_scanner_evidence(project_id=self.project.id)
        self.assertEqual(len(listed), 1)
        for result in (first, second):
            self.assertEqual(result.tool_names, ["[REDACTED]"])
        for record in (first.evidence[0], second.evidence[0], listed[0]):
            self.assertEqual(record.tool_name, "[REDACTED]")
            self.assertEqual(record.rule_id, "[REDACTED]")
            self.assertEqual(record.rule_name, "[REDACTED]")
            for value in (secret, encoded):
                self.assertNotIn(value, record.model_dump_json())

    def test_healthy_encoded_labels_and_optional_rule_name_are_preserved(self) -> None:
        file = self._file(secret="Opaque Credential!", label="checkov%2Frule")
        document = json.loads(file.content)
        document["runs"][0]["tool"]["driver"].pop("rules")
        file = file.model_copy(update={"content": json.dumps(document)})
        result = scanners.import_sarif_file(file, project_id=self.project.id)
        record = result.evidence[0]
        self.assertEqual(result.tool_names, ["checkov%2Frule"])
        self.assertEqual(record.tool_name, "checkov%2Frule")
        self.assertEqual(record.rule_id, "checkov%2Frule")
        self.assertIsNone(record.rule_name)
        with self.sessions() as session:
            stored = session.scalars(select(ExternalScannerEvidence)).one()
            self.assertEqual(stored.tool_name, "checkov%2Frule")
            self.assertEqual(stored.rule_id, "checkov%2Frule")
            self.assertIsNone(stored.rule_name)

    def test_semgrep_encoded_rule_labels_are_screened_before_storage(self) -> None:
        secret = "SemgrepOpaque/Value!"
        encoded = secret
        for _ in range(5):
            encoded = quote(encoded, safe="")
        result = scanners.import_semgrep_json_file(
            scanners.ScannerImportFile(
                source_file="review.json",
                content=json.dumps(
                    {
                        "password": secret,
                        "results": [
                            {
                                "check_id": encoded,
                                "path": "main.tf",
                                "start": {"line": 12, "col": 1},
                                "end": {"line": 12, "col": 20},
                                "extra": {
                                    "message": "Public bucket policy",
                                    "severity": "WARNING",
                                },
                            }
                        ],
                    }
                ),
            ),
            project_id=self.project.id,
        )
        self.assertEqual(result.tool_names, ["Semgrep"])
        with self.sessions() as session:
            stored = session.scalars(select(ExternalScannerEvidence)).one()
            self.assertEqual(stored.rule_id, "[REDACTED]")
            self.assertEqual(stored.rule_name, "[REDACTED]")
            self.assertEqual(stored.tool_name, "Semgrep")
        listed = scanners.list_external_scanner_evidence(project_id=self.project.id)
        for record in (result.evidence[0], listed[0]):
            self.assertEqual(record.rule_id, "[REDACTED]")
            self.assertEqual(record.rule_name, "[REDACTED]")
            self.assertNotIn(encoded, record.model_dump_json())

    def test_real_scope_resolvers_screen_normalized_credentials_and_keep_codes(
        self,
    ) -> None:
        secret = "Opaque Review/Value!"
        normalized = projects.normalize_project_key(secret)
        file = self._file(secret=secret, label="checkov")
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
            with self.subTest(scope=scope):
                with self.assertRaises(projects.ProjectResolutionError) as caught:
                    scanners.import_sarif_file(file, **scope)
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn(secret, str(caught.exception))
                self.assertNotIn(normalized, str(caught.exception))
                self.assertIn("[REDACTED]", caught.exception.message)
        with self.sessions() as session:
            self.assertEqual(session.scalars(select(ScannerImport)).all(), [])
            self.assertEqual(session.scalars(select(ExternalScannerEvidence)).all(), [])

    def _narrative_file(
        self, *, source_format: str, secret: str, message: str
    ) -> scanners.ScannerImportFile:
        if source_format == "sarif":
            file = self._file(secret=secret, label="checkov")
            document = json.loads(file.content)
            document["runs"][0]["results"][0]["message"]["text"] = message
            return file.model_copy(update={"content": json.dumps(document)})
        return scanners.ScannerImportFile(
            source_file="narrative.json",
            content=json.dumps(
                {
                    "password": secret,
                    "results": [
                        {
                            "check_id": "public-bucket",
                            "path": "main.tf",
                            "start": {"line": 12, "col": 1},
                            "end": {"line": 12, "col": 20},
                            "extra": {
                                "message": message,
                                "severity": "WARNING",
                                "metadata": {
                                    "category": message,
                                    "technology": ["terraform", message],
                                },
                            },
                        }
                    ],
                }
            ),
        )

    def test_repeatedly_encoded_narratives_are_screened_without_changing_identity(
        self,
    ) -> None:
        secret = "NarrativeOpaqueValue!"
        encoded = secret
        for _ in range(5):
            encoded = quote(encoded, safe="")
        message = f"Public bucket echo {encoded}"
        expected_message = "[REDACTED]"
        for source_format in ("sarif", "semgrep"):
            with self.subTest(source_format=source_format):
                file = self._narrative_file(
                    source_format=source_format, secret=secret, message=message
                )
                parse = (
                    scanners._parse_sarif
                    if source_format == "sarif"
                    else scanners._parse_semgrep_json
                )
                original = parse(file)[0]
                self.assertEqual(original.identity["message_text"], message)
                expected_digest = hashlib.blake2b(
                    json.dumps(
                        original.identity, sort_keys=True, separators=(",", ":")
                    ).encode(),
                    digest_size=16,
                    person=f"dw-{source_format}-src".encode(),
                ).hexdigest()
                import_file = (
                    scanners.import_sarif_file
                    if source_format == "sarif"
                    else scanners.import_semgrep_json_file
                )
                first = import_file(file, project_id=self.project.id)
                second = import_file(file, project_id=self.project.id)
                self.assertEqual(first.evidence[0].id, second.evidence[0].id)
                self.assertEqual(
                    urlsplit(first.evidence[0].source_ref).path, f"/{expected_digest}"
                )
                listed = scanners.list_external_scanner_evidence(
                    project_id=self.project.id
                )
                record = next(
                    item for item in listed if item.id == first.evidence[0].id
                )
                for evidence in (first.evidence[0], second.evidence[0], record):
                    self.assertEqual(evidence.message, expected_message)
                    for value in (secret, encoded):
                        self.assertNotIn(value, evidence.model_dump_json())
                    if source_format == "semgrep":
                        metadata = evidence.properties["semgrep"]["metadata"]
                        self.assertEqual(metadata["category"], expected_message)
                        self.assertEqual(
                            metadata["technology"], ["terraform", expected_message]
                        )
                with self.sessions() as session:
                    stored = session.get(ExternalScannerEvidence, record.id)
                    self.assertEqual(stored.message, expected_message)
                    for value in (secret, encoded):
                        self.assertNotIn(value, stored.properties_json)
                    if source_format == "semgrep":
                        self.assertEqual(
                            json.loads(stored.properties_json)["semgrep"]["metadata"],
                            {
                                "category": expected_message,
                                "technology": ["terraform", expected_message],
                            },
                        )

    def test_healthy_encoded_narratives_are_preserved(self) -> None:
        message = "Public bucket policy%2521"
        for source_format in ("sarif", "semgrep"):
            with self.subTest(source_format=source_format):
                file = self._narrative_file(
                    source_format=source_format,
                    secret="Unrelated Credential!",
                    message=message,
                )
                import_file = (
                    scanners.import_sarif_file
                    if source_format == "sarif"
                    else scanners.import_semgrep_json_file
                )
                result = import_file(file, project_id=self.project.id)
                listed = scanners.list_external_scanner_evidence(
                    project_id=self.project.id
                )
                record = next(
                    item for item in listed if item.id == result.evidence[0].id
                )
                for evidence in (result.evidence[0], record):
                    self.assertEqual(evidence.message, message)
                    if source_format == "semgrep":
                        self.assertEqual(
                            evidence.properties["semgrep"]["metadata"]["category"],
                            message,
                        )
                with self.sessions() as session:
                    stored = session.get(ExternalScannerEvidence, result.evidence[0].id)
                    self.assertEqual(stored.message, message)


if __name__ == "__main__":
    unittest.main()
