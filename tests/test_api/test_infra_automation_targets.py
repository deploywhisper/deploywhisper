"""Registered target HTTP boundaries use actual verified sessions and scopes."""

from __future__ import annotations

import unittest

from tests.test_api import test_infra_automation_workflows as fixtures
from tests.test_infra_automation.test_target_contracts import definition_payload


class InfraAutomationTargetApiTests(unittest.TestCase):
    member = fixtures.InfraAutomationWorkflowApiTests.member
    principal = fixtures.InfraAutomationWorkflowApiTests.principal
    context = fixtures.InfraAutomationWorkflowApiTests.context
    headers = fixtures.InfraAutomationWorkflowApiTests.headers
    assert_error = fixtures.InfraAutomationWorkflowApiTests.assert_error
    tearDown = fixtures.InfraAutomationWorkflowApiTests.tearDown

    def setUp(self):
        fixtures.InfraAutomationWorkflowApiTests.setUp(self)
        self.member("admin", project=2)
        self.body = dict(
            project_id=1,
            workspace_id=1,
            expected_version=0,
            definition=definition_payload(),
            reason="Register owned receiver destination",
        )

    def test_registry_requires_verified_global_admin_and_csrf(self):
        path = "/api/v1/infra-automation/targets"
        self.assert_error(
            self.client.post(
                path, json=self.body, headers={"Origin": "https://identity.invalid"}
            ),
            401,
        )
        self.assert_error(
            self.client.post(
                path, json=self.body, headers=self.headers(**{"X-CSRF-Token": "wrong"})
            ),
            403,
        )
        self.member("reviewer")
        self.assert_error(
            self.client.post(
                path,
                json=self.body,
                headers=self.headers(**{"X-Actor": "admin", "X-Role": "admin"}),
            ),
            403,
        )

    def test_typed_registry_creation_list_read_and_cas(self):
        path = "/api/v1/infra-automation/targets"
        response = self.client.post(path, json=self.body, headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual((data["id"], data["epoch"]), ("target", 1))
        self.assertEqual(response.headers["cache-control"], "no-store")
        response = self.client.get(
            path + "?project_id=1&workspace_id=1", headers=self.headers()
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["data"]["items"]), 1)
        response = self.client.get(
            path + "/alias?project_id=1&workspace_id=1", headers=self.headers()
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assert_error(
            self.client.get(
                path + "/alias?project_id=1&workspace_id=2", headers=self.headers()
            ),
            403,
        )
        self.assert_error(
            self.client.post(path, json=self.body, headers=self.headers()), 409
        )

    def test_closed_registry_input_does_not_accept_credentials_or_bypass(self):
        path = "/api/v1/infra-automation/targets"
        for change in (
            {"version": True},
            {"expected_version": False},
            {"role": "admin"},
            {"secret": "sensitive"},
        ):
            with self.subTest(change=change):
                self.assert_error(
                    self.client.post(
                        path, json={**self.body, **change}, headers=self.headers()
                    ),
                    422,
                )
        self.assert_error(
            self.client.post(
                path,
                json={
                    **self.body,
                    "definition": {
                        **self.body["definition"],
                        "api_origin": "http://127.0.0.1",
                    },
                },
                headers=self.headers(),
            ),
            422,
        )
