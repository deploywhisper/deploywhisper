"""Production report routes cannot promote legacy headers or sharing into authority."""

from unittest.mock import patch
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from api.routes.analyses import router as analyses_router
from api.routes.stats import router as stats_router
from api.errors import trusted_authorization_error_handler
from app import report_artifact_view
from services import project_service
from services import artifact_snapshot_service
from models.tables import AnalysisReport, Project
from tests.test_services import test_report_authorization as fixtures


class ProtectedReportApiTests(unittest.TestCase):
    principal = fixtures.ReportAuthorizationTests.principal
    member = fixtures.ReportAuthorizationTests.member
    context = fixtures.ReportAuthorizationTests.context
    tearDown = fixtures.ReportAuthorizationTests.tearDown

    def setUp(self):
        fixtures.ReportAuthorizationTests.setUp(self)
        with self.factory.begin() as db:
            db.get(Project, 3).is_default = True
        config.settings.identity_profile = "https"
        config.settings.identity_origin = "https://identity.invalid"
        self.patches.enter_context(
            patch("api.dependencies.identity_service", return_value=self.service)
        )
        app = FastAPI()
        app.include_router(analyses_router)
        app.include_router(stats_router)
        app.add_exception_handler(
            project_service.TrustedAuthorizationError,
            trusted_authorization_error_handler,
        )
        app.add_api_route(
            "/history/{report_id}/artifacts", report_artifact_view, methods=["GET"]
        )
        self.client = TestClient(app, base_url="https://identity.invalid")
        self.addCleanup(self.client.close)

    def headers(self, *, csrf=True):
        headers = {
            "Cookie": f"__Host-dw-session={self.token}",
            "Origin": "https://identity.invalid",
        }
        if csrf:
            headers["X-CSRF-Token"] = self.csrf
        return headers

    def test_analysis_actor_header_cannot_spoof_verified_principal(self):
        from analysis.blast_radius import BlastRadiusResult
        from analysis.rollback_planner import RollbackPlan
        from services.analysis_service import AnalysisArtifacts
        from tests.test_services.test_report_service import ReportServiceTests

        parse_batch, assessment, narrative = (
            ReportServiceTests()._content_boundary_models()
        )
        built = AnalysisArtifacts(
            parse_batch=parse_batch,
            assessment=assessment,
            narrative=narrative,
            blast_radius=BlastRadiusResult(direct_count=0, transitive_count=0),
            rollback_plan=RollbackPlan(complexity="low"),
        )
        self.member("contributor", workspace=1)
        with patch(
            "services.analysis_service.build_analysis_artifacts", return_value=built
        ):
            response = self.client.post(
                "/api/v1/analyses",
                headers={
                    **self.headers(),
                    "X-DeployWhisper-Actor": "forged administrator",
                },
                data={"project_id": "1", "workspace_id": "1"},
                files={
                    "files": (
                        "playbook.yaml",
                        b"hosts: all\ntasks:\n  - debug:\n      msg: safe fixture\n",
                        "text/yaml",
                    )
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()["data"]["persisted_report"]
        self.assertEqual(report["audit"]["actor"], "human-a")
        self.assertEqual(
            report["submission_manifest"]["provenance"]["actor"], "human-a"
        )
        self.assertNotIn("forged administrator", response.text)

    def test_html_artifact_route_requires_same_membership_and_disables_caching(self):
        self.member("admin", workspace=1)
        with self.context(mutation=True):
            artifact_snapshot_service.save_report_artifacts(
                1, {"a.txt": b"private-artifact-fixture"}
            )
        path = "/history/1/artifacts?name=a.txt"
        denied = self.client.get(path)
        self.assert_denied(denied)
        self.assertNotIn("private-artifact-fixture", denied.text)
        allowed = self.client.get(path, headers=self.headers())
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertIn("private-artifact-fixture", allowed.text)
        self.assertEqual(allowed.headers["cache-control"], "no-store")

    def assert_denied(self, response):
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["error"]["code"], "operation_unavailable")
        self.assertEqual(response.json()["error"]["message"], "Operation unavailable.")
        self.assertNotIn("synthetic", response.text)
        self.assertNotIn("project-1", response.text)

    def test_legacy_claims_and_sharing_credentials_cannot_read_protected_report(self):
        headers = {
            "X-DeployWhisper-Project-Role": "admin",
            "X-DeployWhisper-Project-Keys": "project-1",
            "X-DeployWhisper-Share-Token": "forged",
        }
        for path in (
            "/api/v1/analyses/1",
            "/api/v1/analyses/1/shared",
            "/api/v1/analyses/1?compare=previous",
        ):
            with self.subTest(path=path):
                self.assert_denied(self.client.get(path, headers=headers))
        self.assert_denied(
            self.client.post(
                "/api/v1/analyses/1/shared/unlock",
                headers=headers,
                json={"password": "forged"},
            )
        )
        self.assert_denied(
            self.client.post(
                "/api/v1/analyses/1/share",
                headers=headers,
                json={"password": None, "redact_filenames": False},
            )
        )

    def test_verified_identity_ignores_forged_role_and_scope_headers(self):
        self.member("read-only", workspace=1)
        headers = {
            **self.headers(),
            "X-DeployWhisper-Project-Role": "bogus",
            "X-DeployWhisper-Project-Keys": "project-2",
        }
        response = self.client.get("/api/v1/analyses/1", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assert_denied(self.client.get("/api/v1/analyses/2", headers=headers))
        self.assert_denied(
            self.client.request(
                "DELETE",
                "/api/v1/analyses",
                headers={**headers, "X-DeployWhisper-Project-Role": "admin"},
                json={"ids": [1]},
            )
        )

    def test_anonymous_aggregate_metadata_excludes_protected_reports(self):
        response = self.client.get("/api/v1/analyses?page_size=1")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([report["id"] for report in response.json()["data"]], [3])
        self.assertEqual(response.json()["meta"]["total_count"], 1)
        response = self.client.get("/api/v1/stats/summary")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["total_analyses"], 1)

    def test_protected_share_management_uses_membership_and_csrf(self):
        self.member("admin")
        payload = {"password": None, "redact_filenames": True}
        self.assert_denied(
            self.client.post(
                "/api/v1/analyses/1/share",
                headers=self.headers(csrf=False),
                json=payload,
            )
        )
        response = self.client.post(
            "/api/v1/analyses/1/share", headers=self.headers(), json=payload
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assert_denied(self.client.get("/api/v1/analyses/1/shared"))
        response = self.client.get("/api/v1/analyses/1/shared", headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)

    def test_batch_delete_denial_preserves_legacy_and_protected_rows(self):
        response = self.client.request(
            "DELETE", "/api/v1/analyses", json={"ids": [3, 1]}
        )
        self.assert_denied(response)
        with self.factory() as db:
            self.assertIsNotNone(db.get(AnalysisReport, 3))
            self.assertIsNotNone(db.get(AnalysisReport, 1))

    def test_workspace_member_reads_scoped_policy_outputs(self):
        self.member("read-only", workspace=1)
        for endpoint in ("policy-adapter", "enforcement-decision"):
            with self.subTest(endpoint=endpoint):
                path = f"/api/v1/analyses/1/{endpoint}?integration=jenkins"
                self.assert_denied(self.client.get(path))
                response = self.client.get(path, headers=self.headers())
                self.assertEqual(response.status_code, 200, response.text)
