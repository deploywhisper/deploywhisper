"""Tests for external scanner import normalization."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path
from urllib.parse import quote
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.project_service as project_service_module
import services.scanner_import_service as scanner_import_service_module


def _percent_encode_rounds(value: str, rounds: int) -> str:
    encoded = value
    for _ in range(rounds):
        encoded = quote(encoded, safe="")
    return encoded


class ScannerImportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "scanner-imports.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        reload(scanner_import_service_module)
        database_module.init_db()
        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_imports_sarif_findings_as_project_scoped_external_evidence(self) -> None:
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="checkov.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {
                                    "driver": {
                                        "name": "Checkov",
                                        "rules": [
                                            {
                                                "id": "CKV_AWS_20",
                                                "shortDescription": {
                                                    "text": "S3 bucket allows public read",
                                                },
                                            }
                                        ],
                                    }
                                },
                                "results": [
                                    {
                                        "ruleId": "CKV_AWS_20",
                                        "level": "error",
                                        "message": {
                                            "text": "Bucket policy allows public read.",
                                        },
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "main.tf",
                                                    },
                                                    "region": {
                                                        "startLine": 12,
                                                        "startColumn": 3,
                                                    },
                                                }
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.imported_count, 1)
        self.assertEqual(result.rejected_count, 0)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )

        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].source_type, "external_scanner")
        self.assertEqual(evidence[0].source_file, "checkov.sarif")
        self.assertEqual(evidence[0].tool_name, "Checkov")
        self.assertEqual(evidence[0].rule_id, "CKV_AWS_20")
        self.assertEqual(evidence[0].rule_name, "S3 bucket allows public read")
        self.assertEqual(evidence[0].severity, "high")
        self.assertEqual(evidence[0].location, "main.tf:12:3")
        self.assertEqual(evidence[0].project_id, self.project.id)
        self.assertEqual(evidence[0].project_key, "payments")
        self.assertIn("ruleId=CKV_AWS_20", evidence[0].source_ref)

    def test_imports_semgrep_json_as_project_scoped_external_evidence(self) -> None:
        result = scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep.json",
                content=json.dumps(
                    {
                        "version": "1.130.0",
                        "results": [
                            {
                                "check_id": "terraform.aws.security.public-ingress",
                                "path": "network.tf",
                                "start": {"line": 4, "col": 1},
                                "end": {"line": 9, "col": 2},
                                "extra": {
                                    "message": "Security group ingress is broad.",
                                    "severity": "ERROR",
                                    "engine_kind": "oss",
                                    "fingerprint": "semgrep-stable-fingerprint",
                                    "metadata": {
                                        "cwe": ["CWE-284"],
                                        "confidence": "HIGH",
                                        "owasp": ["A01:2021"],
                                    },
                                },
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.imported_count, 1)
        self.assertEqual(result.rejected_count, 0)
        [evidence] = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence.source_type, "external_scanner")
        self.assertEqual(evidence.source_file, "semgrep.json")
        self.assertEqual(evidence.tool_name, "Semgrep")
        self.assertEqual(evidence.rule_id, "terraform.aws.security.public-ingress")
        self.assertEqual(evidence.rule_name, "terraform.aws.security.public-ingress")
        self.assertEqual(evidence.severity, "high")
        self.assertEqual(evidence.level, "ERROR")
        self.assertEqual(evidence.message, "Security group ingress is broad.")
        self.assertEqual(evidence.location, "network.tf:4:1")
        self.assertEqual(evidence.artifact_uri, "network.tf")
        self.assertEqual(
            evidence.region,
            {"startLine": 4, "startColumn": 1, "endLine": 9, "endColumn": 2},
        )
        self.assertEqual(
            evidence.properties["semgrep"]["metadata"],
            {
                "confidence": "HIGH",
                "cwe": ["CWE-284"],
                "owasp": ["A01:2021"],
            },
        )
        self.assertEqual(
            evidence.properties["semgrep"]["fingerprint"],
            "semgrep-stable-fingerprint",
        )
        self.assertEqual(evidence.properties["semgrep"]["engine_kind"], "oss")
        self.assertIn(
            "ruleId=terraform.aws.security.public-ingress", evidence.source_ref
        )
        with database_module.SessionLocal() as session:
            [scanner_import] = session.query(tables_module.ScannerImport).all()
            self.assertEqual(scanner_import.format, "semgrep")

        update_result = scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep.json",
                content=json.dumps(
                    {
                        "version": "1.130.0",
                        "results": [
                            {
                                "check_id": "terraform.aws.security.public-ingress",
                                "path": "network.tf",
                                "start": {"line": 4, "col": 1},
                                "end": {"line": 9, "col": 2},
                                "extra": {
                                    "message": "Updated scanner message.",
                                    "severity": "ERROR",
                                    "fingerprint": "semgrep-stable-fingerprint",
                                },
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(update_result.imported_count, 1)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].message, "Updated scanner message.")

    def test_rejects_semgrep_json_without_partial_storage(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "terraform.aws.security.absolute",
                                    "path": "/Users/alice/project/network.tf",
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Absolute paths must not persist.",
                                        "severity": "ERROR",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "results[0].path")
        self.assertIn("repository-relative", error.message)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_double_encoded_semgrep_source_file(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="%252FUsers%252Falice%252Fsemgrep.json",
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "terraform.aws.security.path",
                                    "path": "network.tf",
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Encoded source must fail.",
                                        "severity": "ERROR",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "source_file")
        self.assertIn("safe relative", error.message)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_double_encoded_semgrep_result_path(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "terraform.aws.security.path",
                                    "path": "%252FUsers%252Falice%252Fnetwork.tf",
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Encoded path must fail.",
                                        "severity": "ERROR",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "results[0].path")
        self.assertIn("repository-relative", error.message)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_deeply_encoded_semgrep_source_file(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file=_percent_encode_rounds(
                        "/Users/alice/semgrep.json",
                        6,
                    ),
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "terraform.aws.security.path",
                                    "path": "network.tf",
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Deep encoded source must fail.",
                                        "severity": "ERROR",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "source_file")
        self.assertIn("safe relative", error.message)

    def test_accepts_semgrep_source_file_encoded_at_decode_round_cap(self) -> None:
        result = scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file=_percent_encode_rounds(
                    "semgrep output.json",
                    scanner_import_service_module.SEMGREP_PERCENT_DECODE_MAX_ROUNDS,
                ),
                content=json.dumps(
                    {
                        "results": [
                            {
                                "check_id": "terraform.aws.security.path",
                                "path": "network.tf",
                                "start": {"line": 4, "col": 1},
                                "extra": {
                                    "message": "Boundary encoded source imports.",
                                    "severity": "ERROR",
                                },
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.source_file, "semgrep output.json")
        self.assertEqual(result.imported_count, 1)

    def test_rejects_over_encoded_semgrep_source_file_without_unbounded_decode(
        self,
    ) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file=_percent_encode_rounds(
                        "/Users/alice/semgrep.json",
                        scanner_import_service_module.SEMGREP_PERCENT_DECODE_MAX_ROUNDS
                        + 1,
                    ),
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "terraform.aws.security.path",
                                    "path": "network.tf",
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Over encoded source must fail.",
                                        "severity": "ERROR",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "source_file")
        self.assertIn("too deeply percent-encoded", error.message)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_encoded_semgrep_source_file_with_control_characters(
        self,
    ) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep%250Ahidden.json",
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "terraform.aws.security.path",
                                    "path": "network.tf",
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Encoded control source must fail.",
                                        "severity": "ERROR",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "source_file")
        self.assertIn("control characters", error.message)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_deeply_encoded_semgrep_result_path(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "terraform.aws.security.path",
                                    "path": _percent_encode_rounds(
                                        "/Users/alice/network.tf",
                                        6,
                                    ),
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Deep encoded path must fail.",
                                        "severity": "ERROR",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "results[0].path")
        self.assertIn("repository-relative", error.message)

    def test_accepts_semgrep_result_path_encoded_at_decode_round_cap(self) -> None:
        result = scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep.json",
                content=json.dumps(
                    {
                        "results": [
                            {
                                "check_id": "terraform.aws.security.path",
                                "path": _percent_encode_rounds(
                                    "network space.tf",
                                    scanner_import_service_module.SEMGREP_PERCENT_DECODE_MAX_ROUNDS,
                                ),
                                "start": {"line": 4, "col": 1},
                                "extra": {
                                    "message": "Boundary encoded path imports.",
                                    "severity": "ERROR",
                                },
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        [evidence] = result.evidence
        self.assertEqual(evidence.artifact_uri, "network space.tf")
        self.assertEqual(evidence.location, "network space.tf:4:1")

    def test_rejects_over_encoded_semgrep_result_path_without_unbounded_decode(
        self,
    ) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "terraform.aws.security.path",
                                    "path": _percent_encode_rounds(
                                        "/Users/alice/network.tf",
                                        scanner_import_service_module.SEMGREP_PERCENT_DECODE_MAX_ROUNDS
                                        + 1,
                                    ),
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Over encoded path must fail.",
                                        "severity": "ERROR",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "results[0].path")
        self.assertIn("too deeply percent-encoded", error.message)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_semgrep_json_missing_severity_without_downgrading_risk(
        self,
    ) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "terraform.aws.security.missing-severity",
                                    "path": "network.tf",
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Security group ingress is broad.",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "results[0].extra.severity")
        self.assertIn("severity", error.message)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_semgrep_json_with_top_level_errors_without_partial_storage(
        self,
    ) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=json.dumps(
                        {
                            "errors": [
                                {
                                    "type": "SemgrepError",
                                    "message": "Scan failed for one file.",
                                }
                            ],
                            "results": [
                                {
                                    "check_id": "terraform.aws.security.partial",
                                    "path": "network.tf",
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Partial scan must not import.",
                                        "severity": "ERROR",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "errors")
        self.assertIn("scan errors", error.message)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_semgrep_json_with_malformed_errors_without_partial_storage(
        self,
    ) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=json.dumps(
                        {
                            "errors": {
                                "type": "SemgrepError",
                                "message": "Scan failed for one file.",
                            },
                            "results": [
                                {
                                    "check_id": "terraform.aws.security.partial",
                                    "path": "network.tf",
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Malformed errors must not import.",
                                        "severity": "ERROR",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "errors")
        self.assertIn("errors must be an array", error.message)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_semgrep_result_count_above_import_limit_before_parsing(
        self,
    ) -> None:
        previous_limit = scanner_import_service_module.SEMGREP_IMPORT_MAX_RESULTS
        scanner_import_service_module.SEMGREP_IMPORT_MAX_RESULTS = 1
        try:
            with self.assertRaises(
                scanner_import_service_module.ScannerImportValidationError
            ) as captured:
                scanner_import_service_module.import_semgrep_json_file(
                    scanner_import_service_module.ScannerImportFile(
                        source_file="too-many-results.json",
                        content=json.dumps(
                            {
                                "results": [
                                    {"check_id": 123},
                                    {"check_id": 456},
                                ],
                            }
                        ),
                    ),
                    project_key="payments",
                )
        finally:
            scanner_import_service_module.SEMGREP_IMPORT_MAX_RESULTS = previous_limit

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "results")
        self.assertIn("1 results", error.message)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_unsupported_sarif_without_partial_storage(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="broken.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Checkov"}},
                                    "results": [
                                        {
                                            "message": {"text": "Missing rule."},
                                            "locations": [],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        errors = captured.exception.field_errors
        self.assertEqual(errors[0].field, "runs[0].results[0].ruleId")
        self.assertIn("Add ruleId", errors[0].correction_path)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_sarif_without_required_version(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="missing-version.sarif",
                    content=json.dumps({"runs": []}),
                ),
                project_key="payments",
            )

        self.assertEqual(captured.exception.field_errors[0].field, "version")
        self.assertIn("2.1.0", captured.exception.field_errors[0].message)

    def test_numeric_security_severity_maps_to_scanner_severity(self) -> None:
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    {
                                        "ruleId": "security.critical",
                                        "level": "warning",
                                        "message": {"text": "Critical scanner hit."},
                                        "properties": {"security-severity": "9.1"},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "main.tf",
                                                    },
                                                }
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.evidence[0].severity, "critical")

    def test_rule_level_security_severity_maps_to_scanner_severity(self) -> None:
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep-rule-severity.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {
                                    "driver": {
                                        "name": "Semgrep",
                                        "rules": [
                                            {
                                                "id": "security.rule-default",
                                                "shortDescription": {
                                                    "text": "Rule metadata severity",
                                                },
                                                "properties": {
                                                    "security-severity": "8.4",
                                                },
                                            }
                                        ],
                                    }
                                },
                                "results": [
                                    {
                                        "ruleId": "security.rule-default",
                                        "message": {
                                            "text": "Severity is defined on the rule.",
                                        },
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "main.tf",
                                                    },
                                                }
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.evidence[0].severity, "high")

    def test_rejects_malformed_result_security_severity(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="bad-security-severity.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "bad.security.severity",
                                            "message": {"text": "Bad severity."},
                                            "properties": {
                                                "security-severity": "urgent",
                                            },
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(
            error.field,
            "runs[0].results[0].properties.security-severity",
        )
        self.assertIn("security-severity", error.message)

    def test_rejects_out_of_range_rule_security_severity(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="bad-rule-security-severity.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {
                                        "driver": {
                                            "name": "Semgrep",
                                            "rules": [
                                                {
                                                    "id": "bad.rule.severity",
                                                    "properties": {
                                                        "security-severity": "11",
                                                    },
                                                }
                                            ],
                                        }
                                    },
                                    "results": [
                                        {
                                            "ruleId": "bad.rule.severity",
                                            "message": {"text": "Bad rule severity."},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(
            error.field,
            "runs[0].tool.driver.rules[0].properties.security-severity",
        )
        self.assertIn("between 0 and 10", error.message)

    def test_rejects_duplicate_rule_ids_across_driver_and_extensions(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="duplicate-rules.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {
                                        "driver": {
                                            "name": "CodeQL",
                                            "rules": [
                                                {
                                                    "id": "duplicate.rule",
                                                    "defaultConfiguration": {
                                                        "level": "warning",
                                                    },
                                                }
                                            ],
                                        },
                                        "extensions": [
                                            {
                                                "name": "extension",
                                                "rules": [
                                                    {
                                                        "id": "duplicate.rule",
                                                        "defaultConfiguration": {
                                                            "level": "error",
                                                        },
                                                    }
                                                ],
                                            }
                                        ],
                                    },
                                    "results": [
                                        {
                                            "ruleId": "duplicate.rule",
                                            "message": {
                                                "text": "Ambiguous rule metadata.",
                                            },
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(
            error.field,
            "runs[0].tool.extensions[0].rules[0].id",
        )
        self.assertIn("duplicates", error.message)

    def test_extension_rule_metadata_resolves_message_and_severity(self) -> None:
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="extension-rule.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {
                                    "driver": {"name": "CodeQL"},
                                    "extensions": [
                                        {
                                            "name": "codeql-javascript",
                                            "rules": [
                                                {
                                                    "id": "js/sql-injection",
                                                    "defaultConfiguration": {
                                                        "level": "error",
                                                    },
                                                    "messageStrings": {
                                                        "default": {
                                                            "text": "SQL injection in {0}."
                                                        }
                                                    },
                                                }
                                            ],
                                        }
                                    ],
                                },
                                "results": [
                                    {
                                        "ruleId": "js/sql-injection",
                                        "message": {
                                            "id": "default",
                                            "arguments": ["handler.js"],
                                        },
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "src/handler.js",
                                                    },
                                                }
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.evidence[0].message, "SQL injection in handler.js.")
        self.assertEqual(result.evidence[0].severity, "high")

    def test_message_markdown_is_accepted_as_sarif_message_text(self) -> None:
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="markdown-message.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    {
                                        "ruleId": "message.markdown",
                                        "message": {
                                            "markdown": "**Markdown** scanner message.",
                                        },
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "main.tf",
                                                    },
                                                }
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.evidence[0].message, "**Markdown** scanner message.")

    def test_message_id_resolves_rule_message_string(self) -> None:
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="message-id.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {
                                    "driver": {
                                        "name": "Semgrep",
                                        "rules": [
                                            {
                                                "id": "message.id",
                                                "messageStrings": {
                                                    "default": {
                                                        "text": "Finding in {0}."
                                                    }
                                                },
                                            }
                                        ],
                                    }
                                },
                                "results": [
                                    {
                                        "ruleId": "message.id",
                                        "message": {
                                            "id": "default",
                                            "arguments": ["network.tf"],
                                        },
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "network.tf",
                                                    },
                                                }
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.evidence[0].message, "Finding in network.tf.")

    def test_rejects_non_array_sarif_message_arguments(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="bad-message-arguments.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {
                                        "driver": {
                                            "name": "Semgrep",
                                            "rules": [
                                                {
                                                    "id": "message.args",
                                                    "messageStrings": {
                                                        "default": {
                                                            "text": "Finding in {0}.",
                                                        }
                                                    },
                                                }
                                            ],
                                        }
                                    },
                                    "results": [
                                        {
                                            "ruleId": "message.args",
                                            "message": {
                                                "id": "default",
                                                "arguments": "network.tf",
                                            },
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "network.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "runs[0].results[0].message.arguments")
        self.assertIn("array", error.message)

    def test_rejects_unresolved_message_id_without_message_string(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="message-id.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "unresolved.message",
                                            "message": {"id": "default"},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "network.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        self.assertEqual(
            captured.exception.field_errors[0].field,
            "runs[0].results[0].message.id",
        )
        self.assertIn("messageStrings", captured.exception.field_errors[0].message)

    def test_rejects_untrusted_sarif_artifact_uri_without_partial_storage(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="absolute-location.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "absolute.path",
                                            "message": {
                                                "text": "Absolute path should not persist.",
                                            },
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "/Users/alice/project/main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        self.assertEqual(
            captured.exception.field_errors[0].field,
            "runs[0].results[0].locations[0].physicalLocation.artifactLocation.uri",
        )
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_sarif_artifact_uri_base_id_with_actionable_error(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="base-id.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "base.id",
                                            "message": {"text": "Base id location."},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                            "uriBaseId": "SRCROOT",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        self.assertEqual(
            captured.exception.field_errors[0].field,
            "runs[0].results[0].locations[0].physicalLocation.artifactLocation.uriBaseId",
        )
        self.assertIn("uriBaseId", captured.exception.field_errors[0].message)

    def test_rejects_sarif_artifact_uri_query_or_fragment(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="uri-query.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "uri.query",
                                            "message": {"text": "URI query."},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf?line=1#frag",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        self.assertEqual(
            captured.exception.field_errors[0].field,
            "runs[0].results[0].locations[0].physicalLocation.artifactLocation.uri",
        )
        self.assertIn("query", captured.exception.field_errors[0].message)

    def test_rejects_percent_encoded_artifact_uri_query_or_fragment(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="encoded-uri-query.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "encoded.uri.query",
                                            "message": {
                                                "text": "Encoded URI query.",
                                            },
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf%3Fline=1",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        uri_errors = [
            error
            for error in captured.exception.field_errors
            if error.field
            == "runs[0].results[0].locations[0].physicalLocation.artifactLocation.uri"
        ]
        self.assertTrue(uri_errors)
        self.assertTrue(any("query" in error.message for error in uri_errors))

    def test_rejects_non_concrete_artifact_uri(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="dot-uri.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "dot.uri",
                                            "message": {"text": "Dot URI."},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "./",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        self.assertEqual(
            captured.exception.field_errors[0].field,
            "runs[0].results[0].locations[0].physicalLocation.artifactLocation.uri",
        )
        self.assertIn("concrete", captured.exception.field_errors[0].message)

    def test_rejects_uri_scheme_artifact_locations(self) -> None:
        for uri in ("urn:example:finding", "https://example.com/main.tf"):
            with self.subTest(uri=uri):
                with self.assertRaises(
                    scanner_import_service_module.ScannerImportValidationError
                ) as captured:
                    scanner_import_service_module.import_sarif_file(
                        scanner_import_service_module.ScannerImportFile(
                            source_file="uri-scheme.sarif",
                            content=json.dumps(
                                {
                                    "version": "2.1.0",
                                    "runs": [
                                        {
                                            "tool": {"driver": {"name": "Semgrep"}},
                                            "results": [
                                                {
                                                    "ruleId": "uri.scheme",
                                                    "message": {
                                                        "text": "URI scheme.",
                                                    },
                                                    "locations": [
                                                        {
                                                            "physicalLocation": {
                                                                "artifactLocation": {
                                                                    "uri": uri,
                                                                },
                                                            }
                                                        }
                                                    ],
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ),
                        ),
                        project_key="payments",
                    )

                error = next(
                    error
                    for error in captured.exception.field_errors
                    if error.field
                    == "runs[0].results[0].locations[0].physicalLocation.artifactLocation.uri"
                )
                self.assertEqual(
                    error.field,
                    "runs[0].results[0].locations[0].physicalLocation.artifactLocation.uri",
                )
                self.assertIn("URI scheme", error.message)

    def test_rejects_lone_surrogate_escape_in_sarif_strings(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="surrogate.sarif",
                    content=(
                        '{"version":"2.1.0","runs":[{"tool":{"driver":{"name":'
                        '"Semgrep"}},"results":[{"ruleId":"bad.surrogate",'
                        '"message":{"text":"bad \\ud800 value"},"locations":'
                        '[{"physicalLocation":{"artifactLocation":{"uri":"main.tf"}}}]}]}]}'
                    ),
                ),
                project_key="payments",
            )

        fields = {error.field for error in captured.exception.field_errors}
        self.assertIn("runs[0].results[0].message.text", fields)
        self.assertTrue(
            any(
                "surrogate" in error.message
                for error in captured.exception.field_errors
            )
        )

    def test_rejects_lone_surrogate_escape_in_semgrep_strings(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=(
                        '{"results":[{"check_id":"bad.surrogate",'
                        '"path":"network.tf","start":{"line":4},'
                        '"extra":{"message":"bad \\ud800 value",'
                        '"severity":"ERROR"}}]}'
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "results[0].extra.message")
        self.assertIn("Semgrep JSON", error.message)
        self.assertNotIn("SARIF", error.message)

    def test_rejects_lone_surrogate_escape_in_sarif_object_keys(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="surrogate-key.sarif",
                    content=(
                        '{"version":"2.1.0","runs":[{"tool":{"driver":{"name":'
                        '"Semgrep"}},"results":[{"ruleId":"bad.surrogate.key",'
                        '"message":{"text":"Bad surrogate key."},'
                        '"properties":{"bad\\ud800key":"value"},"locations":'
                        '[{"physicalLocation":{"artifactLocation":{"uri":"main.tf"}}}]}]}]}'
                    ),
                ),
                project_key="payments",
            )

        fields = {error.field for error in captured.exception.field_errors}
        self.assertIn("runs[0].results[0].properties.<key>", fields)
        self.assertTrue(
            any(
                "surrogate" in error.message
                for error in captured.exception.field_errors
            )
        )

    def test_rejects_raw_lone_surrogate_content_without_unicode_encode_error(
        self,
    ) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile.model_construct(
                    source_file="raw-surrogate.sarif",
                    content="\ud800",
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "content")
        self.assertIn("surrogate", error.message)

    def test_imports_workspace_scoped_sarif_evidence(self) -> None:
        workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )

        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="workspace.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Checkov"}},
                                "results": [
                                    {
                                        "ruleId": "workspace.scope",
                                        "level": "warning",
                                        "message": {"text": "Workspace scoped hit."},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "workspace.tf",
                                                    },
                                                }
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
            workspace_key="prod",
        )

        self.assertEqual(result.workspace_id, workspace.id)
        self.assertEqual(result.workspace_key, "prod")
        self.assertEqual(result.evidence[0].workspace_id, workspace.id)
        self.assertEqual(result.evidence[0].workspace_key, "prod")
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id,
            workspace_id=workspace.id,
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].workspace_key, "prod")
        project_evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(project_evidence, [])

    def test_workspace_delete_preserves_scanner_history_without_project_promotion(
        self,
    ) -> None:
        workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )

        scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="workspace-delete.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    {
                                        "ruleId": "workspace.delete",
                                        "message": {"text": "Workspace scoped."},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "workspace.tf",
                                                    },
                                                }
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
            workspace_key="prod",
        )

        with database_module.SessionLocal() as session:
            session.delete(session.get(tables_module.ProjectWorkspace, workspace.id))
            session.commit()

        with database_module.SessionLocal() as session:
            scanner_imports = session.query(tables_module.ScannerImport).all()
            evidence_records = session.query(
                tables_module.ExternalScannerEvidence
            ).all()
            self.assertEqual(len(scanner_imports), 1)
            self.assertIsNone(scanner_imports[0].workspace_id)
            self.assertEqual(scanner_imports[0].workspace_key, "prod")
            self.assertEqual(len(evidence_records), 1)
            self.assertIsNone(evidence_records[0].workspace_id)
            self.assertEqual(evidence_records[0].workspace_key, "prod")

        project_evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        workspace_evidence = (
            scanner_import_service_module.list_external_scanner_evidence(
                project_id=self.project.id,
                workspace_id=workspace.id,
            )
        )
        self.assertEqual(project_evidence, [])
        self.assertEqual(workspace_evidence, [])

    def test_reimport_refreshes_workspace_key_history_after_workspace_delete(
        self,
    ) -> None:
        workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )

        def sarif_with_message(message: str) -> str:
            return json.dumps(
                {
                    "version": "2.1.0",
                    "runs": [
                        {
                            "tool": {"driver": {"name": "Semgrep"}},
                            "results": [
                                {
                                    "ruleId": "workspace.delete",
                                    "message": {"text": message},
                                    "partialFingerprints": {
                                        "primaryLocationLineHash": "workspace-stable",
                                    },
                                    "locations": [
                                        {
                                            "physicalLocation": {
                                                "artifactLocation": {
                                                    "uri": "workspace.tf",
                                                },
                                                "region": {"startLine": 7},
                                            }
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )

        scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="workspace-delete.sarif",
                content=sarif_with_message("Original workspace finding."),
            ),
            project_key="payments",
            workspace_key="prod",
        )
        with database_module.SessionLocal() as session:
            session.delete(session.get(tables_module.ProjectWorkspace, workspace.id))
            session.commit()
        recreated_workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production Recreated",
        )

        refreshed = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="workspace-delete-rerun.sarif",
                content=sarif_with_message("Refreshed workspace finding."),
            ),
            project_key="payments",
            workspace_key="prod",
        )

        with database_module.SessionLocal() as session:
            scanner_imports = (
                session.query(tables_module.ScannerImport)
                .order_by(tables_module.ScannerImport.id)
                .all()
            )
            evidence_records = session.query(
                tables_module.ExternalScannerEvidence
            ).all()
            self.assertEqual(len(scanner_imports), 2)
            self.assertIsNone(scanner_imports[0].workspace_id)
            self.assertEqual(scanner_imports[0].workspace_key, "prod")
            self.assertEqual(scanner_imports[1].workspace_id, recreated_workspace.id)
            self.assertEqual(scanner_imports[1].workspace_key, "prod")
            self.assertEqual(len(evidence_records), 1)
            self.assertEqual(evidence_records[0].workspace_id, recreated_workspace.id)
            self.assertEqual(evidence_records[0].workspace_key, "prod")
            self.assertEqual(
                evidence_records[0].message, "Refreshed workspace finding."
            )
        self.assertEqual(refreshed.evidence[0].message, "Refreshed workspace finding.")

    def test_reimport_refreshes_workspace_key_history_for_semgrep_after_delete(
        self,
    ) -> None:
        workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )

        def semgrep_with_message(message: str) -> str:
            return json.dumps(
                {
                    "results": [
                        {
                            "check_id": "workspace.delete",
                            "path": "workspace.tf",
                            "start": {"line": 7},
                            "fingerprint": "workspace-stable",
                            "extra": {
                                "message": message,
                                "severity": "WARNING",
                            },
                        }
                    ],
                }
            )

        scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="workspace-delete.json",
                content=semgrep_with_message("Original workspace finding."),
            ),
            project_key="payments",
            workspace_key="prod",
        )
        with database_module.SessionLocal() as session:
            session.delete(session.get(tables_module.ProjectWorkspace, workspace.id))
            session.commit()
        recreated_workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production Recreated",
        )

        refreshed = scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="workspace-delete-rerun.json",
                content=semgrep_with_message("Refreshed workspace finding."),
            ),
            project_key="payments",
            workspace_key="prod",
        )

        with database_module.SessionLocal() as session:
            scanner_imports = (
                session.query(tables_module.ScannerImport)
                .order_by(tables_module.ScannerImport.id)
                .all()
            )
            evidence_records = session.query(
                tables_module.ExternalScannerEvidence
            ).all()
            self.assertEqual(len(scanner_imports), 2)
            self.assertIsNone(scanner_imports[0].workspace_id)
            self.assertEqual(scanner_imports[0].workspace_key, "prod")
            self.assertEqual(scanner_imports[1].workspace_id, recreated_workspace.id)
            self.assertEqual(scanner_imports[1].workspace_key, "prod")
            self.assertEqual(len(evidence_records), 1)
            self.assertEqual(evidence_records[0].workspace_id, recreated_workspace.id)
            self.assertEqual(evidence_records[0].workspace_key, "prod")
            self.assertEqual(
                evidence_records[0].message, "Refreshed workspace finding."
            )
        self.assertEqual(refreshed.evidence[0].message, "Refreshed workspace finding.")

    def test_rejects_storage_bound_violations_before_insert(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="long-rule.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Checkov"}},
                                    "results": [
                                        {
                                            "ruleId": "R" * 256,
                                            "level": "error",
                                            "message": {"text": "Too long."},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        fields = {error.field for error in captured.exception.field_errors}
        self.assertIn("runs[0].results[0].ruleId", fields)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_semgrep_storage_bound_violations_with_semgrep_fields(
        self,
    ) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "R" * 256,
                                    "path": "network.tf",
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Rule id is too long.",
                                        "severity": "ERROR",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        fields = {error.field for error in captured.exception.field_errors}
        self.assertIn("results[0].check_id", fields)
        self.assertTrue(
            all(
                "Semgrep JSON" in error.message
                for error in captured.exception.field_errors
            )
        )
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_oversized_scanner_payload(self) -> None:
        previous_limit = scanner_import_service_module.SARIF_IMPORT_MAX_CONTENT_BYTES
        scanner_import_service_module.SARIF_IMPORT_MAX_CONTENT_BYTES = 10
        try:
            with self.assertRaises(
                scanner_import_service_module.ScannerImportPayloadTooLarge
            ):
                scanner_import_service_module.import_sarif_file(
                    scanner_import_service_module.ScannerImportFile(
                        source_file="large.sarif",
                        content=json.dumps({"version": "2.1.0", "runs": []}),
                    ),
                    project_key="payments",
                )
        finally:
            scanner_import_service_module.SARIF_IMPORT_MAX_CONTENT_BYTES = (
                previous_limit
            )

    def test_rejects_unsafe_or_sensitive_source_file(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="../credentials.sarif",
                    content=json.dumps({"version": "2.1.0", "runs": []}),
                ),
                project_key="payments",
            )

        fields = {error.field for error in captured.exception.field_errors}
        self.assertEqual(fields, {"source_file"})

    def test_uses_later_valid_location_and_preserves_additional_locations(self) -> None:
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="multi-location.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    {
                                        "ruleId": "multi.location",
                                        "level": "warning",
                                        "message": {"text": "Multiple locations."},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "main.tf",
                                                    },
                                                    "region": {"startLine": 9},
                                                }
                                            },
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "variables.tf",
                                                    },
                                                    "region": {"startLine": 2},
                                                }
                                            },
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        evidence = result.evidence[0]
        self.assertEqual(evidence.location, "main.tf:9")
        self.assertEqual(
            evidence.properties["deploywhisper_import"]["additional_locations"][0][
                "location"
            ],
            "variables.tf:2",
        )

    def test_rejects_malformed_location_even_when_later_location_is_valid(
        self,
    ) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="malformed-location.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "malformed.location",
                                            "message": {"text": "Location issue."},
                                            "locations": [
                                                {"physicalLocation": {}},
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                },
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        fields = {error.field for error in captured.exception.field_errors}
        self.assertIn(
            "runs[0].results[0].locations[0].physicalLocation",
            fields,
        )
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_sarif_result_count_above_import_limit(self) -> None:
        previous_limit = scanner_import_service_module.SARIF_IMPORT_MAX_RESULTS
        scanner_import_service_module.SARIF_IMPORT_MAX_RESULTS = 1
        try:
            with self.assertRaises(
                scanner_import_service_module.ScannerImportValidationError
            ) as captured:
                scanner_import_service_module.import_sarif_file(
                    scanner_import_service_module.ScannerImportFile(
                        source_file="too-many-results.sarif",
                        content=json.dumps(
                            {
                                "version": "2.1.0",
                                "runs": [
                                    {
                                        "tool": {"driver": {"name": "Semgrep"}},
                                        "results": [
                                            {
                                                "ruleId": "first",
                                                "message": {"text": "First."},
                                                "locations": [
                                                    {
                                                        "physicalLocation": {
                                                            "artifactLocation": {
                                                                "uri": "one.tf",
                                                            },
                                                        }
                                                    }
                                                ],
                                            },
                                            {
                                                "ruleId": "second",
                                                "message": {"text": "Second."},
                                                "locations": [
                                                    {
                                                        "physicalLocation": {
                                                            "artifactLocation": {
                                                                "uri": "two.tf",
                                                            },
                                                        }
                                                    }
                                                ],
                                            },
                                        ],
                                    }
                                ],
                            }
                        ),
                    ),
                    project_key="payments",
                )
        finally:
            scanner_import_service_module.SARIF_IMPORT_MAX_RESULTS = previous_limit

        self.assertEqual(captured.exception.field_errors[0].field, "runs[0].results")
        self.assertIn("1 results", captured.exception.field_errors[0].message)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_does_not_persist_free_form_sarif_properties(self) -> None:
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="properties.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    {
                                        "ruleId": "properties.secret",
                                        "message": {
                                            "text": "Properties should not echo.",
                                        },
                                        "properties": {
                                            "security-severity": "7.1",
                                            "snippet": "token = 'secret'",
                                            "custom": {
                                                "absolutePath": "/Users/a/main.tf"
                                            },
                                        },
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "main.tf",
                                                    },
                                                }
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.evidence[0].severity, "high")
        self.assertEqual(result.evidence[0].properties, {})

    def test_semgrep_metadata_context_is_bounded_and_report_safe(self) -> None:
        result = scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep.json",
                content=json.dumps(
                    {
                        "results": [
                            {
                                "check_id": "metadata.bounds",
                                "path": "network.tf",
                                "start": {"line": 4, "col": 1},
                                "extra": {
                                    "message": "Metadata should stay bounded.",
                                    "severity": "WARNING",
                                    "engine_kind": "file:///Users/alice/project",
                                    "metadata": {
                                        "confidence": "HIGH",
                                        "cwe": ["CWE-284"],
                                        "technology": ["terraform"],
                                        "category": "modules/network",
                                        "likelihood": "/Users/alice/project/main.tf",
                                        "subcategory": "terraform\\main.tf",
                                        "vulnerability_class": [
                                            "valid class",
                                            "file:///Users/alice/project/main.tf",
                                        ],
                                        "impact": "H" * 513,
                                        "references": [
                                            "https://docs.example.test/rule",
                                            "file:///Users/alice/project/main.tf",
                                        ],
                                        "source": "resource with embedded context",
                                        "unsafe_object": {
                                            "path": "/Users/alice/main.tf"
                                        },
                                    },
                                },
                                "fingerprint": "semgrep-stable-fingerprint",
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        metadata = result.evidence[0].properties["semgrep"]["metadata"]
        self.assertEqual(
            metadata,
            {
                "confidence": "HIGH",
                "cwe": ["CWE-284"],
                "technology": ["terraform"],
            },
        )
        self.assertEqual(
            result.evidence[0].properties["semgrep"]["fingerprint"],
            "semgrep-stable-fingerprint",
        )
        self.assertNotIn("engine_kind", result.evidence[0].properties["semgrep"])

    def test_semgrep_drops_unsafe_fingerprint_and_double_encoded_metadata(
        self,
    ) -> None:
        result = scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep.json",
                content=json.dumps(
                    {
                        "results": [
                            {
                                "check_id": "metadata.encoded",
                                "path": "network.tf",
                                "start": {"line": 4, "col": 1},
                                "extra": {
                                    "message": "Metadata should not echo paths.",
                                    "severity": "WARNING",
                                    "fingerprint": "/Users/alice/project/main.tf",
                                    "metadata": {
                                        "confidence": "HIGH",
                                        "category": (
                                            "https%253A%252F%252Fexample.test"
                                        ),
                                        "technology": [
                                            "terraform",
                                            "..%252Fsecrets",
                                        ],
                                    },
                                },
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        semgrep = result.evidence[0].properties["semgrep"]
        self.assertEqual(semgrep["metadata"], {"confidence": "HIGH"})
        self.assertNotIn("fingerprint", semgrep)

    def test_semgrep_drops_deeply_encoded_metadata_values(self) -> None:
        result = scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep.json",
                content=json.dumps(
                    {
                        "results": [
                            {
                                "check_id": "metadata.deep-encoded",
                                "path": "network.tf",
                                "start": {"line": 4, "col": 1},
                                "extra": {
                                    "message": "Metadata should not echo paths.",
                                    "severity": "WARNING",
                                    "metadata": {
                                        "confidence": "HIGH",
                                        "category": _percent_encode_rounds(
                                            "https://example.test/rule",
                                            6,
                                        ),
                                    },
                                },
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        semgrep = result.evidence[0].properties["semgrep"]
        self.assertEqual(semgrep["metadata"], {"confidence": "HIGH"})

    def test_semgrep_drops_metadata_values_with_uri_schemes(self) -> None:
        result = scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep.json",
                content=json.dumps(
                    {
                        "results": [
                            {
                                "check_id": "metadata.uri-scheme",
                                "path": "network.tf",
                                "start": {"line": 4, "col": 1},
                                "extra": {
                                    "message": "Metadata should not echo URIs.",
                                    "severity": "WARNING",
                                    "metadata": {
                                        "confidence": "HIGH",
                                        "category": "mailto:security@example.test",
                                        "technology": [
                                            "terraform",
                                            "urn:semgrep:rule",
                                        ],
                                    },
                                },
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        semgrep = result.evidence[0].properties["semgrep"]
        self.assertEqual(semgrep["metadata"], {"confidence": "HIGH"})

    def test_unsafe_semgrep_fingerprint_does_not_drive_source_identity(
        self,
    ) -> None:
        content = {
            "results": [
                {
                    "check_id": "fingerprint.unsafe",
                    "path": "network.tf",
                    "start": {"line": 4, "col": 1},
                    "extra": {
                        "message": "Stable finding message.",
                        "severity": "WARNING",
                        "fingerprint": "/Users/alice/one/network.tf",
                    },
                }
            ],
        }
        scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep.json",
                content=json.dumps(content),
            ),
            project_key="payments",
        )
        content["results"][0]["extra"]["severity"] = "ERROR"
        content["results"][0]["extra"]["fingerprint"] = "/Users/alice/two/network.tf"

        scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep.json",
                content=json.dumps(content),
            ),
            project_key="payments",
        )

        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].severity, "high")
        self.assertNotIn("fingerprint", evidence[0].properties.get("semgrep", {}))

    def test_safe_top_level_semgrep_fingerprint_replaces_unsafe_extra_fingerprint(
        self,
    ) -> None:
        content = {
            "results": [
                {
                    "check_id": "fingerprint.fallback",
                    "path": "network.tf",
                    "start": {"line": 4, "col": 1},
                    "fingerprint": "safe-top-level-fingerprint",
                    "extra": {
                        "message": "Original finding message.",
                        "severity": "WARNING",
                        "fingerprint": "/Users/alice/one/network.tf",
                    },
                }
            ],
        }
        scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep.json",
                content=json.dumps(content),
            ),
            project_key="payments",
        )
        content["results"][0]["extra"]["message"] = "Updated finding message."
        content["results"][0]["extra"]["severity"] = "ERROR"
        content["results"][0]["extra"]["fingerprint"] = "/Users/alice/two/network.tf"

        scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep.json",
                content=json.dumps(content),
            ),
            project_key="payments",
        )

        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].message, "Updated finding message.")
        self.assertEqual(evidence[0].severity, "high")
        self.assertEqual(
            evidence[0].properties["semgrep"]["fingerprint"],
            "safe-top-level-fingerprint",
        )

    def test_rejects_semgrep_path_with_control_characters(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "path.control",
                                    "path": "network.tf\nsecret",
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Control path must fail.",
                                        "severity": "ERROR",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "results[0].path")
        self.assertIn("control characters", error.message)

    def test_rejects_semgrep_required_strings_with_control_characters(
        self,
    ) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "rule\nid",
                                    "path": "network.tf",
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Control rule id must fail.",
                                        "severity": "WARNING",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "results[0].check_id")
        self.assertIn("control characters", error.message)

    def test_rejects_non_string_semgrep_required_fields_without_missing_duplicate(
        self,
    ) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": 123,
                                    "path": "network.tf",
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Rule id must be a string.",
                                        "severity": "WARNING",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        errors = captured.exception.field_errors
        self.assertEqual(
            [error.field for error in errors],
            ["results[0].check_id"],
        )
        self.assertIn("must be a string", errors[0].message)
        self.assertNotIn("missing", errors[0].message)

    def test_semgrep_drops_report_context_with_control_characters(self) -> None:
        result = scanner_import_service_module.import_semgrep_json_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep.json",
                content=json.dumps(
                    {
                        "results": [
                            {
                                "check_id": "metadata.control",
                                "path": "network.tf",
                                "start": {"line": 4, "col": 1},
                                "extra": {
                                    "message": "Control metadata must drop.",
                                    "severity": "WARNING",
                                    "fingerprint": "stable\nfingerprint",
                                    "engine_kind": "oss\u0000pro",
                                    "metadata": {
                                        "confidence": "HIGH\nLOW",
                                        "technology": ["terraform", "k8s\u0000"],
                                    },
                                },
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.evidence[0].properties, {})

    def test_rejects_malformed_semgrep_extra_metadata_without_partial_storage(
        self,
    ) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "metadata.malformed",
                                    "path": "network.tf",
                                    "start": {"line": 4, "col": 1},
                                    "extra": {
                                        "message": "Metadata shape must fail.",
                                        "severity": "WARNING",
                                        "metadata": ["confidence", "HIGH"],
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "results[0].extra.metadata")
        self.assertIn("metadata must be an object", error.message)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_malformed_semgrep_end_coordinates_without_partial_storage(
        self,
    ) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "coordinates.malformed",
                                    "path": "network.tf",
                                    "start": {"line": 4, "col": 1},
                                    "end": ["line", 5],
                                    "extra": {
                                        "message": "Malformed end must fail.",
                                        "severity": "WARNING",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "results[0].end")
        self.assertIn("end coordinates must be an object", error.message)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_malformed_semgrep_start_coordinates_without_partial_storage(
        self,
    ) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_semgrep_json_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="semgrep.json",
                    content=json.dumps(
                        {
                            "results": [
                                {
                                    "check_id": "coordinates.malformed",
                                    "path": "network.tf",
                                    "start": ["line", 4],
                                    "extra": {
                                        "message": "Malformed start must fail.",
                                        "severity": "WARNING",
                                    },
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "results[0].start")
        self.assertIn("start coordinates must be an object", error.message)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_boolean_sarif_region_coordinates(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="boolean-region.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "boolean.region",
                                            "message": {
                                                "text": "Boolean coordinates.",
                                            },
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                        "region": {
                                                            "startLine": True,
                                                            "startColumn": True,
                                                            "endLine": False,
                                                            "endColumn": "2",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        fields = {error.field for error in captured.exception.field_errors}
        self.assertIn(
            "runs[0].results[0].locations[0].physicalLocation.region.startLine",
            fields,
        )
        self.assertIn(
            "runs[0].results[0].locations[0].physicalLocation.region.startColumn",
            fields,
        )
        self.assertIn(
            "runs[0].results[0].locations[0].physicalLocation.region.endLine",
            fields,
        )
        self.assertIn(
            "runs[0].results[0].locations[0].physicalLocation.region.endColumn",
            fields,
        )
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_rejects_inconsistent_sarif_region_bounds(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="bad-region-bounds.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "bad.region.bounds",
                                            "message": {"text": "Bad region."},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                        "region": {
                                                            "startLine": 10,
                                                            "startColumn": 8,
                                                            "endLine": 9,
                                                            "endColumn": 2,
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        self.assertEqual(
            captured.exception.field_errors[0].field,
            "runs[0].results[0].locations[0].physicalLocation.region",
        )
        self.assertIn("bounds", captured.exception.field_errors[0].message)

    def test_rejects_sarif_columns_without_start_line(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="column-no-line.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "column.no.line",
                                            "message": {"text": "Column only."},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                        "region": {"startColumn": 2},
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        self.assertEqual(
            captured.exception.field_errors[0].field,
            "runs[0].results[0].locations[0].physicalLocation.region",
        )

    def test_reimport_refreshes_existing_sarif_finding_without_duplicate_evidence(
        self,
    ) -> None:
        file = scanner_import_service_module.ScannerImportFile(
            source_file="duplicate.sarif",
            content=json.dumps(
                {
                    "version": "2.1.0",
                    "runs": [
                        {
                            "tool": {"driver": {"name": "Semgrep"}},
                            "results": [
                                {
                                    "ruleId": "duplicate.finding",
                                    "message": {"text": "Same finding."},
                                    "locations": [
                                        {
                                            "physicalLocation": {
                                                "artifactLocation": {
                                                    "uri": "main.tf",
                                                },
                                                "region": {"startLine": 5},
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

        first = scanner_import_service_module.import_sarif_file(
            file,
            project_key="payments",
        )
        second = scanner_import_service_module.import_sarif_file(
            file,
            project_key="payments",
        )

        self.assertEqual(second.imported_count, 1)
        self.assertEqual(second.evidence[0].id, first.evidence[0].id)
        self.assertNotEqual(second.import_id, first.import_id)
        self.assertEqual(second.evidence[0].import_id, second.import_id)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(len(evidence), 1)

    def test_reimport_from_renamed_file_refreshes_existing_sarif_finding(
        self,
    ) -> None:
        content = json.dumps(
            {
                "version": "2.1.0",
                "runs": [
                    {
                        "tool": {"driver": {"name": "Semgrep"}},
                        "results": [
                            {
                                "ruleId": "duplicate.renamed",
                                "message": {"text": "Same finding, renamed file."},
                                "locations": [
                                    {
                                        "physicalLocation": {
                                            "artifactLocation": {"uri": "main.tf"},
                                            "region": {"startLine": 5},
                                        }
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )

        scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="first.sarif",
                content=content,
            ),
            project_key="payments",
        )
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="renamed.sarif",
                content=content,
            ),
            project_key="payments",
        )

        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(result.evidence[0].source_file, "renamed.sarif")
        self.assertEqual(evidence[0].source_file, "renamed.sarif")

    def test_non_duplicate_integrity_error_is_not_reported_as_duplicate_import(
        self,
    ) -> None:
        with patch.object(
            scanner_import_service_module,
            "create_external_scanner_evidence",
            side_effect=IntegrityError(
                "insert external scanner evidence",
                {},
                Exception(
                    "CHECK constraint failed: ck_external_scanner_evidence_source_type"
                ),
            ),
        ):
            with self.assertRaises(IntegrityError):
                scanner_import_service_module.import_sarif_file(
                    scanner_import_service_module.ScannerImportFile(
                        source_file="integrity.sarif",
                        content=json.dumps(
                            {
                                "version": "2.1.0",
                                "runs": [
                                    {
                                        "tool": {"driver": {"name": "Semgrep"}},
                                        "results": [
                                            {
                                                "ruleId": "integrity.error",
                                                "message": {"text": "Integrity."},
                                                "locations": [
                                                    {
                                                        "physicalLocation": {
                                                            "artifactLocation": {
                                                                "uri": "main.tf",
                                                            },
                                                        }
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ),
                    ),
                    project_key="payments",
                )

    def test_scope_integrity_error_returns_actionable_validation(self) -> None:
        with patch.object(
            scanner_import_service_module,
            "create_scanner_import",
            side_effect=IntegrityError(
                "insert scanner import",
                {},
                Exception("FOREIGN KEY constraint failed"),
            ),
        ):
            with self.assertRaises(
                scanner_import_service_module.ScannerImportValidationError
            ) as captured:
                scanner_import_service_module.import_sarif_file(
                    scanner_import_service_module.ScannerImportFile(
                        source_file="scope-race.sarif",
                        content=json.dumps(
                            {
                                "version": "2.1.0",
                                "runs": [
                                    {
                                        "tool": {"driver": {"name": "Semgrep"}},
                                        "results": [
                                            {
                                                "ruleId": "scope.race",
                                                "message": {"text": "Scope race."},
                                                "locations": [
                                                    {
                                                        "physicalLocation": {
                                                            "artifactLocation": {
                                                                "uri": "main.tf",
                                                            },
                                                        }
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ),
                    ),
                    project_key="payments",
                )

        self.assertEqual(captured.exception.field_errors[0].field, "project")
        self.assertIn("scope changed", captured.exception.field_errors[0].message)

    def test_reimport_refreshes_same_fingerprint_when_message_changes(
        self,
    ) -> None:
        base_result = {
            "ruleId": "duplicate.fingerprint",
            "partialFingerprints": {"primaryLocationLineHash": "stable-line"},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "main.tf"},
                        "region": {"startLine": 5},
                    }
                }
            ],
        }

        scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="first.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    base_result | {"message": {"text": "Old wording."}}
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="renamed.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    base_result | {"message": {"text": "New wording."}}
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(result.evidence[0].message, "New wording.")
        self.assertEqual(evidence[0].message, "New wording.")

    def test_reimport_refreshes_same_fingerprint_when_severity_changes(
        self,
    ) -> None:
        base_result = {
            "ruleId": "duplicate.severity",
            "fingerprints": {"stable": "finding-1"},
            "message": {"text": "Severity changed."},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "main.tf"},
                        "region": {"startLine": 5},
                    }
                }
            ],
        }

        first = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="severity-warning.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [base_result | {"level": "warning"}],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )
        second = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="severity-error.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [base_result | {"level": "error"}],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(first.evidence[0].severity, "medium")
        self.assertEqual(second.evidence[0].id, first.evidence[0].id)
        self.assertEqual(second.evidence[0].severity, "high")
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].severity, "high")

    def test_reimport_refreshes_same_fingerprint_when_rule_name_changes(
        self,
    ) -> None:
        base_result = {
            "fingerprints": {"stable": "renamed-finding"},
            "message": {"text": "Stable finding."},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "main.tf"},
                        "region": {"startLine": 5},
                    }
                }
            ],
        }

        scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="old-tool.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {
                                    "driver": {
                                        "name": "Semgrep",
                                        "rules": [
                                            {
                                                "id": "stable.rule",
                                                "name": "Old display name",
                                            }
                                        ],
                                    }
                                },
                                "results": [base_result | {"ruleId": "stable.rule"}],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="new-tool.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {
                                    "driver": {
                                        "name": "Semgrep",
                                        "rules": [
                                            {
                                                "id": "stable.rule",
                                                "name": "New display name",
                                            }
                                        ],
                                    }
                                },
                                "results": [base_result | {"ruleId": "stable.rule"}],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(result.evidence[0].tool_name, "Semgrep")
        self.assertEqual(result.evidence[0].rule_id, "stable.rule")
        self.assertEqual(result.evidence[0].rule_name, "New display name")
        self.assertEqual(evidence[0].source_file, "new-tool.sarif")

    def test_same_fingerprint_from_different_rules_imports_distinct_evidence(
        self,
    ) -> None:
        base_result = {
            "fingerprints": {"stable": "same-fingerprint"},
            "message": {"text": "Stable finding."},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "main.tf"},
                        "region": {"startLine": 5},
                    }
                }
            ],
        }

        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="same-fingerprint-rules.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    base_result | {"ruleId": "rule.one"},
                                    base_result | {"ruleId": "rule.two"},
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(len(result.evidence), 2)
        self.assertNotEqual(
            result.evidence[0].source_ref,
            result.evidence[1].source_ref,
        )

    def test_same_fingerprint_from_different_tools_imports_distinct_evidence(
        self,
    ) -> None:
        base_result = {
            "ruleId": "shared.rule",
            "fingerprints": {"stable": "same-fingerprint"},
            "message": {"text": "Stable finding."},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "main.tf"},
                        "region": {"startLine": 5},
                    }
                }
            ],
        }

        scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="semgrep.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [base_result],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )
        scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="checkov.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Checkov"}},
                                "results": [base_result],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(len(evidence), 2)
        self.assertEqual(
            {record.tool_name for record in evidence},
            {"Checkov", "Semgrep"},
        )

    def test_reimport_with_duplicate_and_new_sarif_findings_imports_new_evidence(
        self,
    ) -> None:
        duplicate_result = {
            "ruleId": "mixed.duplicate",
            "message": {"text": "Existing finding."},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "main.tf"},
                        "region": {"startLine": 5},
                    }
                }
            ],
        }

        first = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="mixed-first.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [duplicate_result],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )
        second = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="mixed-second.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    duplicate_result,
                                    {
                                        "ruleId": "mixed.new",
                                        "message": {"text": "New finding."},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "new.tf",
                                                    },
                                                    "region": {"startLine": 9},
                                                }
                                            }
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(second.imported_count, 2)
        self.assertEqual(second.evidence[0].id, first.evidence[0].id)
        self.assertNotEqual(second.evidence[1].id, first.evidence[0].id)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(len(evidence), 2)

    def test_distinct_messages_without_fingerprints_at_same_rule_and_location_are_not_deduped(
        self,
    ) -> None:
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="distinct-messages.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    {
                                        "ruleId": "same.rule.location.no.fingerprint",
                                        "message": {"text": "First finding."},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "main.tf",
                                                    },
                                                    "region": {"startLine": 5},
                                                }
                                            }
                                        ],
                                    },
                                    {
                                        "ruleId": "same.rule.location.no.fingerprint",
                                        "message": {"text": "Second finding."},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "main.tf",
                                                    },
                                                    "region": {"startLine": 5},
                                                }
                                            }
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.imported_count, 2)
        self.assertNotEqual(
            result.evidence[0].source_ref,
            result.evidence[1].source_ref,
        )

    def test_distinct_fingerprints_at_same_rule_and_location_are_not_deduped(
        self,
    ) -> None:
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="distinct-findings.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    {
                                        "ruleId": "same.rule.location",
                                        "partialFingerprints": {
                                            "primaryLocationLineHash": "first",
                                        },
                                        "message": {"text": "First finding."},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "main.tf",
                                                    },
                                                    "region": {"startLine": 5},
                                                }
                                            }
                                        ],
                                    },
                                    {
                                        "ruleId": "same.rule.location",
                                        "partialFingerprints": {
                                            "primaryLocationLineHash": "second",
                                        },
                                        "message": {"text": "Second finding."},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "main.tf",
                                                    },
                                                    "region": {"startLine": 5},
                                                }
                                            }
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.imported_count, 2)
        self.assertNotEqual(
            result.evidence[0].source_ref,
            result.evidence[1].source_ref,
        )

    def test_reused_partial_fingerprints_do_not_dedupe_distinct_locations(
        self,
    ) -> None:
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="reused-partial-fingerprints.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    {
                                        "ruleId": "reused.partial",
                                        "partialFingerprints": {
                                            "primaryLocationLineHash": "coarse",
                                        },
                                        "message": {"text": "First location."},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "one.tf",
                                                    },
                                                    "region": {"startLine": 5},
                                                }
                                            }
                                        ],
                                    },
                                    {
                                        "ruleId": "reused.partial",
                                        "partialFingerprints": {
                                            "primaryLocationLineHash": "coarse",
                                        },
                                        "message": {"text": "Second location."},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "two.tf",
                                                    },
                                                    "region": {"startLine": 9},
                                                }
                                            }
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.imported_count, 2)
        self.assertNotEqual(
            result.evidence[0].source_ref,
            result.evidence[1].source_ref,
        )

    def test_reused_full_fingerprints_do_not_dedupe_distinct_locations(self) -> None:
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="reused-full-fingerprints.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    {
                                        "ruleId": "reused.full",
                                        "fingerprints": {"stable": "shared"},
                                        "message": {"text": "First location."},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "one.tf",
                                                    },
                                                    "region": {"startLine": 5},
                                                }
                                            }
                                        ],
                                    },
                                    {
                                        "ruleId": "reused.full",
                                        "fingerprints": {"stable": "shared"},
                                        "message": {"text": "Second location."},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "two.tf",
                                                    },
                                                    "region": {"startLine": 9},
                                                }
                                            }
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.imported_count, 2)
        self.assertNotEqual(
            result.evidence[0].source_ref,
            result.evidence[1].source_ref,
        )

    def test_rejects_non_string_sarif_scalar_fields(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="bad-scalars.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": True}},
                                    "results": [
                                        {
                                            "ruleId": 123,
                                            "message": {"text": False, "id": 99},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": 123,
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        fields = {error.field for error in captured.exception.field_errors}
        self.assertIn("runs[0].tool.driver.name", fields)
        self.assertIn("runs[0].results[0].ruleId", fields)
        self.assertIn("runs[0].results[0].message.text", fields)
        self.assertIn("runs[0].results[0].message.id", fields)
        self.assertIn(
            "runs[0].results[0].locations[0].physicalLocation.artifactLocation.uri",
            fields,
        )

    def test_rejects_non_string_sarif_rule_metadata_fields(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="bad-rule-metadata.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {
                                        "driver": {
                                            "name": "Semgrep",
                                            "rules": [
                                                {"id": True},
                                                {
                                                    "id": "bad.rule.metadata",
                                                    "name": False,
                                                    "shortDescription": {"text": 123},
                                                    "messageStrings": {
                                                        "default": {"text": 456},
                                                    },
                                                },
                                            ],
                                        }
                                    },
                                    "results": [
                                        {
                                            "ruleId": "bad.rule.metadata",
                                            "message": {"id": "default"},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        fields = {error.field for error in captured.exception.field_errors}
        self.assertIn("runs[0].tool.driver.rules[0].id", fields)
        self.assertIn("runs[0].tool.driver.rules[1].name", fields)
        self.assertIn("runs[0].tool.driver.rules[1].shortDescription.text", fields)
        self.assertIn(
            "runs[0].tool.driver.rules[1].messageStrings.default.text",
            fields,
        )

    def test_rejects_non_string_sarif_message_argument_entries(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="bad-message-argument-values.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {
                                        "driver": {
                                            "name": "Semgrep",
                                            "rules": [
                                                {
                                                    "id": "message.arg.value",
                                                    "messageStrings": {
                                                        "default": {
                                                            "text": "Bad {0}.",
                                                        }
                                                    },
                                                }
                                            ],
                                        }
                                    },
                                    "results": [
                                        {
                                            "ruleId": "message.arg.value",
                                            "message": {
                                                "id": "default",
                                                "arguments": [123],
                                            },
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        self.assertEqual(
            captured.exception.field_errors[0].field,
            "runs[0].results[0].message.arguments[0]",
        )

    def test_rejects_unsatisfied_sarif_message_placeholders(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="missing-message-arguments.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {
                                        "driver": {
                                            "name": "Semgrep",
                                            "rules": [
                                                {
                                                    "id": "message.placeholder",
                                                    "messageStrings": {
                                                        "default": {
                                                            "text": "Bad {0} and {1}.",
                                                        }
                                                    },
                                                }
                                            ],
                                        }
                                    },
                                    "results": [
                                        {
                                            "ruleId": "message.placeholder",
                                            "message": {
                                                "id": "default",
                                                "arguments": ["network.tf"],
                                            },
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "runs[0].results[0].message.arguments")
        self.assertIn("placeholders", error.message)

    def test_allows_message_argument_text_with_brace_like_literals(self) -> None:
        result = scanner_import_service_module.import_sarif_file(
            scanner_import_service_module.ScannerImportFile(
                source_file="brace-argument.sarif",
                content=json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {
                                    "driver": {
                                        "name": "Semgrep",
                                        "rules": [
                                            {
                                                "id": "message.literal",
                                                "messageStrings": {
                                                    "default": {"text": "Bad {0}."}
                                                },
                                            }
                                        ],
                                    }
                                },
                                "results": [
                                    {
                                        "ruleId": "message.literal",
                                        "message": {
                                            "id": "default",
                                            "arguments": ["literal {0} text"],
                                        },
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "main.tf",
                                                    },
                                                }
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ),
            ),
            project_key="payments",
        )

        self.assertEqual(result.evidence[0].message, "Bad literal {0} text.")

    def test_rejects_non_string_direct_sarif_severity(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="bad-direct-severity.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "bad.direct.severity",
                                            "message": {"text": "Bad severity."},
                                            "properties": {"severity": True},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        self.assertEqual(
            captured.exception.field_errors[0].field,
            "runs[0].results[0].properties.severity",
        )
        self.assertIn("severity", captured.exception.field_errors[0].message)

    def test_rejects_non_string_sarif_fingerprint_values(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="bad-fingerprint-values.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "bad.fingerprint",
                                            "fingerprints": {"stable": 123},
                                            "partialFingerprints": {
                                                "primaryLocationLineHash": True,
                                            },
                                            "message": {"text": "Bad fingerprint."},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        fields = {error.field for error in captured.exception.field_errors}
        self.assertIn("runs[0].results[0].fingerprints.stable", fields)
        self.assertIn(
            "runs[0].results[0].partialFingerprints.primaryLocationLineHash",
            fields,
        )

    def test_rejects_malformed_sarif_fingerprint_containers(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="bad-fingerprint-containers.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "bad.fingerprint.container",
                                            "fingerprints": ["stable"],
                                            "partialFingerprints": None,
                                            "message": {
                                                "text": "Bad fingerprint container.",
                                            },
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        fields = {error.field for error in captured.exception.field_errors}
        self.assertIn("runs[0].results[0].fingerprints", fields)
        self.assertIn("runs[0].results[0].partialFingerprints", fields)

    def test_rejects_blank_sarif_fingerprint_names_and_values(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="blank-fingerprints.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "blank.fingerprint",
                                            "fingerprints": {"": "stable", "blank": ""},
                                            "message": {"text": "Blank fingerprint."},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        fields = {error.field for error in captured.exception.field_errors}
        self.assertIn("runs[0].results[0].fingerprints.<blank>", fields)
        self.assertIn("runs[0].results[0].fingerprints.blank", fields)

    def test_rejects_non_string_sarif_level_fields(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="bad-levels.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {
                                        "driver": {
                                            "name": "Semgrep",
                                            "rules": [
                                                {
                                                    "id": "bad.level",
                                                    "defaultConfiguration": {
                                                        "level": 1,
                                                    },
                                                }
                                            ],
                                        }
                                    },
                                    "results": [
                                        {
                                            "ruleId": "bad.level",
                                            "level": True,
                                            "message": {"text": "Bad level."},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        fields = {error.field for error in captured.exception.field_errors}
        self.assertIn("runs[0].tool.driver.rules[0].defaultConfiguration.level", fields)
        self.assertIn("runs[0].results[0].level", fields)

    def test_rejects_unknown_sarif_level_values(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="unknown-levels.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {
                                        "driver": {
                                            "name": "Semgrep",
                                            "rules": [
                                                {
                                                    "id": "unknown.rule.level",
                                                    "defaultConfiguration": {
                                                        "level": "vendor-critical",
                                                    },
                                                }
                                            ],
                                        }
                                    },
                                    "results": [
                                        {
                                            "ruleId": "unknown.rule.level",
                                            "level": "vendor-warning",
                                            "message": {"text": "Bad level."},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        fields = {error.field for error in captured.exception.field_errors}
        self.assertIn("runs[0].tool.driver.rules[0].defaultConfiguration.level", fields)
        self.assertIn("runs[0].results[0].level", fields)

    def test_rejects_sarif_level_values_over_storage_limit(self) -> None:
        with self.assertRaises(
            scanner_import_service_module.ScannerImportValidationError
        ) as captured:
            scanner_import_service_module.import_sarif_file(
                scanner_import_service_module.ScannerImportFile(
                    source_file="long-level.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "Semgrep"}},
                                    "results": [
                                        {
                                            "ruleId": "long.level",
                                            "level": "warning" * 7,
                                            "message": {"text": "Long level."},
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": "main.tf",
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                ),
                project_key="payments",
            )

        [error] = captured.exception.field_errors
        self.assertEqual(error.field, "runs[0].results[0].level")
        self.assertIn("40 character storage limit", error.message)
