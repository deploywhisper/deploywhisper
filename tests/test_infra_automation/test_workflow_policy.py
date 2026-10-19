"""Live settings, invalidation and retention consumer proofs on isolated SQLite."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event
from unittest.mock import patch

from sqlalchemy import select

import config
from infra_automation.lifecycle import (
    AdvanceEpochRequest,
    AutomationSettings,
    CreateWorkflowRequest,
    LifecycleError,
    PublishWorkflowRequest,
    UpdateSettingsRequest,
)
from models.repositories import infra_automation_workflows as repository
from models.repositories.settings import get_setting
from models.tables import IdentityAccount, InfraAutomationAudit
from services import infra_automation_policy as policy
from services import infra_automation_service as workflows
from services import infra_automation_support as support
from services.infra_automation_snapshots import export_run_snapshot
from services import settings_service
from services import project_service as authorization
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class WorkflowPolicyTests(LifecycleCase):
    def update(self, settings=None, expected_version=0):
        with self.credentials():
            return policy.update_settings(
                UpdateSettingsRequest(
                    project_id=100,
                    expected_version=expected_version,
                    settings=settings or AutomationSettings(enabled=True),
                    reason="Policy updated.",
                )
            )

    def fixture(self):
        self.update()
        with self.credentials():
            row = workflows.create_workflow(
                CreateWorkflowRequest(
                    project_id=100,
                    workspace_id=100,
                    name="Policy fixture",
                    definition=json.dumps(self.definition()),
                    reason="Created.",
                )
            )
            revision = workflows.publish_workflow(
                row["id"],
                PublishWorkflowRequest(
                    expected_version=1,
                    idempotency_key="policy-fixture",
                    reason="Published.",
                ),
            )
            return export_run_snapshot(row["id"], revision["id"], {}, 100).authority

    def check(self, stamp, operation="start"):
        with self.credentials(), authorization.authorized_session() as db:
            # The deny-only stamp does not authenticate the consumer. Real owners
            # must authenticate their own audience/operation before invoking it.
            support.scope(db, 100, 100, "automation.request", mutation=True)
            return policy.check_live_policy(db, stamp, operation)

    def audits(self):
        with self.factory() as db:
            return list(db.scalars(select(InfraAutomationAudit)))

    def test_defaults_are_disabled_read_only_and_persisted_values_ignore_config(self):
        with self.credentials(mutation=False):
            value = policy.get_settings(100)
        self.assertEqual(value["version"], 0)
        self.assertFalse(value["settings"]["enabled"])
        self.assertEqual(self.audits(), [])
        with patch(
            "config.settings", replace(config.settings, automation_max_workflows=17)
        ):
            with self.credentials(mutation=False):
                self.assertEqual(
                    policy.get_settings(100)["settings"]["max_workflows"], 17
                )
        self.update()
        with patch(
            "config.settings", replace(config.settings, automation_max_workflows=17)
        ):
            with self.credentials(mutation=False):
                self.assertEqual(
                    policy.get_settings(100)["settings"]["max_workflows"], 100
                )

    def test_settings_are_project_admin_only_with_fresh_mutation_credentials(self):
        for role in ("maintainer", "reviewer", "contributor", "read-only"):
            with self.subTest(role=role):
                self.member(role)
                with self.assertRaises(authorization.TrustedAuthorizationError):
                    self.update()
        self.member("admin", workspace=100)
        with self.assertRaises(authorization.TrustedAuthorizationError):
            self.update()
        self.member("admin")
        with (
            self.credentials(mutation=False),
            self.assertRaises(authorization.TrustedAuthorizationError),
        ):
            policy.update_settings(
                UpdateSettingsRequest(
                    project_id=100,
                    expected_version=0,
                    settings=AutomationSettings(),
                    reason="Changed.",
                )
            )
        self.member("maintainer")
        with self.credentials(mutation=False):
            self.assertEqual(policy.get_settings(100)["version"], 0)

    def test_settings_change_noop_conflict_and_epoch_advancement(self):
        initial = self.update()
        same = self.update(expected_version=1)
        self.assertEqual(initial, same)
        self.assertEqual(len(self.audits()), 1)
        with self.assertRaises(LifecycleError) as caught:
            self.update(expected_version=0)
        self.assertEqual(caught.exception.status_code, 409)
        disabled = self.update(AutomationSettings(), 1)
        enabled = self.update(expected_version=2)
        self.assertEqual(disabled["authorization_epoch"], 2)
        self.assertEqual(enabled["authorization_epoch"], 3)
        with self.credentials():
            revoked = policy.advance_epoch(
                AdvanceEpochRequest(
                    project_id=100, expected_version=3, reason="Revoked."
                )
            )
            restored = policy.advance_epoch(
                AdvanceEpochRequest(
                    project_id=100, expected_version=4, reason="Restored."
                ),
                restore=True,
            )
        self.assertEqual((revoked["version"], revoked["authorization_epoch"]), (4, 4))
        self.assertEqual(
            (restored["authorization_epoch"], restored["restore_epoch"]), (5, 2)
        )

    def test_epoch_requires_existing_policy_and_settings_audit_rolls_back(self):
        with self.credentials(), self.assertRaises(LifecycleError):
            policy.advance_epoch(
                AdvanceEpochRequest(
                    project_id=100, expected_version=0, reason="Revoke."
                )
            )
        with patch.object(
            support, "append_audit", side_effect=RuntimeError("synthetic")
        ):
            with self.assertRaises(RuntimeError):
                self.update()
        with self.factory() as db:
            self.assertIsNone(repository.get_policy(db, project_id=100))

    def test_caps_cannot_drop_below_retained_workflows_or_revisions(self):
        stamp = self.fixture()
        with self.credentials():
            workflows.create_workflow(
                CreateWorkflowRequest(
                    project_id=100,
                    workspace_id=100,
                    name="Second",
                    definition=json.dumps(self.definition()),
                    reason="Created.",
                )
            )
            workflows.publish_workflow(
                stamp.workflow_id,
                PublishWorkflowRequest(
                    expected_version=2,
                    idempotency_key="second",
                    reason="Published again.",
                ),
            )
        for changes in ({"max_workflows": 1}, {"max_revisions_per_workflow": 1}):
            with self.subTest(changes=changes), self.assertRaises(LifecycleError):
                self.update(AutomationSettings(enabled=True, **changes), 1)

    def test_effects_deny_disable_restore_and_old_epochs_without_rewriting_stamp(self):
        stamp = self.fixture()
        original = stamp.model_dump()
        for operation in ("start", "claim", "dispatch", "consume"):
            self.check(stamp, operation)
        self.update(AutomationSettings(), 1)
        self.update(expected_version=2)
        for operation in ("start", "claim", "dispatch", "consume"):
            with (
                self.subTest(operation=operation),
                self.assertRaises(authorization.TrustedAuthorizationError),
            ):
                self.check(stamp, operation)
        self.assertEqual(stamp.model_dump(), original)

    def test_membership_change_and_principal_disable_invalidate_original_authority(
        self,
    ):
        stamp = self.fixture()
        self.principal("human-b")
        self.member("admin", principal="human-b")
        self.member("contributor")
        with self.credentials("human-b"), authorization.authorized_session() as db:
            with self.assertRaises(authorization.TrustedAuthorizationError):
                policy.check_live_policy(db, stamp, "claim")
            policy.check_live_policy(db, stamp, "read")
        with self.factory.begin() as db:
            db.get(IdentityAccount, "human-a").enabled = False
        with self.credentials("human-b"), authorization.authorized_session() as db:
            with self.assertRaises(authorization.TrustedAuthorizationError):
                policy.check_live_policy(db, stamp, "consume")
            policy.check_live_policy(db, stamp, "reconcile")
        with self.credentials(), authorization.authorized_session() as db:
            with self.assertRaises(authorization.TrustedAuthorizationError):
                policy.check_live_policy(db, stamp, "read")

    def test_archive_blocks_start_but_retains_read_reconcile_and_accepted_work(self):
        stamp = self.fixture()
        with self.factory.begin() as db:
            repository.update_workflow(
                db, workflow_id=stamp.workflow_id, expected_version=2, archived=True
            )
        with self.assertRaises(authorization.TrustedAuthorizationError):
            self.check(stamp)
        for operation in ("claim", "dispatch", "consume", "read", "reconcile"):
            self.check(stamp, operation)

    def test_live_port_rejects_wrong_scope_missing_transaction_and_forged_stamp(self):
        stamp = self.fixture()
        with (
            self.factory() as db,
            self.assertRaises(authorization.TrustedAuthorizationError),
        ):
            policy.check_live_policy(db, stamp, "start")
        for changes in (
            {"project_id": 200},
            {"workspace_id": 101},
            {"revision_id": "missing"},
            {"membership_version": 999},
            {"principal_id": "missing"},
        ):
            with (
                self.subTest(changes=changes),
                self.assertRaises(
                    (authorization.TrustedAuthorizationError, LifecycleError)
                ),
            ):
                self.check(stamp.model_copy(update=changes))
        with self.assertRaises(LifecycleError):
            self.check(stamp.model_copy(update={"project_id": True}))
        with self.assertRaises(LifecycleError):
            self.check(stamp, "execute")

    def test_retention_protects_current_pending_accepted_unknown_and_corrupt_authority(
        self,
    ):
        stamp = self.fixture()
        old = self.now - timedelta(days=8)

        def allowed(state, created=old):
            with self.credentials(), authorization.authorized_session() as db:
                return policy.retention_allows_delete(
                    db, stamp, state, created, self.now
                )

        for state in ("pending", "accepted", "unknown"):
            self.assertFalse(allowed(state))
        self.assertTrue(allowed("terminal"))
        self.assertFalse(allowed("terminal", self.now - timedelta(hours=1)))
        self.update(AutomationSettings(retention_seconds=86400), 1)
        self.assertTrue(allowed("pending"))
        self.assertFalse(allowed("pending", self.now - timedelta(seconds=3601)))
        self.assertFalse(allowed("accepted"))
        self.assertFalse(allowed("unknown"))
        with self.factory.begin() as db:
            repository.get_policy(db, project_id=100).settings_json = "{}broken"
        self.assertFalse(allowed("pending"))
        self.assertFalse(allowed("terminal"))

    def test_advisory_save_delete_integration_and_noop_share_epoch_transaction(self):
        self.update()
        with (
            patch.object(settings_service, "SessionLocal", self.factory),
            self.credentials(),
        ):
            settings_service.save_policy_adapter_settings(project_key="lifecycle-one")
            self.assertEqual(policy.get_settings(100)["authorization_epoch"], 2)
            settings_service.save_policy_adapter_settings(project_key="lifecycle-one")
            self.assertEqual(policy.get_settings(100)["authorization_epoch"], 2)
            settings_service.save_policy_adapter_settings(
                project_key="lifecycle-one", integration="terraform"
            )
            self.assertEqual(policy.get_settings(100)["authorization_epoch"], 3)
            settings_service.delete_policy_adapter_settings(
                project_key="lifecycle-one", integration="terraform"
            )
            self.assertEqual(policy.get_settings(100)["authorization_epoch"], 4)
            settings_service.delete_policy_adapter_settings(
                project_key="lifecycle-one", integration="terraform"
            )
            self.assertEqual(policy.get_settings(100)["authorization_epoch"], 4)
        self.assertEqual(len(self.audits()), 4)

    def test_advisory_hook_rollback_and_unconfigured_noop(self):
        with (
            patch.object(settings_service, "SessionLocal", self.factory),
            self.credentials(),
        ):
            settings_service.save_policy_adapter_settings(project_key="lifecycle-one")
        self.assertEqual(self.audits(), [])
        self.update()
        with (
            patch.object(settings_service, "SessionLocal", self.factory),
            self.credentials(),
            patch.object(
                support, "append_audit", side_effect=RuntimeError("synthetic")
            ),
        ):
            with self.assertRaises(RuntimeError):
                settings_service.delete_policy_adapter_settings(
                    project_key="lifecycle-one"
                )
        with self.factory() as db:
            self.assertIsNotNone(
                get_setting(
                    db,
                    settings_service._policy_adapter_settings_key(
                        project_key="lifecycle-one"
                    ),
                )
            )
            self.assertEqual(
                repository.get_policy(db, project_id=100).authorization_epoch, 1
            )

    def test_consumer_mutation_reserves_authority_until_commit_then_revocation_denies(
        self,
    ):
        stamp = self.fixture()
        checked, attempted, release = Event(), Event(), Event()

        def consume():
            with self.credentials(), authorization.authorized_session() as db:
                support.scope(db, 100, 100, "automation.request", mutation=True)
                policy.check_live_policy(db, stamp, "consume")
                checked.set()
                if not release.wait(5):
                    raise RuntimeError("Test synchronization timed out")
                repository.append_audit(
                    db,
                    project_id=100,
                    workspace_id=100,
                    actor_principal_id="human-a",
                    actor_type="human",
                    actor_role="admin",
                    event_type="synthetic_consume",
                    target_id=stamp.revision_id,
                    reason="Consumed.",
                )

        def revoke():
            attempted.set()
            with self.credentials():
                return policy.advance_epoch(
                    AdvanceEpochRequest(
                        project_id=100, expected_version=1, reason="Revoked."
                    )
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            consuming = pool.submit(consume)
            self.assertTrue(checked.wait(5))
            revoking = pool.submit(revoke)
            self.assertTrue(attempted.wait(5))
            self.assertFalse(revoking.done())
            release.set()
            consuming.result(timeout=10)
            revoking.result(timeout=10)
        with self.assertRaises(authorization.TrustedAuthorizationError):
            self.check(stamp, "consume")
        self.assertLess(
            next(
                a.sequence for a in self.audits() if a.event_type == "synthetic_consume"
            ),
            self.audits()[-1].sequence,
        )

    def test_scope_overflow_and_aware_timestamp_are_bounded(self):
        with self.credentials(), authorization.authorized_session() as db:
            with self.assertRaises(authorization.TrustedAuthorizationError):
                support.scope(db, 2**100, None, "automation.read", mutation=False)
        offset = self.now.astimezone(timezone(timedelta(hours=5, minutes=30)))
        self.assertEqual(support.utc(offset), support.utc(self.now))

    def test_config_defaults_validate_floors_types_and_cross_field_lifetimes(self):
        for values in (
            {"automation_max_workflows": 0},
            {"automation_max_workflows": True},
            {"automation_max_active_runs": 11},
            {"automation_max_queued_runs": 1001},
            {"automation_max_artifact_bytes": 8388609},
            {"automation_retention_seconds": 86399},
            {"automation_evidence_ttl_seconds": 60},
            {"automation_credential_ttl_seconds": 3601},
            {"automation_approval_ttl_seconds": 3601},
        ):
            with (
                self.subTest(values=values),
                patch("config.settings", replace(config.settings, **values)),
            ):
                with self.assertRaises(ValueError):
                    config.automation_settings_defaults()
                with (
                    self.credentials(mutation=False),
                    self.assertRaises(LifecycleError) as caught,
                ):
                    policy.get_settings(100)
                self.assertEqual(caught.exception.status_code, 503)
        self.assertFalse(config.automation_settings_defaults().enabled)

    def test_revoke_reassign_membership_and_authentication_rotation_never_revive(self):
        from models.repositories.project_memberships import revoke_membership

        stamp = self.fixture()
        self.principal("human-b")
        self.member("admin", principal="human-b")
        with self.factory.begin() as db:
            revoke_membership(db, principal_id="human-a", project_id=100)
        self.member("admin")
        with self.credentials("human-b"), authorization.authorized_session() as db:
            with self.assertRaises(authorization.TrustedAuthorizationError):
                policy.check_live_policy(db, stamp, "dispatch")
        with self.credentials():
            fresh = export_run_snapshot(
                stamp.workflow_id, stamp.revision_id, {}, 100
            ).authority
        with self.factory.begin() as db:
            db.get(IdentityAccount, "human-a").authentication_version += 1
        with self.credentials("human-b"), authorization.authorized_session() as db:
            with self.assertRaises(authorization.TrustedAuthorizationError):
                policy.check_live_policy(db, fresh, "consume")
            policy.check_live_policy(db, fresh, "reconcile")

    def test_read_permissions_remain_live_for_each_operator(self):
        stamp = self.fixture()
        self.update(AutomationSettings(), 1)
        self.principal("human-b")
        self.member("read-only", principal="human-b")
        with (
            self.credentials("human-b", mutation=False),
            authorization.authorized_session() as db,
        ):
            for operation in ("read", "reconcile"):
                policy.check_live_policy(db, stamp, operation)
        self.member("read-only", principal="human-b", workspace=101)
        with (
            self.credentials("human-b", mutation=False),
            authorization.authorized_session() as db,
        ):
            with self.assertRaises(authorization.TrustedAuthorizationError):
                policy.check_live_policy(db, stamp, "read")
        self.member("read-only", principal="human-b")
        with (
            self.credentials("human-b", mutation=False),
            authorization.authorized_session() as db,
        ):
            with self.assertRaises(authorization.TrustedAuthorizationError):
                policy.retention_allows_delete(
                    db, stamp, "terminal", self.now - timedelta(days=8), self.now
                )

    def test_advisory_change_and_restore_invalidates_even_with_equal_effective_content(
        self,
    ):
        stamp = self.fixture()
        with (
            patch.object(settings_service, "SessionLocal", self.factory),
            self.credentials(),
        ):
            settings_service.save_policy_adapter_settings(
                project_key="lifecycle-one", integration="terraform"
            )
            settings_service.delete_policy_adapter_settings(
                project_key="lifecycle-one", integration="terraform"
            )
        with self.assertRaises(authorization.TrustedAuthorizationError):
            self.check(stamp, "consume")
        with self.credentials(), authorization.authorized_session() as db:
            self.assertEqual(
                stamp.advisory_policy_digest,
                support.digest(
                    support.canonical(
                        support.advisory_policy(db, 100).model_dump(mode="json")
                    )
                ),
            )

    def test_advisory_hook_requires_automation_admin_even_if_legacy_guard_is_open(self):
        self.update()
        self.member("maintainer")
        with (
            patch.object(settings_service, "SessionLocal", self.factory),
            self.credentials(),
            patch.object(settings_service, "_guard_policy_project", return_value=None),
        ):
            with self.assertRaises(authorization.TrustedAuthorizationError):
                settings_service.save_policy_adapter_settings(
                    project_key="lifecycle-one", enforcement_mode="advisory"
                )
        with self.factory() as db:
            self.assertIsNone(
                get_setting(
                    db,
                    settings_service._policy_adapter_settings_key(
                        project_key="lifecycle-one"
                    ),
                )
            )
            self.assertEqual(
                repository.get_policy(db, project_id=100).authorization_epoch, 1
            )

    def test_out_of_band_digest_changes_are_not_retention_invalidation_proof(self):
        stamp = self.fixture()
        with self.factory.begin() as db:
            repository.get_policy(
                db, project_id=100
            ).settings_json = AutomationSettings(
                enabled=True, max_workflows=50
            ).model_dump_json()
        with self.assertRaises(LifecycleError) as caught:
            self.check(stamp, "consume")
        self.assertEqual(caught.exception.status_code, 503)
        with self.credentials(), authorization.authorized_session() as db:
            self.assertFalse(
                policy.retention_allows_delete(
                    db, stamp, "pending", self.now - timedelta(days=8), self.now
                )
            )

    def test_revocation_winning_race_denies_consumer_before_any_mutation(self):
        from models.repositories.project_memberships import revoke_membership

        stamp = self.fixture()
        self.principal("human-b")
        self.member("admin", principal="human-b")
        revoked, attempted, release = Event(), Event(), Event()

        def revoke():
            with self.credentials(), authorization.authorized_session() as db:
                support.scope(db, 100, None, "automation.admin", mutation=True)
                revoke_membership(db, principal_id="human-a", project_id=100)
                revoked.set()
                if not release.wait(5):
                    raise RuntimeError("Test synchronization timed out")

        def consume():
            attempted.set()
            with self.credentials("human-b"), authorization.authorized_session() as db:
                support.scope(db, 100, 100, "automation.request", mutation=True)
                with self.assertRaises(authorization.TrustedAuthorizationError):
                    policy.check_live_policy(db, stamp, "claim")

        with ThreadPoolExecutor(max_workers=2) as pool:
            revoking = pool.submit(revoke)
            self.assertTrue(revoked.wait(5))
            consuming = pool.submit(consume)
            self.assertTrue(attempted.wait(5))
            self.assertFalse(consuming.done())
            release.set()
            revoking.result(timeout=10)
            consuming.result(timeout=10)

    def test_untyped_operations_and_naive_retention_times_are_rejected(self):
        stamp = self.fixture()
        for operation in (None, [], {}, True):
            with self.subTest(operation=operation), self.assertRaises(LifecycleError):
                self.check(stamp, operation)
        with self.credentials(), authorization.authorized_session() as db:
            with self.assertRaises(LifecycleError):
                policy.retention_allows_delete(db, stamp, [], self.now, self.now)
            with self.assertRaises(LifecycleError):
                policy.retention_allows_delete(
                    db, stamp, "terminal", self.now.replace(tzinfo=None), self.now
                )

    def test_archive_alone_cannot_release_pending_claim_authority_for_retention(self):
        stamp = self.fixture()
        with self.factory.begin() as db:
            repository.update_workflow(
                db, workflow_id=stamp.workflow_id, expected_version=2, archived=True
            )
        with self.credentials(), authorization.authorized_session() as db:
            policy.check_live_policy(db, stamp, "claim")
            self.assertFalse(
                policy.retention_allows_delete(
                    db, stamp, "pending", self.now - timedelta(days=8), self.now
                )
            )

    def test_persisted_policy_never_defaults_partial_duplicate_or_invalid_state(self):
        self.update()
        original = AutomationSettings(enabled=True).model_dump_json()
        invalid = (
            "{}",
            "[]",
            "null",
            '{"enabled":true}',
            original[:-1] + ',"enabled":false}',
            original.replace('"enabled":true', '"enabled":NaN'),
            original.replace('"max_workflows":100', '"max_workflows":Infinity'),
            '{"enabled":' + "[" * 1000,
        )
        for raw in invalid:
            with self.subTest(raw=raw[:60]):
                with self.factory.begin() as db:
                    repository.get_policy(db, project_id=100).settings_json = raw
                with (
                    self.credentials(mutation=False),
                    self.assertRaises(LifecycleError) as caught,
                ):
                    policy.get_settings(100)
                self.assertEqual(caught.exception.status_code, 503)
        with self.factory.begin() as db:
            repository.get_policy(db, project_id=100).settings_json = json.dumps(
                json.loads(original), indent=2
            )
        with self.credentials(mutation=False):
            self.assertTrue(policy.get_settings(100)["settings"]["enabled"])
        for field, value in (
            ("version", 1.5),
            ("authorization_epoch", 2**53),
            ("restore_epoch", 1.25),
        ):
            with self.subTest(field=field):
                with self.factory.begin() as db:
                    row = repository.get_policy(db, project_id=100)
                    row.version = row.authorization_epoch = row.restore_epoch = 1
                    setattr(row, field, value)
                with (
                    self.credentials(mutation=False),
                    self.assertRaises(LifecycleError) as caught,
                ):
                    policy.get_settings(100)
                self.assertEqual(caught.exception.status_code, 503)
