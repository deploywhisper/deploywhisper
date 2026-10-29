"""Real-session confirmation denial, receipt and scoped audit HTTP contracts."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from api.routes import infra_automation as routes
from models.tables import InfraAutomationAudit, ProjectAuthorizationAudit
from services import infra_automation_decisions as service
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_approval_confirmation as fixture


class ApprovalConfirmationApiTests(LifecycleCase):
    enable = fixture.ApprovalConfirmationTests.enable
    publish_fixture = fixture.ApprovalConfirmationTests.publish_fixture
    setUp = fixture.ApprovalConfirmationTests.setUp
    pending = fixture.ApprovalConfirmationTests.pending
    request = fixture.ApprovalConfirmationTests.request
    severity = fixture.ApprovalConfirmationTests.severity
    request_with_confirmation = (
        fixture.ApprovalConfirmationTests.request_with_confirmation
    )

    def headers(self, principal="reviewer"):
        token, csrf = self.tokens[principal]
        return {
            "Cookie": f"__Host-dw-session={token}",
            "Origin": self.origin,
            "X-CSRF-Token": csrf,
        }

    def counts(self):
        with self.factory() as db:
            return tuple(
                db.scalar(select(func.count()).select_from(table))
                for table in (InfraAutomationAudit, ProjectAuthorizationAudit)
            )

    def test_real_http_high_confirmation_is_required_without_false_audit_writes(self):
        self.severity("high")
        row = self.pending()
        before = self.counts()
        app = FastAPI()
        app.include_router(routes.router)
        path = f"/api/v1/infra-automation/approvals/{row['id']}/decision"
        payload = self.request(row).model_dump(mode="json")
        with (
            patch("api.dependencies.identity_service", return_value=self.identity),
            patch.object(service, "_default_service", self.service),
            TestClient(app, base_url=self.origin) as client,
        ):
            self.assertEqual(
                client.post(
                    path, json=payload, headers={"Origin": self.origin}
                ).status_code,
                401,
            )
            self.assertEqual(
                client.post(
                    path,
                    json={**payload, "confirmation": "APPROVE target"},
                    headers=self.headers("human-a"),
                ).status_code,
                403,
            )
            for value in (None, "", "APPROVE other", "ACKNOWLEDGE target", True):
                with self.subTest(confirmation=value):
                    denied = client.post(
                        path,
                        json={**payload, "confirmation": value},
                        headers=self.headers(),
                    )
                    self.assertEqual(denied.status_code, 422, denied.text)
                    self.assertEqual(self.counts(), before)
            for field in ("reviewer_id", "actor", "decision_kind", "role"):
                denied = client.post(
                    path,
                    json={**payload, "confirmation": "APPROVE target", field: "admin"},
                    headers=self.headers(),
                )
                self.assertEqual(denied.status_code, 422, denied.text)
                self.assertEqual(self.counts(), before)
            missing_csrf = client.post(
                path,
                json={**payload, "confirmation": "APPROVE target"},
                headers={
                    k: v for k, v in self.headers().items() if k != "X-CSRF-Token"
                },
            )
            self.assertEqual(missing_csrf.status_code, 403)
            response = client.post(
                path,
                json={**payload, "confirmation": "APPROVE target"},
                headers=self.headers(),
            )
            self.assertEqual(response.status_code, 200, response.text)
            receipt = response.json()["data"]
            self.assertEqual(receipt["status"], "approved")
            self.assertEqual(receipt["reviewer_id"], "reviewer")
            self.assertNotIn("confirmation", receipt)
            self.assertNotIn("report_bytes", receipt)
            self.assertEqual(response.headers["cache-control"], "no-store")
            replay = client.post(
                path,
                json={**payload, "confirmation": "APPROVE target"},
                headers=self.headers(),
            )
            self.assertEqual(replay.status_code, 409)

    def test_existing_admin_only_audit_export_contains_transition_digests(self):
        row = self.pending()
        with self.credentials("reviewer"):
            self.service.decide(row["id"], self.request(row))
        app = FastAPI()
        app.include_router(routes.router)
        path = "/api/v1/infra-automation/audit?project_id=100&workspace_id=100"
        with (
            patch("api.dependencies.identity_service", return_value=self.identity),
            TestClient(app, base_url=self.origin) as client,
        ):
            self.assertEqual(client.get(path, headers=self.headers()).status_code, 403)
            response = client.get(path, headers=self.headers("human-a"))
            self.assertEqual(response.status_code, 200, response.text)
            event = next(
                item
                for item in response.json()["data"]["items"]
                if item["event_type"] == "decision_approve"
            )
            self.assertEqual(
                (event["actor_principal_id"], event["actor_type"], event["actor_role"]),
                ("reviewer", "human", "reviewer"),
            )
            self.assertTrue(event["before_digest"].startswith("sha256:"))
            self.assertTrue(event["after_digest"].startswith("sha256:"))
            self.assertNotEqual(event["before_digest"], event["after_digest"])
            self.assertNotEqual(event["after_digest"], row["binding_digest"])
            self.assertEqual(event["project_id"], 100)
            self.assertEqual(event["workspace_id"], 100)
            self.assertEqual(event["reason"], "Synthetic review")
