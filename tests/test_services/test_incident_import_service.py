"""Tests for incident file imports."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.incident_import_service as incident_import_service_module
import services.incident_service as incident_service_module
import services.project_service as project_service_module


class IncidentImportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "incident-imports.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        reload(incident_service_module)
        reload(incident_import_service_module)
        database_module.init_db()
        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        self.other_project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_imports_markdown_yaml_and_json_incidents_under_project(self) -> None:
        result = incident_import_service_module.import_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="checkout-ingress.md",
                    content=(
                        "---\n"
                        "severity: high\n"
                        "incident_date: '2026-04-20'\n"
                        "affected_services:\n"
                        "  - checkout-api\n"
                        "  - edge-router\n"
                        "source:\n"
                        "  system: manual\n"
                        "  reference: INC-100\n"
                        "redaction:\n"
                        "  status: redacted\n"
                        "  contains_sensitive_data: false\n"
                        "---\n"
                        "# Checkout ingress exposure\n\n"
                        "## Root cause\n"
                        "Temporary administrative ingress was not removed.\n\n"
                        "## Trigger change\n"
                        "A deployment template widened the access range.\n\n"
                        "## Rollback path\n"
                        "Restore the previous access range and redeploy.\n\n"
                        "## Prevention notes\n"
                        "Require expiry checks for temporary access.\n"
                    ),
                ),
                incident_import_service_module.IncidentImportFile(
                    source_file="cache-rebuild.yaml",
                    content=(
                        "title: Cache rebuild latency\n"
                        "severity: medium\n"
                        "incident_date: '2026-04-21'\n"
                        "root_cause: Cache replacement ran without warm-up.\n"
                        "trigger_change: Node sizing update replaced cache_primary.\n"
                        "affected_services:\n"
                        "  - checkout-api\n"
                        "rollback_path: Restore previous cache size.\n"
                        "prevention_notes:\n"
                        "  - Require warm-up confirmation before release.\n"
                        "source:\n"
                        "  system: manual\n"
                        "  reference: INC-101\n"
                        "redaction:\n"
                        "  status: redacted\n"
                        "  contains_sensitive_data: false\n"
                    ),
                ),
                incident_import_service_module.IncidentImportFile(
                    source_file="gitops-order.json",
                    content=json.dumps(
                        {
                            "title": "GitOps ordering incident",
                            "severity": "low",
                            "incident_date": "2026-04-22",
                            "root_cause": "Configuration arrived before code.",
                            "trigger_change": "Sync ordering changed.",
                            "affected_services": ["checkout-api", "feature-router"],
                            "rollback_path": "Revert config and redeploy code first.",
                            "prevention_notes": [
                                "Verify sync-wave ordering before release.",
                            ],
                            "source": {
                                "system": "manual",
                                "reference": "INC-102",
                            },
                            "redaction": {
                                "status": "redacted",
                                "contains_sensitive_data": "false",
                            },
                        }
                    ),
                ),
            ],
            project_key="payments",
        )

        self.assertEqual(result.imported, 3)
        self.assertEqual(
            [record["project_id"] for record in result.records], [self.project.id] * 3
        )
        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )
        other_records = incident_service_module.get_incident_records(
            project_id=self.other_project.id
        )

        self.assertEqual(len(records), 3)
        self.assertEqual(other_records, [])
        self.assertEqual(records[0]["title"], "Checkout ingress exposure")
        self.assertEqual(records[0]["severity"], "high")
        self.assertEqual(records[0]["incident_date"], "2026-04-20")
        self.assertIn("Root cause", records[0]["content"])
        self.assertIn("Temporary administrative ingress", records[0]["content"])
        self.assertIn("Source system: manual", records[0]["content"])
        self.assertIn("Redaction status: redacted", records[0]["content"])
        self.assertIn("Affected services", records[0]["content"])
        self.assertIn("Contains sensitive data: false", records[2]["content"])

    def test_rejects_invalid_record_with_field_errors_and_no_partial_import(
        self,
    ) -> None:
        valid_file = incident_import_service_module.IncidentImportFile(
            source_file="valid.json",
            content=json.dumps(
                {
                    "title": "Valid incident",
                    "severity": "high",
                    "incident_date": "2026-04-23",
                    "root_cause": "Valid root cause.",
                    "trigger_change": "Valid trigger.",
                    "affected_services": ["checkout-api"],
                    "rollback_path": "Valid rollback.",
                    "prevention_notes": ["Valid prevention."],
                    "source": {"system": "manual", "reference": "INC-103"},
                    "redaction": {
                        "status": "redacted",
                        "contains_sensitive_data": False,
                    },
                }
            ),
        )
        invalid_file = incident_import_service_module.IncidentImportFile(
            source_file="invalid.yaml",
            content=(
                "title: Invalid incident\n"
                "severity: high\n"
                "incident_date: '2026-04-24'\n"
                "root_cause: Missing required metadata.\n"
                "trigger_change: Import attempt.\n"
                "affected_services:\n"
                "  - checkout-api\n"
                "rollback_path: Do not import.\n"
                "prevention_notes:\n"
                "  - Fix metadata before import.\n"
            ),
        )

        with self.assertRaises(
            incident_import_service_module.IncidentImportValidationError
        ) as ctx:
            incident_import_service_module.import_incident_files(
                [valid_file, invalid_file],
                project_id=self.project.id,
            )

        self.assertEqual(
            [error.source_file for error in ctx.exception.field_errors],
            ["invalid.yaml", "invalid.yaml", "invalid.yaml"],
        )
        self.assertEqual(
            [error.field for error in ctx.exception.field_errors],
            [
                "source.system",
                "source.reference",
                "redaction.status",
            ],
        )
        self.assertIn("redaction", str(ctx.exception).lower())
        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )
        self.assertEqual(records, [])

    def test_requires_project_scope_before_importing_records(self) -> None:
        with self.assertRaises(
            incident_import_service_module.IncidentImportValidationError
        ) as ctx:
            incident_import_service_module.import_incident_files(
                [
                    incident_import_service_module.IncidentImportFile(
                        source_file="incident.json",
                        content="{}",
                    )
                ]
            )

        self.assertEqual(len(ctx.exception.field_errors), 1)
        self.assertEqual(ctx.exception.field_errors[0].field, "project")
        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )
        self.assertEqual(records, [])

    def test_rejects_invalid_scope_with_field_error_before_import(self) -> None:
        valid_files = [
            incident_import_service_module.IncidentImportFile(
                source_file=f"valid-{index}.json",
                content=json.dumps(
                    {
                        "title": f"Valid incident {index}",
                        "severity": "high",
                        "incident_date": "2026-04-25",
                        "root_cause": "Valid root cause.",
                        "trigger_change": "Valid trigger.",
                        "affected_services": ["checkout-api"],
                        "rollback_path": "Valid rollback.",
                        "prevention_notes": ["Valid prevention."],
                        "source": {"system": "manual", "reference": f"INC-20{index}"},
                        "redaction": {
                            "status": "redacted",
                            "contains_sensitive_data": False,
                        },
                    }
                ),
            )
            for index in range(2)
        ]

        with self.assertRaises(
            incident_import_service_module.IncidentImportValidationError
        ) as ctx:
            incident_import_service_module.import_incident_files(
                valid_files,
                project_id=self.project.id,
                workspace_key="missing-workspace",
            )

        self.assertEqual(len(ctx.exception.field_errors), 1)
        self.assertEqual(ctx.exception.field_errors[0].source_file, "batch")
        self.assertEqual(ctx.exception.field_errors[0].field, "workspace")
        self.assertIn("missing-workspace", ctx.exception.field_errors[0].message)
        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )
        self.assertEqual(records, [])

    def test_rejects_malformed_collection_fields_without_coercion(self) -> None:
        malformed_file = incident_import_service_module.IncidentImportFile(
            source_file="malformed.json",
            content=json.dumps(
                {
                    "title": "Malformed incident",
                    "severity": "medium",
                    "incident_date": "2026-04-26",
                    "root_cause": "Invalid collection fields.",
                    "trigger_change": "Import attempt.",
                    "affected_services": ["checkout-api", None],
                    "rollback_path": "Do not import.",
                    "prevention_notes": {"note": "Not a list or text."},
                    "source": {"system": "manual", "reference": "INC-300"},
                    "redaction": {
                        "status": "redacted",
                        "contains_sensitive_data": "not sure",
                    },
                }
            ),
        )

        with self.assertRaises(
            incident_import_service_module.IncidentImportValidationError
        ) as ctx:
            incident_import_service_module.import_incident_files(
                [malformed_file],
                project_id=self.project.id,
            )

        self.assertEqual(
            [error.field for error in ctx.exception.field_errors],
            [
                "affected_services",
                "prevention_notes",
                "redaction.contains_sensitive_data",
            ],
        )
        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )
        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
