"""Receiver HTTP authority is isolated from human automation routes."""

from __future__ import annotations
from unittest import TestCase
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes.infra_automation_receiver import router


class ReceiverHttpTests(TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app, base_url="https://testserver")

    def test_plaintext_and_human_session_without_receiver_bearer_are_denied(self):
        app = FastAPI()
        app.include_router(router)
        with TestClient(app, base_url="http://testserver") as client:
            response = client.get("/api/v1/infra-automation/handoffs/op/status")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.headers["cache-control"], "no-store")
        response = self.client.get(
            "/api/v1/infra-automation/handoffs/op/status",
            headers={"cookie": "session=human"},
        )
        self.assertEqual(response.status_code, 401)

    def test_receiver_identity_is_operation_bound_and_query_closed(self):
        with patch(
            "services.infra_automation_handoffs._default_service.receiver_status",
            return_value={"state": "consumed"},
        ) as port:
            response = self.client.get(
                "/api/v1/infra-automation/handoffs/op/status",
                headers={
                    "authorization": "Bearer receiver-secret",
                    "x-receiver-id": "receiver",
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(port.call_args.args[0], "op")
            self.assertEqual(port.call_args.args[1].receiver_id, "receiver")
            self.assertEqual(response.headers["cache-control"], "no-store")
            response = self.client.get(
                "/api/v1/infra-automation/handoffs/op/status?grant_token=forbidden",
                headers={
                    "authorization": "Bearer receiver-secret",
                    "x-receiver-id": "receiver",
                },
            )
            self.assertEqual(response.status_code, 403)

    def test_duplicate_json_fields_and_unbound_consume_are_rejected(self):
        response = self.client.post(
            "/api/v1/infra-automation/handoffs/op/receipt",
            content='{"version":1,"version":1,"binding_digest":"sha256:'
            + "0" * 64
            + '"}',
            headers={
                "content-type": "application/json",
                "authorization": "Bearer receiver-secret",
                "x-receiver-id": "receiver",
            },
        )
        self.assertEqual(response.status_code, 422)
