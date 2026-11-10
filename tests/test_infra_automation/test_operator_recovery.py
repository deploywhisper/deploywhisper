"""Operator recovery matrix over actual services and synthetic admitted material.

These tests prove lifecycle contracts, not live receiver, custody or restore
qualification. A project epoch transition is not a coordinated database restore.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from infra_automation.lifecycle import (
    AdvanceEpochRequest,
    AutomationSettings,
    LifecycleError,
    UpdateSettingsRequest,
)
from infra_automation.targets import BreakLockRequest
from models.repositories import infra_automation_targets as registry
from models.tables import InfraAutomationAudit, InfraAutomationGrant
from services import infra_automation_policy as policy
from services import infra_automation_targets as targets
from services import project_service as auth
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_handoff_service as handoff_fixture
from tests.test_infra_automation import test_receiver_reconciliation as receiver_fixture
from tests.test_infra_automation import test_runner_enrollment as runner_fixture


class OperatorHandoffRecoveryTests(LifecycleCase):
    setUp = handoff_fixture.HandoffServiceTests.setUp
    enable = handoff_fixture.HandoffServiceTests.enable
    publish_fixture = handoff_fixture.HandoffServiceTests.publish_fixture
    deliver = handoff_fixture.HandoffServiceTests.deliver
    request = handoff_fixture.HandoffServiceTests.request
    prepare = handoff_fixture.HandoffServiceTests.prepare
    dispatch = handoff_fixture.HandoffServiceTests.dispatch
    callback = receiver_fixture.ReceiverReconciliationTests.callback

    def change_policy(self, *, enabled=None, restore=False):
        with self.credentials():
            current = policy.get_settings(100)
            if enabled is None:
                return policy.advance_epoch(
                    AdvanceEpochRequest(
                        project_id=100,
                        expected_version=current["version"],
                        reason="Operator invalidates prior automation authority",
                    ),
                    restore=restore,
                )
            return policy.update_settings(
                UpdateSettingsRequest(
                    project_id=100,
                    expected_version=current["version"],
                    settings=AutomationSettings.model_validate(
                        current["settings"]
                    ).model_copy(update={"enabled": enabled}),
                    reason="Operator changes automation enablement",
                )
            )

    def assert_retained_unknown(self, operation, *, consumed=False, human_read=True):
        if human_read:
            with self.credentials():
                view = self.handoffs.get_operation(operation["id"], 100, 100)
        else:
            view = self.handoffs.receiver_status(operation["id"], self.receiver)
        self.assertEqual(view["id"], operation["id"])
        with self.factory() as session:
            self.assertEqual(registry.get_lock(session, "held-lock").status, "held")
            grant = session.scalar(select(InfraAutomationGrant))
            self.assertEqual(grant.status, "consumed" if consumed else "available")
            self.assertEqual(grant.receipt_bytes is not None, consumed)

    def test_disable_before_dispatch_preserves_unsent_intent_and_lock(self):
        operation = self.prepare()
        self.change_policy(enabled=False)
        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.dispatch(operation)
        self.assertEqual(self.sent, [])
        self.assert_retained_unknown(operation)

    def test_disable_reenable_does_not_resurrect_dispatched_grant(self):
        operation = self.prepare()
        self.dispatch(operation)
        self.change_policy(enabled=False)
        self.change_policy(enabled=True)
        envelope = self.sent[0]
        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        self.assertEqual(len(self.sent), 1)
        self.assert_retained_unknown(operation)

    def test_project_restore_epoch_invalidates_grant_without_claiming_db_restore(self):
        operation = self.prepare()
        self.dispatch(operation)
        self.change_policy(restore=True)
        envelope = self.sent[0]
        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        self.assert_retained_unknown(operation)

    def test_revoke_after_consumption_preserves_receipt_and_same_operation_outcome(
        self,
    ):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        receipt = self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        self.change_policy()
        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.handoffs.authorize_action(operation["id"], self.receiver)
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver)["receipt"],
            receipt["receipt"],
        )
        self.assert_retained_unknown(operation, consumed=True)
        outcome = self.handoffs.callback(
            self.callback(operation, state="failed"), self.receiver
        )
        self.assertEqual(outcome["id"], operation["id"])
        self.assertEqual(outcome["state"], "failed")
        self.assertEqual(outcome["receipt"], receipt["receipt"])
        self.assertEqual(len(self.sent), 1)

    def test_expiry_never_unlocks_unknown_work_or_reissues_consumed_authority(self):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        self.now += timedelta(minutes=5)
        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.handoffs.authorize_action(operation["id"], self.receiver)
        self.assert_retained_unknown(operation, consumed=True, human_read=False)
        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.dispatch(operation)
        self.assertEqual(len(self.sent), 1)

    def test_reviewer_membership_revoke_blocks_action_but_keeps_receipt_reconciliation(
        self,
    ):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        receipt = self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        with self.credentials():
            auth.revoke_project_membership(100, "reviewer")
        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.handoffs.authorize_action(operation["id"], self.receiver)
        self.assert_retained_unknown(operation, consumed=True)
        result = self.handoffs.callback(
            self.callback(operation, state="failed"), self.receiver
        )
        self.assertEqual(result["receipt"], receipt["receipt"])
        self.assertEqual(result["state"], "failed")

    def test_nonadmin_cannot_break_unknown_lock_or_change_available_grant(self):
        operation = self.prepare()
        self.dispatch(operation)
        request = BreakLockRequest(
            project_id=100,
            workspace_id=100,
            expected_lock_id="held-lock",
            expected_version=1,
            acknowledge_uncertainty=True,
            reason="Attempt uncertain lock recovery",
        )
        with (
            self.credentials("reviewer"),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            targets.break_lock("target", request, now=self.now)
        self.assert_retained_unknown(operation)
        with self.factory() as session:
            events = list(session.scalars(select(InfraAutomationAudit)))
            self.assertFalse(
                any(event.event_type == "target_lock_broken" for event in events)
            )

    def test_audited_break_acknowledges_uncertainty_without_new_authority(self):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        with self.credentials():
            result = targets.break_lock(
                "target",
                BreakLockRequest(
                    project_id=100,
                    workspace_id=100,
                    expected_lock_id="held-lock",
                    expected_version=1,
                    acknowledge_uncertainty=True,
                    reason="Operator accepts unresolved external outcome",
                ),
                now=self.now,
            )
        self.assertEqual(result["status"], "broken")
        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        with self.factory() as session:
            self.assertEqual(
                session.scalar(select(InfraAutomationGrant)).status, "invalidated"
            )
            events = list(session.scalars(select(InfraAutomationAudit)))
            self.assertEqual(
                sum(event.event_type == "target_lock_broken" for event in events), 1
            )
            self.assertEqual(
                sum(event.event_type == "handoff_authority_broken" for event in events),
                1,
            )
        self.assertTrue(
            self.handoffs.receiver_status(operation["id"], self.receiver)["broken"]
        )
        self.assertEqual(len(self.sent), 1)


class OperatorRunnerRecoveryTests(LifecycleCase):
    def setUp(self):
        super().setUp()
        with self.credentials():
            policy.update_settings(
                UpdateSettingsRequest(
                    project_id=100,
                    expected_version=0,
                    settings=AutomationSettings(enabled=True),
                    reason="Enable operator runner recovery fixture",
                )
            )

    issue = runner_fixture.RunnerEnrollmentTests.issue
    redeem = runner_fixture.RunnerEnrollmentTests.redeem

    def test_project_epoch_revocation_rejects_old_runner_without_deleting_health(self):
        from services import infra_automation_runners as runners

        issued = self.issue()
        credential = self.redeem(issued)
        with self.credentials():
            current = policy.get_settings(100)
            policy.advance_epoch(
                AdvanceEpochRequest(
                    project_id=100,
                    expected_version=current["version"],
                    reason="Revoke old runner authority",
                )
            )
        with auth.authorized_session() as session:
            with self.assertRaises(LifecycleError):
                runners.authenticate(
                    session,
                    runners.RunnerCredential(
                        credential.runner_id, credential.token.get_secret_value()
                    ),
                    now=self.now,
                )
        with self.credentials():
            health = runners.health(100, 100, now=self.now)
        self.assertEqual(health["items"][0]["id"], credential.runner_id)

    def test_runner_rotation_then_revocation_keeps_history_without_revalidating_old_token(
        self,
    ):
        from services import infra_automation_runners as runners

        credential = self.redeem(self.issue())
        with self.credentials():
            rotated = runners.rotate(
                credential.runner_id, reason="Rotate operator credential", now=self.now
            )
            runners.revoke(
                credential.runner_id,
                reason="Revoke replacement credential",
                now=self.now,
            )
        for candidate in (credential, rotated):
            with auth.authorized_session() as session:
                with self.assertRaises(LifecycleError):
                    runners.authenticate(
                        session,
                        runners.RunnerCredential(
                            candidate.runner_id, candidate.token.get_secret_value()
                        ),
                        now=self.now,
                    )
        with self.credentials():
            health = runners.health(100, 100, now=self.now)
        self.assertEqual(health["items"][0]["status"], "revoked")
