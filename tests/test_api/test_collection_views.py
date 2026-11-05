"""Collection observation endpoints bind human identity and exact requested scope."""

from __future__ import annotations

import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes.infra_automation_collection_views import router
from tests.test_infra_automation import test_collection_intake as fixture


class CollectionViewsHttpTests(unittest.TestCase):
    def setUp(self):
        self.case = fixture.CollectionIntakeTests(
            "test_authenticated_complete_publishes_manifest_and_clears_staging"
        )
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.install_profile()
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app, base_url=self.case.origin)
        self.addCleanup(self.client.close)
        self.enterContext(
            patch("api.dependencies.identity_service", return_value=self.case.identity)
        )
        token, _ = self.case.tokens["human-a"]
        self.headers = {"cookie": "__Host-dw-session=" + token}
        self.url = "/api/v1/infra-automation/runs/" + self.case.run.id + "/collection"

    def test_authenticated_read_is_bounded_no_store_and_never_exposes_bearer(self):
        response = self.client.get(
            self.url + "?project_id=100&workspace_id=100", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertTrue(response.json()["data"]["cancellation"]["can_cancel"])
        self.assertNotIn(self.case.assignment["task_token"], response.text)
        self.assertNotIn(self.case.credential.token, response.text)

    def test_foreign_scope_missing_scope_and_unauthenticated_reads_deny(self):
        for query, headers, status in [
            ("?project_id=200&workspace_id=200", self.headers, 403),
            ("", self.headers, 422),
            ("?project_id=100&workspace_id=100", {}, 401),
        ]:
            with self.subTest(status=status):
                response = self.client.get(self.url + query, headers=headers)
                self.assertEqual(response.status_code, status)
                self.assertNotIn("synthetic-repo", response.text)

    def test_published_collection_readiness_uses_same_existing_session(self):
        response = self.client.get(
            "/api/v1/infra-automation/workflows/"
            + self.case.run.workflow_id
            + "/revisions/"
            + self.case.run.revision_id
            + "/collection?project_id=100&workspace_id=100",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["can_request"])
        self.assertEqual(response.json()["data"]["finite_wait_seconds"], 0)
