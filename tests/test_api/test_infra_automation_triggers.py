"""Actual signed HTTP boundary authenticates bytes before JSON construction."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from api.routes import infra_automation_triggers as routes
from api.routes.infra_automation import router as human_router
from infra_automation.trigger_signing import (
    sign_request,
    KEY_ID_HEADER,
    TIMESTAMP_HEADER,
    NONCE_HEADER,
    SIGNATURE_HEADER,
)
from models.tables import InfraAutomationTriggerNonce, IdentitySession, IdentityAccount
from tests.test_infra_automation import test_trigger_authority as fixtures


class SignedTriggerApiTests(fixtures.TriggerFixture):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(routes.router)
        app.include_router(routes.human_router)
        app.include_router(human_router)
        self.client = TestClient(app, base_url=self.origin)
        self.addCleanup(self.client.close)
        for target in (
            "api.dependencies.identity_service",
            "api.routes.infra_automation_triggers.identity_service",
        ):
            p = patch(target, return_value=self.identity)
            p.start()
            self.addCleanup(p.stop)
        self.counter = 0

    def headers(self, path, body, nonce=None):
        self.counter += 1
        fields = dict(
            key_id="key-one",
            method="POST",
            path=path,
            timestamp=str(int(self.now.timestamp())),
            nonce=nonce or f"api-nonce-{self.counter:024}",
            body=body,
        )
        return {
            "Origin": self.origin,
            "Content-Type": "application/json",
            KEY_ID_HEADER: fields["key_id"],
            TIMESTAMP_HEADER: fields["timestamp"],
            NONCE_HEADER: fields["nonce"],
            SIGNATURE_HEADER: sign_request(secret=self.secret, **fields),
        }

    def test_valid_signed_validation_uses_live_machine_read_authority(self):
        path = "/api/v1/infra-automation/triggers/validate"
        body = json.dumps(
            {
                "project_id": 100,
                "workspace_id": 100,
                "definition": json.dumps(self.definition()),
            }
        ).encode()
        response = self.client.post(
            path, content=body, headers=self.headers(path, body)
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["data"]["valid"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        headers = self.headers(path, body)
        headers.pop("Origin")
        response = self.client.post(path, content=body, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)

    def test_bad_mac_never_reaches_parser_and_reencoding_invalidates_signature(self):
        path = "/api/v1/infra-automation/triggers/webhook"
        body = b'{"version":1}'
        headers = self.headers(path, body)
        with patch.object(
            routes,
            "_bounded_body",
            AsyncMock(side_effect=AssertionError("Parser reached")),
        ):
            response = self.client.post(
                path, content=b'{ "version": 1 }', headers=headers
            )
        self.assertEqual(response.status_code, 401, response.text)
        with self.factory() as db:
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(InfraAutomationTriggerNonce)
                ),
                0,
            )

    def test_valid_mac_invalid_json_burns_nonce_across_another_request(self):
        path = "/api/v1/infra-automation/triggers/webhook"
        body = b'{"broken":'
        headers = self.headers(path, body)
        first = self.client.post(path, content=body, headers=headers)
        second = self.client.post(path, content=body, headers=headers)
        self.assertEqual(first.status_code, 422, first.text)
        self.assertEqual(second.status_code, 401, second.text)
        self.assertNotIn("broken", first.text)

    def test_duplicate_headers_queries_cookies_and_oversize_deny(self):
        path = "/api/v1/infra-automation/triggers/webhook"
        body = b"{}"
        headers = self.headers(path, body)
        duplicate = list(headers.items()) + [(NONCE_HEADER, headers[NONCE_HEADER])]
        cases = [
            (path, body, duplicate),
            (path + "?unexpected=1", body, headers),
            (path, body, {**headers, "Cookie": "dw-local-session=caller"}),
            (path, b"x" * 131073, headers),
        ]
        for target, raw, values in cases:
            with self.subTest(target=target, length=len(raw)):
                response = self.client.post(target, content=raw, headers=values)
                self.assertIn(response.status_code, (401, 429), response.text)
        with self.factory() as db:
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(InfraAutomationTriggerNonce)
                ),
                0,
            )

    def test_machine_headers_cannot_publish_decide_or_provision_human_authority(self):
        path = "/api/v1/infra-automation/triggers/webhook"
        body = b"{}"
        headers = self.headers(path, body)
        headers.update({"X-Role": "admin", "X-Actor": "human-a"})
        for target, payload in (
            (
                "/api/v1/infra-automation/workflows/unknown/revisions",
                {
                    "reason": "Attempt forbidden publication",
                    "expected_version": 1,
                    "idempotency_key": "x",
                },
            ),
            (
                "/api/v1/infra-automation/approvals/unknown/decision",
                {
                    "reason": "Attempt forbidden decision",
                    "expected_version": 1,
                    "binding_digest": "sha256:" + "a" * 64,
                    "outcome": "approve",
                },
            ),
            (
                "/api/v1/infra-automation/triggers/principals",
                {
                    "project_id": 100,
                    "workspace_id": 100,
                    "username": "forbidden",
                    "principal_type": "agent",
                    "reason": "Attempt forbidden issuer",
                },
            ),
        ):
            with self.subTest(target=target):
                response = self.client.post(target, json=payload, headers=headers)
                self.assertIn(response.status_code, (401, 403), response.text)
        with self.factory() as db:
            self.assertIsNone(
                db.scalar(
                    select(IdentityAccount).where(
                        IdentityAccount.username == "forbidden"
                    )
                )
            )
            self.assertEqual(
                db.scalar(
                    select(func.count())
                    .select_from(IdentitySession)
                    .where(IdentitySession.principal_id == self.machine["principal_id"])
                ),
                0,
            )

    def test_openapi_keeps_human_and_signed_wire_types_closed(self):
        schema = self.client.app.openapi()
        self.assertIn("/api/v1/infra-automation/triggers/webhook", schema["paths"])
        self.assertFalse(
            schema["components"]["schemas"]["TriggerRequest"]["additionalProperties"]
        )
        self.assertIn(
            "origin", schema["components"]["schemas"]["RunView"]["properties"]
        )
