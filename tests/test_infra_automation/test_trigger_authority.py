"""Durable signed request authority never acquires human capabilities."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import config
from infra_automation.lifecycle import LifecycleError
from infra_automation.trigger_signing import sign_request
from services.infra_automation_trigger_authority import TriggerAuthority
from services.infra_automation_triggers import (
    provision_principal,
    ProvisionPrincipalRequest,
)
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class TriggerFixture(LifecycleCase):
    def setUp(self):
        super().setUp()
        from tests.test_infra_automation.test_workflow_snapshots import (
            WorkflowSnapshotTests,
        )

        WorkflowSnapshotTests.enable(self)
        with self.credentials():
            self.machine = provision_principal(
                ProvisionPrincipalRequest(
                    project_id=100,
                    workspace_id=100,
                    username="synthetic-service",
                    principal_type="service",
                    role="contributor",
                    reason="Test scoped issuer",
                )
            )
        self.secret = b"k" * 32
        self.key = {
            "key_id": "key-one",
            "principal_id": self.machine["principal_id"],
            "principal_type": "service",
            "project_id": 100,
            "workspace_id": 100,
            "allowed_revision_ids": ["revision-one"],
            "allowed_sources": [{"repository_id": "repo", "commit_sha": "a" * 40}],
            "allowed_origins": ["webhook", "cli"],
            "authentication_version": self.machine["authentication_version"],
            "membership_version": self.machine["membership_version"],
            "restore_epoch": self.machine["restore_epoch"],
            "expires_at": (self.now + timedelta(hours=1)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "secret_env_ref": "SYNTHETIC_TRIGGER_KEY",
        }
        path = Path(self.temp.name).resolve() / "keys.json"
        raw = json.dumps({"version": 1, "keys": [self.key]}).encode()
        path.write_bytes(raw)
        path.chmod(0o600)
        context = patch(
            "config.settings",
            replace(
                config.settings,
                trigger_keys_path=str(path),
                trigger_keys_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
            ),
        )
        context.start()
        self.addCleanup(context.stop)
        environment = patch.dict(
            os.environ, {"SYNTHETIC_TRIGGER_KEY": self.secret.hex()}
        )
        environment.start()
        self.addCleanup(environment.stop)

    def authority(self, nonce="n" * 24, body=b"{}"):
        fields = dict(
            key_id="key-one",
            method="POST",
            path="/api/v1/infra-automation/triggers/webhook",
            timestamp=str(int(self.now.timestamp())),
            nonce=nonce,
            body=body,
        )
        return TriggerAuthority(
            **fields,
            signature=sign_request(secret=self.secret, **fields),
            session_factory=self.factory,
            now=lambda: self.now,
        )


class TriggerAuthorityTests(TriggerFixture):
    def test_nonce_is_durable_and_scope_is_live(self):
        first = self.authority()
        first.reserve_nonce()
        with self.assertRaises(LifecycleError):
            self.authority().reserve_nonce()
        with first.credentials():
            from services import project_service as auth

            with auth.authorized_session() as db:
                grant = auth.guard_project(
                    db, 100, 100, "automation.request", mutation=True
                )
                self.assertEqual(grant.principal.principal_type, "service")
                with self.assertRaises(auth.TrustedAuthorizationError):
                    auth.guard_project(
                        db, 100, 100, "automation.publish", mutation=True
                    )
                with self.assertRaises(auth.TrustedAuthorizationError):
                    auth.guard_project(db, 200, 200, "automation.read")

    def test_raw_body_change_and_clock_rollback_deny(self):
        first = self.authority()
        first.reserve_nonce()
        self.now -= timedelta(seconds=1)
        with self.assertRaises(LifecycleError):
            self.authority(nonce="x" * 24).reserve_nonce()

    def test_key_removal_revokes_already_verified_context(self):
        authority = self.authority()
        authority.reserve_nonce()
        with (
            authority.credentials(),
            patch.dict(os.environ, {"SYNTHETIC_TRIGGER_KEY": ""}),
        ):
            from services import project_service as auth

            with (
                auth.authorized_session() as db,
                self.assertRaises(auth.TrustedAuthorizationError),
            ):
                auth.guard_project(db, 100, 100, "automation.read")

    def test_live_issuer_rejects_unsupported_nonhuman_membership_role(self):

        member = self.member(
            "admin", principal=self.machine["principal_id"], workspace=100
        )
        self.key["membership_version"] = member.authorization_version
        raw = json.dumps({"version": 1, "keys": [self.key]}).encode()
        Path(config.settings.trigger_keys_path).write_bytes(raw)
        with patch(
            "config.settings",
            replace(
                config.settings,
                trigger_keys_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
            ),
        ):
            from services import project_service as auth

            with self.assertRaises(auth.TrustedAuthorizationError):
                self.authority().reserve_nonce()

    def test_nonce_capacity_and_key_expiry_are_bounded(self):
        first = self.authority()
        first.reserve_nonce()
        with (
            patch("services.infra_automation_trigger_authority.KEY_NONCES", 1),
            self.assertRaises(LifecycleError) as caught,
        ):
            self.authority(nonce="z" * 24).reserve_nonce()
        self.assertEqual(caught.exception.status_code, 429)
        self.now += timedelta(hours=1)
        from services import project_service as auth

        with self.assertRaises(auth.TrustedAuthorizationError):
            self.authority(nonce="y" * 24).reserve_nonce()
