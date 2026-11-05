"""Collection views report durable observations without inventing runner phases."""

from __future__ import annotations

from datetime import timedelta
import unittest
from sqlalchemy import func, insert, select

from infra_automation import claims as engine_claims
from models.repositories import infra_automation_runners as runner_repo
from models.repositories import infra_automation_runs as runs
from models.tables import InfraAutomationAudit, InfraAutomationRunner
from tests.test_infra_automation import test_collection_intake as fixture
from services import infra_automation_collection_views as views
from services import infra_automation_runner_tasks as tasks
from services.infra_automation_support import digest
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


class CollectionRoutingIntegrationTests(unittest.TestCase):
    setUp = CollectionViewTests.setUp

    def seed_history(self, **changes):
        # Synthetic retained registrations deliberately sort ahead of the real
        # runner under ID ordering, with identical timestamps to test tie breaks.
        template = {
            column.key: getattr(self.case.runner, column.key)
            for column in InfraAutomationRunner.__table__.columns
        }
        template["credential_expires_at"] = self.case.now
        template.update(changes)
        with self.case.factory.begin() as db:
            db.execute(
                insert(InfraAutomationRunner),
                [dict(template, id=f"000-history-{i:04d}") for i in range(1000)],
            )

    def new_pending(self, *, busy=False):
        if not busy:
            with self.case.factory() as db:
                original = runs.get_attempt(db, self.case.pending.id)
            if original.state == "claimed":
                self.case.operation(
                    engine_claims.safety_cleanup,
                    self.case.owner,
                    attempt_id=self.case.pending.id,
                    expected_version=original.version,
                    state="failed",
                )
        self.request_count = getattr(self, "request_count", 0) + 1
        self.case.request["key_digest"] = digest(
            f"readiness-to-routing-{self.request_count}".encode()
        )
        run = self.case.admit()
        pending = self.case.attempt(run)
        self.case.operation(
            engine_claims.start_run,
            self.case.owner,
            run_id=run.id,
            expected_version=1,
        )
        self.addCleanup(lambda: tasks._MAILBOX.pop(pending.id, None))
        return pending

    def readiness_then_assign(self, pending, expected_code):
        with self.case.credentials():
            readiness = views.get_readiness(
                self.case.run.workflow_id,
                self.case.run.revision_id,
                project_id=100,
                workspace_id=100,
                now=self.case.now,
            )
        self.assertEqual(readiness["items"][0]["diagnosis"]["code"], expected_code)
        result = tasks.queue_assignment(
            self.case.owner,
            pending.id,
            self.case.requirements,
            now=self.case.now,
            session_factory=self.case.factory,
        )
        with self.case.factory() as db:
            attempt = runs.get_attempt(db, pending.id)
            failure = db.scalar(
                select(InfraAutomationAudit.id).where(
                    InfraAutomationAudit.target_id == pending.id,
                    InfraAutomationAudit.event_type == "runner.no_eligible_runner",
                )
            )
            if expected_code == "eligible":
                self.assertIsNotNone(result)
                self.assertEqual(result["runner_id"], self.case.runner.id)
                self.assertEqual(attempt.state, "claimed")
                self.assertIsNone(failure)
            else:
                self.assertIsNone(result)
                self.assertEqual(attempt.state, "failed")
                self.assertIsNotNone(failure)
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationRunner)),
                1001,
            )

    def test_expired_active_history_cannot_mask_available_runner(self):
        self.seed_history()
        self.readiness_then_assign(self.new_pending(), "eligible")

    def test_future_created_history_cannot_mask_available_runner(self):
        self.seed_history(
            created_at=self.case.now + timedelta(days=1),
            credential_expires_at=self.case.now + timedelta(days=30),
        )
        self.readiness_then_assign(self.new_pending(), "eligible")

    def test_busy_runner_remains_unavailable_with_expired_history(self):
        self.seed_history()
        self.readiness_then_assign(self.new_pending(busy=True), "runner_busy")

    def test_expired_history_does_not_bypass_profile_rejection(self):
        self.seed_history(profile_digest="sha256:" + "c" * 64)
        with self.case.factory.begin() as db:
            db.get(InfraAutomationRunner, self.case.runner.id).profile_digest = (
                "sha256:" + "c" * 64
            )
        self.readiness_then_assign(self.new_pending(), "profile_mismatch")

    def test_current_candidate_order_is_bounded_and_deterministic(self):
        self.seed_history()
        with self.case.factory() as db:
            candidates = runner_repo.routing_candidates(db, 100, 100, self.case.now)
            self.assertEqual(
                [row.id for row in candidates],
                [self.case.runner.id] + [f"000-history-{i:04d}" for i in range(999)],
            )
            self.assertEqual(
                runner_repo.routing_candidates(db, 100, 101, self.case.now), []
            )

    def test_candidate_priority_preserves_live_rejections(self):
        self.seed_history()
        mutations = (
            ("credential_hash", None, "credential_unavailable"),
            ("credential_expires_at", self.case.now, "credential_unavailable"),
            (
                "credential_expires_at",
                self.case.now.replace(microsecond=999999),
                "credential_unavailable",
            ),
            (
                "created_at",
                self.case.now + timedelta(microseconds=1),
                "credential_unavailable",
            ),
            ("authorization_epoch", 999, "credential_unavailable"),
            ("issuer_membership_version", 999, "credential_unavailable"),
            ("last_seen_at", self.case.now - timedelta(seconds=61), "heartbeat_stale"),
            ("last_seen_at", self.case.now + timedelta(seconds=1), "heartbeat_stale"),
        )
        for field, value, expected in mutations:
            with self.subTest(field=field, value=value):
                pending = self.new_pending()
                with self.case.factory.begin() as db:
                    row = db.get(InfraAutomationRunner, self.case.runner.id)
                    original = getattr(row, field)
                    setattr(row, field, value)
                try:
                    self.readiness_then_assign(pending, expected)
                finally:
                    with self.case.factory.begin() as db:
                        setattr(
                            db.get(InfraAutomationRunner, self.case.runner.id),
                            field,
                            original,
                        )
