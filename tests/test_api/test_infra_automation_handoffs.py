"""HTTP intent/read/dispatch adapters preserve human authority and durable state."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

from api.routes import infra_automation as routes
from services import infra_automation_handoffs as handoffs
from tests.test_infra_automation import test_handoff_service as fixture
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class HandoffApiTests(LifecycleCase):
    enable = fixture.HandoffServiceTests.enable
    publish_fixture = fixture.HandoffServiceTests.publish_fixture
    deliver = fixture.HandoffServiceTests.deliver
    request = fixture.HandoffServiceTests.request
    prepare = fixture.HandoffServiceTests.prepare
    dispatch = fixture.HandoffServiceTests.dispatch

    def setUp(self):
        fixture.HandoffServiceTests.setUp(self)
        first = patch("api.dependencies.identity_service", return_value=self.identity)
        first.start()
        self.addCleanup(first.stop)
        second = patch.object(handoffs, "_default_service", self.handoffs)
        second.start()
        self.addCleanup(second.stop)
        app = FastAPI()
        app.include_router(routes.router)
        self.client = TestClient(app, base_url=self.origin)
        self.addCleanup(self.client.close)

    def headers(self, principal="human-a"):
        token, csrf = self.tokens[principal]
        return {
            "Origin": self.origin,
            "Cookie": f"__Host-dw-session={token}",
            "X-CSRF-Token": csrf,
        }

    def test_prepare_replay_and_read_expose_recorded_intent_without_grant(self):
        path = "/api/v1/infra-automation/handoffs/prepare"
        body = self.request().model_dump(mode="json")
        response = self.client.post(path, json=body, headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        first = response.json()["data"]
        self.assertEqual(first["state"], "prepared")
        self.assertIsNone(first["receipt"])
        self.assertNotIn("grant_token", response.text)
        replay = self.client.post(path, json=body, headers=self.headers())
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(first, replay.json()["data"])
        detail = self.client.get(
            f"/api/v1/infra-automation/handoffs/{first['id']}?project_id=100&workspace_id=100",
            headers=self.headers(),
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        wrong = self.client.get(
            f"/api/v1/infra-automation/handoffs/{first['id']}?project_id=200&workspace_id=200",
            headers=self.headers(),
        )
        self.assertEqual(wrong.status_code, 403, wrong.text)

    def test_dispatch_is_one_committed_attempt_then_receipt_history_is_readable(self):
        operation = self.prepare()
        body = dict(
            project_id=100,
            workspace_id=100,
            expected_version=operation["version"],
            reason="Dispatch exact approved intent",
        )
        path = f"/api/v1/infra-automation/handoffs/{operation['id']}/dispatch"
        response = self.client.post(path, json=body, headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["state"], "delivery_unknown")
        self.assertEqual(
            self.client.post(path, json=body, headers=self.headers()).status_code, 409
        )
        envelope = self.sent[0]
        consumed = self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        detail = self.client.get(
            f"/api/v1/infra-automation/handoffs/{operation['id']}?project_id=100&workspace_id=100",
            headers=self.headers(),
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["data"]["receipt"], consumed["receipt"])

    def test_credentials_actor_claims_and_destination_overrides_cannot_prepare(self):
        path = "/api/v1/infra-automation/handoffs/prepare"
        body = self.request().model_dump(mode="json")
        self.assertEqual(
            self.client.post(
                path, json=body, headers={"Origin": self.origin}
            ).status_code,
            401,
        )
        bad = {**self.headers(), "X-CSRF-Token": "wrong"}
        self.assertEqual(
            self.client.post(path, json=body, headers=bad).status_code, 403
        )
        for changes in (
            {"actor": "admin"},
            {"role": "admin"},
            {"url": "https://foreign.invalid"},
            {"grant_token": "forged"},
            {"version": True},
        ):
            with self.subTest(field=tuple(changes)):
                response = self.client.post(
                    path, json={**body, **changes}, headers=self.headers()
                )
                self.assertEqual(response.status_code, 422, response.text)

    def test_unqualified_production_ports_fail_closed_and_no_receiver_route_is_installed(
        self,
    ):
        self.handoffs.ref_port = None
        response = self.client.post(
            "/api/v1/infra-automation/handoffs/prepare",
            json=self.request().model_dump(mode="json"),
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 503, response.text)
        response = self.client.post(
            "/api/v1/infra-automation/handoffs/unknown/consume",
            json={},
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 404)
