"""Linked report immutability is a typed denial for authorized mutations."""

from __future__ import annotations

from importlib import import_module
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.routes.analyses import router
from models.tables import AnalysisReport, InfraAutomationReportLink
from services import project_service as auth
from services import report_service
from services.artifact_snapshot_service import load_report_artifact
from tests.test_infra_automation import test_preflight_service as fixtures


class PreflightMutationDenialTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.PreflightServiceTests(methodName="runTest")
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        with self.case.engine.begin() as db:
            for name, body in import_module(
                "migrations.versions.033_add_infra_preflight"
            ).GUARDS.items():
                db.exec_driver_sql(f"CREATE TRIGGER {name} {body}")
        self.link = self.case.execute(self.case.admit())
        self.report_id = self.link["report_id"]

    def operations(self):
        return (
            lambda: report_service.remove_analysis_report(self.report_id),
            lambda: report_service.remove_analysis_reports([self.report_id]),
            lambda: report_service.configure_report_share(
                self.report_id,
                password="synthetic-share-password",
                redact_filenames=False,
            ),
        )

    def ordinary_report(self):
        from services.analysis_service import analyze_uploaded_files

        with self.case.credentials(), auth.authorized_session():
            return analyze_uploaded_files(
                fixtures.FILES, project_id=100, workspace_id=100
            ).persisted_report["id"]

    def test_authorized_service_mutations_are_denied_before_database_or_file_changes(
        self,
    ):
        with self.case.credentials():
            original = report_service.fetch_analysis_report(self.report_id)
            artifact = load_report_artifact(self.report_id, "main.tf").content
        with self.case.factory() as db:
            row = db.scalar(select(InfraAutomationReportLink))
            original_link = row.provenance_bytes, row.digest
        with (
            patch.object(report_service, "delete_analysis_report") as delete,
            patch.object(
                report_service, "update_analysis_report_share_settings"
            ) as share,
        ):
            for operation in self.operations():
                with self.subTest(operation=operation), self.case.credentials():
                    with self.assertRaises(auth.TrustedAuthorizationError) as denied:
                        operation()
                    self.assertEqual(denied.exception.status_code, 403)
            delete.assert_not_called()
            share.assert_not_called()
        with self.case.credentials():
            self.assertEqual(
                report_service.fetch_analysis_report(self.report_id), original
            )
            self.assertEqual(
                load_report_artifact(self.report_id, "main.tf").content, artifact
            )
        with self.case.factory() as db:
            row = db.scalar(select(InfraAutomationReportLink))
            self.assertEqual((row.provenance_bytes, row.digest), original_link)

    def test_mixed_bulk_prevalidates_linkage_before_deleting_ordinary_report(self):
        ordinary_id = self.ordinary_report()
        with patch.object(report_service, "delete_analysis_report") as delete:
            with (
                self.case.credentials(),
                self.assertRaises(auth.TrustedAuthorizationError),
            ):
                report_service.remove_analysis_reports([ordinary_id, self.report_id])
            delete.assert_not_called()
        with self.case.factory() as db:
            self.assertIsNotNone(db.get(AnalysisReport, ordinary_id))
            self.assertIsNotNone(db.get(AnalysisReport, self.report_id))
        with self.case.credentials():
            self.assertEqual(
                load_report_artifact(ordinary_id, "main.tf").content,
                fixtures.FILES[0][1].decode(),
            )

    def test_unlinked_share_and_single_and_bulk_deletion_keep_existing_behavior(self):
        single_id, bulk_id = self.ordinary_report(), self.ordinary_report()
        with self.case.credentials():
            shared = report_service.configure_report_share(
                single_id, password="synthetic-share-password", redact_filenames=False
            )
            self.assertTrue(shared["password_protected"])
            self.assertFalse(shared["redact_filenames"])
            self.assertTrue(report_service.remove_analysis_report(single_id))
            self.assertEqual(report_service.remove_analysis_reports([bulk_id]), 1)
        with self.case.factory() as db:
            self.assertIsNone(db.get(AnalysisReport, single_id))
            self.assertIsNone(db.get(AnalysisReport, bulk_id))
            self.assertIsNotNone(db.get(AnalysisReport, self.report_id))

    def test_missing_credentials_and_wrong_scope_remain_denied(self):
        self.case.principal("wrong-scope")
        self.case.member("admin", principal="wrong-scope", project=200)
        for operation in self.operations():
            with self.subTest(operation=operation):
                with self.assertRaises(auth.TrustedAuthorizationError):
                    operation()
                with self.case.credentials("wrong-scope"):
                    with self.assertRaises(auth.TrustedAuthorizationError):
                        operation()

    def test_real_https_api_returns_typed_403_for_authorized_delete_and_share(self):
        app = FastAPI()
        app.include_router(router)
        token, csrf = self.case.tokens["human-a"]
        headers = {
            "Origin": self.case.origin,
            "X-CSRF-Token": csrf,
            "Cookie": "__Host-dw-session=" + token,
        }
        with (
            patch("api.dependencies.identity_service", return_value=self.case.identity),
            TestClient(app, base_url=self.case.origin) as client,
        ):
            for method, path, payload in (
                ("DELETE", "/api/v1/analyses", {"ids": [self.report_id]}),
                (
                    "POST",
                    f"/api/v1/analyses/{self.report_id}/share",
                    {"password": "synthetic-share-password", "redact_filenames": False},
                ),
            ):
                with self.subTest(path=path):
                    response = client.request(
                        method, path, json=payload, headers=headers
                    )
                    self.assertEqual(response.status_code, 403, response.text)
                    self.assertEqual(
                        response.json()["error"]["code"], "operation_unavailable"
                    )
                    self.assertNotIn("Immutable linked report", response.text)
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
