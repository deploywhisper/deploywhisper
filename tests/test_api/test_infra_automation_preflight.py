"""Authenticated upload admission, bounded transport and report-link reads."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from sqlalchemy import func, select

from api.routes import infra_automation as routes
from infra_automation.lifecycle import AutomationSettings
from models.tables import (
    AnalysisReport,
    InfraAutomationArtifactManifest,
    InfraAutomationReportLink,
    InfraAutomationRun,
)
from tests.test_api import test_infra_automation_workflows as fixtures


class InfraAutomationPreflightApiTests(unittest.TestCase):
    principal = fixtures.InfraAutomationWorkflowApiTests.principal
    member = fixtures.InfraAutomationWorkflowApiTests.member
    context = fixtures.InfraAutomationWorkflowApiTests.context
    tearDown = fixtures.InfraAutomationWorkflowApiTests.tearDown
    headers = fixtures.InfraAutomationWorkflowApiTests.headers
    create = fixtures.InfraAutomationWorkflowApiTests.create
    assert_error = fixtures.InfraAutomationWorkflowApiTests.assert_error
    path = "/api/v1/infra-automation/preflights"

    def setUp(self):
        fixtures.InfraAutomationWorkflowApiTests.setUp(self)
        self.definition["steps"].append(
            {
                "id": "analysis",
                "kind": "shared_analysis",
                "depends_on": ["intake"],
                "artifact": {
                    "ref": "step",
                    "step_id": "intake",
                    "output": "screened_artifacts",
                },
            }
        )
        created = self.create()
        self.assertEqual(created.status_code, 200, created.text)
        workflow = created.json()["data"]
        published = self.client.post(
            f"/api/v1/infra-automation/workflows/{workflow['id']}/revisions",
            json={
                "expected_version": workflow["draft_version"],
                "idempotency_key": "preflight-publication",
                "reason": "Publish synthetic upload workflow",
            },
            headers=self.headers(),
        )
        self.assertEqual(published.status_code, 200, published.text)
        enabled = self.client.patch(
            "/api/v1/infra-automation/settings",
            json={
                "project_id": 1,
                "expected_version": 0,
                "settings": AutomationSettings(enabled=True).model_dump(),
                "reason": "Enable synthetic preflight",
            },
            headers=self.headers(),
        )
        self.assertEqual(enabled.status_code, 200, enabled.text)
        self.payload = {
            "run": {
                "workflow_id": workflow["id"],
                "revision_id": published.json()["data"]["id"],
                "workspace_id": 1,
                "inputs": {},
                "idempotency_key": "preflight-request",
                "reason": "Review synthetic uploaded evidence",
            },
            "artifacts": [
                {
                    "name": "main.tf",
                    "content": 'resource "aws_s3_bucket" "synthetic" { bucket = "synthetic-upload" }',
                }
            ],
        }

    def counts(self):
        with self.factory() as session:
            return tuple(
                session.scalar(select(func.count()).select_from(model))
                for model in (
                    InfraAutomationRun,
                    InfraAutomationArtifactManifest,
                    InfraAutomationReportLink,
                    AnalysisReport,
                )
            )

    def post(self, payload=None, *, headers=None):
        return self.client.post(
            self.path,
            json=self.payload if payload is None else payload,
            headers=self.headers() if headers is None else headers,
        )

    def test_real_admission_and_replay_bind_manifest_without_starting_analysis(self):
        before = self.counts()
        response = self.post()
        self.assertEqual(response.status_code, 200, response.text)
        run = response.json()["data"]
        self.assertEqual(run["state"], "queued")
        self.assertEqual(run["project_id"], 1)
        self.assertEqual(run["workspace_id"], 1)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("synthetic-upload", response.text)
        self.assertEqual(
            self.counts(), (before[0] + 1, before[1] + 1, before[2], before[3])
        )
        replay = self.post()
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["data"], run)
        changed = copy.deepcopy(self.payload)
        changed["artifacts"][0]["content"] += "\n# changed"
        self.assert_error(self.post(changed), 409)
        self.assertEqual(
            self.counts(), (before[0] + 1, before[1] + 1, before[2], before[3])
        )
        links = self.client.get(
            f"/api/v1/infra-automation/runs/{run['id']}/reports", headers=self.headers()
        )
        self.assertEqual(links.status_code, 200, links.text)
        self.assertEqual(links.json()["data"]["items"], [])

    def test_actor_role_and_unrecognized_fields_cannot_select_authority(self):
        before = self.counts()
        for target in ("request", "run", "artifact"):
            for field in ("actor", "role", "project_id", "provenance"):
                payload = copy.deepcopy(self.payload)
                container = (
                    payload
                    if target == "request"
                    else payload["run"]
                    if target == "run"
                    else payload["artifacts"][0]
                )
                container[field] = "synthetic-untrusted-authority"
                with self.subTest(target=target, field=field):
                    response = self.post(payload)
                    self.assert_error(response, 422)
                    self.assertNotIn("synthetic-untrusted-authority", response.text)
        self.assertEqual(self.counts(), before)

    def test_identity_csrf_membership_and_scope_fail_closed(self):
        before = self.counts()
        self.assert_error(
            self.post(
                headers={
                    "X-Actor": "admin",
                    "X-DeployWhisper-Project-Role": "admin",
                    "Origin": "https://identity.invalid",
                }
            ),
            401,
        )
        missing_csrf = self.headers()
        missing_csrf.pop("X-CSRF-Token")
        self.assert_error(self.post(headers=missing_csrf), 403)
        self.member("read-only")
        self.assert_error(
            self.post(
                headers=self.headers(**{"X-DeployWhisper-Project-Role": "admin"})
            ),
            403,
        )
        self.member("admin", workspace=1)
        changed = copy.deepcopy(self.payload)
        changed["run"]["workspace_id"] = 2
        self.assert_error(self.post(changed), 403)
        changed["run"]["workspace_id"] = 999
        self.assert_error(self.post(changed), 403)
        changed["run"]["workflow_id"] = "nonexistent"
        self.assert_error(self.post(changed), 403)
        self.assertEqual(self.counts(), before)

    def test_bad_artifacts_fail_before_manifest_report_or_run_persistence(self):
        before = self.counts()
        for artifact in (
            {"name": "../main.tf", "content": "synthetic"},
            {"name": "saved.tfplan", "content": "synthetic"},
            {"name": "private.key", "content": "synthetic"},
            {"name": "terraform.tfstate", "content": "synthetic"},
            {"name": "main.txt", "content": "synthetic"},
            {"name": "main.tf", "content": 'password = "synthetic-private-corpus"'},
            {"name": "main.tf", "content": '\ufeff{"version":1,"modules":[]}'},
        ):
            payload = {**self.payload, "artifacts": [artifact]}
            with self.subTest(artifact=artifact):
                response = self.post(payload)
                self.assert_error(response, 422)
                self.assertNotIn("synthetic-private-corpus", response.text)
                self.assertEqual(self.counts(), before)

    def test_chunk_split_sensitive_json_is_never_reflected_or_stored(self):
        before = self.counts()
        payload = copy.deepcopy(self.payload)
        secret = "ghp_abcdefghijklmnopqrstuvwxyz"
        payload["artifacts"][0]["content"] += "\n# " + secret
        body = json.dumps(payload).encode()
        start = body.index(secret.encode())
        for offset in (start + 2, start + 10, start + len(secret) - 1):
            with self.subTest(offset=offset):
                response = self.client.post(
                    self.path,
                    content=iter((body[:offset], body[offset:])),
                    headers=self.headers(**{"Content-Type": "application/json"}),
                )
                self.assert_error(response, 422)
                self.assertNotIn(secret, response.text)
                self.assertEqual(self.counts(), before)

    def test_escaped_lone_surrogate_names_return_generic_validation_error(self):
        before = self.counts()
        for name in ("\ud800.tf", "modules/\udfff/main.tf", "main\ud800.tf"):
            payload = copy.deepcopy(self.payload)
            payload["artifacts"][0]["name"] = name
            # Send literal JSON escapes so the client does not encode surrogates.
            body = json.dumps(payload, ensure_ascii=True).encode("ascii")
            with self.subTest(name=ascii(name)):
                response = self.client.post(
                    self.path,
                    content=body,
                    headers=self.headers(**{"Content-Type": "application/json"}),
                )
                self.assert_error(response, 422)
                self.assertNotIn("surrogate", response.text.lower())
                self.assertNotIn("\\ud800", response.text.lower())
                self.assertNotIn("\\udfff", response.text.lower())
                self.assertEqual(self.counts(), before)

    def test_versioned_known_sensitive_corpus_has_zero_error_or_storage_matches(self):
        """This named finite corpus proves only its declared known patterns."""
        corpus = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "fixtures/infra_automation/preflight_v1/sensitive-corpus.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(corpus["version"], 1)
        self.assertEqual(corpus["name"], "preflight-screening-v1")
        patterns = tuple(
            pattern for case in corpus["cases"] for pattern in case["known_patterns"]
        )
        before = self.counts()
        for case in corpus["cases"]:
            payload = copy.deepcopy(self.payload)
            payload["artifacts"][0]["content"] += "\n" + case["value"]
            with self.subTest(case=case["id"]):
                response = self.post(payload)
                self.assert_error(response, 422)
                error_json = json.dumps(response.json(), sort_keys=True)
                self.assertEqual(self.counts(), before)
                with self.factory() as session:
                    stored_dump = "\n".join(
                        session.connection().connection.driver_connection.iterdump()
                    )
                for pattern in patterns:
                    self.assertNotIn(pattern, error_json)
                    self.assertNotIn(pattern, stored_dump)

    def test_actual_body_and_aggregate_bytes_have_independent_ceilings(self):
        before = self.counts()
        with patch.object(routes, "MAX_PREFLIGHT_BODY_BYTES", 128):
            response = self.client.post(
                self.path,
                content=iter((b'{"value":"', b"x" * 80, b"x" * 80, b'"}')),
                headers=self.headers(
                    **{"Content-Type": "application/json", "Content-Length": "1"}
                ),
            )
            self.assert_error(response, 429)
        payload = copy.deepcopy(self.payload)
        payload["artifacts"] = [
            {"name": "one.tf", "content": "x" * 4194305},
            {"name": "two.tf", "content": "x" * 4194305},
        ]
        self.assert_error(self.post(payload), 429)
        self.assertEqual(self.counts(), before)

    def test_link_collection_does_not_disclose_unknown_run_or_cross_scope(self):
        admitted = self.post()
        self.assertEqual(admitted.status_code, 200, admitted.text)
        run_id = admitted.json()["data"]["id"]
        path = f"/api/v1/infra-automation/runs/{run_id}/reports"
        self.assert_error(self.client.get(path, headers={"X-Actor": "admin"}), 401)
        self.member("read-only", workspace=2)
        self.assert_error(self.client.get(path, headers=self.headers()), 403)
        self.assert_error(
            self.client.get(
                "/api/v1/infra-automation/runs/nonexistent/reports",
                headers=self.headers(),
            ),
            403,
        )
