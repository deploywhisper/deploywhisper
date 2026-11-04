"""Runner transport credentials and errors remain separate from human authority."""

from __future__ import annotations

from tests.test_infra_automation.lifecycle_support import LifecycleCase
from services import infra_automation_policy as policy
from infra_automation.lifecycle import AutomationSettings, UpdateSettingsRequest
from api.routes.infra_automation_runner_admin import router as admin_router

from unittest import TestCase
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes.infra_automation_runner import router


class RunnerHttpTests(TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.app = app
        self.client = TestClient(app, base_url="https://testserver")

    def test_transport_and_query_are_closed(self):
        for url in ("http://testserver", "https://testserver"):
            client = TestClient(self.app, base_url=url)
            suffix = "" if url.startswith("http:") else "?token=secret"
            response = client.get("/api/v1/infra-automation/runners/r1/tasks" + suffix)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertNotIn("secret", response.text)

    def test_human_cookie_does_not_authenticate_runner(self):
        response = self.client.get(
            "/api/v1/infra-automation/runners/r1/tasks",
            headers={"cookie": "session=human"},
        )
        self.assertEqual(response.status_code, 401)

    def test_duplicate_authorization_denied(self):
        response = self.client.get(
            "/api/v1/infra-automation/runners/r1/tasks",
            headers=[
                ("authorization", "Bearer first"),
                ("authorization", "Bearer second"),
            ],
        )
        self.assertEqual(response.status_code, 401)

    def test_poll_binds_path_runner_and_redacts_failure(self):
        with patch(
            "services.infra_automation_runner_tasks.poll",
            side_effect=RuntimeError("secret-value"),
        ) as port:
            response = self.client.get(
                "/api/v1/infra-automation/runners/r1/tasks",
                headers={"authorization": "Bearer " + "a" * 64},
            )
            self.assertEqual(port.call_args.args[0].runner_id, "r1")
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("secret-value", response.text)


class RunnerEnrollmentHttpTests(LifecycleCase):
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
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.include_router(admin_router)
        self.client = TestClient(self.app, base_url=self.origin)
        token, csrf = self.tokens["human-a"]
        self.headers = {
            "cookie": "__Host-dw-session=" + token,
            "x-csrf-token": csrf,
            "origin": self.origin,
        }
        self.identity_patch = patch(
            "api.dependencies.identity_service", return_value=self.identity
        )
        self.identity_patch.start()
        self.addCleanup(self.identity_patch.stop)

    def test_human_enrollment_machine_redeem_rotation_and_revoke(self):
        response = self.client.post(
            "/api/v1/infra-automation/runners/enrollments",
            headers=self.headers,
            json={
                "project_id": 100,
                "workspace_id": 100,
                "tags": ["linux"],
                "tool": "opentofu",
                "profile_digest": "sha256:" + "a" * 64,
                "runner_version": "1.0",
                "reason": "Enroll fixture.",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        issued = response.json()["data"]
        self.assertNotEqual(issued["token"], "**********")
        enrollment = issued["enrollment"]
        url = (
            "/api/v1/infra-automation/runners/enrollments/"
            + enrollment["enrollment_id"]
            + "/redeem"
        )
        response = self.client.post(
            url, headers={"authorization": "Bearer " + issued["token"]}, json=enrollment
        )
        self.assertEqual(response.status_code, 200, response.text)
        credential = response.json()["data"]
        self.assertNotEqual(credential["token"], "**********")
        self.assertEqual(
            self.client.post(
                url,
                headers={"authorization": "Bearer " + issued["token"]},
                json=enrollment,
            ).status_code,
            401,
        )
        runner_url = "/api/v1/infra-automation/runners/" + credential["runner_id"]
        response = self.client.post(
            runner_url + "/rotate",
            headers=self.headers,
            json={"reason": "Rotate fixture."},
        )
        self.assertEqual(response.status_code, 200, response.text)
        new = response.json()["data"]
        response = self.client.get(
            runner_url + "/tasks",
            headers={"authorization": "Bearer " + credential["token"]},
        )
        self.assertEqual(response.status_code, 401)
        response = self.client.post(
            runner_url + "/revoke",
            headers=self.headers,
            json={"reason": "Revoke fixture."},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            self.client.get(
                runner_url + "/tasks",
                headers={"authorization": "Bearer " + new["token"]},
            ).status_code,
            401,
        )
        response = self.client.get(
            "/api/v1/infra-automation/runners?project_id=100&workspace_id=100",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(new["token"], response.text)

    def test_missing_csrf_cannot_issue(self):
        headers = {
            key: value for key, value in self.headers.items() if key != "x-csrf-token"
        }
        response = self.client.post(
            "/api/v1/infra-automation/runners/enrollments", headers=headers, json={}
        )
        self.assertEqual(response.status_code, 403)

    def test_health_default_limit_continuations_and_closed_openapi(self):
        from services import infra_automation_runners as runners

        with self.credentials():
            for _ in range(26):
                runners.create_enrollment(
                    runners.EnrollmentRequest(
                        project_id=100,
                        workspace_id=100,
                        tags=["linux"],
                        tool="opentofu",
                        profile_digest="sha256:" + "a" * 64,
                        runner_version="1.0",
                        reason="Page fixture.",
                    )
                )
        url = "/api/v1/infra-automation/runners"
        params = {"project_id": 100, "workspace_id": 100}
        first = self.client.get(url, params=params, headers=self.headers)
        self.assertEqual(first.status_code, 200, first.text)
        data = first.json()["data"]
        self.assertEqual(set(data), {"items", "cursor"})
        self.assertEqual(len(data["items"]), 25)
        self.assertEqual(data["cursor"]["limit"], 25)
        cursor = data["cursor"]["next_cursor"]
        second = self.client.get(
            url, params={**params, "cursor": cursor}, headers=self.headers
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(len(second.json()["data"]["items"]), 1)
        self.assertIsNone(second.json()["data"]["cursor"]["next_cursor"])
        largest = self.client.get(
            url, params={**params, "limit": 100}, headers=self.headers
        )
        self.assertEqual(len(largest.json()["data"]["items"]), 26)
        for extra, expected in (
            ({"limit": 101}, 422),
            ({"cursor": "synthetic"}, 409),
            ({"cursor": ""}, 409),
            ({"cursor": "!bad"}, 409),
            ({"cursor": cursor, "limit": 24}, 409),
            ({"cursor": cursor, "workspace_id": 101}, 409),
        ):
            response = self.client.get(
                url, params={**params, **extra}, headers=self.headers
            )
            self.assertEqual(response.status_code, expected, response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")
        schemas = self.app.openapi()["components"]["schemas"]
        for name in (
            "RunnerHealthResponse",
            "RunnerHealthPage",
            "RunnerHealth",
            "CursorEnvelope",
        ):
            self.assertFalse(schemas[name]["additionalProperties"])
        health_schema = schemas["RunnerHealth"]["properties"]
        self.assertNotIn("credential_hash", health_schema)
        self.assertNotIn("token", health_schema)
        response_schema = self.app.openapi()["paths"][url]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        self.assertEqual(
            response_schema["$ref"], "#/components/schemas/RunnerHealthResponse"
        )

    def test_health_cursor_rechecks_session_and_membership_before_every_page(self):
        from sqlalchemy import select
        from models.tables import IdentitySession, ProjectMembership
        from services import infra_automation_runners as runners

        with self.credentials():
            for _ in range(2):
                runners.create_enrollment(
                    runners.EnrollmentRequest(
                        project_id=100,
                        workspace_id=100,
                        tags=[],
                        tool="opentofu",
                        profile_digest="sha256:" + "a" * 64,
                        runner_version="1.0",
                        reason="Revocation fixture.",
                    )
                )
        url = "/api/v1/infra-automation/runners"
        params = {"project_id": 100, "workspace_id": 100, "limit": 1}
        first = self.client.get(url, params=params, headers=self.headers)
        cursor = first.json()["data"]["cursor"]["next_cursor"]
        with self.factory.begin() as db:
            member = db.scalar(
                select(ProjectMembership).where(
                    ProjectMembership.principal_id == "human-a",
                    ProjectMembership.project_id == 100,
                )
            )
            member.enabled = False
        denied = self.client.get(
            url, params={**params, "cursor": cursor}, headers=self.headers
        )
        self.assertEqual(denied.status_code, 403)
        with self.factory.begin() as db:
            member = db.scalar(
                select(ProjectMembership).where(
                    ProjectMembership.principal_id == "human-a",
                    ProjectMembership.project_id == 100,
                )
            )
            member.enabled = True
            member.authorization_version += 1
        stale = self.client.get(
            url, params={**params, "cursor": cursor}, headers=self.headers
        )
        self.assertEqual(stale.status_code, 409)
        fresh = self.client.get(url, params=params, headers=self.headers)
        cursor = fresh.json()["data"]["cursor"]["next_cursor"]
        with self.factory.begin() as db:
            session = db.scalar(
                select(IdentitySession).where(IdentitySession.principal_id == "human-a")
            )
            session.revoked_at = self.now
        denied = self.client.get(
            url, params={**params, "cursor": cursor}, headers=self.headers
        )
        self.assertEqual(denied.status_code, 401)
