"""Direct service effects cannot bypass the deny-only recovery barrier."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from unittest.mock import patch

from infra_automation.lifecycle import (
    AutomationSettings,
    LifecycleError,
    UpdateSettingsRequest,
)
from infra_automation.operator_recovery import RecoveryError
from services import infra_automation_policy as policy
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_handoff_service as fixture


class RecoveryOnlyStore:
    def participate(self):
        return nullcontext()

    def assert_ready(self, *, effects=False, session=None):
        if effects:
            raise RecoveryError()


class RecoveryBarrierTests(LifecycleCase):
    setUp = fixture.HandoffServiceTests.setUp
    enable = fixture.HandoffServiceTests.enable
    publish_fixture = fixture.HandoffServiceTests.publish_fixture
    deliver = fixture.HandoffServiceTests.deliver
    request = fixture.HandoffServiceTests.request
    prepare = fixture.HandoffServiceTests.prepare
    dispatch = fixture.HandoffServiceTests.dispatch

    def barrier(self):
        return patch(
            "infra_automation.operator_recovery.configured_store",
            return_value=RecoveryOnlyStore(),
        )

    def test_enabled_policy_cannot_be_saved_during_recovery_even_if_unchanged(self):
        with self.credentials():
            current = policy.get_settings(100)
            request = UpdateSettingsRequest(
                project_id=100,
                expected_version=current["version"],
                settings=AutomationSettings.model_validate(current["settings"]),
                reason="Attempt reenable during recovery",
            )
            with self.barrier(), self.assertRaises(LifecycleError) as error:
                policy.update_settings(request)
            self.assertEqual(error.exception.status_code, 503)
            self.assertEqual(policy.get_settings(100), current)

    def test_new_run_capture_denies_but_history_remains_readable(self):
        operation = self.prepare()
        with self.barrier():
            from services.infra_automation_snapshots import export_run_snapshot

            with self.credentials(), self.assertRaises(LifecycleError) as error:
                export_run_snapshot(self.run.workflow_id, self.run.revision_id, {}, 100)
            self.assertEqual(error.exception.status_code, 503)
            with self.credentials():
                self.assertEqual(
                    self.handoffs.get_operation(operation["id"], 100, 100)["id"],
                    operation["id"],
                )

    def test_dispatch_and_consume_deny_without_sending_again(self):
        operation = self.prepare()
        with self.barrier(), self.assertRaises(LifecycleError) as error:
            self.dispatch(operation)
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(self.sent, [])
        self.dispatch(operation)
        envelope = self.sent[0]
        with self.barrier(), self.assertRaises(LifecycleError) as error:
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(len(self.sent), 1)

    def test_identity_transaction_participates_before_opening_writer(self):
        from services.identity_service import IdentityError

        class UnavailableStore:
            @contextmanager
            def participate(self):
                raise RecoveryError()
                yield

        with patch(
            "infra_automation.operator_recovery.configured_store",
            return_value=UnavailableStore(),
        ):
            with self.assertRaises(IdentityError) as error:
                with self.identity._transaction():
                    self.fail("Identity writer entered during offline recovery")
        self.assertEqual(error.exception.status_code, 503)
