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
import services.project_service as project_service_module
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
        os.environ["APP_BASE_URL"] = "https://deploywhisper.example.com"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(project_service_module)
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
        os.environ.pop("APP_BASE_URL", None)
        os.environ.pop("DEPLOYWHISPER_SHARE_TOKEN", None)
        self.tempdir.cleanup()

    def test_list_analyses_returns_persisted_reports(self) -> None:
        response = self.client.get("/api/v1/analyses")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["report_schema_version"], "v2")
        self.assertEqual(payload["meta"]["count"], 1)
        self.assertEqual(payload["meta"]["total_count"], 1)
        self.assertEqual(payload["meta"]["page"], 1)
        self.assertEqual(payload["meta"]["page_size"], 50)

    def test_list_analyses_defaults_to_unassigned_scope(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments.json",
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
                top_risk="Scoped project report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: scoped project report.",
                explanation="Scoped report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=project.id,
            audit_context={"source_interface": "api"},
        )

        response = self.client.get("/api/v1/analyses")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["count"], 1)
        self.assertEqual(payload["data"][0]["project"]["project_key"], "unassigned")

    def test_get_analysis_returns_single_report(self) -> None:
        response = self.client.get(f"/api/v1/analyses/{self.persisted['id']}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["id"], self.persisted["id"])
        self.assertEqual(payload["meta"]["report_schema_version"], "v2")
        self.assertEqual(payload["data"]["report_schema_version"], "v2")
        self.assertEqual(payload["data"]["audit"]["llm_provider"], "ollama")
        self.assertEqual(payload["data"]["blast_radius"]["direct_count"], 0)

    def test_get_analysis_rejects_unknown_project_reference(self) -> None:
        response = self.client.get(
            f"/api/v1/analyses/{self.persisted['id']}",
            params={"project_key": "missing"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "project_not_found")

    def test_get_analysis_defaults_to_unassigned_scope(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        scoped = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments.json",
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
                top_risk="Low-risk payments change.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: low-risk payments change.",
                explanation="Scoped report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=project.id,
            audit_context={"source_interface": "api"},
        )

        response = self.client.get(f"/api/v1/analyses/{scoped['id']}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "analysis_not_found")

    def test_configure_share_is_disabled_without_management_token(self) -> None:
        response = self.client.post(
            f"/api/v1/analyses/{self.persisted['id']}/share",
            json={"password": "s3cret-pass", "redact_filenames": True},
        )

        self.assertEqual(response.status_code, 405)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "share_configuration_disabled")

    def test_configure_share_requires_valid_management_token(self) -> None:
        os.environ["DEPLOYWHISPER_SHARE_TOKEN"] = "review-secret"
        self.client = TestClient(create_app())

        response = self.client.post(
            f"/api/v1/analyses/{self.persisted['id']}/share",
            json={"password": "s3cret-pass", "redact_filenames": True},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "share_configuration_forbidden")

    def test_configure_share_returns_public_report_settings(self) -> None:
        os.environ["DEPLOYWHISPER_SHARE_TOKEN"] = "review-secret"
        self.client = TestClient(create_app())

        response = self.client.post(
            f"/api/v1/analyses/{self.persisted['id']}/share",
            json={"password": "s3cret-pass", "redact_filenames": True},
            headers={"X-DeployWhisper-Share-Token": "review-secret"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["data"]["share_url"],
            f"https://deploywhisper.example.com/reports/{self.persisted['id']}",
        )
        self.assertTrue(payload["data"]["password_protected"])
        self.assertTrue(payload["data"]["redact_filenames"])

    def test_configure_share_rejects_unauthorized_reset_of_public_protection(
        self,
    ) -> None:
        report_service_module.configure_report_share(
            self.persisted["id"],
            password="s3cret-pass",
            redact_filenames=True,
        )

        reset_response = self.client.post(
            f"/api/v1/analyses/{self.persisted['id']}/share",
            json={"password": "", "redact_filenames": False},
        )
        report_response = self.client.get(f"/reports/{self.persisted['id']}")

        self.assertEqual(reset_response.status_code, 405)
        self.assertIn("Password required", report_response.text)

    def test_create_analysis_returns_structured_result(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
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
                data={"project_key": "payments"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["api_version"], "v1")
        self.assertEqual(payload["meta"]["report_schema_version"], "v2")
        self.assertTrue(payload["meta"]["advisory_only"])
        self.assertEqual(payload["meta"]["accepted_artifact_count"], 1)
        self.assertEqual(payload["data"]["intake"]["items"][0]["status"], "ready")
        self.assertEqual(payload["data"]["assessment"]["source"], "heuristic+llm")
        self.assertIn("context_completeness", payload["data"]["assessment"])
        self.assertEqual(
            payload["data"]["assessment"]["top_risk_contributors"], ["ev-001"]
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["project"]["project_key"], "payments"
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
        self.assertLessEqual(len(payload["data"]["share_summary"]["markdown"]), 1500)
        self.assertEqual(
            payload["data"]["share_summary"]["json_payload"]["version"], "v1"
        )
        self.assertEqual(
            payload["data"]["share_summary"]["json_payload"]["report_id"],
            payload["data"]["persisted_report"]["id"],
        )
        self.assertIn(
            "https://deploywhisper.example.com/reports/",
            payload["data"]["share_summary"]["json_payload"]["rollback_link"],
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["source_interface"], "api"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["trigger_type"], "api_request"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["top_risk_contributors"], ["ev-001"]
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["report_schema_version"], "v2"
        )
        self.assertIn("blast_radius", payload["data"]["persisted_report"])
        self.assertTrue(payload["data"]["persisted_report"]["findings"])
        self.assertTrue(payload["data"]["persisted_report"]["evidence_items"])
        self.assertEqual(
            payload["data"]["persisted_report"]["contributors"][0]["evidence_id"],
            "ev-001",
        )
        self.assertEqual(payload["data"]["persisted_report"]["id"], 2)

    def test_create_analysis_accepts_project_id(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
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
                data={"project_id": str(project.id)},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["data"]["persisted_report"]["project"]["project_key"], "payments"
        )

    def test_create_analysis_accepts_project_id_with_blank_project_key(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
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
            guidance=[],
            degraded=False,
            warnings=[],
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
                data={"project_id": str(project.id), "project_key": "   "},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["data"]["persisted_report"]["project"]["project_key"], "payments"
        )

    def test_create_analysis_rejects_unknown_project_reference(self) -> None:
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

        response = self.client.post(
            "/api/v1/analyses",
            files=files,
            data={"project_key": "missing"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "project_not_found")

    def test_create_analysis_rejects_unknown_project_before_parsing(self) -> None:
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

        with patch(
            "services.analysis_service.build_parse_batch",
            side_effect=AssertionError("project must resolve before parsing"),
        ) as build_parse_batch:
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "missing"},
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "project_not_found")
        build_parse_batch.assert_not_called()
        list_response = self.client.get("/api/v1/analyses")
        self.assertEqual(list_response.json()["meta"]["total_count"], 1)

    def test_create_analysis_rejects_missing_project_scope_before_parsing(
        self,
    ) -> None:
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

        with patch(
            "services.analysis_service.build_parse_batch",
            side_effect=AssertionError("project must resolve before parsing"),
        ) as build_parse_batch:
            response = self.client.post("/api/v1/analyses", files=files)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "missing_project_scope")
        build_parse_batch.assert_not_called()

    def test_create_analysis_rejects_blank_explicit_project_key_before_parsing(
        self,
    ) -> None:
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

        with patch(
            "services.analysis_service.build_parse_batch",
            side_effect=AssertionError("project must resolve before parsing"),
        ) as build_parse_batch:
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "   "},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_project_reference")
        build_parse_batch.assert_not_called()

    def test_list_analyses_rejects_unknown_project_reference(self) -> None:
        response = self.client.get(
            "/api/v1/analyses",
            params={"project_key": "missing"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "project_not_found")

    def test_create_analysis_rejects_conflicting_project_reference(self) -> None:
        first = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        second = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
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

        with patch(
            "services.analysis_service.build_parse_batch",
            side_effect=AssertionError("project must resolve before parsing"),
        ) as build_parse_batch:
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_id": str(first.id), "project_key": second.project_key},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"],
            "conflicting_project_reference",
        )
        build_parse_batch.assert_not_called()
        list_response = self.client.get("/api/v1/analyses")
        self.assertEqual(list_response.json()["meta"]["total_count"], 1)

    def test_create_analysis_captures_trigger_headers_when_present(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
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
                data={"project_key": "payments"},
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
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
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
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "payments"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        intake_names = [item["name"] for item in payload["data"]["intake"]["items"]]
        self.assertEqual(intake_names, ["plan.json", "plan#2.json"])

    def test_create_analysis_rejects_payloads_over_50_mb(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        oversized = b"x" * 50_000_001
        files = [("files", ("plan.json", oversized, "application/json"))]

        response = self.client.post(
            "/api/v1/analyses",
            files=files,
            data={"project_key": "payments"},
        )

        self.assertEqual(response.status_code, 413)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "upload_limit_exceeded")

    def test_create_analysis_rejects_requests_without_supported_artifacts(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [("files", ("README.txt", b"hello", "text/plain"))]

        response = self.client.post(
            "/api/v1/analyses",
            files=files,
            data={"project_key": "payments"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "no_supported_artifacts")
        self.assertEqual(
            payload["error"]["details"]["items"][0]["status"], "unsupported"
        )

    def test_create_analysis_rejects_missing_scope_before_unsupported_preflight(
        self,
    ) -> None:
        files = [("files", ("README.txt", b"hello", "text/plain"))]

        response = self.client.post("/api/v1/analyses", files=files)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "missing_project_scope")

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
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
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
            response = client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "payments"},
            )

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
