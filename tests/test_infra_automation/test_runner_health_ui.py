"""Authoritative connectivity and permissions never turn health into trust."""

from __future__ import annotations

from datetime import timedelta
import math
from unittest.mock import patch

from infra_automation.collection_contracts import CollectionProfile
from infra_automation.lifecycle import (
    AutomationSettings,
    UpdateSettingsRequest,
    LifecycleError,
)
from models.tables import InfraAutomationRunner
from services import infra_automation_policy as policy
from services import infra_automation_runners as runners
from services import project_service as auth
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_runner_health as existing


class RunnerHealthProjectionTests(LifecycleCase):
    issue = existing.RunnerHealthTests.issue

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

    def health(self):
        with self.credentials():
            return runners.health(100, 100, now=self.now)["items"][0]

    def test_connectivity_boundaries_are_server_evaluated_and_not_qualification(self):
        issued = self.issue()
        for age, expected in (
            (None, "offline"),
            (0, "online"),
            (60, "online"),
            (60.1, "stale"),
            (61, "stale"),
            (180, "stale"),
            (181, "offline"),
            (-1, "offline"),
        ):
            with self.subTest(age=age):
                with self.factory.begin() as db:
                    row = db.get(InfraAutomationRunner, issued.enrollment.runner_id)
                    row.last_seen_at = (
                        None if age is None else self.now - timedelta(seconds=age)
                    )
                view = self.health()
                self.assertEqual(view["connectivity"], expected)
                if age == -1:
                    self.assertEqual(view["connectivity_reason"], "clock_unavailable")
                self.assertEqual(
                    view["heartbeat_age_seconds"],
                    math.ceil(age) if age is not None and age >= 0 else None,
                )
                self.assertEqual(
                    view["evaluated_at"], self.now.strftime("%Y-%m-%dT%H:%M:%SZ")
                )
                self.assertIs(view["isolation_qualified"], False)
                self.assertEqual(view["credential_status"], "pending")

    def test_profile_registration_and_credential_expiry_are_separate(self):
        issued = self.issue()
        credential = runners.redeem(
            issued.enrollment.enrollment_id,
            issued.token.get_secret_value(),
            now=self.now,
        )
        profile = CollectionProfile(
            profile_digest="sha256:" + "a" * 64,
            tool="opentofu",
            tool_version="1.13.1",
            runner_version="1.0",
            tags=["linux"],
        )
        with patch(
            "services.infra_automation_collection.configured_profiles",
            return_value=(profile,),
        ):
            view = self.health()
            self.assertEqual(view["profile_status"], "registered")
            self.assertEqual(view["tool_version"], "1.13.1")
            self.assertEqual(view["credential_status"], "valid")
            with self.factory.begin() as db:
                db.get(
                    InfraAutomationRunner, credential.runner_id
                ).credential_expires_at = self.now
            view = self.health()
            self.assertEqual(view["credential_status"], "expired")
            self.assertIs(view["isolation_qualified"], False)
        with patch(
            "services.infra_automation_collection.configured_profiles",
            side_effect=LifecycleError(503),
        ):
            view = self.health()
            self.assertEqual(view["profile_status"], "unavailable")
            self.assertIsNone(view["tool_version"])

    def test_capabilities_read_does_not_create_mutation_authority(self):
        with self.credentials():
            value = runners.capabilities(100, 100, now=self.now)
        self.assertTrue(value["can_read_health"])
        self.assertTrue(value["can_enroll"])
        self.member("maintainer")
        with self.credentials():
            value = runners.capabilities(100, 100, now=self.now)
        self.assertTrue(value["can_read_health"])
        self.assertFalse(value["can_enroll"])
        self.assertFalse(value["can_rotate"])
        self.assertFalse(value["can_revoke"])
        self.assertEqual(value["restriction"], "administrator_required")
        self.member("read-only")
        with self.credentials():
            value = runners.capabilities(100, 100, now=self.now)
        self.assertFalse(value["can_read_health"])
        with self.credentials(), self.assertRaises(auth.TrustedAuthorizationError):
            runners.health(100, 100, now=self.now)

    def test_disabled_execution_still_allows_revocation(self):
        with self.credentials():
            policy.update_settings(
                UpdateSettingsRequest(
                    project_id=100,
                    expected_version=1,
                    settings=AutomationSettings(enabled=False),
                    reason="Disable fixture.",
                )
            )
            value = runners.capabilities(100, 100, now=self.now)
        self.assertFalse(value["can_enroll"])
        self.assertFalse(value["can_rotate"])
        self.assertTrue(value["can_revoke"])
        self.assertEqual(value["restriction"], "execution_disabled")

    def test_profile_choices_never_reflect_sensitive_or_unbounded_metadata(self):
        for version in ("runner-v1-" + "b" * 64, "1" * 1000 + ".2.3"):
            with self.subTest(
                case="secret" if version.startswith("runner") else "size"
            ):
                profile = CollectionProfile(
                    profile_digest="sha256:" + "a" * 64,
                    tool="opentofu",
                    tool_version="1.13.1" if version.startswith("runner") else version,
                    runner_version=version if version.startswith("runner") else "1.0",
                    tags=["linux"],
                )
                with (
                    self.credentials(),
                    patch(
                        "services.infra_automation_collection.configured_profiles",
                        return_value=(profile,),
                    ),
                ):
                    value = runners.capabilities(100, 100, now=self.now)
                self.assertEqual(value["profile_status"], "unavailable")
                self.assertEqual(value["configured_profiles"], [])
                self.assertNotIn(version, str(value))
