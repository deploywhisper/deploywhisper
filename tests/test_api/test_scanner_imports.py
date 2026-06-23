"""Tests for external scanner import API routes."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path

import app as app_module
import api.routes.scanner_imports as scanner_imports_route_module
import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.project_service as project_service_module
import services.scanner_import_service as scanner_import_service_module
from fastapi.testclient import TestClient


class ScannerImportsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "scanner-imports-api.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        reload(scanner_import_service_module)
        reload(scanner_imports_route_module)
        reload(app_module)
        database_module.init_db()
        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        self.other_project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        self.other_workspace = project_service_module.create_workspace(
            project_key="platform",
            workspace_key="prod",
            display_name="Prod",
        )
        self.client = TestClient(app_module.create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def _semgrep_content(self) -> str:
        return json.dumps(
            {
                "results": [
                    {
                        "check_id": "terraform.aws.security",
                        "path": "network.tf",
                        "start": {"line": 4, "col": 1},
                        "extra": {
                            "message": "Security group ingress is broad.",
                            "severity": "WARNING",
                        },
                    }
                ]
            }
        )

    def _assert_masked_project_scope_error(self, payload: dict) -> None:
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")
        self.assertEqual(
            payload["error"]["message"],
            "Caller is not authorized for the requested project.",
        )
        self.assertEqual(payload["error"].get("details", {}), {})

    def test_import_sarif_returns_external_evidence_payload(self) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/sarif",
            json={
                "project_key": "payments",
                "source_file": "semgrep.sarif",
                "content": json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    {
                                        "ruleId": "terraform.aws.security",
                                        "level": "warning",
                                        "message": {
                                            "text": "Security group ingress is broad.",
                                        },
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "network.tf",
                                                    },
                                                    "region": {"startLine": 4},
                                                }
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["imported_count"], 1)
        self.assertEqual(
            payload["data"]["evidence"][0]["source_type"], "external_scanner"
        )
        self.assertEqual(payload["data"]["evidence"][0]["project_id"], self.project.id)
        self.assertEqual(payload["data"]["evidence"][0]["tool_name"], "Semgrep")
        self.assertEqual(payload["data"]["evidence"][0]["severity"], "medium")
        self.assertEqual(payload["meta"]["count"], 1)

    def test_import_semgrep_json_returns_external_evidence_payload(self) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/semgrep",
            json={
                "project_key": "payments",
                "source_file": "semgrep.json",
                "content": json.dumps(
                    {
                        "results": [
                            {
                                "check_id": "terraform.aws.security.public-ingress",
                                "path": "network.tf",
                                "start": {"line": 4, "col": 1},
                                "extra": {
                                    "message": "Security group ingress is broad.",
                                    "severity": "WARNING",
                                    "metadata": {"confidence": "MEDIUM"},
                                },
                                "fingerprint": "semgrep-api-fingerprint",
                            }
                        ]
                    }
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["imported_count"], 1)
        self.assertEqual(payload["data"]["tool_names"], ["Semgrep"])
        evidence = payload["data"]["evidence"][0]
        self.assertEqual(evidence["source_type"], "external_scanner")
        self.assertEqual(evidence["project_id"], self.project.id)
        self.assertEqual(evidence["tool_name"], "Semgrep")
        self.assertEqual(evidence["rule_id"], "terraform.aws.security.public-ingress")
        self.assertEqual(evidence["severity"], "medium")
        self.assertEqual(evidence["location"], "network.tf:4:1")
        self.assertEqual(
            evidence["properties"]["semgrep"]["fingerprint"],
            "semgrep-api-fingerprint",
        )
        self.assertEqual(payload["meta"]["count"], 1)

    def test_import_semgrep_validation_errors_are_actionable(self) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/semgrep",
            json={
                "project_key": "payments",
                "source_file": "semgrep.json",
                "content": json.dumps(
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
                        ]
                    }
                ),
            },
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "semgrep_import_validation_failed")
        failure = payload["error"]["details"]["failures"][0]
        self.assertEqual(failure["field"], "results[0].extra.severity")
        self.assertIn("severity", failure["message"])
        self.assertIn("Semgrep JSON", failure["correction_path"])

    def test_import_semgrep_rejects_top_level_scan_errors(self) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/semgrep",
            json={
                "project_key": "payments",
                "source_file": "semgrep.json",
                "content": json.dumps(
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
            },
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "semgrep_import_validation_failed")
        failure = payload["error"]["details"]["failures"][0]
        self.assertEqual(failure["field"], "errors")
        self.assertIn("scan errors", failure["message"])
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_import_semgrep_rejects_malformed_top_level_errors(self) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/semgrep",
            json={
                "project_key": "payments",
                "source_file": "semgrep.json",
                "content": json.dumps(
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
            },
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "semgrep_import_validation_failed")
        failure = payload["error"]["details"]["failures"][0]
        self.assertEqual(failure["field"], "errors")
        self.assertIn("errors must be an array", failure["message"])
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])

    def test_import_sarif_validation_errors_are_actionable(self) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/sarif",
            json={
                "project_key": "payments",
                "source_file": "invalid.sarif",
                "content": json.dumps({"version": "2.1.0", "runs": {}}),
            },
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "sarif_import_validation_failed")
        failure = payload["error"]["details"]["failures"][0]
        self.assertEqual(failure["field"], "runs")
        self.assertIn("array", failure["message"])
        self.assertIn("Use a SARIF 2.1.0 runs array", failure["correction_path"])

    def test_import_sarif_masks_workspace_scope_errors_for_restricted_callers(
        self,
    ) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/sarif",
            headers={
                "X-DeployWhisper-Project-Role": "maintainer",
                "X-DeployWhisper-Project-Keys": "payments",
            },
            json={
                "project_key": "payments",
                "workspace_id": self.other_workspace.id,
                "source_file": "semgrep.sarif",
                "content": json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    {
                                        "ruleId": "terraform.aws.security",
                                        "level": "warning",
                                        "message": {"text": "Broad ingress."},
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
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self._assert_masked_project_scope_error(payload)

    def test_import_semgrep_masks_workspace_scope_errors_for_restricted_callers(
        self,
    ) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/semgrep",
            headers={
                "X-DeployWhisper-Project-Role": "maintainer",
                "X-DeployWhisper-Project-Keys": "payments",
            },
            json={
                "project_key": "payments",
                "workspace_id": self.other_workspace.id,
                "source_file": "semgrep.json",
                "content": self._semgrep_content(),
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self._assert_masked_project_scope_error(payload)

    def test_import_sarif_masks_project_key_scope_errors_for_restricted_callers(
        self,
    ) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/sarif",
            headers={
                "X-DeployWhisper-Project-Role": "maintainer",
                "X-DeployWhisper-Project-Keys": "ghost-project",
            },
            json={
                "project_key": "ghost-project",
                "source_file": "semgrep.sarif",
                "content": json.dumps({"version": "2.1.0", "runs": []}),
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")

    def test_import_semgrep_masks_project_key_scope_errors_for_restricted_callers(
        self,
    ) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/semgrep",
            headers={
                "X-DeployWhisper-Project-Role": "maintainer",
                "X-DeployWhisper-Project-Keys": "payments",
            },
            json={
                "project_key": "platform",
                "source_file": "semgrep.json",
                "content": self._semgrep_content(),
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self._assert_masked_project_scope_error(payload)

    def test_import_sarif_allows_restricted_project_id_scope(self) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/sarif",
            headers={
                "X-DeployWhisper-Project-Role": "maintainer",
                "X-DeployWhisper-Project-Keys": "payments",
            },
            json={
                "project_id": self.project.id,
                "source_file": "semgrep.sarif",
                "content": json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Semgrep"}},
                                "results": [
                                    {
                                        "ruleId": "terraform.aws.security",
                                        "level": "warning",
                                        "message": {"text": "Broad ingress."},
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
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["project_key"], "payments")

    def test_import_semgrep_allows_restricted_project_id_scope(self) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/semgrep",
            headers={
                "X-DeployWhisper-Project-Role": "maintainer",
                "X-DeployWhisper-Project-Keys": "payments",
            },
            json={
                "project_id": self.project.id,
                "source_file": "semgrep.json",
                "content": self._semgrep_content(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["project_key"], "payments")

    def test_import_sarif_masks_restricted_project_id_outside_scope(self) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/sarif",
            headers={
                "X-DeployWhisper-Project-Role": "maintainer",
                "X-DeployWhisper-Project-Keys": "payments",
            },
            json={
                "project_id": self.other_project.id,
                "source_file": "semgrep.sarif",
                "content": json.dumps({"version": "2.1.0", "runs": []}),
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")

    def test_import_semgrep_masks_restricted_project_id_outside_scope(self) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/semgrep",
            headers={
                "X-DeployWhisper-Project-Role": "maintainer",
                "X-DeployWhisper-Project-Keys": "payments",
            },
            json={
                "project_id": self.other_project.id,
                "source_file": "semgrep.json",
                "content": self._semgrep_content(),
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")

    def test_import_sarif_returns_413_for_oversized_payload(self) -> None:
        previous_limit = scanner_import_service_module.SARIF_IMPORT_MAX_CONTENT_BYTES
        scanner_import_service_module.SARIF_IMPORT_MAX_CONTENT_BYTES = 10
        try:
            response = self.client.post(
                "/api/v1/scanner-imports/sarif",
                json={
                    "project_key": "payments",
                    "source_file": "large.sarif",
                    "content": json.dumps({"version": "2.1.0", "runs": []}),
                },
            )
        finally:
            scanner_import_service_module.SARIF_IMPORT_MAX_CONTENT_BYTES = (
                previous_limit
            )

        self.assertEqual(response.status_code, 413)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "scanner_import_limit_exceeded")

    def test_import_semgrep_returns_413_for_oversized_payload(self) -> None:
        previous_limit = scanner_import_service_module.SARIF_IMPORT_MAX_CONTENT_BYTES
        scanner_import_service_module.SARIF_IMPORT_MAX_CONTENT_BYTES = 10
        try:
            response = self.client.post(
                "/api/v1/scanner-imports/semgrep",
                json={
                    "project_key": "payments",
                    "source_file": "large.json",
                    "content": self._semgrep_content(),
                },
            )
        finally:
            scanner_import_service_module.SARIF_IMPORT_MAX_CONTENT_BYTES = (
                previous_limit
            )

        self.assertEqual(response.status_code, 413)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "scanner_import_limit_exceeded")
        self.assertIn("Semgrep JSON content", payload["error"]["message"])

    def test_import_sarif_allows_valid_content_when_json_envelope_exceeds_content_limit(
        self,
    ) -> None:
        message_text = "A" * 20_000
        content = json.dumps(
            {
                "version": "2.1.0",
                "runs": [
                    {
                        "tool": {"driver": {"name": "Semgrep"}},
                        "results": [
                            {
                                "ruleId": "escaped.envelope",
                                "message": {"text": message_text},
                                "locations": [
                                    {
                                        "physicalLocation": {
                                            "artifactLocation": {"uri": "main.tf"},
                                        }
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            separators=(",", ":"),
        )
        escaped_content = "".join(f"\\u{ord(character):04x}" for character in content)
        encoded_request = (
            '{"project_key":"payments","source_file":"near-limit.sarif",'
            f'"content":"{escaped_content}"'
            "}"
        ).encode("utf-8")
        previous_content_limit = (
            scanner_import_service_module.SARIF_IMPORT_MAX_CONTENT_BYTES
        )
        previous_request_limit = (
            scanner_import_service_module.SARIF_IMPORT_MAX_REQUEST_BYTES
        )
        scanner_import_service_module.SARIF_IMPORT_MAX_CONTENT_BYTES = len(
            content.encode("utf-8")
        )
        scanner_import_service_module.SARIF_IMPORT_MAX_REQUEST_BYTES = len(
            encoded_request
        )
        try:
            response = self.client.post(
                "/api/v1/scanner-imports/sarif",
                content=encoded_request,
                headers={"content-type": "application/json"},
            )
        finally:
            scanner_import_service_module.SARIF_IMPORT_MAX_CONTENT_BYTES = (
                previous_content_limit
            )
            scanner_import_service_module.SARIF_IMPORT_MAX_REQUEST_BYTES = (
                previous_request_limit
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["imported_count"], 1)

    def test_import_sarif_rejects_oversized_request_body_before_body_validation(
        self,
    ) -> None:
        previous_request_limit = (
            scanner_import_service_module.SARIF_IMPORT_MAX_REQUEST_BYTES
        )
        scanner_import_service_module.SARIF_IMPORT_MAX_REQUEST_BYTES = 8
        try:
            response = self.client.post(
                "/api/v1/scanner-imports/sarif",
                content=b'{"not":"parsed"}',
                headers={"content-type": "application/json"},
            )
        finally:
            scanner_import_service_module.SARIF_IMPORT_MAX_REQUEST_BYTES = (
                previous_request_limit
            )

        self.assertEqual(response.status_code, 413)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "scanner_import_limit_exceeded")
        self.assertIn("request envelope", payload["error"]["message"])

    def test_import_sarif_openapi_success_response_is_typed(self) -> None:
        schema = self.client.app.openapi()
        response_schema = schema["paths"]["/api/v1/scanner-imports/sarif"]["post"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]

        self.assertEqual(
            response_schema["$ref"],
            "#/components/schemas/ScannerImportResponse",
        )

    def test_import_openapi_preserves_sarif_request_schema_name(self) -> None:
        schema = self.client.app.openapi()
        sarif_request = schema["paths"]["/api/v1/scanner-imports/sarif"]["post"][
            "requestBody"
        ]["content"]["application/json"]["schema"]
        semgrep_request = schema["paths"]["/api/v1/scanner-imports/semgrep"]["post"][
            "requestBody"
        ]["content"]["application/json"]["schema"]

        self.assertEqual(
            sarif_request["$ref"], "#/components/schemas/SarifImportRequest"
        )
        self.assertEqual(
            semgrep_request["$ref"],
            "#/components/schemas/ScannerImportRequest",
        )
        self.assertIn("SarifImportRequest", schema["components"]["schemas"])
        self.assertIn("ScannerImportRequest", schema["components"]["schemas"])

    def test_import_sarif_openapi_documents_project_scope_not_found(self) -> None:
        schema = self.client.app.openapi()
        responses = schema["paths"]["/api/v1/scanner-imports/sarif"]["post"][
            "responses"
        ]

        self.assertEqual(
            responses["404"]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/ErrorResponse",
        )

    def test_import_sarif_rejects_boolean_numeric_scope_ids(self) -> None:
        response = self.client.post(
            "/api/v1/scanner-imports/sarif",
            json={
                "project_id": True,
                "workspace_id": True,
                "source_file": "boolean-scope.sarif",
                "content": json.dumps({"version": "2.1.0", "runs": []}),
            },
        )

        self.assertEqual(response.status_code, 422)
        evidence = scanner_import_service_module.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertEqual(evidence, [])
