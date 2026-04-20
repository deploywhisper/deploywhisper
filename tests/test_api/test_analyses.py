"""Tests for analysis history API routes."""

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
import services.report_service as report_service_module
from analysis.risk_scorer import RiskAssessment, RiskContributor
from app import create_app
from fastapi.testclient import TestClient
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange


class AnalysesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "reports.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(report_service_module)
        database_module.init_db()
        self.client = TestClient(create_app())

        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="aws_security_group.main",
                            action="modify",
                            summary="Terraform changed a security group.",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform changed a security group.",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        self.persisted = report_service_module.persist_analysis_report(
            parse_batch, assessment, narrative
        )

    @staticmethod
    def _analysis_assessment(
        *,
        severity: str = "high",
        recommendation: str = "no-go",
        top_risk: str = "Security group exposure risk",
        partial_context: bool = False,
    ) -> RiskAssessment:
        return RiskAssessment(
            score=72,
            severity=severity,
            recommendation=recommendation,
            top_risk=top_risk,
            top_risk_contributors=["ev-001"],
            contributors=[
                RiskContributor(
                    evidence_id="ev-001",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=20,
                    summary=top_risk,
                    severity=severity,
                    reasoning=top_risk,
                )
            ],
            interaction_risks=[],
            partial_context=partial_context,
            warnings=[],
            source="heuristic+llm",
        )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_list_analyses_returns_persisted_reports(self) -> None:
        response = self.client.get("/api/v1/analyses")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["count"], 1)
        self.assertEqual(payload["meta"]["total_count"], 1)
        self.assertEqual(payload["meta"]["page"], 1)
        self.assertEqual(payload["meta"]["page_size"], 50)

    def test_get_analysis_returns_single_report(self) -> None:
        response = self.client.get(f"/api/v1/analyses/{self.persisted['id']}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["id"], self.persisted["id"])
        self.assertEqual(payload["data"]["audit"]["llm_provider"], "ollama")

    def test_create_analysis_returns_structured_result(self) -> None:
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["modify"]}}]}',
                    "application/json",
                ),
            )
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=["Review the security group change before deploy."],
            degraded=False,
            warnings=[],
            source="llm",
            provider="ollama",
            model="ollama/llama3",
            local_mode=True,
            skills_applied=["git", "terraform"],
        )

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=self._analysis_assessment(),
            ),
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            response = self.client.post("/api/v1/analyses", files=files)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["api_version"], "v1")
        self.assertTrue(payload["meta"]["advisory_only"])
        self.assertEqual(payload["meta"]["accepted_artifact_count"], 1)
        self.assertEqual(payload["data"]["intake"]["items"][0]["status"], "ready")
        self.assertEqual(payload["data"]["assessment"]["source"], "heuristic+llm")
        self.assertIn("context_completeness", payload["data"]["assessment"])
        self.assertEqual(
            payload["data"]["assessment"]["top_risk_contributors"], ["ev-001"]
        )
        self.assertEqual(
            payload["data"]["assessment"]["contributors"][0]["evidence_id"], "ev-001"
        )
        self.assertTrue(payload["data"]["findings"])
        self.assertTrue(payload["data"]["evidence_items"])
        self.assertEqual(payload["data"]["evidence_items"][0]["analysis_id"], 0)
        self.assertEqual(payload["data"]["findings"][0]["confidence"], 1.0)
        self.assertIn(payload["data"]["assessment"]["severity"], {"high", "critical"})
        self.assertEqual(payload["data"]["narrative"]["source"], "llm")
        self.assertTrue(payload["data"]["narrative"]["skills_applied"])
        self.assertFalse(payload["data"]["advisory"]["should_block"])
        self.assertTrue(payload["data"]["advisory"]["requires_attention"])
        self.assertIn("Advisory only", payload["data"]["share_summary"]["markdown"])
        self.assertEqual(payload["data"]["share_summary"]["recommendation"], "no-go")
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["source_interface"], "api"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["trigger_type"], "api_request"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["top_risk_contributors"], ["ev-001"]
        )
        self.assertTrue(payload["data"]["persisted_report"]["findings"])
        self.assertTrue(payload["data"]["persisted_report"]["evidence_items"])
        self.assertEqual(
            payload["data"]["persisted_report"]["contributors"][0]["evidence_id"],
            "ev-001",
        )
        self.assertEqual(payload["data"]["persisted_report"]["id"], 2)

    def test_create_analysis_captures_trigger_headers_when_present(self) -> None:
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["modify"]}}]}',
                    "application/json",
                ),
            )
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=["Review the security group change before deploy."],
            degraded=False,
            warnings=[],
            source="llm",
            provider="ollama",
            model="ollama/llama3",
            local_mode=True,
            skills_applied=["git", "terraform"],
        )

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=self._analysis_assessment(),
            ),
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                headers={
                    "X-DeployWhisper-Trigger-Type": "user_session",
                    "X-DeployWhisper-Trigger-Id": "sess-456",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["trigger_type"], "user_session"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["trigger_id"], "sess-456"
        )

    def test_create_analysis_preserves_distinct_artifacts_with_same_basename(
        self,
    ) -> None:
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.first", "change": {"actions": ["modify"]}}]}',
                    "application/json",
                ),
            ),
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.second", "change": {"actions": ["modify"]}}]}',
                    "application/json",
                ),
            ),
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group updates.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=["Review both security group changes before deploy."],
            degraded=False,
            warnings=[],
            source="llm",
            provider="ollama",
            model="ollama/llama3",
            local_mode=True,
            skills_applied=["git", "terraform"],
        )

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=self._analysis_assessment(
                    top_risk="Security group updates"
                ),
            ),
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            response = self.client.post("/api/v1/analyses", files=files)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        intake_names = [item["name"] for item in payload["data"]["intake"]["items"]]
        self.assertEqual(intake_names, ["plan.json", "plan#2.json"])

    def test_create_analysis_rejects_payloads_over_50_mb(self) -> None:
        oversized = b"x" * 50_000_001
        files = [("files", ("plan.json", oversized, "application/json"))]

        response = self.client.post("/api/v1/analyses", files=files)

        self.assertEqual(response.status_code, 413)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "upload_limit_exceeded")

    def test_create_analysis_rejects_requests_without_supported_artifacts(self) -> None:
        files = [("files", ("README.txt", b"hello", "text/plain"))]

        response = self.client.post("/api/v1/analyses", files=files)

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "no_supported_artifacts")
        self.assertEqual(
            payload["error"]["details"]["items"][0]["status"], "unsupported"
        )

    def test_get_analysis_returns_standard_error_envelope_for_missing_report(
        self,
    ) -> None:
        response = self.client.get("/api/v1/analyses/9999")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "analysis_not_found")
        self.assertEqual(payload["error"]["message"], "Analysis report not found.")

    def test_invalid_analysis_id_uses_standard_error_envelope(self) -> None:
        response = self.client.get("/api/v1/analyses/not-an-int")

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "request_validation_failed")
        self.assertEqual(
            payload["error"]["details"]["issues"][0]["loc"], ["path", "report_id"]
        )

    def test_method_not_allowed_uses_standard_error_envelope(self) -> None:
        response = self.client.patch("/api/v1/analyses")

        self.assertEqual(response.status_code, 405)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "method_not_allowed")
        self.assertEqual(payload["error"]["message"], "Method Not Allowed")

    def test_analysis_pipeline_failure_uses_standard_error_envelope(self) -> None:
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["modify"]}}]}',
                    "application/json",
                ),
            )
        ]
        client = TestClient(create_app(), raise_server_exceptions=False)

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=self._analysis_assessment(),
            ),
            patch(
                "services.analysis_service.generate_narrative",
                return_value=NarrativeResult(
                    opening_sentence="CAUTION: review the security group update.",
                    explanation="The deployment widens database access and should be reviewed.",
                    guidance=["Review the security group change before deploy."],
                    degraded=False,
                    warnings=[],
                    source="llm",
                    provider="ollama",
                    model="ollama/llama3",
                    local_mode=True,
                    skills_applied=["git", "terraform"],
                ),
            ),
            patch(
                "services.analysis_service.find_incident_matches",
                side_effect=RuntimeError("boom"),
            ),
        ):
            response = client.post("/api/v1/analyses", files=files)

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "internal_error")
        self.assertEqual(payload["error"]["message"], "Internal server error.")

    def test_openapi_documents_analysis_submission_contract(self) -> None:
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        schema = response.json()
        analyses_post = schema["paths"]["/api/v1/analyses"]["post"]
        request_body_schema = analyses_post["requestBody"]["content"][
            "multipart/form-data"
        ]["schema"]
        self.assertIn("$ref", request_body_schema)
        component_name = request_body_schema["$ref"].split("/")[-1]
        self.assertEqual(
            schema["components"]["schemas"][component_name]["type"], "object"
        )
        self.assertIn("AnalysisRunResponse", str(analyses_post["responses"]["200"]))
        self.assertIn("ErrorResponse", str(analyses_post["responses"]["400"]))
        self.assertNotIn("ParseBatchResult", schema["components"]["schemas"])
        self.assertNotIn("RiskAssessment", schema["components"]["schemas"])


if __name__ == "__main__":
    unittest.main()
