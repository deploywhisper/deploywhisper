"""Tests for the bounded agent-callable API interface."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path
from unittest.mock import patch

import config as config_module
import models.database as database_module
import models.repositories.analysis_reports as analysis_reports_repository_module
import models.tables as tables_module
import services.project_service as project_service_module
import services.report_service as report_service_module
from analysis.risk_scorer import RiskAssessment
from api.errors import ApiError
from app import create_app
from fastapi.testclient import TestClient
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult
from sqlalchemy import text


class AgentApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "agent.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(project_service_module)
        reload(report_service_module)
        database_module.init_db()
        self.client = TestClient(create_app())
        self.payments = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        self.platform = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        self.platform_workspace = project_service_module.create_workspace(
            project_key="platform",
            workspace_key="prod",
            display_name="Production",
        )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    @staticmethod
    def _headers(*, role: str = "contributor") -> dict[str, str]:
        return {
            "X-DeployWhisper-Project-Role": role,
            "X-DeployWhisper-Project-Keys": "payments",
        }

    def _submit(self):
        return self.client.post(
            "/api/v1/agent/analyses",
            headers=self._headers(),
            files=[
                (
                    "files",
                    (
                        "plan.json",
                        b'{"resource_changes": []}',
                        "application/json",
                    ),
                ),
                (
                    "files",
                    (
                        ".env",
                        b"DEPLOY_TOKEN=raw-secret-value",
                        "text/plain",
                    ),
                ),
            ],
            data={"project_key": "payments"},
        )

    def _persist_report(
        self,
        *,
        project_id: int,
        guidance: list[str] | None = None,
    ) -> dict:
        return report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="platform.json",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=15,
                severity="low",
                recommendation="go",
                top_risk="Platform-scoped report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: platform-scoped report.",
                explanation="No material deterministic risk was identified.",
                guidance=guidance or [],
                degraded=False,
                warnings=[],
            ),
            project_id=project_id,
            audit_context={"source_interface": "agent-api"},
        )

    def _persist_platform_report(self) -> dict:
        return self._persist_report(project_id=self.platform.id)

    def test_submit_returns_bounded_schema_versioned_advisory_output(self) -> None:
        response = self._submit()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(set(payload), {"data", "meta"})
        self.assertEqual(payload["data"]["schema_version"], "v1")
        self.assertEqual(payload["meta"]["interface_schema_version"], "v1")
        self.assertEqual(payload["meta"]["operation"], "analysis.submit")
        self.assertTrue(payload["data"]["advisory_only"])
        self.assertFalse(payload["data"]["deployment_approval"])
        self.assertTrue(payload["data"]["human_decision_required"])
        self.assertEqual(payload["data"]["scope"]["project_key"], "payments")
        self.assertLessEqual(
            len(payload["data"]["findings"]),
            payload["meta"]["output_limits"]["max_findings"],
        )
        self.assertLessEqual(
            len(payload["data"]["evidence"]),
            payload["meta"]["output_limits"]["max_evidence"],
        )
        self.assertNotIn("raw-secret-value", response.text)
        self.assertNotIn("DEPLOY_TOKEN", response.text)

    def test_report_request_reuses_same_bounded_agent_contract(self) -> None:
        submitted = self._submit()
        self.assertEqual(submitted.status_code, 200)
        report_id = submitted.json()["data"]["report_id"]

        response = self.client.get(
            f"/api/v1/agent/reports/{report_id}",
            headers=self._headers(role="read-only"),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["report_id"], report_id)
        self.assertEqual(payload["data"]["scope"]["project_key"], "payments")
        self.assertEqual(payload["meta"]["operation"], "report.read")
        self.assertNotIn("submission_manifest", payload["data"])
        self.assertNotIn("audit", payload["data"])

    def test_report_request_preserves_persisted_narrative_guidance(self) -> None:
        report = self._persist_report(
            project_id=self.payments.id,
            guidance=["Verify the generated rollback sequence with an operator."],
        )

        response = self.client.get(
            f"/api/v1/agent/reports/{report['id']}",
            headers=self._headers(role="read-only"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Verify the generated rollback sequence with an operator.",
            response.json()["data"]["verification_guidance"],
        )

    def test_report_scope_denial_does_not_reveal_resource_existence(self) -> None:
        forbidden_report = self._persist_platform_report()
        headers = self._headers(role="read-only")

        existing = self.client.get(
            f"/api/v1/agent/reports/{forbidden_report['id']}",
            headers=headers,
        )
        missing = self.client.get(
            "/api/v1/agent/reports/999999",
            headers=headers,
        )

        self.assertEqual(existing.status_code, 403)
        self.assertEqual(missing.status_code, 403)
        self.assertEqual(existing.json(), missing.json())
        self.assertEqual(
            existing.json()["error"]["code"],
            "agent_scope_forbidden",
        )
        self.assertNotIn("platform", existing.text)

    def test_restricted_report_lookup_does_not_materialize_unscoped_report(
        self,
    ) -> None:
        with (
            patch(
                "api.routes.agent.fetch_analysis_report_for_project_keys",
                return_value=None,
            ) as scoped_fetch,
            patch("api.routes.agent.fetch_analysis_report") as unscoped_fetch,
        ):
            response = self.client.get(
                "/api/v1/agent/reports/42",
                headers=self._headers(role="read-only"),
            )

        self.assertEqual(response.status_code, 403)
        scoped_fetch.assert_called_once_with(42, project_keys=["payments"])
        unscoped_fetch.assert_not_called()

    def test_malformed_persisted_narrative_guidance_degrades_safely(self) -> None:
        report = self._persist_report(
            project_id=self.payments.id,
            guidance=["Verify the generated rollback sequence with an operator."],
        )
        with database_module.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE analysis_reports "
                    "SET narrative_guidance_json = :payload "
                    "WHERE id = :report_id"
                ),
                {"payload": "{not-json", "report_id": report["id"]},
            )

        response = self.client.get(
            f"/api/v1/agent/reports/{report['id']}",
            headers=self._headers(role="read-only"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"]["verification_guidance"],
            [
                "Have a human reviewer inspect the evidence and findings before deployment."
            ],
        )

    def test_project_scope_denial_does_not_reveal_resource_existence(self) -> None:
        files = {
            "files": (
                "plan.json",
                b'{"resource_changes": []}',
                "application/json",
            )
        }
        existing = self.client.post(
            "/api/v1/agent/analyses",
            headers=self._headers(),
            files=files,
            data={"project_key": "platform"},
        )
        missing = self.client.post(
            "/api/v1/agent/analyses",
            headers=self._headers(),
            files=files,
            data={"project_key": "does-not-exist"},
        )

        self.assertEqual(existing.status_code, 403)
        self.assertEqual(missing.status_code, 403)
        self.assertEqual(existing.json(), missing.json())
        self.assertEqual(
            existing.json()["error"]["code"],
            "agent_scope_forbidden",
        )
        self.assertNotIn("platform", existing.text)
        self.assertNotIn("does-not-exist", missing.text)

    def test_context_scope_denial_is_bounded_and_non_disclosing(self) -> None:
        files = {
            "files": (
                "plan.json",
                b'{"resource_changes": []}',
                "application/json",
            )
        }
        response = self.client.post(
            "/api/v1/agent/analyses",
            headers=self._headers(),
            files=files,
            data={
                "project_key": "payments",
                "workspace_id": str(self.platform_workspace.id),
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "agent_scope_forbidden")
        self.assertEqual(payload["error"]["details"], {})
        self.assertLessEqual(len(response.content), 512)
        self.assertNotIn("platform", response.text)
        self.assertNotIn("prod", response.text)

    def test_missing_workspace_scope_is_indistinguishable_from_forbidden(self) -> None:
        files = {
            "files": (
                "plan.json",
                b'{"resource_changes": []}',
                "application/json",
            )
        }
        forbidden = self.client.post(
            "/api/v1/agent/analyses",
            headers=self._headers(),
            files=files,
            data={
                "project_key": "payments",
                "workspace_id": str(self.platform_workspace.id),
            },
        )
        missing = self.client.post(
            "/api/v1/agent/analyses",
            headers=self._headers(),
            files=files,
            data={"project_key": "payments", "workspace_id": "999999"},
        )

        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(missing.status_code, 403)
        self.assertEqual(forbidden.json(), missing.json())

    def test_shared_analysis_not_found_error_is_masked_for_scoped_caller(self) -> None:
        with patch(
            "api.routes.agent.create_analysis",
            side_effect=ApiError(
                status_code=404,
                code="workspace_not_found",
                message="Unknown workspace reference: secret-workspace.",
            ),
        ):
            response = self.client.post(
                "/api/v1/agent/analyses",
                headers=self._headers(),
                files={
                    "files": (
                        "plan.json",
                        b'{"resource_changes": []}',
                        "application/json",
                    )
                },
                data={"project_key": "payments"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "agent_scope_forbidden")
        self.assertNotIn("secret-workspace", response.text)

    def test_shared_analysis_not_found_error_remains_404_for_admin(self) -> None:
        with patch(
            "api.routes.agent.create_analysis",
            side_effect=ApiError(
                status_code=404,
                code="workspace_not_found",
                message="Unknown workspace reference.",
            ),
        ):
            response = self.client.post(
                "/api/v1/agent/analyses",
                files={
                    "files": (
                        "plan.json",
                        b'{"resource_changes": []}',
                        "application/json",
                    )
                },
                data={"project_key": "payments"},
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "workspace_not_found")

    def test_malformed_persisted_report_returns_bounded_contract_error(self) -> None:
        with patch(
            "api.routes.agent.fetch_analysis_report",
            return_value={"id": 42, "project": None},
        ):
            response = self.client.get("/api/v1/agent/reports/42")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["error"]["code"],
            "agent_report_contract_invalid",
        )
        self.assertLessEqual(len(response.content), 256)

    def test_artifact_paths_are_safe_metadata_not_server_file_access(self) -> None:
        response = self.client.post(
            "/api/v1/agent/analyses",
            headers=self._headers(),
            files={
                "files": (
                    "passwd",
                    b'{"resource_changes": []}',
                    "application/json",
                )
            },
            data={
                "project_key": "payments",
                "artifact_paths": "/etc/passwd",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_artifact_path")

    def test_openapi_documents_agent_interface_contract(self) -> None:
        schema = self.client.get("/openapi.json").json()

        submit = schema["paths"]["/api/v1/agent/analyses"]["post"]
        report = schema["paths"]["/api/v1/agent/reports/{report_id}"]["get"]

        self.assertIn("AgentInterfaceResponse", str(submit["responses"]["200"]))
        self.assertIn("AgentInterfaceResponse", str(report["responses"]["200"]))
        for responses in (submit["responses"], report["responses"]):
            self.assertIn("ErrorResponse", str(responses["403"]))
            self.assertIn("ErrorResponse", str(responses["422"]))
            self.assertIn("ErrorResponse", str(responses["500"]))


if __name__ == "__main__":
    unittest.main()
