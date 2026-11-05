"""Runner UI schemas and permission reads preserve transport and secret rules."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.routes.infra_automation_runner_admin import (
    router as admin_router,
    EnrollmentReveal,
)
from api.routes.infra_automation_runner_views import router as views_router
from infra_automation.lifecycle import AutomationSettings, UpdateSettingsRequest
from models.tables import IdentitySession
from services import infra_automation_policy as policy
from services.identity_service import IdentityService
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class RunnerHealthUiHttpTests(LifecycleCase):
    def setUp(self):
        super().setUp()
        with self.credentials():
            policy.update_settings(
                UpdateSettingsRequest(
                    project_id=100,
                    expected_version=0,
                    settings=AutomationSettings(enabled=True),
                    reason="Enable fixture.",
                )
            )
        app = FastAPI()
        app.include_router(admin_router)
        app.include_router(views_router)
        self.app = app
        self.client = TestClient(app, base_url=self.origin)
        token, csrf = self.tokens["human-a"]
        self.headers = {
            "cookie": "__Host-dw-session=" + token,
            "origin": self.origin,
            "x-csrf-token": csrf,
        }
        self.enterContext(
            patch("api.dependencies.identity_service", return_value=self.identity)
        )

    def test_typed_reveal_is_transient_and_repr_stays_masked(self):
        payload = dict(
            project_id=100,
            workspace_id=100,
            tags=["linux"],
            tool="opentofu",
            profile_digest="sha256:" + "a" * 64,
            runner_version="1.0",
            reason="Enroll fixture.",
        )
        response = self.client.post(
            "/api/v1/infra-automation/runners/enrollments",
            headers=self.headers,
            json=payload,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        value = response.json()["data"]
        typed = EnrollmentReveal.model_validate(value)
        self.assertNotIn(value["token"], repr(typed))
        self.assertEqual(typed.model_dump(mode="json")["token"], value["token"])
        for path, expected in (
            (
                "/api/v1/infra-automation/runners/enrollments",
                "RunnerEnrollmentResponse",
            ),
            (
                "/api/v1/infra-automation/runners/{runner_id}/rotate",
                "RunnerCredentialResponse",
            ),
            (
                "/api/v1/infra-automation/runners/{runner_id}/revoke",
                "RunnerRegistrationResponse",
            ),
        ):
            schema = self.app.openapi()["paths"][path]["post"]["responses"]["200"][
                "content"
            ]["application/json"]["schema"]
            self.assertEqual(schema["$ref"], "#/components/schemas/" + expected)

    def test_capabilities_are_scoped_and_cannot_authorize_mutations(self):
        url = "/api/v1/infra-automation/runner-capabilities?project_id=100&workspace_id=100"
        response = self.client.get(url, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["data"]["can_enroll"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        denied = self.client.get(
            url.replace("project_id=100", "project_id=200"), headers=self.headers
        )
        self.assertEqual(denied.status_code, 403)
        self.member("maintainer")
        response = self.client.get(url, headers=self.headers)
        self.assertTrue(response.json()["data"]["can_read_health"])
        self.assertFalse(response.json()["data"]["can_enroll"])
        response = self.client.post(
            "/api/v1/infra-automation/runners/enrollments",
            headers=self.headers,
            json=dict(
                project_id=100,
                workspace_id=100,
                tags=[],
                tool="opentofu",
                profile_digest="sha256:" + "a" * 64,
                runner_version="1.0",
                reason="Denied fixture.",
            ),
        )
        self.assertEqual(response.status_code, 403)

    def test_local_profile_can_explain_but_never_bypass_https_gate(self):
        origin = "http://localhost:8080"
        with self.factory.begin() as db:
            for row in db.scalars(select(IdentitySession)):
                row.security_profile = "local-development"
                row.trusted_origin = origin
        local = IdentityService(
            self.factory,
            now=lambda: self.now,
            security_profile="local-development",
            trusted_origin=origin,
        )
        token, csrf = self.tokens["human-a"]
        headers = {
            "cookie": "dw-local-session=" + token,
            "origin": origin,
            "x-csrf-token": csrf,
        }
        with (
            patch.object(
                config,
                "settings",
                replace(
                    config.settings,
                    identity_profile="local-development",
                    identity_origin=origin,
                ),
            ),
            patch("api.dependencies.identity_service", return_value=local),
        ):
            client = TestClient(self.app, base_url=origin)
            response = client.get(
                "/api/v1/infra-automation/runner-capabilities?project_id=100&workspace_id=100",
                headers=headers,
            )
            self.assertEqual(response.status_code, 200, response.text)
            value = response.json()["data"]
            self.assertEqual(value["restriction"], "https_required")
            self.assertFalse(value["can_read_health"])
            self.assertFalse(value["can_enroll"])
            self.assertEqual(value["configured_profiles"], [])
            for method, path in (
                (
                    "get",
                    "/api/v1/infra-automation/runners?project_id=100&workspace_id=100",
                ),
                ("post", "/api/v1/infra-automation/runners/enrollments"),
            ):
                response = getattr(client, method)(path, headers=headers)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.headers["cache-control"], "no-store")
