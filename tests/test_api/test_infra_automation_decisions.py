"""Decision HTTP admission rejects untrusted actors and closed-body bypasses."""

from __future__ import annotations

import unittest

from tests.test_api import test_infra_automation_workflows as fixtures


class InfraAutomationDecisionApiTests(unittest.TestCase):
    principal = fixtures.InfraAutomationWorkflowApiTests.principal
    member = fixtures.InfraAutomationWorkflowApiTests.member
    context = fixtures.InfraAutomationWorkflowApiTests.context
    setUp = fixtures.InfraAutomationWorkflowApiTests.setUp
    tearDown = fixtures.InfraAutomationWorkflowApiTests.tearDown
    headers = fixtures.InfraAutomationWorkflowApiTests.headers
    assert_error = fixtures.InfraAutomationWorkflowApiTests.assert_error

    def test_approval_reads_require_verified_scope_and_return_empty_page(self):
        path = "/api/v1/infra-automation/approvals?project_id=1&workspace_id=1"
        self.assert_error(self.client.get(path), 401)
        response = self.client.get(path, headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["items"], [])
        self.assertIsNone(response.json()["data"]["cursor"]["next_cursor"])
        self.assert_error(
            self.client.get(path + "&actor=admin", headers=self.headers()), 422
        )

    def test_decision_has_no_bypass_or_client_authority_fields(self):
        path = "/api/v1/infra-automation/approvals/missing/decision"
        body = {
            "expected_version": 1,
            "binding_digest": "sha256:" + "0" * 64,
            "outcome": "approve",
            "reason": "Review current evidence",
        }
        self.assert_error(
            self.client.post(
                path, json=body, headers={"Origin": "https://identity.invalid"}
            ),
            401,
        )
        self.assert_error(
            self.client.post(path, json=body, headers=self.headers()), 403
        )
        for name in (
            "requester",
            "reviewer",
            "role",
            "emergency",
            "delegated",
            "authorization_kind",
            "decision_kind",
        ):
            with self.subTest(name=name):
                self.assert_error(
                    self.client.post(
                        path, json={**body, name: "admin"}, headers=self.headers()
                    ),
                    422,
                )

    def test_decision_body_is_strict_and_csrf_is_required(self):
        path = "/api/v1/infra-automation/approvals/missing/decision"
        body = {
            "expected_version": 1,
            "binding_digest": "sha256:" + "0" * 64,
            "outcome": "approve",
            "reason": "Review current evidence",
        }
        for outcome in ("autoapprove", "acknowledgement", "delegate", "bypass"):
            self.assert_error(
                self.client.post(
                    path, json={**body, "outcome": outcome}, headers=self.headers()
                ),
                422,
            )
        self.assert_error(
            self.client.post(
                path, json={**body, "expected_version": True}, headers=self.headers()
            ),
            422,
        )
