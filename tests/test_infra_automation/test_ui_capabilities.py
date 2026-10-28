"""Scope/policy freshness and read-only service guarantees for the UI projection."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import func, select

from infra_automation.lifecycle import (
    AutomationSettings,
    LifecycleError,
    UpdateSettingsRequest,
)
from models.repositories import project_memberships
from models.tables import (
    InfraAutomationAudit,
    InfraAutomationPolicy,
    InfraWorkflow,
    InfraWorkflowRevision,
)
from services import infra_automation_service as service
from services import infra_automation_support as support
from services import project_service as authorization
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class UiCapabilitiesTests(LifecycleCase):
    def read(self, workspace=100):
        with self.credentials(mutation=False):
            return service.get_capabilities(100, workspace_id=workspace)

    def update(self, enabled, version):
        with self.credentials():
            return service.update_settings(
                UpdateSettingsRequest(
                    project_id=100,
                    expected_version=version,
                    settings=AutomationSettings(enabled=enabled),
                    reason="Update policy",
                )
            )

    def test_live_enable_disable_and_membership_change_never_cache_permissions(self):
        initial = self.read()
        self.assertFalse(initial["execution_enabled"])
        self.assertEqual(initial["policy_version"], 0)
        self.update(True, 0)
        enabled = self.read()
        self.assertTrue(enabled["execution_enabled"])
        self.assertEqual(enabled["policy_version"], 1)
        self.update(False, 1)
        disabled = self.read()
        self.assertFalse(disabled["execution_enabled"])
        self.assertEqual(disabled["policy_version"], 2)
        self.assertEqual(disabled["capabilities"], initial["capabilities"])
        changed = self.member("read-only", workspace=100)
        restricted = self.read()
        self.assertEqual(
            restricted["membership_version"], changed.authorization_version
        )
        self.assertEqual(restricted["capabilities"], ["automation.read"])
        with self.factory.begin() as db:
            project_memberships.revoke_membership(
                db, principal_id="human-a", project_id=100
            )
        with self.assertRaises(authorization.TrustedAuthorizationError):
            self.read()

    def test_scope_remains_exact_and_global_admin_is_not_a_project_permission(self):
        self.member("read-only", workspace=100)
        self.assertEqual(self.read()["workspace_id"], 100)
        for workspace in (None, 101, 200, 999):
            with (
                self.subTest(workspace=workspace),
                self.assertRaises(authorization.TrustedAuthorizationError),
            ):
                self.read(workspace)
        self.member("read-only")
        self.assertIsNone(self.read(None)["workspace_id"])
        self.assertEqual(self.read()["capabilities"], ["automation.read"])

    def test_direct_service_requires_live_credentials_even_on_legacy_project(self):
        with self.assertRaises(authorization.TrustedAuthorizationError):
            service.get_capabilities(100, workspace_id=100)
        self.now += timedelta(hours=2)
        with self.assertRaises(authorization.TrustedAuthorizationError):
            self.read()

    def test_nonhuman_direct_service_credentials_cannot_read_projection(self):
        for principal_type in ("service", "agent", "runner", "receiver"):
            self.principal(
                principal_type, principal_type=principal_type, audience="human"
            )
            self.member("admin", principal=principal_type)
            with (
                self.subTest(principal_type=principal_type),
                self.credentials(principal=principal_type, mutation=False),
                self.assertRaises(authorization.TrustedAuthorizationError),
            ):
                service.get_capabilities(100, workspace_id=100)

    def test_corrupt_policy_fails_closed_without_partial_capabilities(self):
        self.update(True, 0)
        with self.factory.begin() as db:
            row = db.scalar(select(InfraAutomationPolicy))
            row.settings_json = '{"enabled":true,"unregistered":"synthetic-private"}'
        with self.assertRaises(LifecycleError) as caught:
            self.read()
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn("synthetic-private", str(caught.exception))

    def test_projection_reads_membership_and_policy_in_same_reserved_transaction(self):
        original = support.policy_state
        observed = []

        def inspect(session, project_id):
            self.assertTrue(authorization.has_authorized_session())
            self.assertTrue(
                session.connection().connection.driver_connection.in_transaction
            )
            observed.append(project_id)
            return original(session, project_id)

        with patch.object(support, "policy_state", side_effect=inspect):
            self.read()
        self.assertEqual(observed, [100])

    def test_no_workflow_policy_revision_or_audit_is_created_by_reads(self):
        models = (
            InfraAutomationPolicy,
            InfraWorkflow,
            InfraWorkflowRevision,
            InfraAutomationAudit,
        )

        def counts():
            with self.factory() as db:
                return tuple(
                    db.scalar(select(func.count()).select_from(model))
                    for model in models
                )

        before = counts()
        for _ in range(2):
            self.read()
        self.assertEqual(counts(), before)
