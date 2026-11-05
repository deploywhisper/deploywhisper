"""Collection views report durable observations without inventing runner phases."""

from __future__ import annotations

from datetime import timedelta
import unittest
from tests.test_infra_automation import test_collection_intake as fixture
from services import infra_automation_collection_views as views
from services import project_service as auth


class CollectionViewTests(unittest.TestCase):
    def setUp(self):
        self.case = fixture.CollectionIntakeTests(
            "test_authenticated_complete_publishes_manifest_and_clears_staging"
        )
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.install_profile()

    def read(self, **kwargs):
        with self.case.credentials():
            return views.get_collection(
                self.case.run.id,
                project_id=100,
                workspace_id=100,
                now=self.case.now,
                **kwargs,
            )

    def test_unobserved_phases_are_not_claimed_complete(self):
        item = self.read()["items"][0]
        facts = {x["kind"]: x for x in item["observations"]}
        self.assertEqual(facts["source_bound"]["state"], "bound")
        self.assertEqual(facts["screened_upload"]["state"], "not_observed")
        self.assertIsNone(facts["screened_upload"]["event_at"])
        self.assertEqual(
            self.read()["cancellation"]["owned_processes"], "not_confirmed"
        )

    def test_finalized_manifest_proves_screened_upload_but_not_analysis(self):
        self.case.collect()
        facts = {x["kind"]: x for x in self.read()["items"][0]["observations"]}
        self.assertEqual(facts["screened_upload"]["state"], "finalized")
        self.assertIsNotNone(facts["screened_upload"]["event_at"])
        self.assertEqual(facts["analysis"]["state"], "not_observed")

    def test_wrong_requested_scope_rejected(self):
        with self.case.credentials(), self.assertRaises(auth.TrustedAuthorizationError):
            views.get_collection(
                self.case.run.id, project_id=200, workspace_id=200, now=self.case.now
            )

    def test_routing_diagnoses_version_mismatch_without_runner_identity(self):
        from models.tables import InfraAutomationRunner

        with self.case.factory.begin() as db:
            row = db.get(InfraAutomationRunner, self.case.runner.id)
            row.runner_version = "2.0"
        item = self.read()["items"][0]
        self.assertEqual(item["diagnosis"]["code"], "runner_version_mismatch")
        self.assertNotIn(self.case.runner.id, str(item["diagnosis"]))

    def test_expired_lease_is_stale_not_terminated(self):
        self.case.send(self.case.message("claim", 1))
        with self.case.credentials():
            value = views.get_collection(
                self.case.run.id,
                project_id=100,
                workspace_id=100,
                now=self.case.now + timedelta(minutes=2),
            )
        self.assertEqual(value["items"][0]["observations"][1]["state"], "stale")
        self.assertEqual(value["cancellation"]["owned_processes"], "not_confirmed")

    def test_revision_readiness_uses_same_scoped_profile(self):
        with self.case.credentials():
            value = views.get_readiness(
                self.case.run.workflow_id,
                self.case.run.revision_id,
                project_id=100,
                workspace_id=100,
                now=self.case.now,
            )
        self.assertTrue(value["can_request"])
        self.assertEqual(value["items"][0]["profile_digest"], self.case.profile)
        self.assertEqual(value["finite_wait_seconds"], 0)

    def test_cancel_projection_matches_owner_and_admin_rule(self):
        self.assertTrue(self.read()["cancellation"]["can_cancel"])
        self.case.principal("other")
        self.case.member("maintainer", principal="other")
        with self.case.credentials("other"):
            value = views.get_collection(
                self.case.run.id, project_id=100, workspace_id=100, now=self.case.now
            )
        self.assertFalse(value["cancellation"]["can_cancel"])

    def test_multiple_analysis_branches_do_not_hide_failure(self):
        from types import SimpleNamespace

        attempts = [
            SimpleNamespace(step_id="a", attempt_number=1, state="failed"),
            SimpleNamespace(step_id="b", attempt_number=1, state="succeeded"),
        ]
        self.assertEqual(
            views._analysis_observation(attempts, {"a", "b"}, self.case.now).state,
            "failed",
        )
        self.assertEqual(
            views._analysis_observation(attempts, {"b", "c"}, self.case.now).state,
            "not_observed",
        )

    def test_staged_upload_has_no_invented_event_timestamp(self):
        from services.infra_automation_support import canonical, digest

        self.case.send(self.case.message("claim", 1))
        raw = canonical(self.case.payload())
        self.case.send(
            self.case.message(
                "upload", 2, atomic_upload_id="stage", upload_digest=digest(raw)
            ),
            upload_bytes=raw,
        )
        fact = self.read()["items"][0]["observations"][2]
        self.assertEqual(fact["state"], "received")
        self.assertIsNone(fact["event_at"])

    def test_nonadmin_nonowner_can_read_without_runner_diagnostics(self):
        self.case.principal("reader")
        self.case.member("read-only", principal="reader")
        with self.case.credentials("reader"):
            value = views.get_collection(
                self.case.run.id, project_id=100, workspace_id=100, now=self.case.now
            )
        self.assertEqual(value["items"][0]["diagnosis"]["code"], "details_unavailable")
        self.assertFalse(value["cancellation"]["can_cancel"])

    def test_specific_routing_corrections_remain_scope_bound(self):
        from models.tables import InfraAutomationRunner

        mutations = (
            ("profile_digest", "sha256:" + "c" * 64, "profile_mismatch"),
            ("tool", "terraform", "tool_mismatch"),
            ("runner_version", "2.0", "runner_version_mismatch"),
            ("tags_json", "[]", "tags_mismatch"),
            ("last_seen_at", self.case.now - timedelta(seconds=61), "heartbeat_stale"),
            ("credential_expires_at", self.case.now, "credential_unavailable"),
            ("status", "revoked", "runner_inactive"),
        )
        for field, value, expected in mutations:
            with self.subTest(field=field):
                with self.case.factory.begin() as db:
                    row = db.get(InfraAutomationRunner, self.case.runner.id)
                    original = getattr(row, field)
                    setattr(row, field, value)
                try:
                    self.assertEqual(
                        self.read()["items"][0]["diagnosis"]["code"], expected
                    )
                finally:
                    with self.case.factory.begin() as db:
                        setattr(
                            db.get(InfraAutomationRunner, self.case.runner.id),
                            field,
                            original,
                        )

    def test_read_time_is_captured_after_authorization_wait(self):
        from unittest.mock import patch
        from services import infra_automation_engine_service as engine

        self.case.send(self.case.message("claim", 1))
        current = [self.case.now]
        original = engine._authorized_run

        def delayed(session, run_id):
            value = original(session, run_id)
            current[0] += timedelta(minutes=2)
            return value

        with (
            self.case.credentials(),
            patch.object(engine, "_authorized_run", side_effect=delayed),
            patch.object(
                views, "_now", side_effect=lambda supplied: supplied or current[0]
            ),
        ):
            value = views.get_collection(
                self.case.run.id, project_id=100, workspace_id=100
            )
        self.assertEqual(value["items"][0]["observations"][1]["state"], "stale")
