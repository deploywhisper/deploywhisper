"""Workflow HTTP contract, bounded transport and live human authority."""

from __future__ import annotations

from contextlib import ExitStack
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import config
from api.routes import infra_automation as routes
from api.schemas import AutomationDiagnostic
from infra_automation.lifecycle import AutomationSettings, LifecycleError
from services import infra_automation_service as service
from services import project_service as authorization
from tests.test_services import test_project_authorization as fixtures


class InfraAutomationWorkflowApiTests(unittest.TestCase):
    def test_validation_diagnostics_keep_the_closed_v2_vocabulary_and_message_bound(
        self,
    ):
        values = {
            "code": "schema_field",
            "message": "Definition does not satisfy the closed workflow schema.",
            "path": [],
        }
        for extra in ({"code": "unregistered_code"}, {"message": "x" * 161}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                AutomationDiagnostic.model_validate({**values, **extra})

    principal = fixtures.ProjectAuthorizationTests.principal
    member = fixtures.ProjectAuthorizationTests.member
    context = fixtures.ProjectAuthorizationTests.context
    tearDown = fixtures.ProjectAuthorizationTests.tearDown

    def setUp(self):
        fixtures.ProjectAuthorizationTests.setUp(self)
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(
            patch.object(service, "SessionLocal", self.factory, create=True)
        )
        self.patches.enter_context(
            patch("api.dependencies.identity_service", return_value=self.service)
        )
        config.settings.identity_profile = "https"
        config.settings.identity_origin = "https://identity.invalid"
        app = FastAPI()
        app.include_router(routes.router)
        self.app = app
        self.client = TestClient(app, base_url="https://identity.invalid")
        self.addCleanup(self.client.close)
        self.member("admin")
        self.definition = {
            "workflow_version": 2,
            "project_id": "1",
            "workspace_id": "1",
            "environment": "test",
            "steps": [
                {
                    "id": "intake",
                    "kind": "uploaded_intake",
                    "depends_on": [],
                    "source": {"kind": "uploaded"},
                }
            ],
        }

    def headers(self, **extra):
        return {
            "Cookie": f"__Host-dw-session={self.token}",
            "Origin": "https://identity.invalid",
            "X-CSRF-Token": self.csrf,
            **extra,
        }

    def create(self):
        return self.client.post(
            "/api/v1/infra-automation/workflows",
            json={
                "project_id": 1,
                "workspace_id": 1,
                "name": "HTTP fixture",
                "definition": json.dumps(self.definition),
                "reason": "Create fixture",
            },
            headers=self.headers(),
        )

    def assert_error(self, response, status):
        expected = LifecycleError(status)
        self.assertEqual(response.status_code, status, response.text)
        error = response.json()["error"]
        self.assertEqual(error["code"], expected.code)
        self.assertEqual(error["message"], expected.message)
        self.assertEqual(set(error["details"]), {"retryable", "correlation_id"})
        self.assertEqual(error["details"]["retryable"], expected.retryable)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_large_valid_workflow_uses_exact_response_ceiling_and_rolls_back_overflow(
        self,
    ):
        ids = [f"s{i:02d}" + "x" * 85 for i in range(50)]
        self.definition["steps"] = [
            {
                "id": step_id,
                "kind": "uploaded_intake",
                "depends_on": ids[:index],
                "source": {"kind": "uploaded"},
            }
            for index, step_id in enumerate(ids)
        ]
        created = self.create()
        self.assertEqual(created.status_code, 200, created.text)
        self.assertGreater(len(created.content), 130000)
        self.assertLess(len(created.content), 131072)
        path = "/api/v1/infra-automation/workflows/" + created.json()["data"]["id"]
        saved = self.client.put(
            path + "/draft",
            json={
                "expected_version": 1,
                "definition": json.dumps(self.definition),
                "reason": "Save large draft",
            },
            headers=self.headers(),
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        published = self.client.post(
            path + "/revisions",
            json={
                "expected_version": 2,
                "idempotency_key": "large",
                "reason": "Publish",
            },
            headers=self.headers(),
        )
        self.assertEqual(published.status_code, 200, published.text)
        for url in (path, path + "/revisions/" + published.json()["data"]["id"]):
            response = self.client.get(url, headers=self.headers())
            self.assertEqual(response.status_code, 200, response.text)
            self.assertLessEqual(len(response.content), 131072)

        # Calibrate a scalar default against the actual HTTP envelope, including
        # model defaults and metadata, then exercise both sides of the wire limit.
        candidate = created.json()
        padding = {
            "type": "string",
            "required": False,
            "default": "",
            "max_length": 1024,
        }
        candidate["data"]["definition"]["inputs"] = {"padding": padding}
        size = len(
            json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode()
        )
        self.assertTrue(0 < 131072 - size < 1024)
        padding["default"] = "x" * (131072 - size)
        self.definition["inputs"] = {"padding": padding}
        exact = self.create()
        self.assertEqual(exact.status_code, 200, exact.text)
        self.assertEqual(len(exact.content), 131072)
        audit_path = "/api/v1/infra-automation/audit?project_id=1"
        before = self.client.get(audit_path, headers=self.headers()).json()["data"][
            "items"
        ]
        padding["default"] += "x"
        self.assert_error(self.create(), 429)
        after = self.client.get(audit_path, headers=self.headers()).json()["data"][
            "items"
        ]
        self.assertEqual(after, before)
        workflows = self.client.get(
            "/api/v1/infra-automation/workflows?project_id=1", headers=self.headers()
        )
        self.assertEqual(len(workflows.json()["data"]["items"]), 2)

        exact_path = "/api/v1/infra-automation/workflows/" + exact.json()["data"]["id"]
        for version in range(1, 9):
            published = self.client.post(
                exact_path + "/revisions",
                json={
                    "expected_version": version,
                    "idempotency_key": f"exact-{version}",
                    "reason": "Publish exact-limit draft",
                },
                headers=self.headers(),
            )
            self.assertEqual(published.status_code, 200, published.text)
        before = self.client.get(audit_path, headers=self.headers()).json()["data"][
            "items"
        ]
        rejected = self.client.post(
            exact_path + "/revisions",
            json={
                "expected_version": 9,
                "idempotency_key": "exact-9",
                "reason": "Publish",
            },
            headers=self.headers(),
        )
        self.assert_error(rejected, 429)
        unchanged = self.client.get(exact_path, headers=self.headers())
        self.assertEqual(unchanged.status_code, 200, unchanged.text)
        self.assertEqual(unchanged.json()["data"]["draft_version"], 9)
        self.assertEqual(len(unchanged.content), 131072)
        revisions = self.client.get(exact_path + "/revisions", headers=self.headers())
        self.assertEqual(len(revisions.json()["data"]["items"]), 8)
        after = self.client.get(audit_path, headers=self.headers()).json()["data"][
            "items"
        ]
        self.assertEqual(after, before)

    def test_settings_response_ceiling_checks_reads_noops_and_rolls_back_mutations(
        self,
    ):
        large_metadata = SimpleNamespace(
            **{**vars(config.settings), "app_name": "a" * 131000}
        )
        path = "/api/v1/infra-automation/settings"
        audit_path = "/api/v1/infra-automation/audit?project_id=1"
        payload = {
            "project_id": 1,
            "expected_version": 0,
            "settings": AutomationSettings(enabled=True).model_dump(),
            "reason": "Enable fixture",
        }
        with patch("api.schemas.settings", large_metadata):
            self.assert_error(
                self.client.patch(path, json=payload, headers=self.headers()), 429
            )
        initial = self.client.get(path + "?project_id=1", headers=self.headers())
        self.assertEqual(initial.json()["data"]["version"], 0)
        self.assertEqual(
            self.client.get(audit_path, headers=self.headers()).json()["data"]["items"],
            [],
        )

        configured = self.client.patch(path, json=payload, headers=self.headers())
        self.assertEqual(configured.status_code, 200, configured.text)
        expected = configured.json()["data"]
        audit = self.client.get(audit_path, headers=self.headers()).json()["data"][
            "items"
        ]
        payload["expected_version"] = 1
        requests = [
            ("GET", path + "?project_id=1", None),
            ("PATCH", path, payload),
            (
                "PATCH",
                path,
                {**payload, "settings": AutomationSettings(enabled=False).model_dump()},
            ),
            *[
                (
                    "POST",
                    path + "/" + action,
                    {"project_id": 1, "expected_version": 1, "reason": "Invalidate"},
                )
                for action in ("revoke", "restore-epoch")
            ],
        ]
        for method, url, body in requests:
            with (
                self.subTest(method=method, url=url),
                patch("api.schemas.settings", large_metadata),
            ):
                response = self.client.request(
                    method, url, json=body, headers=self.headers()
                )
                self.assert_error(response, 429)
            self.assertEqual(
                self.client.get(path + "?project_id=1", headers=self.headers()).json()[
                    "data"
                ],
                expected,
            )
            self.assertEqual(
                self.client.get(audit_path, headers=self.headers()).json()["data"][
                    "items"
                ],
                audit,
            )

    def test_success_responses_include_fresh_nonsecret_correlation_ids(self):
        created = self.create()
        self.assertEqual(created.status_code, 200, created.text)
        first = created.json()["meta"]["correlation_id"]
        response = self.client.get(
            "/api/v1/infra-automation/workflows/" + created.json()["data"]["id"],
            headers=self.headers(),
        )
        second = response.json()["meta"]["correlation_id"]
        self.assertRegex(first, r"^[0-9a-f]{32}$")
        self.assertRegex(second, r"^[0-9a-f]{32}$")
        self.assertNotEqual(first, second)
        self.assertNotIn(self.token, (first, second))

    def test_live_authorization_exception_rebinding_preserves_forbidden_response(self):
        class ReloadedDenial(PermissionError):
            status_code = 403

        self.member("read-only")
        with patch.object(authorization, "TrustedAuthorizationError", ReloadedDenial):
            self.assert_error(self.create(), 403)

    def test_transport_rejects_before_service_and_does_not_echo(self):
        marker = "SENSITIVE_BOUNDARY_MARKER"
        cases = [
            ('{"project_id":1,"project_id":2}', 422),
            ('{"nested":' + "[" * 16 + "0" + "]" * 16 + "}", 422),
            ('{"project_id":NaN}', 422),
            ('{"project_id":1e999}', 422),
            ('{"project_id":9007199254740992}', 422),
            ('{"project_id":true,"definition":"' + marker + '"}', 422),
            (json.dumps({"unknown_" + marker: marker}), 422),
            ('{"value":"' + "x" * 131072 + '"}', 429),
            ('{"definition":"\\ud800"}', 422),
        ]
        with patch.object(service, "create_workflow") as create:
            for body, status in cases:
                with self.subTest(body=body[:40]):
                    response = self.client.post(
                        "/api/v1/infra-automation/workflows",
                        content=body,
                        headers=self.headers(**{"Content-Type": "application/json"}),
                    )
                    self.assert_error(response, status)
                    self.assertNotIn(marker, response.text)
            create.assert_not_called()

    def test_stream_limit_ignores_claimed_content_length(self):
        with patch.object(service, "create_workflow") as create:
            response = self.client.post(
                "/api/v1/infra-automation/workflows",
                content=iter([b'{"definition":"', b"x" * 65536, b"x" * 65536, b'"}']),
                headers=self.headers(
                    **{"Content-Type": "application/json", "Content-Length": "1"}
                ),
            )
            self.assert_error(response, 429)
            create.assert_not_called()

    def test_identity_failures_are_frozen_and_never_trust_actor_headers(self):
        url = "/api/v1/infra-automation/workflows?project_id=1"
        with patch.object(service, "list_workflows") as listing:
            self.assert_error(
                self.client.get(
                    url,
                    headers={
                        "X-Actor": "admin",
                        "X-DeployWhisper-Project-Role": "admin",
                    },
                ),
                401,
            )
            self.assert_error(
                self.client.get(
                    url, headers=self.headers(Authorization="Bearer synthetic-machine")
                ),
                401,
            )
            listing.assert_not_called()
        response = self.client.post(
            "/api/v1/infra-automation/workflows/validate",
            json={"project_id": 1, "definition": "{}"},
            headers={
                "Cookie": f"__Host-dw-session={self.token}",
                "Origin": "https://identity.invalid",
            },
        )
        self.assert_error(response, 403)
        for audience in ("service", "agent", "runner", "receiver"):
            token, csrf = self.principal(
                "synthetic-" + audience, principal_type=audience, audience=audience
            )
            self.assert_error(
                self.client.get(
                    url,
                    headers={
                        **self.headers(),
                        "Cookie": f"__Host-dw-session={token}",
                        "X-CSRF-Token": csrf,
                    },
                ),
                401,
            )

    def test_live_scope_and_capability_checks_apply_to_real_service(self):
        self.member("read-only")
        self.assert_error(self.create(), 403)
        self.member("maintainer", workspace=1)
        other = {**self.definition, "workspace_id": "2"}
        self.assert_error(
            self.client.post(
                "/api/v1/infra-automation/workflows",
                json={
                    "project_id": 1,
                    "workspace_id": 2,
                    "name": "Hidden",
                    "definition": json.dumps(other),
                    "reason": "Denied",
                },
                headers=self.headers(),
            ),
            403,
        )
        created = self.create()
        self.assertEqual(created.status_code, 200, created.text)
        workflow_id = created.json()["data"]["id"]
        self.assert_error(
            self.client.post(
                f"/api/v1/infra-automation/workflows/{workflow_id}/revisions",
                json={
                    "expected_version": 1,
                    "idempotency_key": "publish-one",
                    "reason": "Denied",
                },
                headers=self.headers(),
            ),
            403,
        )
        self.member("admin")
        self.assertEqual(
            self.client.get(
                f"/api/v1/infra-automation/workflows/{workflow_id}",
                headers=self.headers(),
            ).status_code,
            200,
        )
        self.member("read-only", project=2)
        self.assert_error(
            self.client.get(
                "/api/v1/infra-automation/workflows?project_id=3",
                headers=self.headers(),
            ),
            403,
        )
        self.assert_error(
            self.client.get(
                "/api/v1/infra-automation/workflows/nonexistent", headers=self.headers()
            ),
            403,
        )

    def test_publish_restore_history_settings_and_audit(self):
        created = self.create()
        self.assertEqual(created.status_code, 200, created.text)
        row = created.json()["data"]
        base = f"/api/v1/infra-automation/workflows/{row['id']}"
        payload = {
            "expected_version": row["draft_version"],
            "idempotency_key": "publish-one",
            "reason": "Reviewed fixture",
        }
        published = self.client.post(
            base + "/revisions", json=payload, headers=self.headers()
        )
        self.assertEqual(published.status_code, 200, published.text)
        revision = published.json()["data"]
        replay = self.client.post(
            base + "/revisions", json=payload, headers=self.headers()
        )
        self.assertEqual(replay.json()["data"], revision)
        self.assert_error(
            self.client.post(
                base + "/revisions",
                json={**payload, "reason": "Different"},
                headers=self.headers(),
            ),
            409,
        )
        detail = self.client.get(base, headers=self.headers()).json()["data"]
        archived = self.client.post(
            base + "/archive",
            json={
                "expected_version": detail["draft_version"],
                "reason": "Pause fixture",
            },
            headers=self.headers(),
        )
        self.assertEqual(archived.status_code, 200, archived.text)
        restored = self.client.post(
            base + "/restore",
            json={
                "expected_version": archived.json()["data"]["draft_version"],
                "revision_id": revision["id"],
                "reason": "Restore reviewed fixture",
            },
            headers=self.headers(),
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertFalse(restored.json()["data"]["archived"])
        history = self.client.get(base + "/revisions", headers=self.headers())
        self.assertEqual(history.json()["data"]["items"][0]["id"], revision["id"])
        immutable = self.client.get(
            base + "/revisions/" + revision["id"], headers=self.headers()
        )
        self.assertEqual(immutable.json()["data"], revision)
        settings_response = self.client.get(
            "/api/v1/infra-automation/settings?project_id=1", headers=self.headers()
        )
        self.assertEqual(settings_response.status_code, 200, settings_response.text)
        settings = settings_response.json()["data"]
        updated = self.client.patch(
            "/api/v1/infra-automation/settings",
            json={
                "project_id": 1,
                "expected_version": settings["version"],
                "settings": AutomationSettings(enabled=True).model_dump(),
                "reason": "Enable fixture",
            },
            headers=self.headers(),
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        for endpoint in ("revoke", "restore-epoch"):
            prior = updated.json()["data"]
            updated = self.client.post(
                "/api/v1/infra-automation/settings/" + endpoint,
                json={
                    "project_id": 1,
                    "expected_version": prior["version"],
                    "reason": "Advance fixture",
                },
                headers=self.headers(),
            )
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertGreater(
                updated.json()["data"]["authorization_epoch"],
                prior["authorization_epoch"],
            )
        audit = self.client.get(
            "/api/v1/infra-automation/audit?project_id=1", headers=self.headers()
        )
        self.assertEqual(audit.status_code, 200, audit.text)
        self.assertGreaterEqual(len(audit.json()["data"]["items"]), 6)
        self.assertNotIn('"definition"', audit.text)

    def test_draft_save_and_validation_keep_publication_immutable(self):
        created = self.create()
        self.assertEqual(created.status_code, 200, created.text)
        row = created.json()["data"]
        base = f"/api/v1/infra-automation/workflows/{row['id']}"
        published = self.client.post(
            base + "/revisions",
            json={
                "expected_version": row["draft_version"],
                "idempotency_key": "immutable-fixture",
                "reason": "Publish fixture",
            },
            headers=self.headers(),
        )
        self.assertEqual(published.status_code, 200, published.text)
        revision = published.json()["data"]
        current = self.client.get(base, headers=self.headers()).json()["data"]
        candidate = {**self.definition, "environment": "staging"}
        validated = self.client.post(
            base + "/validate",
            json={
                "expected_version": current["draft_version"],
                "definition": json.dumps(candidate),
            },
            headers=self.headers(),
        )
        self.assertEqual(validated.status_code, 200, validated.text)
        self.assertTrue(validated.json()["data"]["valid"])
        self.assertEqual(
            self.client.get(base, headers=self.headers()).json()["data"], current
        )
        saved = self.client.put(
            base + "/draft",
            json={
                "expected_version": current["draft_version"],
                "definition": json.dumps(candidate),
                "reason": "Edit candidate",
            },
            headers=self.headers(),
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertGreater(
            saved.json()["data"]["draft_version"], current["draft_version"]
        )
        self.assertEqual(
            self.client.get(
                base + "/revisions/" + revision["id"], headers=self.headers()
            ).json()["data"],
            revision,
        )
        self.assert_error(
            self.client.post(
                base + "/validate",
                json={"expected_version": current["draft_version"]},
                headers=self.headers(),
            ),
            409,
        )
        listing = self.client.get(
            "/api/v1/infra-automation/workflows?project_id=1&workspace_id=1",
            headers=self.headers(),
        )
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertEqual(
            [item["id"] for item in listing.json()["data"]["items"]], [row["id"]]
        )
        self.assertNotIn("definition", listing.json()["data"]["items"][0])

    def test_validation_errors_are_success_data_not_error_details(self):
        response = self.client.post(
            "/api/v1/infra-automation/workflows/validate",
            json={
                "project_id": 1,
                "workspace_id": 1,
                "definition": '{"sensitive-unknown-key":"private-value"}',
            },
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["data"]["valid"])
        self.assertTrue(response.json()["data"]["errors"])
        self.assertNotIn("sensitive-unknown-key", response.text)
        self.assertNotIn("private-value", response.text)
        self.assertNotIn("error", response.json())

    def test_query_duplicate_unknown_and_bounds_never_reach_service(self):
        with patch.object(service, "list_workflows") as listing:
            for query in (
                "project_id=1&project_id=2",
                "project_id=1&actor=admin",
                "project_id=1&limit=101",
                "project_id=1&workspace_id=0",
            ):
                self.assert_error(
                    self.client.get(
                        "/api/v1/infra-automation/workflows?" + query,
                        headers=self.headers(),
                    ),
                    422,
                )
            for cursor in ("", "bad%2Ftoken", "x" * 129):
                self.assert_error(
                    self.client.get(
                        "/api/v1/infra-automation/workflows?project_id=1&cursor="
                        + cursor,
                        headers=self.headers(),
                    ),
                    409,
                )
            listing.assert_not_called()

    def test_service_errors_are_nonreflective_and_response_models_are_closed(self):
        for status in (401, 403, 409, 422, 429, 503):
            with patch.object(
                service, "get_settings", side_effect=LifecycleError(status)
            ):
                self.assert_error(
                    self.client.get(
                        "/api/v1/infra-automation/settings?project_id=1",
                        headers=self.headers(),
                    ),
                    status,
                )
        with patch.object(
            service, "get_settings", return_value={"private": "secret-value"}
        ):
            response = self.client.get(
                "/api/v1/infra-automation/settings?project_id=1", headers=self.headers()
            )
            self.assert_error(response, 503)
            self.assertNotIn("secret-value", response.text)

    def test_openapi_has_closed_authoring_and_engine_contract_without_runner_transport(
        self,
    ):
        from app import create_app

        schema = self.app.openapi()
        production_paths = create_app().openapi()["paths"]
        self.assertTrue(set(schema["paths"]).issubset(production_paths))
        components = schema["components"]["schemas"]
        for name in (
            "CreateWorkflowRequest",
            "SaveDraftRequest",
            "AutomationWorkflowResponse",
            "AutomationWorkflowDetail",
            "AutomationPolicyResponse",
        ):
            self.assertFalse(components[name]["additionalProperties"])
        for path, methods in schema["paths"].items():
            self.assertNotIn("/runners", path)
            self.assertNotIn("/handoffs", path)
            for operation in methods.values():
                response = operation["responses"]["200"]["content"]["application/json"][
                    "schema"
                ]
                self.assertIn("$ref", response)
        for reference in components["AutomationWorkflowDetail"]["properties"].values():
            self.assertNotIn("additionalProperties", reference)
