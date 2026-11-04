"""Retained runner history pagination and live enrollment capacity boundaries."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from sqlalchemy import select, func
from infra_automation.lifecycle import (
    AutomationSettings,
    UpdateSettingsRequest,
    LifecycleError,
)
from infra_automation.lifecycle_cursors import CursorStore
from models.tables import InfraAutomationRunner, ProjectMembership
from services import infra_automation_policy as policy
from services import infra_automation_runners as runners
from services import project_service as auth
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class RunnerHealthTests(LifecycleCase):
    def setUp(self):
        super().setUp()
        with self.credentials():
            policy.update_settings(
                UpdateSettingsRequest(
                    project_id=100,
                    expected_version=0,
                    settings=AutomationSettings(enabled=True),
                    reason="Enable fixture.",
                )
            )

    def issue(self, *, now=None):
        with self.credentials():
            return runners.create_enrollment(
                runners.EnrollmentRequest(
                    project_id=100,
                    workspace_id=100,
                    tags=["linux"],
                    tool="opentofu",
                    profile_digest="sha256:" + "a" * 64,
                    runner_version="1.0",
                    reason="History fixture.",
                ),
                now=now or self.now,
            )

    def read(self, **kwargs):
        with self.credentials():
            return runners.health(100, 100, **kwargs)

    def test_more_than_100_revoked_records_preserve_history_and_allow_replacement(self):
        identifiers = set()
        for _ in range(105):
            issued = self.issue()
            identifiers.add(issued.enrollment.runner_id)
            with self.credentials():
                runners.revoke(
                    issued.enrollment.runner_id, reason="Replace fixture.", now=self.now
                )
        replacement = self.issue()
        identifiers.add(replacement.enrollment.runner_id)
        first = self.read()
        self.assertEqual(len(first["items"]), 25)
        found = [item["id"] for item in first["items"]]
        page = first
        while page["cursor"]["next_cursor"]:
            page = self.read(cursor=page["cursor"]["next_cursor"])
            found.extend(item["id"] for item in page["items"])
        self.assertEqual(set(found), identifiers)
        self.assertEqual(len(found), 106)
        self.assertEqual(len(self.read(limit=100)["items"]), 100)

    def test_expired_pending_enrollments_free_live_capacity(self):
        for _ in range(100):
            self.issue()
        with self.assertRaises(LifecycleError) as error:
            self.issue()
        self.assertEqual(error.exception.status_code, 429)
        self.issue(now=self.now + timedelta(minutes=6))
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationRunner)), 101
            )

    def test_active_capacity_and_expired_rotation_cannot_overbook(self):
        first = self.issue()
        credential = runners.redeem(
            first.enrollment.enrollment_id, first.token.get_secret_value(), now=self.now
        )
        later = self.now + timedelta(minutes=16)
        for _ in range(100):
            self.issue(now=later)
        with self.credentials(), self.assertRaises(LifecycleError) as error:
            runners.rotate(
                credential.runner_id, reason="Reactivate fixture.", now=later
            )
        self.assertEqual(error.exception.status_code, 429)
        with self.assertRaises(LifecycleError) as error:
            self.issue(now=later)
        self.assertEqual(error.exception.status_code, 429)

    def test_concurrent_enrollment_reserves_only_final_live_slot(self):
        for _ in range(99):
            self.issue()
        barrier = Barrier(2)

        def issue(_):
            barrier.wait(timeout=10)
            try:
                self.issue()
                return 200
            except LifecycleError as exc:
                return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(issue, range(2))), [200, 429])

    def test_snapshot_order_excludes_new_backdated_insert(self):
        ids = [self.issue().enrollment.runner_id for _ in range(28)]
        first = self.read()
        self.assertEqual(len(first["items"]), 25)
        added = self.issue(now=self.now - timedelta(seconds=1)).enrollment.runner_id
        second = self.read(cursor=first["cursor"]["next_cursor"])
        actual = [item["id"] for item in first["items"] + second["items"]]
        self.assertEqual(actual, sorted(ids, reverse=True))
        self.assertNotIn(added, actual)
        self.assertIsNone(second["cursor"]["next_cursor"])
        self.assertEqual(
            first["cursor"]["snapshot_id"], second["cursor"]["snapshot_id"]
        )
        self.assertEqual(len(self.read(limit=100)["items"]), 29)

    def test_cursors_bind_identity_scope_limit_generation_and_expiry(self):
        for _ in range(3):
            self.issue()
        clock = [0.0]
        store = CursorStore(clock=lambda: clock[0])
        with patch("services.infra_automation_service.cursor_store", store):
            cursor = self.read(limit=1)["cursor"]["next_cursor"]
            for candidate in (
                "synthetic",
                cursor[:-1] + ("0" if cursor[-1] != "0" else "1"),
            ):
                with self.assertRaises(LifecycleError) as error:
                    self.read(limit=1, cursor=candidate)
                self.assertEqual(error.exception.status_code, 409)
            with self.assertRaises(LifecycleError):
                self.read(limit=2, cursor=cursor)
            self.principal("other")
            self.member("admin", principal="other")
            with self.credentials("other"), self.assertRaises(LifecycleError) as error:
                runners.health(100, 100, limit=1, cursor=cursor)
            self.assertEqual(error.exception.status_code, 409)
            with self.credentials(), self.assertRaises(LifecycleError):
                runners.health(100, 101, limit=1, cursor=cursor)
            self.member("admin", project=200)
            with self.credentials(), self.assertRaises(LifecycleError):
                runners.health(200, 200, limit=1, cursor=cursor)
            clock[0] = 900
            with self.assertRaises(LifecycleError):
                self.read(limit=1, cursor=cursor)
        cursor = self.read(limit=1)["cursor"]["next_cursor"]
        self.member("admin")
        with self.assertRaises(LifecycleError):
            self.read(limit=1, cursor=cursor)
        with self.factory.begin() as db:
            db.scalar(
                select(ProjectMembership).where(
                    ProjectMembership.principal_id == "human-a",
                    ProjectMembership.project_id == 100,
                )
            ).enabled = False
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.read(limit=1, cursor=cursor)

    def test_policy_disable_preserves_authorized_history_continuation(self):
        for _ in range(3):
            self.issue()
        cursor = self.read(limit=1)["cursor"]["next_cursor"]
        with self.credentials():
            policy.update_settings(
                UpdateSettingsRequest(
                    project_id=100,
                    expected_version=1,
                    settings=AutomationSettings(enabled=False),
                    reason="Disable fixture.",
                )
            )
        self.assertEqual(len(self.read(limit=1, cursor=cursor)["items"]), 1)

    def test_100_active_credentials_enforce_cap_but_allow_in_place_rotation(self):
        for _ in range(100):
            issued = self.issue()
            credential = runners.redeem(
                issued.enrollment.enrollment_id,
                issued.token.get_secret_value(),
                now=self.now,
            )
        with self.assertRaises(LifecycleError) as error:
            self.issue()
        self.assertEqual(error.exception.status_code, 429)
        with self.credentials():
            rotated = runners.rotate(
                credential.runner_id, reason="Rotate existing live slot.", now=self.now
            )
        self.assertEqual(rotated.generation, 2)
        with auth.authorized_session() as db:
            runners.authenticate(
                db,
                runners.RunnerCredential(
                    rotated.runner_id, rotated.token.get_secret_value()
                ),
                now=self.now,
            )
