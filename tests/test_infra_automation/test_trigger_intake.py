"""Authenticated machine admission, source pinning and immutable origin proof."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select
import config
from infra_automation.contracts import ProfileContract, RegistryContract
from infra_automation.lifecycle import (
    AuthorityStamp,
    MachineAuthorityStamp,
    LifecycleError,
    decode_authority,
)
from infra_automation.trigger_contracts import (
    TriggerRequest,
    TriggerListRequest,
    TriggerStatusRequest,
)
from infra_automation.trigger_signing import sign_request
from models.tables import InfraAutomationRun, InfraAutomationTriggerNonce
from models.repositories.infra_automation_runs import get_run
from services import infra_automation_trigger_authority as authority
from services import infra_automation_triggers as intake
from services import infra_automation_engine_service as engine
from services import project_service as auth
from services.infra_automation_policy import check_live_policy
from tests.test_infra_automation import test_trigger_authority as base
from tests.test_infra_automation.test_engine_service import AvailableHandlers
from tests.test_infra_automation import test_workflow_snapshots as snapshots

D = "sha256:" + "b" * 64


class TriggerIntakeTests(base.TriggerFixture):
    def setUp(self):
        super().setUp()
        self.registry = RegistryContract(
            profiles=(
                ProfileContract(
                    digest=D, tool="opentofu", authorization_kinds=("advisory_request",)
                ),
            )
        )
        definition = {
            "workflow_version": 2,
            "project_id": "100",
            "workspace_id": "100",
            "environment": "dev",
            "inputs": {},
            "steps": [
                {
                    "id": "collect",
                    "kind": "admitted_collection",
                    "depends_on": [],
                    "source": {
                        "kind": "collected",
                        "repository_id": "repo",
                        "commit_sha": "a" * 40,
                        "profile_digest": D,
                    },
                }
            ],
        }
        self.workflow, self.revision = snapshots.WorkflowSnapshotTests.publish_fixture(
            self, definition
        )
        self.key["allowed_revision_ids"] = [self.revision]
        self.write_key()
        self.payload = {
            "version": 1,
            "workflow_revision_id": self.revision,
            "project_id": 100,
            "workspace_id": 100,
            "source": {
                "repository_id": "repo",
                "commit_sha": "a" * 40,
                "origin": "webhook",
            },
            "inputs": {},
            "idempotency_key": "one",
        }
        self.counter = 0

    def write_key(self):
        raw = json.dumps({"version": 1, "keys": [self.key]}).encode()
        Path(config.settings.trigger_keys_path).write_bytes(raw)
        setting = patch(
            "config.settings",
            replace(
                config.settings,
                trigger_keys_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
            ),
        )
        setting.start()
        self.addCleanup(setting.stop)

    def signed(
        self,
        payload=None,
        *,
        nonce=None,
        path="/api/v1/infra-automation/triggers/webhook",
        body=None,
    ):
        self.counter += 1
        fields = dict(
            key_id="key-one",
            method="POST",
            path=path,
            timestamp=str(int(self.now.timestamp())),
            nonce=nonce or f"nonce-{self.counter:024}",
            body=body or json.dumps(payload or self.payload).encode(),
        )
        proof = authority.TriggerAuthority(
            **fields,
            signature=sign_request(secret=self.secret, **fields),
            session_factory=self.factory,
            now=lambda: self.now,
        )
        proof.reserve_nonce()
        return proof

    def admit(self, payload=None, **kwargs):
        value = payload or self.payload
        proof = self.signed(value, **kwargs)
        with proof.credentials():
            return intake.request_trigger(
                TriggerRequest.model_validate(value),
                registry=AvailableHandlers(),
                registry_contract=self.registry,
            )

    def test_machine_admission_replay_and_live_effects_keep_nonhuman_identity(self):
        first = self.admit()
        self.assertEqual(self.admit()["id"], first["id"])
        self.assertEqual(first["origin"]["principal_type"], "service")
        self.assertEqual(first["origin"]["kind"], "webhook")
        with self.factory() as db:
            run = get_run(db, first["id"])
            stamp = engine._document(run).authority
            self.assertIs(type(stamp), MachineAuthorityStamp)
            self.assertLessEqual(
                run.deadline_at,
                authority._instant(self.key["expires_at"]).replace(tzinfo=None),
            )
        with self.credentials(), auth.authorized_session() as db:
            check_live_policy(db, stamp, "claim")
            with (
                patch.dict(os.environ, {"SYNTHETIC_TRIGGER_KEY": (b"x" * 32).hex()}),
                self.assertRaises(auth.TrustedAuthorizationError),
            ):
                check_live_policy(db, stamp, "claim")
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationRun)), 1
            )

    def test_reencoded_body_conflicts_with_reused_operation_but_nonce_is_consumed(self):
        self.admit()
        with self.assertRaises(LifecycleError) as error:
            self.admit(body=json.dumps(self.payload, separators=(",", ":")).encode())
        self.assertEqual(error.exception.status_code, 409)
        with self.factory() as db:
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(InfraAutomationTriggerNonce)
                ),
                2,
            )

    def test_pinning_scope_and_unknown_inputs_schedule_nothing(self):
        for changes in (
            {"project_id": 200},
            {"workspace_id": 101},
            {"inputs": {"unknown": "value"}},
            {
                "source": {
                    "repository_id": "repo",
                    "commit_sha": "b" * 40,
                    "origin": "webhook",
                }
            },
        ):
            with (
                self.subTest(changes=changes),
                self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)),
            ):
                self.admit({**self.payload, **changes})
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationRun)), 0
            )

    def test_nonce_concurrency_and_restart_have_one_winner(self):
        def reserve(_):
            try:
                self.signed(nonce="r" * 24)
                return True
            except LifecycleError:
                return False

        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(reserve, range(4))), 1)
        with self.assertRaises(LifecycleError):
            self.signed(nonce="r" * 24)

    def test_machine_reads_filter_key_sources_before_pages_and_rotation_breaks_cursor(
        self,
    ):
        run = self.admit()
        self.payload["idempotency_key"] = "two"
        self.admit()
        listing = TriggerListRequest(version=1, limit=1)
        proof = self.signed(
            listing.model_dump(mode="json"),
            path="/api/v1/infra-automation/triggers/list",
        )
        with proof.credentials():
            page = intake.signed_list(listing)
            self.assertEqual(len(page["items"]), 1)
            self.assertIsNotNone(page["cursor"]["next_cursor"])
        status_request = TriggerStatusRequest(version=1, run_id=run["id"])
        proof = self.signed(
            status_request.model_dump(mode="json"),
            path="/api/v1/infra-automation/triggers/status",
        )
        with proof.credentials():
            self.assertEqual(intake.signed_status(status_request)["id"], run["id"])
        self.key["allowed_sources"] = [
            {"repository_id": "other", "commit_sha": "a" * 40}
        ]
        self.write_key()
        listing = TriggerListRequest(version=1)
        proof = self.signed(
            listing.model_dump(mode="json"),
            path="/api/v1/infra-automation/triggers/list",
        )
        with proof.credentials():
            self.assertEqual(intake.signed_list(listing)["items"], [])
        proof = self.signed(
            status_request.model_dump(mode="json"),
            path="/api/v1/infra-automation/triggers/status",
        )
        with proof.credentials(), self.assertRaises(auth.TrustedAuthorizationError):
            intake.signed_status(status_request)
        listing = TriggerListRequest(
            version=1, limit=1, cursor=page["cursor"]["next_cursor"]
        )
        proof = self.signed(
            listing.model_dump(mode="json"),
            path="/api/v1/infra-automation/triggers/list",
        )
        with proof.credentials(), self.assertRaises(LifecycleError):
            intake.signed_list(listing)

    def test_human_stamp_roundtrip_has_no_machine_default_fields(self):
        values = dict(
            version=1,
            workflow_id="w",
            revision_id="r",
            project_id=100,
            workspace_id=100,
            principal_id="human-a",
            authentication_version=1,
            membership_version=1,
            authorization_epoch=1,
            restore_epoch=1,
            policy_digest=D,
            advisory_policy_digest=D,
        )
        stamp = decode_authority(values)
        self.assertIs(type(stamp), AuthorityStamp)
        self.assertEqual(stamp.model_dump(), values)

    def test_project_wide_publication_uses_concrete_signed_workspace(self):
        definition = {
            "workflow_version": 2,
            "project_id": "100",
            "workspace_id": None,
            "environment": "dev",
            "inputs": {},
            "steps": [
                {
                    "id": "collect",
                    "kind": "admitted_collection",
                    "depends_on": [],
                    "source": {
                        "kind": "collected",
                        "repository_id": "repo",
                        "commit_sha": "a" * 40,
                        "profile_digest": D,
                    },
                }
            ],
        }
        workflow, revision = snapshots.WorkflowSnapshotTests.publish_fixture(
            self, definition, workspace_id=None
        )
        self.key["allowed_revision_ids"].append(revision)
        self.write_key()
        self.payload["workflow_revision_id"] = revision
        run = self.admit()
        self.assertEqual(run["workspace_id"], 100)
        listing = TriggerListRequest(version=1, workflow_id=workflow)
        proof = self.signed(
            listing.model_dump(mode="json"),
            path="/api/v1/infra-automation/triggers/list",
        )
        with proof.credentials():
            self.assertEqual(intake.signed_list(listing)["items"][0]["id"], run["id"])

    def test_global_clock_prevents_expired_key_effects_reviving_after_rollback(self):
        run = self.admit()
        with self.factory() as db:
            stamp = engine._document(get_run(db, run["id"])).authority
        original_now = self.now
        other = {
            **self.key,
            "key_id": "key-two",
            "expires_at": (self.now + timedelta(hours=3)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        }
        raw = json.dumps({"version": 1, "keys": [self.key, other]}).encode()
        Path(config.settings.trigger_keys_path).write_bytes(raw)
        with patch(
            "config.settings",
            replace(
                config.settings,
                trigger_keys_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
            ),
        ):
            self.now += timedelta(hours=2)
            fields = dict(
                key_id="key-two",
                method="POST",
                path="/api/v1/infra-automation/triggers/list",
                timestamp=str(int(self.now.timestamp())),
                nonce="later-key-nonce-000000000",
                body=b'{"version":1}',
            )
            proof = authority.TriggerAuthority(
                **fields,
                signature=sign_request(secret=self.secret, **fields),
                session_factory=self.factory,
                now=lambda: self.now,
            )
            proof.reserve_nonce()
            self.now = original_now
            with self.credentials(), auth.authorized_session() as db:
                for operation in ("claim", "dispatch", "consume"):
                    with (
                        self.subTest(operation=operation),
                        self.assertRaises(LifecycleError),
                    ):
                        check_live_policy(db, stamp, operation)
            with self.assertRaises(LifecycleError):
                self.signed()

    def test_service_payload_and_operation_cannot_diverge_from_signed_bytes(self):
        proof = self.signed()
        altered = {**self.payload, "idempotency_key": "unsigned-change"}
        with proof.credentials(), self.assertRaises(LifecycleError):
            intake.request_trigger(
                TriggerRequest.model_validate(altered),
                registry=AvailableHandlers(),
                registry_contract=self.registry,
            )
        proof = self.signed(path="/api/v1/infra-automation/triggers/validate")
        with proof.credentials(), self.assertRaises(LifecycleError):
            intake.request_trigger(
                TriggerRequest.model_validate(self.payload),
                registry=AvailableHandlers(),
                registry_contract=self.registry,
            )
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationRun)), 0
            )

    def test_known_signing_key_cannot_enter_snapshot_through_decoded_values(self):
        definition = {
            "workflow_version": 2,
            "project_id": "100",
            "workspace_id": "100",
            "environment": "dev",
            "inputs": {"note": {"type": "string", "max_length": 128}},
            "steps": [
                {
                    "id": "collect",
                    "kind": "admitted_collection",
                    "depends_on": [],
                    "source": {
                        "kind": "collected",
                        "repository_id": "repo",
                        "commit_sha": "a" * 40,
                        "profile_digest": D,
                    },
                }
            ],
        }
        _, revision = snapshots.WorkflowSnapshotTests.publish_fixture(self, definition)
        self.key["allowed_revision_ids"].append(revision)
        self.write_key()
        for value in (
            self.secret.hex(),
            self.secret.hex().upper(),
            "".join(
                c.upper() if (i // 2) % 2 else c
                for i, c in enumerate(self.secret.hex())
            ),
            self.secret.decode(),
        ):
            payload = {
                **self.payload,
                "workflow_revision_id": revision,
                "inputs": {"note": value},
            }
            escaped = (
                json.dumps(payload)
                .replace(value, "".join("\\u%04x" % ord(c) for c in value))
                .encode()
            )
            with (
                self.subTest(form=len(value)),
                self.assertRaises(LifecycleError) as caught,
            ):
                self.admit(payload, body=escaped)
            self.assertNotIn(value, str(caught.exception))
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationRun)), 0
            )
