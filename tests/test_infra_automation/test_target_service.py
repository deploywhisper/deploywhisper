"""Verified global registry ownership and live captured target admission."""

from __future__ import annotations

from datetime import timedelta
import json

from services import infra_automation_targets as targets
from services import project_service as auth
from infra_automation.targets import RegisterTargetRequest
from infra_automation.lifecycle import LifecycleError
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation.test_target_contracts import definition_payload


class TargetServiceTests(LifecycleCase):
    def setUp(self):
        super().setUp()
        self.member("admin", project=200)

    def request(self, *, expected_version=0, **changes):
        definition = {
            **definition_payload(),
            "allowed_scopes": [
                dict(project_id=100, workspace_id=100),
                dict(project_id=200, workspace_id=200),
            ],
            **changes,
        }
        return RegisterTargetRequest.model_validate_json(
            json.dumps(
                dict(
                    project_id=100,
                    workspace_id=100,
                    expected_version=expected_version,
                    definition=definition,
                    reason="Register exact owned target",
                )
            )
        )

    def test_global_admin_registration_and_atomic_epoch_change(self):
        with self.credentials():
            first = targets.register_target(self.request(), now=self.now)
            self.assertEqual(
                (first["id"], first["version"], first["epoch"]), ("target", 1, 1)
            )
            second = targets.register_target(
                self.request(expected_version=1, enabled=False),
                now=self.now + timedelta(seconds=1),
            )
            self.assertEqual((second["version"], second["epoch"]), (2, 2))
            self.assertFalse(second["definition"]["enabled"])
            self.assertEqual(targets.get_target("alias", 100, 100)["id"], "target")

    def test_project_admin_and_missing_csrf_cannot_redefine_global_aliases(self):
        self.principal("project-admin")
        self.member("admin", principal="project-admin")
        with (
            self.credentials("project-admin"),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            targets.register_target(self.request(), now=self.now)
        with (
            self.credentials(csrf="wrong"),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            targets.register_target(self.request(), now=self.now)

    def test_aliases_never_rebind_and_unassigned_scope_reads_deny(self):
        with self.credentials():
            targets.register_target(self.request(), now=self.now)
            with self.assertRaises(LifecycleError):
                targets.register_target(
                    self.request(canonical_target="other"), now=self.now
                )
            with self.assertRaises(auth.TrustedAuthorizationError):
                targets.get_target("target", 100, 101)

    def test_registry_page_scope_snapshot_and_backwards_clock(self):
        with self.credentials():
            targets.register_target(self.request(), now=self.now)
            targets.register_target(
                self.request(canonical_target="two", aliases=["second"]), now=self.now
            )
            page = targets.list_targets(100, 100, limit=1)
            targets.register_target(
                self.request(canonical_target="three", aliases=["third"]),
                now=self.now + timedelta(seconds=1),
            )
            older = targets.list_targets(
                100, 100, limit=1, cursor=page["cursor"]["next_cursor"]
            )
            self.assertEqual(len(older["items"]), 1)
            self.assertNotEqual(older["items"][0]["id"], "three")
            with self.assertRaises(LifecycleError) as error:
                targets.register_target(
                    self.request(expected_version=1),
                    now=self.now - timedelta(seconds=1),
                )
            self.assertEqual(error.exception.status_code, 503)
