"""Closed human run HTTP contracts over isolated real engine persistence."""

from __future__ import annotations

import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from infra_automation.lifecycle import AutomationSettings
from services import infra_automation_service as service
from tests.test_api import test_infra_automation_workflows as workflow_tests


class AvailableHandlers:
    """Trusted server-side test catalog; admission does not execute work."""

    def get(self, kind):
        return object()


class InfraAutomationEngineApiTests(unittest.TestCase):
    principal = workflow_tests.InfraAutomationWorkflowApiTests.principal
    member = workflow_tests.InfraAutomationWorkflowApiTests.member
    context = workflow_tests.InfraAutomationWorkflowApiTests.context
    tearDown = workflow_tests.InfraAutomationWorkflowApiTests.tearDown
    headers = workflow_tests.InfraAutomationWorkflowApiTests.headers
    create = workflow_tests.InfraAutomationWorkflowApiTests.create
    assert_error = workflow_tests.InfraAutomationWorkflowApiTests.assert_error

    def setUp(self):
        workflow_tests.InfraAutomationWorkflowApiTests.setUp(self)
        self.patches.enter_context(
            patch(
                "infra_automation.local_workers.DEFAULT_REGISTRY", AvailableHandlers()
            )
        )
        workflow = self.create()
        self.assertEqual(workflow.status_code, 200, workflow.text)
        row = workflow.json()["data"]
        revision = self.client.post(
            f"/api/v1/infra-automation/workflows/{row['id']}/revisions",
            json={
                "expected_version": 1,
                "idempotency_key": "publish",
                "reason": "Publish fixture",
            },
            headers=self.headers(),
        )
        self.assertEqual(revision.status_code, 200, revision.text)
        enabled = self.client.patch(
            "/api/v1/infra-automation/settings",
            json={
                "project_id": 1,
                "expected_version": 0,
                "settings": AutomationSettings(enabled=True).model_dump(),
                "reason": "Enable fixture",
            },
            headers=self.headers(),
        )
        self.assertEqual(enabled.status_code, 200, enabled.text)
        self.payload = {
            "workflow_id": row["id"],
            "revision_id": revision.json()["data"]["id"],
            "workspace_id": 1,
            "inputs": {},
            "idempotency_key": "start-one",
            "reason": "Start synthetic work",
        }

    def admit(self, **updates):
        return self.client.post(
            "/api/v1/infra-automation/runs",
            json={**self.payload, **updates},
            headers=self.headers(),
        )

    def test_real_admission_replay_reads_and_closed_typed_openapi(self):
        admitted = self.admit()
        self.assertEqual(admitted.status_code, 200, admitted.text)
        run = admitted.json()["data"]
        self.assertEqual(run["state"], "queued")
        self.assertEqual(self.admit().json()["data"], run)
        self.assert_error(self.admit(reason="Changed request"), 409)
        detail = self.client.get(
            f"/api/v1/infra-automation/runs/{run['id']}", headers=self.headers()
        )
        self.assertEqual(detail.json()["data"], run)
        listing = self.client.get(
            "/api/v1/infra-automation/runs?project_id=1&workspace_id=1",
            headers=self.headers(),
        )
        self.assertEqual(
            [item["id"] for item in listing.json()["data"]["items"]], [run["id"]]
        )
        steps = self.client.get(
            f"/api/v1/infra-automation/runs/{run['id']}/steps", headers=self.headers()
        )
        self.assertEqual(steps.json()["data"]["items"], [])
        self.assertNotIn("owner_secret", json.dumps(admitted.json()))
        self.assertEqual(admitted.headers["cache-control"], "no-store")
        schemas = self.app.openapi()["components"]["schemas"]
        for name in (
            "RunRequest",
            "CancelRunRequest",
            "RunView",
            "RunPage",
            "StepPage",
            "LogPage",
            "AutomationRunResponse",
        ):
            self.assertFalse(schemas[name]["additionalProperties"])

    def test_closed_transport_identity_and_csrf_precede_admission(self):
        for update in (
            {"state": "running"},
            {"workspace_id": True},
            {"total_timeout_seconds": 3601},
        ):
            self.assert_error(self.admit(**update), 422)
        self.assert_error(
            self.client.post(
                "/api/v1/infra-automation/runs",
                json=self.payload,
                headers={"Origin": "https://identity.invalid"},
            ),
            401,
        )
        headers = self.headers()
        headers.pop("X-CSRF-Token")
        self.assert_error(
            self.client.post(
                "/api/v1/infra-automation/runs", json=self.payload, headers=headers
            ),
            403,
        )
        self.member("read-only")
        self.assert_error(self.admit(), 403)

    def test_cursor_and_log_queries_are_closed_and_current_scope_is_live(self):
        run = self.admit().json()["data"]
        for suffix in (
            "?project_id=1&limit=101",
            "?project_id=1&actor=admin",
            "?project_id=1&cursor=bad%2Fcursor",
        ):
            self.assert_error(
                self.client.get(
                    "/api/v1/infra-automation/runs" + suffix, headers=self.headers()
                ),
                409 if "cursor" in suffix else 422,
            )
        log_path = f"/api/v1/infra-automation/runs/{run['id']}/logs"
        self.assert_error(self.client.get(log_path, headers=self.headers()), 422)
        self.assert_error(
            self.client.get(log_path + "?attempt_id=missing", headers=self.headers()),
            403,
        )
        self.member("read-only", workspace=2)
        self.assert_error(
            self.client.get(
                f"/api/v1/infra-automation/runs/{run['id']}", headers=self.headers()
            ),
            403,
        )

    def test_cancel_route_passes_owned_coordinator_port_and_closed_payload(self):
        run = self.admit().json()["data"]
        port = Mock()
        self.app.state.infra_automation_coordinator = SimpleNamespace(cancel_run=port)
        path = f"/api/v1/infra-automation/runs/{run['id']}/cancel"
        with patch.object(service, "cancel_run", return_value=run) as cancel:
            response = self.client.post(
                path,
                json={"expected_version": run["version"], "reason": "Cancel fixture"},
                headers=self.headers(),
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIs(cancel.call_args.kwargs["cancel_port"], port)
            self.assertEqual(cancel.call_args.args[0], run["id"])
            self.assert_error(
                self.client.post(
                    path,
                    json={"expected_version": 1, "reason": "Cancel", "pid": 123},
                    headers=self.headers(),
                ),
                422,
            )
            self.assertEqual(cancel.call_count, 1)

    def test_audit_response_retains_real_service_actor(self):
        from infra_automation import claims
        from services import project_service as authorization

        self.admit()
        with authorization.authorized_session(self.factory) as session:
            claims.acquire_coordinator(session, project_id=1, workspace_id=1)
        response = self.client.get(
            "/api/v1/infra-automation/audit?project_id=1", headers=self.headers()
        )
        self.assertEqual(response.status_code, 200, response.text)
        events = [
            item
            for item in response.json()["data"]["items"]
            if item["actor_type"] == "service"
        ]
        self.assertTrue(events)
        self.assertEqual({item["actor_role"] for item in events}, {"coordinator"})

    def test_real_cancel_enforces_ownership_and_replays_durable_receipt(self):
        run = self.admit().json()["data"]
        path = f"/api/v1/infra-automation/runs/{run['id']}/cancel"
        payload = {
            "expected_version": run["version"],
            "reason": "Cancel queued fixture",
        }
        token, csrf = self.principal("human-b")
        self.member("maintainer", principal="human-b")
        self.assert_error(
            self.client.post(
                path,
                json=payload,
                headers=self.headers(
                    Cookie=f"__Host-dw-session={token}", **{"X-CSRF-Token": csrf}
                ),
            ),
            403,
        )
        cancelled = self.client.post(path, json=payload, headers=self.headers())
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["data"]["state"], "cancelled")
        self.assertTrue(cancelled.json()["data"]["cancel_requested"])
        replay = self.client.post(path, json=payload, headers=self.headers())
        self.assertEqual(replay.json()["data"], cancelled.json()["data"])
        self.assert_error(
            self.client.post(
                path,
                json={**payload, "reason": "Changed cancellation"},
                headers=self.headers(),
            ),
            409,
        )

    def test_response_validation_never_exposes_untyped_service_output(self):
        with patch.object(service, "get_run", return_value={"private": "secret-value"}):
            response = self.client.get(
                "/api/v1/infra-automation/runs/missing", headers=self.headers()
            )
        self.assert_error(response, 503)
        self.assertNotIn("secret-value", response.text)
