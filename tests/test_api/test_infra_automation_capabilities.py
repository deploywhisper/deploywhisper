"""Live editor capabilities without granting workflow mutation authority."""

from __future__ import annotations

from datetime import timedelta
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from api import schemas
from infra_automation.lifecycle import AutomationSettings
from models.tables import IdentityAccount, IdentitySession
from services import infra_automation_service as service
from tests.test_api import test_infra_automation_preflight as preflight
from tests.test_api import test_infra_automation_workflows as fixtures


class InfraAutomationCapabilitiesApiTests(unittest.TestCase):
    principal = fixtures.InfraAutomationWorkflowApiTests.principal
    member = fixtures.InfraAutomationWorkflowApiTests.member
    context = fixtures.InfraAutomationWorkflowApiTests.context
    setUp = fixtures.InfraAutomationWorkflowApiTests.setUp
    tearDown = fixtures.InfraAutomationWorkflowApiTests.tearDown
    headers = fixtures.InfraAutomationWorkflowApiTests.headers
    create = fixtures.InfraAutomationWorkflowApiTests.create
    assert_error = fixtures.InfraAutomationWorkflowApiTests.assert_error
    path = "/api/v1/infra-automation/capabilities"

    def read(self, query="project_id=1&workspace_id=1", *, headers=None):
        return self.client.get(
            self.path + "?" + query,
            headers=self.headers() if headers is None else headers,
        )

    def test_roles_use_live_membership_not_global_admin_or_headers(self):
        expected = {
            "admin": [
                "automation.read",
                "automation.draft",
                "automation.publish",
                "automation.request",
            ],
            "maintainer": ["automation.read", "automation.draft", "automation.request"],
            "reviewer": ["automation.read"],
            "contributor": ["automation.read", "automation.request"],
            "read-only": ["automation.read"],
        }
        for role, capabilities in expected.items():
            with self.subTest(role=role):
                member = self.member(role)
                response = self.read(
                    headers=self.headers(**{"X-DeployWhisper-Project-Role": "admin"})
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(
                    response.json()["data"],
                    {
                        "version": 1,
                        "project_id": 1,
                        "workspace_id": 1,
                        "membership_version": member.authorization_version,
                        "policy_version": 0,
                        "execution_enabled": False,
                        "capabilities": capabilities,
                    },
                )
                for secret in (self.token, self.csrf, "synthetic-unused"):
                    self.assertNotIn(secret, response.text)

    def test_read_needs_no_csrf_and_cannot_authorize_a_mutation(self):
        headers = self.headers()
        headers.pop("X-CSRF-Token")
        response = self.read(headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        denied = self.client.post(
            "/api/v1/infra-automation/workflows",
            json={
                "project_id": 1,
                "workspace_id": 1,
                "name": "Denied",
                "definition": "{}",
                "reason": "Create",
            },
            headers=headers,
        )
        self.assert_error(denied, 403)
        self.member("read-only")
        self.assertEqual(
            self.read().json()["data"]["capabilities"], ["automation.read"]
        )
        self.assert_error(self.create(), 403)

    def test_project_admin_capabilities_do_not_require_global_admin(self):
        with self.factory.begin() as db:
            db.get(IdentityAccount, "human-a").is_admin = False
        response = self.read()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("automation.publish", response.json()["data"]["capabilities"])

    def test_exact_project_workspace_scope_and_missing_scope_are_generic(self):
        self.member("read-only", workspace=1)
        self.assertEqual(self.read().status_code, 200)
        for query in (
            "project_id=1",
            "project_id=1&workspace_id=2",
            "project_id=2&workspace_id=3",
            "project_id=999",
            "project_id=1&workspace_id=999",
            "project_id=1&workspace_id=3",
        ):
            with self.subTest(query=query):
                self.assert_error(self.read(query), 403)
        self.member("read-only")
        whole_project = self.read("project_id=1")
        self.assertEqual(whole_project.status_code, 200, whole_project.text)
        self.assertIsNone(whole_project.json()["data"]["workspace_id"])

    def test_unauthenticated_expired_disabled_and_bad_origin_fail_closed(self):
        self.assert_error(self.read(headers={"X-Actor": "admin"}), 401)
        self.assert_error(
            self.read(headers=self.headers(Origin="https://foreign.invalid")), 403
        )
        self.assert_error(
            self.read(headers=self.headers(Authorization="Bearer synthetic")), 401
        )
        with self.factory.begin() as db:
            account = db.get(IdentityAccount, "human-a")
            account.enabled = False
        self.assert_error(self.read(), 401)
        with self.factory.begin() as db:
            account = db.get(IdentityAccount, "human-a")
            account.enabled = True
            for session in db.query(IdentitySession):
                session.expires_at = self.now - timedelta(seconds=1)
        self.assert_error(self.read(), 401)

    def test_logged_out_session_denies_with_enabled_account_before_expiry(self):
        self.assertEqual(self.read().status_code, 200)
        self.service.logout(self.token, csrf_token=self.csrf)
        with self.factory() as db:
            self.assertTrue(db.get(IdentityAccount, "human-a").enabled)
            session = db.query(IdentitySession).one()
            self.assertIsNotNone(session.revoked_at)
            self.assertGreater(
                session.expires_at.replace(tzinfo=self.now.tzinfo), self.now
            )
        self.assert_error(self.read(), 401)

    def test_nonhuman_credentials_and_missing_membership_deny(self):
        for principal_type in ("service", "agent", "runner", "receiver"):
            token, _ = self.principal(
                principal_type, principal_type=principal_type, audience="human"
            )
            self.member("admin", principal=principal_type)
            with self.subTest(principal_type=principal_type):
                self.assert_error(
                    self.read(headers={"Cookie": f"__Host-dw-session={token}"}), 401
                )
        token, _ = self.principal("unassigned", is_admin=True)
        self.assert_error(
            self.read(headers={"Cookie": f"__Host-dw-session={token}"}), 403
        )

    def test_invalid_queries_do_not_reach_service(self):
        with patch.object(service, "get_capabilities", create=True) as operation:
            for query in (
                "",
                "project_id=0",
                "project_id=9007199254740992",
                "project_id=1&workspace_id=0",
                "project_id=1&workspace_id=1&workspace_id=2",
                "project_id=1&project_id=2",
                "project_id=1&role=admin",
            ):
                with self.subTest(query=query):
                    self.assert_error(self.read(query), 422)
            operation.assert_not_called()

    def test_malformed_service_data_is_not_reflected(self):
        with patch.object(
            service,
            "get_capabilities",
            return_value={"private": "synthetic-private"},
            create=True,
        ):
            response = self.read()
        self.assert_error(response, 503)
        self.assertNotIn("synthetic-private", response.text)

    def test_capabilities_are_unique_canonical_subsets_containing_read(self):
        value = self.read().json()["data"]
        for capabilities in (
            ["automation.read", "automation.read"],
            ["automation.request"],
            ["automation.request", "automation.read"],
            ["automation.read", "automation.publish", "automation.draft"],
        ):
            malformed = {**value, "capabilities": capabilities}
            with self.subTest(capabilities=capabilities):
                with self.assertRaises(ValidationError):
                    schemas.AutomationCapabilities.model_validate(malformed)
                with patch.object(service, "get_capabilities", return_value=malformed):
                    self.assert_error(self.read(), 503)

    def test_policy_storage_failure_returns_sanitized_503_without_partial_data(self):
        failure = OperationalError(
            "synthetic-private-storage", {}, RuntimeError("synthetic-private-cause")
        )
        with patch(
            "models.repositories.infra_automation_workflows.get_policy",
            side_effect=failure,
        ):
            response = self.read()
        self.assert_error(response, 503)
        self.assertNotIn("data", response.json())
        self.assertNotIn("synthetic-private", response.text)

    def test_openapi_closed_schema_and_strict_constructor(self):
        schema = self.app.openapi()
        self.assertIn(self.path, schema["paths"])
        for name in ("AutomationCapabilities", "AutomationCapabilitiesResponse"):
            self.assertFalse(
                schema["components"]["schemas"][name]["additionalProperties"]
            )
        value = self.read().json()["data"]
        for extra in (
            {"version": True},
            {"version": 2},
            {"execution_enabled": 1},
            {"capabilities": ["automation.admin"]},
            {"unexpected": "value"},
        ):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                schemas.AutomationCapabilities.model_validate({**value, **extra})


class PreflightCapabilitiesCompatibilityTests(unittest.TestCase):
    principal = fixtures.InfraAutomationWorkflowApiTests.principal
    member = fixtures.InfraAutomationWorkflowApiTests.member
    context = fixtures.InfraAutomationWorkflowApiTests.context
    setUp = preflight.InfraAutomationPreflightApiTests.setUp
    tearDown = fixtures.InfraAutomationWorkflowApiTests.tearDown
    headers = fixtures.InfraAutomationWorkflowApiTests.headers
    create = fixtures.InfraAutomationWorkflowApiTests.create
    assert_error = fixtures.InfraAutomationWorkflowApiTests.assert_error
    post = preflight.InfraAutomationPreflightApiTests.post
    counts = preflight.InfraAutomationPreflightApiTests.counts
    path = preflight.InfraAutomationPreflightApiTests.path

    def test_feature_disable_preserves_actual_16_6_reads_and_denies_cached_start(self):
        capabilities_path = (
            "/api/v1/infra-automation/capabilities?project_id=1&workspace_id=1"
        )
        before = self.client.get(capabilities_path, headers=self.headers())
        self.assertEqual(before.status_code, 200, before.text)
        self.assertTrue(before.json()["data"]["execution_enabled"])
        self.assertIn("automation.request", before.json()["data"]["capabilities"])
        admitted = self.post()
        self.assertEqual(admitted.status_code, 200, admitted.text)
        run_id = admitted.json()["data"]["id"]
        disabled = self.client.patch(
            "/api/v1/infra-automation/settings",
            json={
                "project_id": 1,
                "expected_version": 1,
                "settings": AutomationSettings(enabled=False).model_dump(),
                "reason": "Disable new preflights",
            },
            headers=self.headers(),
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.member("read-only", workspace=1)
        after = self.client.get(capabilities_path, headers=self.headers())
        self.assertEqual(after.status_code, 200, after.text)
        self.assertFalse(after.json()["data"]["execution_enabled"])
        self.assertEqual(after.json()["data"]["policy_version"], 2)
        for path in (
            "/api/v1/infra-automation/runs?project_id=1&workspace_id=1",
            f"/api/v1/infra-automation/runs/{run_id}",
            f"/api/v1/infra-automation/runs/{run_id}/reports",
        ):
            with self.subTest(path=path):
                response = self.client.get(path, headers=self.headers())
                self.assertEqual(response.status_code, 200, response.text)
        self.member("admin")
        self.payload["run"]["idempotency_key"] = "new-disabled-request"
        count = self.counts()
        self.assert_error(self.post(), 403)
        self.assertEqual(self.counts(), count)
