"""Tests for analysis history API routes."""

from __future__ import annotations

import os
import sqlite3
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
from evidence.models import EvidenceItem
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
        resource_id: str = "aws_security_group.main",
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
                    resource_id=resource_id,
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

    def test_workspace_query_prevents_cross_workspace_report_lookup(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        prod = project_service_module.create_workspace(
            project_key=project.project_key,
            workspace_key="prod",
            display_name="Production",
            environment="prod",
        )
        staging = project_service_module.create_workspace(
            project_key=project.project_key,
            workspace_key="staging",
            display_name="Staging",
            environment="staging",
        )
        scoped = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments-prod.json",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=72,
                severity="high",
                recommendation="no-go",
                top_risk="Production payment ingress widened.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="NO-GO: production payment ingress widened.",
                explanation="Workspace-scoped report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=project.id,
            workspace_id=prod.id,
            audit_context={"source_interface": "api"},
        )

        wrong_workspace_response = self.client.get(
            f"/api/v1/analyses/{scoped['id']}",
            params={
                "project_key": project.project_key,
                "workspace_key": staging.workspace_key,
            },
        )
        unscoped_workspace_id_response = self.client.get(
            f"/api/v1/analyses/{scoped['id']}",
            params={"workspace_id": prod.id},
        )
        unscoped_workspace_id_list_response = self.client.get(
            "/api/v1/analyses",
            params={"workspace_id": prod.id},
        )
        scoped_id_response = self.client.get(
            f"/api/v1/analyses/{scoped['id']}",
            params={"project_id": project.id, "workspace_id": prod.id},
        )
        scoped_list_response = self.client.get(
            "/api/v1/analyses",
            params={
                "project_key": project.project_key,
                "workspace_key": prod.workspace_key,
            },
        )

        self.assertEqual(wrong_workspace_response.status_code, 404)
        self.assertEqual(
            wrong_workspace_response.json()["error"]["code"], "analysis_not_found"
        )
        self.assertEqual(unscoped_workspace_id_response.status_code, 400)
        self.assertEqual(
            unscoped_workspace_id_response.json()["error"]["code"],
            "missing_project_scope",
        )
        self.assertEqual(unscoped_workspace_id_list_response.status_code, 400)
        self.assertEqual(
            unscoped_workspace_id_list_response.json()["error"]["code"],
            "missing_project_scope",
        )
        self.assertEqual(scoped_id_response.status_code, 200)
        self.assertEqual(scoped_id_response.json()["data"]["id"], scoped["id"])
        self.assertEqual(scoped_list_response.status_code, 200)
        payload = scoped_list_response.json()
        self.assertEqual(payload["meta"]["total_count"], 1)
        self.assertEqual(payload["data"][0]["workspace"]["workspace_key"], "prod")

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

    def test_configure_share_denies_project_outside_actor_scope(self) -> None:
        os.environ["DEPLOYWHISPER_SHARE_TOKEN"] = "review-secret"
        self.client = TestClient(create_app())

        response = self.client.post(
            f"/api/v1/analyses/{self.persisted['id']}/share",
            json={"password": "s3cret-pass", "redact_filenames": True},
            headers={
                "X-DeployWhisper-Share-Token": "review-secret",
                "X-DeployWhisper-Project-Role": "maintainer",
                "X-DeployWhisper-Project-Keys": "payments",
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")
        self.assertNotIn("unassigned", payload["error"]["message"])

    def test_configure_share_denies_reviewer_within_actor_scope(self) -> None:
        os.environ["DEPLOYWHISPER_SHARE_TOKEN"] = "review-secret"
        self.client = TestClient(create_app())

        response = self.client.post(
            f"/api/v1/analyses/{self.persisted['id']}/share",
            json={"password": "s3cret-pass", "redact_filenames": True},
            headers={
                "X-DeployWhisper-Share-Token": "review-secret",
                "X-DeployWhisper-Project-Role": "reviewer",
                "X-DeployWhisper-Project-Keys": "unassigned",
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_permission_denied")

    def test_configure_share_validates_missing_scope_before_missing_report(
        self,
    ) -> None:
        os.environ["DEPLOYWHISPER_SHARE_TOKEN"] = "review-secret"
        self.client = TestClient(create_app())

        response = self.client.post(
            "/api/v1/analyses/999999/share",
            json={"password": "s3cret-pass", "redact_filenames": True},
            headers={
                "X-DeployWhisper-Share-Token": "review-secret",
                "X-DeployWhisper-Project-Role": "maintainer",
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_scope_required")

    def test_configure_share_validates_invalid_actor_before_missing_report(
        self,
    ) -> None:
        os.environ["DEPLOYWHISPER_SHARE_TOKEN"] = "review-secret"
        self.client = TestClient(create_app())

        response = self.client.post(
            "/api/v1/analyses/999999/share",
            json={"password": "s3cret-pass", "redact_filenames": True},
            headers={
                "X-DeployWhisper-Share-Token": "review-secret",
                "X-DeployWhisper-Project-Role": "unknown-role",
                "X-DeployWhisper-Project-Keys": "unassigned",
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "invalid_project_role")

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

    def test_create_analysis_masks_foreign_workspace_for_scoped_actor(self) -> None:
        allowed = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        forbidden = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        workspace = project_service_module.create_workspace(
            project_key=forbidden.project_key,
            workspace_key="prod",
            display_name="Production",
        )

        response = self.client.post(
            "/api/v1/analyses",
            data={
                "project_key": allowed.project_key,
                "workspace_id": str(workspace.id),
            },
            files=[
                (
                    "files",
                    (
                        "plan.json",
                        b'{"resource_changes": []}',
                        "application/json",
                    ),
                )
            ],
            headers={
                "X-DeployWhisper-Project-Role": "contributor",
                "X-DeployWhisper-Project-Keys": allowed.project_key,
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")

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
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
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
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-001",
                analysis_id=0,
                finding_id="pending:change-001",
                source_type="artifact",
                source_ref="terraform://plan.json#aws_security_group.main?action=modify",
                summary="Terraform changed a security group.",
                severity_hint="high",
                deterministic=True,
                confidence=1.0,
                related_change_ids=["change-001"],
            )
        ]

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=self._analysis_assessment(),
            ),
            patch(
                "services.analysis_service.extract_batch_evidence",
                return_value=evidence_items,
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
        self.assertLess(payload["data"]["assessment"]["confidence"], 0.7)
        self.assertIn("context_completeness", payload["data"]["assessment"])
        self.assertTrue(
            payload["data"]["assessment"]["context_completeness"][
                "insufficient_context"
            ]
        )
        self.assertTrue(
            payload["data"]["assessment"]["context_completeness"]["context_todos"]
        )
        self.assertEqual(
            payload["data"]["assessment"]["top_risk_contributors"], ["ev-001"]
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["project"]["project_key"], "payments"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["confidence"],
            payload["data"]["assessment"]["confidence"],
        )
        self.assertEqual(
            payload["data"]["assessment"]["contributors"][0]["evidence_id"], "ev-001"
        )
        self.assertTrue(payload["data"]["findings"])
        self.assertTrue(payload["data"]["evidence_items"])
        self.assertEqual(payload["data"]["evidence_items"][0]["analysis_id"], 0)
        self.assertEqual(payload["data"]["findings"][0]["confidence"], 1.0)
        self.assertEqual(
            payload["data"]["findings"][0]["evidence_classification"],
            "deterministic",
        )
        self.assertEqual(payload["data"]["findings"][0]["evidence_refs"], ["ev-001"])
        self.assertEqual(
            payload["data"]["findings"][0]["explanation"],
            "Security group exposure risk",
        )
        self.assertTrue(payload["data"]["findings"][0]["guidance"])
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
        persisted_evidence_id = payload["data"]["persisted_report"]["evidence_items"][
            0
        ]["evidence_id"]
        self.assertEqual(
            payload["data"]["persisted_report"]["top_risk_contributors"],
            [persisted_evidence_id],
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["report_schema_version"], "v2"
        )
        self.assertIn("blast_radius", payload["data"]["persisted_report"])
        self.assertTrue(payload["data"]["persisted_report"]["findings"])
        self.assertTrue(payload["data"]["persisted_report"]["evidence_items"])
        self.assertEqual(
            payload["data"]["persisted_report"]["contributors"][0]["evidence_id"],
            persisted_evidence_id,
        )
        self.assertEqual(payload["data"]["persisted_report"]["id"], 2)

    def test_create_analysis_preserves_real_pipeline_metadata_in_persisted_contributors(
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
                    (
                        b'{"planned_values": {}, "resource_changes": ['
                        b'{"address": "data.aws_ami.selected", "mode": "data", '
                        b'"change": {"actions": ["read"], "after_unknown": {"id": true}}}, '
                        b'{"address": '
                        b'"module.network.aws_security_group.main", "module_address": '
                        b'"module.network", "provider_name": '
                        b'"registry.terraform.io/hashicorp/aws", "type": '
                        b'"aws_security_group", "name": "main", "change": '
                        b'{"actions": ["update"]}}]}'
                    ),
                    "application/json",
                ),
            )
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment should be reviewed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "analysis.risk_scorer.generate_completion_with_settings",
                return_value='{"change_scores": []}',
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
        contributors = {
            contributor["resource_id"]: contributor
            for contributor in payload["data"]["persisted_report"]["contributors"]
        }
        metadata = contributors["module.network.aws_security_group.main"]["metadata"]
        self.assertEqual(metadata["module_address"], "module.network")
        self.assertEqual(
            metadata["provider_name"], "registry.terraform.io/hashicorp/aws"
        )
        self.assertEqual(metadata["plan_unsupported_fields"], ["plan.planned_values"])
        self.assertEqual(
            contributors["data.aws_ami.selected"]["metadata"]["unknown_after_apply"],
            ["id"],
        )
        self.assertIsNone(contributors["data.aws_ami.selected"]["evidence_id"])
        self.assertEqual(contributors["data.aws_ami.selected"]["contribution"], 0)

        detail = self.client.get(
            f"/api/v1/analyses/{payload['data']['persisted_report']['id']}",
            params={"project_key": "payments"},
        )
        self.assertEqual(detail.status_code, 200)
        detail_contributors = {
            contributor["resource_id"]: contributor
            for contributor in detail.json()["data"]["contributors"]
        }
        self.assertEqual(
            detail_contributors["module.network.aws_security_group.main"]["metadata"][
                "plan_unsupported_fields"
            ],
            ["plan.planned_values"],
        )
        self.assertEqual(
            detail_contributors["data.aws_ami.selected"]["metadata"][
                "unknown_after_apply"
            ],
            ["id"],
        )

        history = self.client.get(
            "/api/v1/analyses",
            params={"project_key": "payments"},
        )
        self.assertEqual(history.status_code, 200)
        history_contributors = {
            contributor["resource_id"]: contributor
            for contributor in history.json()["data"][0]["contributors"]
        }
        self.assertEqual(
            history_contributors["module.network.aws_security_group.main"]["metadata"][
                "plan_unsupported_fields"
            ],
            ["plan.planned_values"],
        )
        self.assertEqual(
            history_contributors["data.aws_ami.selected"]["metadata"][
                "unknown_after_apply"
            ],
            ["id"],
        )

    def test_create_analysis_preserves_all_non_mutating_plan_metadata(
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
                    "empty-plan.json",
                    (
                        b'{"format_version": "1.2", "terraform_version": "1.8.5", '
                        b'"planned_values": {}, "resource_changes": []}'
                    ),
                    "application/json",
                ),
            )
        ]
        narrative = NarrativeResult(
            opening_sentence="GO: no planned infrastructure changes.",
            explanation="The submitted Terraform plan contains no resource changes.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
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
        contributor = payload["data"]["persisted_report"]["contributors"][0]
        self.assertEqual(contributor["resource_id"], "terraform-plan")
        self.assertEqual(contributor["contribution"], 0)
        self.assertEqual(
            contributor["metadata"]["plan_unsupported_fields"],
            ["plan.planned_values"],
        )

        detail = self.client.get(
            f"/api/v1/analyses/{payload['data']['persisted_report']['id']}",
            params={"project_key": "payments"},
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(
            detail.json()["data"]["contributors"][0]["metadata"][
                "plan_unsupported_fields"
            ],
            ["plan.planned_values"],
        )

        history = self.client.get(
            "/api/v1/analyses",
            params={"project_key": "payments"},
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(
            history.json()["data"][0]["contributors"][0]["metadata"][
                "plan_unsupported_fields"
            ],
            ["plan.planned_values"],
        )

    def test_create_analysis_persists_submission_manifest_with_partial_coverage(
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
                    (
                        b'{"planned_values": {}, "resource_changes": [{"address": "module.network.aws_security_group.main", '
                        b'"module_address": "module.network", "type": "aws_security_group", '
                        b'"name": "main", "provider_name": "registry.terraform.io/hashicorp/aws", '
                        b'"change": {"actions": ["update"], "after_unknown": {"arn": true}, '
                        b'"after_sensitive": {"ingress": [{"description": true}]}, '
                        b'"replace_paths": [["ingress", 0, "cidr_blocks"]], '
                        b'"importing": {"id": "sg-123"}}, "deposed": "legacy"}]}'
                    ),
                    "application/json",
                ),
            ),
            (
                "files",
                (
                    "broken.tf",
                    b"resource {",
                    "application/octet-stream",
                ),
            ),
            (
                "files",
                (
                    ".env",
                    b"SECRET=1",
                    "text/plain",
                ),
            ),
            (
                "files",
                (
                    "notes.txt",
                    b"deployment notes",
                    "text/plain",
                ),
            ),
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review partial analysis.",
            explanation="One artifact failed to parse.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=self._analysis_assessment(
                    resource_id="module.network.aws_security_group.main",
                    partial_context=True,
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
                headers={"X-DeployWhisper-Trigger-Id": "build-77"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        manifest = payload["data"]["persisted_report"]["submission_manifest"]
        self.assertEqual(manifest["submitted_artifact_count"], 4)
        self.assertEqual(manifest["accepted_artifact_count"], 2)
        self.assertEqual(manifest["analyzed_artifact_count"], 1)
        self.assertEqual(manifest["excluded_artifact_count"], 1)
        self.assertEqual(manifest["sensitive_artifact_count"], 1)
        self.assertEqual(manifest["failed_artifact_count"], 1)
        self.assertEqual(manifest["partial_artifact_count"], 3)
        self.assertTrue(manifest["partial_analysis"])
        by_name = {item["name"]: item for item in manifest["items"]}
        self.assertEqual(by_name["plan.json"]["status"], "accepted")
        self.assertEqual(by_name["broken.tf"]["status"], "failed")
        self.assertTrue(by_name["broken.tf"]["partial"])
        self.assertEqual(by_name[".env"]["status"], "sensitive")
        self.assertTrue(by_name[".env"]["partial"])
        self.assertEqual(by_name["notes.txt"]["status"], "excluded")
        self.assertTrue(by_name["notes.txt"]["partial"])
        self.assertEqual(by_name["plan.json"]["provenance"]["source_interface"], "api")
        self.assertEqual(by_name["plan.json"]["provenance"]["trigger_id"], "build-77")
        change = payload["data"]["parse_batch"]["files"][0]["changes"][0]
        self.assertEqual(
            change["resource_id"], "module.network.aws_security_group.main"
        )
        self.assertEqual(change["metadata"]["module_address"], "module.network")
        self.assertEqual(change["metadata"]["unknown_after_apply"], ["arn"])
        self.assertEqual(
            change["metadata"]["redacted_fields"], ["ingress.0.description"]
        )
        self.assertEqual(
            change["metadata"]["unsupported_fields"],
            ["change.importing", "resource_change.deposed"],
        )
        self.assertEqual(
            change["metadata"]["plan_unsupported_fields"],
            ["plan.planned_values"],
        )
        self.assertTrue(payload["data"]["assessment"]["partial_context"])

        detail = self.client.get(
            f"/api/v1/analyses/{payload['data']['persisted_report']['id']}",
            params={"project_key": "payments"},
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(
            detail.json()["data"]["submission_manifest"]["failed_artifact_count"],
            1,
        )

    def test_create_analysis_surfaces_duplicate_terraform_action_parse_failure(
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
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            ),
            (
                "files",
                (
                    "duplicate-plan.json",
                    b'{"resource_changes": [{"address": "aws_instance.web", "change": {"actions": ["create", "create"]}}]}',
                    "application/json",
                ),
            ),
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review partial analysis.",
            explanation="One Terraform plan could not be parsed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
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
        by_name = {
            file_result["file_name"]: file_result
            for file_result in payload["data"]["parse_batch"]["files"]
        }
        self.assertEqual(by_name["plan.json"]["status"], "parsed")
        self.assertEqual(by_name["duplicate-plan.json"]["status"], "failed")
        self.assertIn(
            "Duplicate Terraform action",
            by_name["duplicate-plan.json"]["issue"]["message"],
        )
        manifest = payload["data"]["persisted_report"]["submission_manifest"]
        self.assertEqual(manifest["accepted_artifact_count"], 2)
        self.assertEqual(manifest["failed_artifact_count"], 1)
        self.assertTrue(manifest["partial_analysis"])

    def test_create_analysis_denies_role_without_submit_capability(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": []}',
                    "application/json",
                ),
            )
        ]

        response = self.client.post(
            "/api/v1/analyses",
            headers={
                "X-DeployWhisper-Project-Role": "read-only",
                "X-DeployWhisper-Project-Keys": "payments",
            },
            files=files,
            data={"project_key": "payments"},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_permission_denied")
        self.assertNotIn("payments", payload["error"]["message"])

    def test_project_role_header_requires_nonblank_role(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": []}',
                    "application/json",
                ),
            )
        ]

        response = self.client.post(
            "/api/v1/analyses",
            headers={"X-DeployWhisper-Project-Role": " "},
            files=files,
            data={"project_key": "payments"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "invalid_project_role")

    def test_non_admin_role_requires_project_scope_header(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

        response = self.client.get(
            "/api/v1/analyses",
            params={"project_key": "payments"},
            headers={"X-DeployWhisper-Project-Role": "read-only"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "project_scope_required")

    def test_analysis_reads_mask_missing_project_id_for_scoped_actor(self) -> None:
        response = self.client.get(
            "/api/v1/analyses",
            params={"project_id": 999},
            headers={
                "X-DeployWhisper-Project-Role": "read-only",
                "X-DeployWhisper-Project-Keys": "payments",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "project_scope_forbidden")

    def test_analysis_reads_mask_conflicting_project_reference_for_scoped_actor(
        self,
    ) -> None:
        allowed = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        forbidden = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        headers = {
            "X-DeployWhisper-Project-Role": "read-only",
            "X-DeployWhisper-Project-Keys": allowed.project_key,
        }

        list_response = self.client.get(
            "/api/v1/analyses",
            params={
                "project_key": allowed.project_key,
                "project_id": forbidden.id,
            },
            headers=headers,
        )
        detail_response = self.client.get(
            f"/api/v1/analyses/{self.persisted['id']}",
            params={
                "project_key": allowed.project_key,
                "project_id": forbidden.id,
            },
            headers=headers,
        )

        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(
            list_response.json()["error"]["code"], "project_scope_forbidden"
        )
        self.assertEqual(detail_response.status_code, 403)
        self.assertEqual(
            detail_response.json()["error"]["code"], "project_scope_forbidden"
        )
        self.assertNotIn("payments", detail_response.json()["error"]["message"])

    def test_analysis_reads_deny_project_outside_actor_scope(self) -> None:
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
        headers = {
            "X-DeployWhisper-Project-Role": "read-only",
            "X-DeployWhisper-Project-Keys": "platform",
        }

        list_response = self.client.get(
            "/api/v1/analyses",
            params={"project_key": "payments"},
            headers=headers,
        )
        detail_response = self.client.get(
            f"/api/v1/analyses/{scoped['id']}",
            params={"project_key": "payments"},
            headers=headers,
        )

        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(
            list_response.json()["error"]["code"], "project_scope_forbidden"
        )
        self.assertNotIn("payments", list_response.json()["error"]["message"])
        self.assertEqual(detail_response.status_code, 403)
        self.assertEqual(
            detail_response.json()["error"]["code"], "project_scope_forbidden"
        )
        self.assertNotIn("payments", detail_response.json()["error"]["message"])

    def test_analysis_detail_returns_null_manifest_when_persisted_json_is_malformed(
        self,
    ) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE analysis_reports SET submission_manifest_json = ? WHERE id = ?",
                ("{not-valid-json", self.persisted["id"]),
            )

        response = self.client.get(f"/api/v1/analyses/{self.persisted['id']}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertIsNone(payload["submission_manifest"])
        self.assertEqual(
            payload["submission_manifest_fallback"][0]["name"], "plan.json"
        )
        self.assertEqual(
            payload["submission_manifest_fallback"][0]["status"], "accepted"
        )
        self.assertIn(
            "Submission manifest metadata was unavailable because persisted JSON was malformed.",
            payload["warnings"],
        )

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
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
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
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
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
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
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
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
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
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
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
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
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
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
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
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
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
                    b'{"resource_changes": [{"address": "aws_security_group.first", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            ),
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.second", "change": {"actions": ["update"]}}]}',
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
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
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
