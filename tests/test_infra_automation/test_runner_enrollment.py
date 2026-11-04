"""Real SQLite enrollment, revocation and scope regression tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from infra_automation.lifecycle import (
    AutomationSettings,
    UpdateSettingsRequest,
    LifecycleError,
)
from models.tables import InfraAutomationRunner, InfraAutomationRunnerEnrollment
from services import infra_automation_runners as runners
from services import infra_automation_policy as policy
from services import project_service as auth
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class RunnerEnrollmentTests(LifecycleCase):
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

    def issue(self):
        with self.credentials():
            return runners.create_enrollment(
                runners.EnrollmentRequest(
                    project_id=100,
                    workspace_id=100,
                    tags=["linux"],
                    tool="opentofu",
                    profile_digest="sha256:" + "a" * 64,
                    runner_version="1.0",
                    reason="Enroll fixture.",
                ),
                now=self.now,
            )

    def redeem(self, issue):
        return runners.redeem(
            issue.enrollment.enrollment_id, issue.token.get_secret_value(), now=self.now
        )

    def test_one_use_hashes_and_authentication(self):
        issued = self.issue()
        credential = self.redeem(issued)
        token = credential.token.get_secret_value()
        self.assertNotIn(token, repr(credential))
        with self.assertRaises(LifecycleError):
            self.redeem(issued)
        with auth.authorized_session() as db:
            row = runners.authenticate(
                db, runners.RunnerCredential(credential.runner_id, token), now=self.now
            )
            self.assertEqual(row.project_id, 100)
            self.assertNotEqual(row.credential_hash, token)
            enrollment = db.scalar(select(InfraAutomationRunnerEnrollment))
            self.assertNotEqual(enrollment.token_hash, issued.token.get_secret_value())

    def test_rotation_revocation_and_health(self):
        issued = self.issue()
        first = self.redeem(issued)
        with self.credentials():
            second = runners.rotate(
                first.runner_id, reason="Rotate fixture.", now=self.now
            )
        with auth.authorized_session() as db:
            with self.assertRaises(LifecycleError):
                runners.authenticate(
                    db,
                    runners.RunnerCredential(
                        first.runner_id, first.token.get_secret_value()
                    ),
                    now=self.now,
                )
            runners.authenticate(
                db,
                runners.RunnerCredential(
                    second.runner_id, second.token.get_secret_value()
                ),
                now=self.now,
            )
        with self.credentials():
            runners.revoke(first.runner_id, reason="Revoke fixture.", now=self.now)
            result = runners.health(100, 100)
        self.assertEqual(result["items"][0]["status"], "revoked")
        self.assertNotIn("credential_hash", str(result))
        with auth.authorized_session() as db:
            with self.assertRaises(LifecycleError):
                runners.authenticate(
                    db,
                    runners.RunnerCredential(
                        second.runner_id, second.token.get_secret_value()
                    ),
                    now=self.now,
                )

    def test_nonadmin_and_wrong_scope_denied(self):
        self.member("maintainer")
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.issue()
        with self.credentials():
            with self.assertRaises(auth.TrustedAuthorizationError):
                runners.health(200, 200)

    def test_expiration_and_disabled_policy(self):
        issued = self.issue()
        with self.assertRaises(LifecycleError):
            runners.redeem(
                issued.enrollment.enrollment_id,
                issued.token.get_secret_value(),
                now=self.now + timedelta(minutes=6),
            )
        credential = self.redeem(issued)
        with self.credentials():
            policy.update_settings(
                UpdateSettingsRequest(
                    project_id=100,
                    expected_version=1,
                    settings=AutomationSettings(enabled=False),
                    reason="Disable fixture.",
                )
            )
        with auth.authorized_session() as db:
            with self.assertRaises(LifecycleError):
                runners.authenticate(
                    db,
                    runners.RunnerCredential(
                        credential.runner_id, credential.token.get_secret_value()
                    ),
                    now=self.now,
                )

    def test_concurrent_redemption_has_one_winner(self):
        issued = self.issue()

        def redeem(_):
            try:
                self.redeem(issued)
                return True
            except LifecycleError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(redeem, range(2))), 1)

    def test_envelope_binding_and_version_denied_without_consumption(self):
        issued = self.issue()
        for field, value in (
            ("project_id", "200"),
            ("runner_id", "other"),
            ("workspace_id", "101"),
            ("expires_at", "2030-01-01T00:00:00Z"),
        ):
            with self.subTest(field=field), self.assertRaises(LifecycleError):
                runners.redeem(
                    issued.enrollment.enrollment_id,
                    issued.token.get_secret_value(),
                    enrollment=issued.enrollment.model_copy(update={field: value}),
                    now=self.now,
                )
        for version in (True, "1", 2):
            with self.assertRaises(LifecycleError):
                runners.redeem(
                    issued.enrollment.enrollment_id,
                    issued.token.get_secret_value(),
                    protocol_version=version,
                    now=self.now,
                )
        self.redeem(issued)

    def test_member_change_invalidates_existing_credential(self):
        credential = self.redeem(self.issue())
        self.member("admin")  # Same role still advances authorization generation.
        with auth.authorized_session() as db:
            with self.assertRaises(LifecycleError):
                runners.authenticate(
                    db,
                    runners.RunnerCredential(
                        credential.runner_id, credential.token.get_secret_value()
                    ),
                    now=self.now,
                )

    def test_machine_secrets_cannot_be_persisted_in_reason(self):
        credential = self.redeem(self.issue())
        with self.credentials():
            with self.assertRaises(LifecycleError):
                runners.revoke(
                    credential.runner_id,
                    reason=credential.token.get_secret_value(),
                    now=self.now,
                )
        with auth.authorized_session() as db:
            runners.authenticate(
                db,
                runners.RunnerCredential(
                    credential.runner_id, credential.token.get_secret_value()
                ),
                now=self.now,
            )

    def test_health_retained_when_disabled_and_mutations_fail(self):
        credential = self.redeem(self.issue())
        with self.credentials():
            policy.update_settings(
                UpdateSettingsRequest(
                    project_id=100,
                    expected_version=1,
                    settings=AutomationSettings(enabled=False),
                    reason="Disable fixture.",
                )
            )
            self.assertEqual(len(runners.health(100, 100)["items"]), 1)
            with self.assertRaises(LifecycleError):
                runners.rotate(
                    credential.runner_id, reason="Rotate fixture.", now=self.now
                )
            runners.revoke(
                credential.runner_id, reason="Revoke while disabled.", now=self.now
            )

    def test_redemption_rechecks_clock_after_waiting_for_transaction(self):
        from contextlib import contextmanager
        from unittest.mock import patch

        issued = self.issue()
        original = auth.authorized_session
        clock = [self.now]

        @contextmanager
        def delayed_transaction():
            with original() as session:
                clock[0] = self.now + timedelta(minutes=6)
                yield session

        with (
            patch.object(auth, "authorized_session", delayed_transaction),
            patch.object(
                runners, "_now", lambda value=None: clock[0] if value is None else value
            ),
        ):
            with self.assertRaises(LifecycleError):
                runners.redeem(
                    issued.enrollment.enrollment_id, issued.token.get_secret_value()
                )
        # Expired attempt did not consume or issue credentials.
        with original() as db:
            self.assertIsNone(
                db.scalar(select(InfraAutomationRunnerEnrollment)).consumed_at
            )

    def test_enrollment_expiry_matches_advertised_second_including_legacy_fraction(
        self,
    ):
        issued = self.issue()
        expires = datetime.strptime(
            issued.enrollment.expires_at, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        with self.factory.begin() as db:
            item = db.get(
                InfraAutomationRunnerEnrollment, issued.enrollment.enrollment_id
            )
            self.assertEqual(item.expires_at.microsecond, 0)
            # Previously imported rows cannot extend the advertised second.
            item.expires_at = expires + timedelta(microseconds=750000)
        with self.assertRaises(LifecycleError):
            runners.redeem(
                issued.enrollment.enrollment_id,
                issued.token.get_secret_value(),
                now=expires,
            )

    def test_runner_expiry_matches_advertised_second_for_both_authentication_paths(
        self,
    ):
        issued = self.redeem(self.issue())
        expires = datetime.strptime(issued.expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        with self.factory.begin() as db:
            row = db.get(InfraAutomationRunner, issued.runner_id)
            self.assertEqual(row.credential_expires_at.microsecond, 0)
            row.credential_expires_at = expires + timedelta(microseconds=750000)
        with auth.authorized_session() as db:
            for operation in (
                lambda: runners.authenticate(
                    db,
                    runners.RunnerCredential(
                        issued.runner_id, issued.token.get_secret_value()
                    ),
                    now=expires,
                ),
                lambda: runners.validate_runner(
                    db, db.get(InfraAutomationRunner, issued.runner_id), now=expires
                ),
            ):
                with self.assertRaises(LifecycleError):
                    operation()

    def test_encoded_machine_credentials_cannot_enter_audit_reasons(self):
        from sqlalchemy import func
        from models.tables import InfraAutomationAudit

        enrollment = self.issue()
        credential = self.redeem(enrollment)
        runner_id = credential.runner_id

        def snapshot():
            with self.factory() as db:
                row = db.get(InfraAutomationRunner, runner_id)
                return (
                    db.scalar(select(func.count()).select_from(InfraAutomationAudit)),
                    db.scalar(select(func.count()).select_from(InfraAutomationRunner)),
                    db.scalar(
                        select(func.count()).select_from(
                            InfraAutomationRunnerEnrollment
                        )
                    ),
                    row.generation,
                    row.credential_hash,
                    row.status,
                )

        before = snapshot()
        for bearer in (
            enrollment.token.get_secret_value(),
            credential.token.get_secret_value(),
        ):
            prefix, suffix = bearer.rsplit("-", 1)
            encoded_prefix = "".join(f"%{ord(char):02x}" for char in prefix + "-")
            encodings = (
                "".join(f"%{ord(char):02x}" for char in bearer),
                encoded_prefix + suffix,
                encoded_prefix.replace("%", "%25") + suffix,
            )
            for index, reason in enumerate(encodings):
                request = runners.EnrollmentRequest(
                    project_id=100,
                    workspace_id=100,
                    tags=["linux"],
                    tool="opentofu",
                    profile_digest="sha256:" + "a" * 64,
                    runner_version="1.0",
                    reason=reason,
                )
                operations = (
                    lambda: runners.create_enrollment(request, now=self.now),
                    lambda: runners.rotate(runner_id, reason=reason, now=self.now),
                    lambda: runners.revoke(runner_id, reason=reason, now=self.now),
                )
                for operation_index, operation in enumerate(operations):
                    with self.subTest(encoding=index, operation=operation_index):
                        with (
                            self.credentials(),
                            self.assertRaises(LifecycleError) as error,
                        ):
                            operation()
                        self.assertEqual(error.exception.status_code, 422)
                        self.assertTrue(
                            snapshot() == before,
                            "Rejected reason changed retained authority or audit.",
                        )
