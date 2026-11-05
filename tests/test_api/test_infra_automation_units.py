"""Declared inventory HTTP boundaries use actual verified sessions and services."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from api.routes.infra_automation_units import router
from infra_automation.unit_contracts import (
    UnitRevisionView,
    UnitRunView,
    UnitValidation,
)
from tests.test_api import test_infra_automation_preflight as preflight
from tests.test_api import test_infra_automation_workflows as fixtures


class UnitApiTests(unittest.TestCase):
    principal = fixtures.InfraAutomationWorkflowApiTests.principal
    member = fixtures.InfraAutomationWorkflowApiTests.member
    context = fixtures.InfraAutomationWorkflowApiTests.context
    tearDown = fixtures.InfraAutomationWorkflowApiTests.tearDown
    headers = fixtures.InfraAutomationWorkflowApiTests.headers
    create = fixtures.InfraAutomationWorkflowApiTests.create
    assert_error = fixtures.InfraAutomationWorkflowApiTests.assert_error
    path = "/api/v1/infra-automation/units"

    def setUp(self):
        preflight.InfraAutomationPreflightApiTests.setUp(self)
        self.app.include_router(router)
        self.inventory = {
            "version": 1,
            "affected": ["app"],
            "units": [
                {
                    "id": "app",
                    "source": {"kind": "uploaded", "path": "."},
                    "environment": "test",
                    "target": "local",
                    "prerequisites": [],
                }
            ],
        }
        self.save_payload = {
            "project_id": 1,
            "workspace_id": 1,
            "expected_version": 0,
            "reason": "Declare exact scope",
            "map": self.inventory,
        }

    def save(self):
        response = self.client.post(
            self.path, json=self.save_payload, headers=self.headers()
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def test_actual_revision_roundtrip_and_schema(self):
        saved = self.save()
        UnitRevisionView.model_validate(saved)
        response = self.client.get(
            self.path + "?project_id=1&workspace_id=1", headers=self.headers()
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["data"]["items"][0]["revision_id"], saved["revision_id"]
        )
        response = self.client.get(
            self.path
            + f"/{saved['inventory_id']}/revisions/{saved['revision_id']}?project_id=1&workspace_id=1",
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"], saved)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_revision_history_keeps_superseded_saves_recoverable_and_scoped(self):
        first = self.save()
        for version in range(1, 32):
            self.save_payload.update(
                inventory_id=first["inventory_id"], expected_version=version
            )
            self.save()
        path = self.path + f"/{first['inventory_id']}/revisions"
        response = self.client.get(
            path + "?project_id=1&workspace_id=1", headers=self.headers()
        )
        self.assertEqual(response.status_code, 200, response.text)
        history = response.json()["data"]
        self.assertFalse(history["truncated"])
        self.assertEqual(
            [item["version"] for item in history["items"]], list(range(32, 0, -1))
        )
        self.assertEqual(history["items"][-1]["revision_id"], first["revision_id"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assert_error(
            self.client.get(
                path + "?project_id=2&workspace_id=3", headers=self.headers()
            ),
            403,
        )
        self.assert_error(
            self.client.get(
                path + "?project_id=1&workspace_id=2", headers=self.headers()
            ),
            403,
        )
        self.assert_error(self.client.get(path + "?project_id=1&workspace_id=1"), 401)
        self.assert_error(
            self.client.get(
                self.path + "/unavailable/revisions?project_id=1&workspace_id=1",
                headers=self.headers(),
            ),
            403,
        )
        self.member("read-only")
        self.assertEqual(
            self.client.get(
                path + "?project_id=1&workspace_id=1", headers=self.headers()
            ).status_code,
            200,
        )

    def test_validation_returns_located_nonreflective_errors(self):
        self.inventory["units"][0]["prerequisites"] = ["private-unknown-unit"]
        response = self.client.post(
            self.path + "/validate",
            json={"project_id": 1, "workspace_id": 1, "map": self.inventory},
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = UnitValidation.model_validate(response.json()["data"])
        self.assertFalse(result.valid)
        self.assertEqual(result.errors[0].path, ["units", 0, "prerequisites", 0])
        self.assertNotIn("private-unknown-unit", response.text)

    def test_run_admission_and_snapshot_use_actual_service(self):
        saved = self.save()
        request = {
            "run": self.payload["run"],
            "revision_id": saved["revision_id"],
            "confirmed_map_digest": saved["map_digest"],
            "bindings": [
                {
                    "unit_id": "app",
                    "intake_step_id": "intake",
                    "analysis_step_id": "analysis",
                    "artifacts": self.payload["artifacts"],
                }
            ],
        }
        response = self.client.post(
            self.path + "/runs", json=request, headers=self.headers()
        )
        self.assertEqual(response.status_code, 200, response.text)
        run_id = response.json()["data"]["id"]
        response = self.client.get(
            f"/api/v1/infra-automation/runs/{run_id}/units?project_id=1&workspace_id=1",
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = UnitRunView.model_validate(response.json()["data"])
        self.assertEqual(result.snapshot.revision.map_digest, saved["map_digest"])
        self.assertEqual(result.evidence.status, "pending")

    def test_authority_scope_and_csrf_deny(self):
        self.assert_error(
            self.client.get(self.path + "?project_id=1&workspace_id=1"), 401
        )
        self.assert_error(
            self.client.get(
                self.path + "?project_id=2&workspace_id=3", headers=self.headers()
            ),
            403,
        )
        headers = self.headers()
        headers.pop("X-CSRF-Token")
        self.assert_error(
            self.client.post(self.path, json=self.save_payload, headers=headers), 403
        )
        self.member("read-only")
        self.assert_error(
            self.client.post(self.path, json=self.save_payload, headers=self.headers()),
            403,
        )

    def test_wire_shape_size_and_duplicate_query_fail_without_service(self):
        with patch("api.routes.infra_automation_units.service.save_units") as save:
            for raw, status in [
                (b" " * 131073, 429),
                (b'{"private-secret":1,"private-secret":2}', 422),
                (b'{"project_id":true}', 422),
            ]:
                response = self.client.post(
                    self.path,
                    content=raw,
                    headers={**self.headers(), "Content-Type": "application/json"},
                )
                self.assert_error(response, status)
                self.assertNotIn("private-secret", response.text)
            save.assert_not_called()
        self.assert_error(
            self.client.get(
                self.path + "?project_id=1&project_id=1&workspace_id=1",
                headers=self.headers(),
            ),
            422,
        )

    def test_openapi_routes_use_closed_response_models(self):
        schema = self.app.openapi()
        base = "/api/v1/infra-automation"
        expected = {
            (base + "/units", "get"),
            (base + "/units", "post"),
            (base + "/units/validate", "post"),
            (base + "/units/{inventory_id}/revisions/{revision_id}", "get"),
            (base + "/units/{inventory_id}/revisions", "get"),
            (base + "/units/runs", "post"),
            (base + "/runs/{run_id}/units", "get"),
        }
        for path, method in expected:
            response = schema["paths"][path][method]["responses"]["200"]["content"][
                "application/json"
            ]["schema"]
            self.assertIn("$ref", response)
            model = schema["components"]["schemas"][response["$ref"].split("/")[-1]]
            self.assertFalse(model["additionalProperties"])
