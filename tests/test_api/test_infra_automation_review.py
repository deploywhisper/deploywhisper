"""Actual verified-session approval packet reads and durable HTTP receipt recovery."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import infra_automation as routes
from services import infra_automation_decisions as decisions
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_decision_service as fixture


class ApprovalReviewApiTests(LifecycleCase):
    enable = fixture.DecisionServiceTests.enable
    publish_fixture = fixture.DecisionServiceTests.publish_fixture
    pending = fixture.DecisionServiceTests.pending
    request = fixture.DecisionServiceTests.request

    def setUp(self):
        fixture.DecisionServiceTests.setUp(self)
        self.enterContext(
            patch("api.dependencies.identity_service", return_value=self.identity)
        )
        self.enterContext(patch.object(decisions, "_default_service", self.service))
        app = FastAPI()
        app.include_router(routes.router)
        self.client = self.enterContext(TestClient(app, base_url=self.origin))

    def headers(self, principal="reviewer", *, csrf=False):
        token, csrf_token = self.tokens[principal]
        result = {"Cookie": f"__Host-dw-session={token}", "Origin": self.origin}
        if csrf:
            result["X-CSRF-Token"] = csrf_token
        return result

    def path(self, row, scope="project_id=100&workspace_id=100"):
        return f"/api/v1/infra-automation/approvals/{row['id']}?{scope}"

    def test_nonempty_packet_read_needs_human_but_no_csrf(self):
        row = self.pending()
        self.assertEqual(self.client.get(self.path(row)).status_code, 401)
        response = self.client.get(self.path(row), headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        packet = response.json()["data"]
        self.assertEqual(packet["receipt"]["id"], row["id"])
        self.assertEqual(packet["receipt"]["binding_digest"], row["binding_digest"])
        self.assertEqual(packet["report"]["recommendation"], "go")
        self.assertEqual(packet["report"]["confidence"]["score"], 1.0)
        self.assertEqual(packet["action"]["canonical_target"], "target")
        self.assertTrue(packet["context"]["can_submit"])
        self.assertEqual(packet["context"]["status"], "eligible")
        self.assertNotIn("report_bytes", packet["receipt"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_scope_query_unknown_fields_and_shared_requester_fail_safely(self):
        row = self.pending()
        response = self.client.get(
            self.path(row, "project_id=200&workspace_id=200"), headers=self.headers()
        )
        self.assertEqual(response.status_code, 403, response.text)
        self.assertNotIn(row["id"], response.text)
        self.assertEqual(
            self.client.get(
                self.path(row, "workspace_id=100"), headers=self.headers()
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(
                self.path(row) + "&role=admin", headers=self.headers()
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(
                self.path(row) + "&project_id=100", headers=self.headers()
            ).status_code,
            422,
        )
        own = self.client.get(self.path(row), headers=self.headers("human-a"))
        self.assertEqual(own.status_code, 200, own.text)
        self.assertFalse(own.json()["data"]["context"]["can_submit"])
        self.assertIn("requester_excluded", own.json()["data"]["context"]["reasons"])

    def test_lost_response_recovery_reads_recorded_generation_without_live_port(self):
        row = self.pending()
        response = self.client.post(
            f"/api/v1/infra-automation/approvals/{row['id']}/decision",
            json=self.request(row).model_dump(mode="json"),
            headers=self.headers(csrf=True),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.service.material_port = None
        recovered = self.client.get(self.path(row), headers=self.headers())
        self.assertEqual(recovered.status_code, 200, recovered.text)
        packet = recovered.json()["data"]
        self.assertEqual(packet["receipt"]["status"], "approved")
        self.assertEqual(packet["receipt"]["generation"], row["generation"])
        self.assertEqual(packet["receipt"]["version"], row["version"] + 1)
        self.assertEqual(packet["context"]["status"], "decided")
        self.assertFalse(packet["context"]["can_submit"])
        self.assertEqual(packet["attribution"]["principal_id"], "reviewer")
        self.assertEqual(packet["attribution"]["role"], "reviewer")
        self.assertEqual(packet["attribution"]["state_digest_version"], 1)
        stale = self.client.post(
            f"/api/v1/infra-automation/approvals/{row['id']}/decision",
            json=self.request(row).model_dump(mode="json"),
            headers=self.headers(csrf=True),
        )
        self.assertEqual(stale.status_code, 409, stale.text)
