"""Restored receiver reconciliation over actual migration and synthetic effects."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from infra_automation.handoff import ReceiverCredential
from infra_automation.lifecycle import LifecycleError
from infra_automation.operator_recovery import RecoveryStore
from models.database import Base
from services import infra_automation_receiver_recovery as recovery
from services import project_service as auth
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_handoff_service as fixture
from tests.test_infra_automation import test_receiver_reconciliation as callbacks


class ReceiverRecoveryTests(LifecycleCase):
    enable = fixture.HandoffServiceTests.enable
    publish_fixture = fixture.HandoffServiceTests.publish_fixture
    deliver = fixture.HandoffServiceTests.deliver
    request = fixture.HandoffServiceTests.request
    prepare = fixture.HandoffServiceTests.prepare
    dispatch = fixture.HandoffServiceTests.dispatch
    callback = callbacks.ReceiverReconciliationTests.callback

    def setUp(self):
        from alembic import command
        from alembic.config import Config

        seed_guards = []

        def migrate(bind):
            bind.url = bind.url.set(database=str(Path(bind.url.database).resolve()))
            cfg = Config("alembic.ini")
            with patch.dict(os.environ, {"DATABASE_URL": str(bind.url)}):
                command.upgrade(cfg, "head")
            # Shared collected-material fixtures directly populate synthetic
            # engine states without its CAS API. Disable guards only for that
            # fixture seeding, then reinstall the exact actual migration SQL
            # before any tested service call, backup or restore.
            with bind.begin() as db:
                seed_guards.extend(
                    db.exec_driver_sql(
                        "SELECT name, sql FROM sqlite_master WHERE type='trigger'"
                    ).all()
                )
                for name, _ in seed_guards:
                    db.exec_driver_sql(f'DROP TRIGGER "{name}"')

        with patch.object(Base.metadata, "create_all", side_effect=migrate):
            fixture.HandoffServiceTests.setUp(self)
        with self.engine.begin() as db:
            for name, sql in seed_guards:
                db.exec_driver_sql(f'DROP TRIGGER IF EXISTS "{name}"')
                db.exec_driver_sql(sql)
        self.base = Path(self.temp.name).resolve()
        self.dbpath = self.base / "lifecycle.db"
        self.dbpath.chmod(0o600)
        roots = {}
        for role in ("artifacts", "custody"):
            root = self.base / role
            root.mkdir(mode=0o700)
            roots[role] = root
        self.store = RecoveryStore(self.base / "control")
        self.store.initialize(self.dbpath, roots)
        configured = patch(
            "infra_automation.operator_recovery.configured_store",
            return_value=self.store,
        )
        configured.start()
        self.addCleanup(configured.stop)
        clock = patch.object(recovery, "_now", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.operation = self.prepare()
        self.dispatch(self.operation)
        sent = self.sent[0]
        if not getattr(self, "defer_consumption", False):
            self.handoffs.consume(sent.message_bytes, sent.grant_token, self.receiver)

    def restored(self):
        self.engine.dispose()
        backup = self.base / "snapshot"
        self.store.backup(backup)
        self.store.restore(backup)
        # Use actual one-use host recovery and fresh session issuance.
        self.now += timedelta(seconds=2)
        recovery_credential = self.identity.issue_recovery_credential("human-a")
        self.identity.recover(
            recovery_credential.token.get_secret_value(), "synthetic-fresh-password"
        )
        issued = self.identity.login("human-a", "synthetic-fresh-password")
        self.tokens["human-a"] = (
            issued.token.get_secret_value(),
            issued.csrf_token.get_secret_value(),
        )

    def issue(self):
        with self.credentials():
            return recovery.issue_credential(
                self.store,
                self.operation["id"],
                "Reconcile exact retained receiver operation",
            )

    def credential(self):
        return ReceiverCredential(
            self.receiver.receiver_id, self.issue().token.get_secret_value()
        )

    def signed(self, credential, **kwargs):
        import hashlib
        import hmac
        from infra_automation.receiver_http_contracts import callback_signing_bytes

        envelope = self.callback(self.operation, **kwargs)
        signature = (
            "sha256:"
            + hmac.new(
                credential.secret.encode(),
                callback_signing_bytes(envelope),
                hashlib.sha256,
            ).hexdigest()
        )
        return envelope.model_copy(update={"signature": signature})

    def test_actual_restore_fresh_reconciliation_never_restores_action_authority(self):
        self.restored()
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.handoffs.receiver_status(self.operation["id"], self.receiver)
        issued = self.issue()
        credential = ReceiverCredential(
            self.receiver.receiver_id, issued.token.get_secret_value()
        )
        view = self.handoffs.receiver_status(self.operation["id"], credential)
        self.assertEqual(view["state"], "consumed")
        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.handoffs.authorize_action(self.operation["id"], credential)
        terminal = self.signed(credential, state="failed")
        result = self.handoffs.callback(terminal, credential)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["receipt"], view["receipt"])
        self.assertEqual(len(self.sent), 1)
        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.handoffs.callback(terminal, credential)

    def test_recovery_token_cannot_bootstrap_consume_unsigned_terminal_or_progress(
        self,
    ):
        self.restored()
        credential = self.credential()
        for call in (
            lambda: self.handoffs.bootstrap(
                self.operation["id"],
                self.operation["receiver_binding_digest"],
                credential,
            ),
            lambda: self.handoffs.consume(
                self.sent[0].message_bytes, self.sent[0].grant_token, credential
            ),
            lambda: self.handoffs.authorize_action(self.operation["id"], credential),
            lambda: self.handoffs.resolve_terminal(
                self.signed(credential).message, credential
            ),
            lambda: self.handoffs.callback(
                self.signed(credential, state="running"), credential
            ),
        ):
            with (
                self.subTest(call=call),
                self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)),
            ):
                call()
        self.assertEqual(
            self.handoffs.receiver_status(self.operation["id"], credential)["state"],
            "consumed",
        )

    def test_rotation_invalidates_old_hash_without_persisting_bearer(self):
        from models.receiver_recovery import ReceiverRecoveryCredential

        self.restored()
        first = self.credential()
        second = self.credential()
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.handoffs.receiver_status(self.operation["id"], first)
        self.assertEqual(
            self.handoffs.receiver_status(self.operation["id"], second)["state"],
            "consumed",
        )
        with self.factory() as db:
            row = db.get(ReceiverRecoveryCredential, self.operation["id"])
            self.assertEqual(row.issue_count, 2)
            self.assertEqual(row.version, 2)
            self.assertNotIn(
                first.secret,
                repr(
                    {
                        column.name: getattr(row, column.name)
                        for column in row.__table__.columns
                    }
                ),
            )
            self.assertNotIn(
                second.secret,
                repr(
                    {
                        column.name: getattr(row, column.name)
                        for column in row.__table__.columns
                    }
                ),
            )

    def test_terminal_lost_ack_after_restore_is_status_only(self):
        from models.receiver_recovery import ReceiverRecoveryCredential

        accepted = self.callback(self.operation)
        self.handoffs.callback(accepted, self.receiver)
        self.restored()
        credential = self.credential()
        view = self.handoffs.receiver_status(self.operation["id"], credential)
        self.assertEqual(view["state"], "succeeded")
        self.assertEqual(view["callback_ack"]["nonce"], accepted.nonce)
        with self.factory() as db:
            self.assertEqual(
                db.get(ReceiverRecoveryCredential, self.operation["id"]).mode,
                "status_only",
            )
        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.handoffs.callback(self.signed(credential, state="failed"), credential)

    def test_ready_phase_and_reflected_secret_reason_cannot_issue(self):
        with self.credentials(), self.assertRaises(LifecycleError):
            self.issue()
        self.restored()
        with self.credentials(), self.assertRaises(LifecycleError) as error:
            recovery.issue_credential(
                self.store, self.operation["id"], "Lost " + recovery.PREFIX + "a" * 64
            )
        self.assertEqual(error.exception.status_code, 422)

    def test_exact_expiry_backward_clock_and_receiver_generation_deny(self):
        from models.tables import IdentityAccount

        self.restored()
        issued = self.issue()
        credential = ReceiverCredential(
            self.receiver.receiver_id, issued.token.get_secret_value()
        )
        original = self.now
        self.now = issued.expires_at
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.handoffs.receiver_status(self.operation["id"], credential)
        self.now = original - timedelta(seconds=1)
        with self.assertRaises(LifecycleError):
            self.handoffs.receiver_status(self.operation["id"], credential)
        self.now = original
        with self.factory.begin() as db:
            db.get(IdentityAccount, "receiver-actor").authentication_version += 1
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.handoffs.receiver_status(self.operation["id"], credential)

    def test_revoked_issuer_membership_cannot_leave_a_recovery_credential_live(self):
        from models.repositories import project_memberships

        self.restored()
        credential = self.credential()
        with self.factory.begin() as db:
            project_memberships.revoke_membership(
                db, principal_id="human-a", project_id=100, now=self.now
            )
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.handoffs.receiver_status(self.operation["id"], credential)

    def test_quota_and_late_audit_failure_roll_back_rotation(self):
        from models.receiver_recovery import ReceiverRecoveryCredential

        self.restored()
        first = self.credential()
        for target, exception in (
            ("claims._charge", LifecycleError(429)),
            ("support.append_audit", RuntimeError("synthetic audit fault")),
        ):
            with patch.object(
                recovery.claims if target.startswith("claims") else recovery.support,
                target.split(".")[1],
                side_effect=exception,
            ):
                with self.assertRaises(type(exception)):
                    self.issue()
            with self.factory() as db:
                self.assertEqual(
                    db.get(ReceiverRecoveryCredential, self.operation["id"]).version, 1
                )
            self.assertEqual(
                self.handoffs.receiver_status(self.operation["id"], first)["state"],
                "consumed",
            )

    def test_again_restore_invalidates_token_even_when_original_operation_is_retained(
        self,
    ):
        self.restored()
        credential = self.credential()
        self.handoffs.callback(self.signed(credential, state="failed"), credential)
        with self.credentials():
            self.store.complete("Completed exact retained receiver reconciliation")
        self.engine.dispose()
        backup = self.base / "second-snapshot"
        self.store.backup(backup)
        self.store.restore(backup)
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.handoffs.receiver_status(self.operation["id"], credential)

    def test_expiry_during_callback_hmac_rolls_back_fact_lock_and_outcome(self):
        from infra_automation import receiver_http_contracts
        from models.tables import InfraAutomationExternalFact, InfraAutomationHandoff
        from sqlalchemy import select

        self.restored()
        issued = self.issue()
        credential = ReceiverCredential(
            self.receiver.receiver_id, issued.token.get_secret_value()
        )
        envelope = self.signed(credential, state="failed")
        signing_bytes = receiver_http_contracts.callback_signing_bytes

        def slow_signing(value):
            result = signing_bytes(value)
            self.now = issued.expires_at
            return result

        with (
            patch.object(
                receiver_http_contracts,
                "callback_signing_bytes",
                side_effect=slow_signing,
            ),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            self.handoffs.callback(envelope, credential)
        with self.factory() as db:
            self.assertEqual(
                db.get(InfraAutomationHandoff, self.operation["id"]).state, "consumed"
            )
            self.assertIsNone(
                db.scalar(
                    select(InfraAutomationExternalFact).where(
                        InfraAutomationExternalFact.kind == "callback"
                    )
                )
            )

    def test_expired_status_and_terminal_token_cannot_revive_after_clock_rollback(self):
        self.restored()
        issued = self.issue()
        credential = ReceiverCredential(
            self.receiver.receiver_id, issued.token.get_secret_value()
        )
        envelope = self.signed(credential, state="failed")
        self.now = issued.expires_at
        for call in (
            lambda: self.handoffs.receiver_status(self.operation["id"], credential),
            lambda: self.handoffs.callback(envelope, credential),
        ):
            with (
                self.subTest(call=call),
                self.assertRaises(auth.TrustedAuthorizationError),
            ):
                call()
        self.now -= timedelta(seconds=1)
        for call in (
            lambda: self.handoffs.receiver_status(self.operation["id"], credential),
            lambda: self.handoffs.callback(envelope, credential),
        ):
            with self.subTest(call=call), self.assertRaises(LifecycleError):
                call()

    def test_expiry_during_terminal_audit_rolls_back_already_staged_terminal(self):
        from models.tables import InfraAutomationHandoff
        from models.repositories import infra_automation_targets

        self.restored()
        issued = self.issue()
        credential = ReceiverCredential(
            self.receiver.receiver_id, issued.token.get_secret_value()
        )
        original = self.handoffs._audit

        def slow_audit(*args, **kwargs):
            result = original(*args, **kwargs)
            self.now = issued.expires_at
            return result

        with (
            patch.object(self.handoffs, "_audit", side_effect=slow_audit),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            self.handoffs.callback(self.signed(credential, state="failed"), credential)
        with self.factory() as db:
            self.assertEqual(
                db.get(InfraAutomationHandoff, self.operation["id"]).state, "consumed"
            )
            self.assertEqual(
                infra_automation_targets.get_lock(db, "held-lock").status, "held"
            )

    def test_parallel_rotation_has_one_current_hash_and_wrong_audience_does_not_match(
        self,
    ):
        from concurrent.futures import ThreadPoolExecutor

        self.restored()
        with ThreadPoolExecutor(max_workers=2) as pool:
            issued = list(pool.map(lambda _: self.issue(), range(2)))
        accepted = 0
        for item in issued:
            credential = ReceiverCredential(
                self.receiver.receiver_id, item.token.get_secret_value()
            )
            try:
                self.handoffs.receiver_status(self.operation["id"], credential)
                accepted += 1
            except auth.TrustedAuthorizationError:
                pass
            for wrong in (
                ReceiverCredential("another-receiver", credential.secret),
                ReceiverCredential(
                    credential.receiver_id, credential.secret, audience="human"
                ),
            ):
                with (
                    self.subTest(wrong=wrong),
                    self.assertRaises(auth.TrustedAuthorizationError),
                ):
                    self.handoffs.receiver_status(self.operation["id"], wrong)
        self.assertEqual(accepted, 1)

    def test_wrong_verifier_never_advances_clock_and_project_restore_epoch_invalidates(
        self,
    ):
        from infra_automation.lifecycle import AdvanceEpochRequest
        from services import infra_automation_policy

        self.restored()
        credential = self.credential()
        original = self.now
        self.now += timedelta(days=1)
        wrong = ReceiverCredential(credential.receiver_id, recovery.PREFIX + "0" * 64)
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.handoffs.receiver_status(self.operation["id"], wrong)
        self.now = original
        self.assertEqual(
            self.handoffs.receiver_status(self.operation["id"], credential)["state"],
            "consumed",
        )
        with self.credentials():
            current = infra_automation_policy.get_settings(100)
            infra_automation_policy.advance_epoch(
                AdvanceEpochRequest(
                    project_id=100,
                    expected_version=current["version"],
                    reason="Invalidate project recovery credential",
                ),
                restore=True,
            )
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.handoffs.receiver_status(self.operation["id"], credential)


class ReceiverCompletedRestoreTests(LifecycleCase):
    enable = ReceiverRecoveryTests.enable
    publish_fixture = ReceiverRecoveryTests.publish_fixture
    deliver = ReceiverRecoveryTests.deliver
    request = ReceiverRecoveryTests.request
    prepare = ReceiverRecoveryTests.prepare
    dispatch = ReceiverRecoveryTests.dispatch
    restored = ReceiverRecoveryTests.restored
    issue = ReceiverRecoveryTests.issue

    def setUp(self):
        import hashlib

        self.synthetic_raw = b"deploywhisper-synthetic-v1\nrestored-receiver\n"
        digest = "sha256:" + hashlib.sha256(self.synthetic_raw).hexdigest()
        for target in (
            "tests.test_infra_automation.test_decision_service.D",
            "tests.test_infra_automation.test_approval_eligibility.DIGEST",
        ):
            context = patch(target, digest)
            context.start()
            self.addCleanup(context.stop)
        self.defer_consumption = True
        ReceiverRecoveryTests.setUp(self)

    def test_completed_receiver_recovers_signed_original_outcome_after_actual_restore(
        self,
    ):
        from dataclasses import replace
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.infra_automation_receiver import router
        from infra_automation.receiver_runtime import ReferenceReceiver
        from infra_automation.receiver_protocol import validate_receiver_message

        old_secret = "original-receiver-" + "x" * 32
        self.receiver = replace(self.receiver, secret=old_secret)
        settings = patch(
            "config.handoff_credentials",
            return_value={"receiver": old_secret, "github": "dispatch-secret"},
        )
        settings.start()
        self.addCleanup(settings.stop)
        service = patch(
            "services.infra_automation_handoffs._default_service", self.handoffs
        )
        service.start()
        self.addCleanup(service.stop)
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, base_url="https://receiver.invalid")
        self.addCleanup(client.close)

        class Port:
            secret = old_secret
            callbacks_offline = True
            actions = []

            def call(inner, operation_id, suffix, payload=None):
                inner.actions.append(suffix)
                path = f"/api/v1/infra-automation/handoffs/{operation_id}/{suffix}"
                headers = {
                    "authorization": "Bearer " + inner.secret,
                    "x-receiver-id": self.receiver.receiver_id,
                }
                response = (
                    client.get(path, headers=headers)
                    if payload is None
                    else client.post(path, json=payload, headers=headers)
                )
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Synthetic receiver HTTP {response.status_code}"
                    )
                return response.json()["data"]

            def bootstrap(inner, operation_id, digest):
                return inner.call(
                    operation_id, "receipt", {"version": 1, "binding_digest": digest}
                )

            def consume(inner, message, token):
                return inner.call(
                    message.operation_id,
                    "consume",
                    {
                        "version": 1,
                        "message": message.model_dump(mode="json"),
                        "grant_token": token,
                    },
                )

            def authorize_action(inner, operation_id):
                return inner.call(operation_id, "authorize-action", {"version": 1})

            def status(inner, operation_id):
                return inner.call(operation_id, "status")

            def callback(inner, envelope):
                if inner.callbacks_offline:
                    raise ConnectionError("Synthetic callback transport interruption")
                return inner.call(envelope["operation_id"], "outcome", envelope)

        port = Port()
        directory = self.base / "custody" / "receiver"
        receiver = ReferenceReceiver(directory, port, old_secret.encode())
        message = validate_receiver_message(self.sent[0].message_bytes)
        custody = message.binding.provenance.custody
        # The shared fixture advances its signed collection clock by one second.
        # Use that clock for publication, preserving the real custody guards.
        with patch(
            "infra_automation.receiver_custody.datetime", wraps=datetime
        ) as clock:
            clock.now.return_value = self.now
            receiver.custody.publish(
                custody.handle,
                self.synthetic_raw,
                message.binding.provenance.source.model_dump(mode="json"),
                custody.expires_at,
            )
        with self.assertRaises(ConnectionError):
            receiver.run(
                self.operation["id"], self.operation["receiver_binding_digest"]
            )
        before = len(port.actions)
        self.restored()
        issued = self.issue()
        port.secret = issued.token.get_secret_value()
        port.callbacks_offline = False
        restarted = ReferenceReceiver(directory, port, port.secret.encode())
        result = restarted.recover_completed(
            self.operation["id"], self.operation["receiver_binding_digest"]
        )
        self.assertEqual(result["counted_actions"], 1)
        self.assertTrue(result["callback_delivered"])
        self.assertTrue(set(port.actions[before:]) <= {"status", "outcome"})
        again = restarted.recover_completed(
            self.operation["id"], self.operation["receiver_binding_digest"]
        )
        self.assertEqual(again["counted_actions"], 1)
