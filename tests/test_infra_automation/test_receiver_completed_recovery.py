"""Completed-only reference receiver recovery; synthetic authenticated server port."""

from __future__ import annotations

import hashlib
import hmac
import json
import unittest
from unittest.mock import patch

from infra_automation.receiver_custody import canonical, digest
from infra_automation.receiver_http_contracts import (
    CallbackEnvelope,
    callback_signing_bytes,
)
from infra_automation.receiver_runtime import ReferenceReceiver, ReceiverConflict
from tests.test_infra_automation import test_receiver_runtime as fixture

RECOVERY_SECRET = b"receiver-reconcile-v1-" + b"a" * 43
ROTATED_SECRET = b"receiver-reconcile-v1-" + b"b" * 43


class RecoveryServer:
    """Only authenticated status/terminal callbacks exist on this test channel."""

    def __init__(self, original, secret):
        self.original = original
        self.secret = secret
        self.sends = 0
        self.lost_reply = False
        self.status_unavailable = False
        self.override = None

    def bootstrap(self, *args):
        raise AssertionError("Recovery cannot bootstrap")

    def consume(self, *args):
        raise AssertionError("Recovery cannot consume")

    def authorize_action(self, *args):
        raise AssertionError("Recovery cannot authorize action")

    def status(self, operation_id):
        if self.status_unavailable:
            raise ConnectionError("Synthetic status unavailable")
        value = self.original.status(operation_id)
        with self.original.connection() as db:
            callback = db.execute("SELECT envelope FROM callbacks").fetchone()
        if callback:
            value["state"] = json.loads(callback[0])["message"]["state"]
        return self.override(value) if self.override else value

    def callback(self, envelope):
        self.sends += 1
        parsed = CallbackEnvelope.model_validate(envelope)
        expected = (
            "sha256:"
            + hmac.new(
                self.secret, callback_signing_bytes(parsed), hashlib.sha256
            ).hexdigest()
        )
        if not hmac.compare_digest(expected, parsed.signature):
            raise ValueError("Rotated recovery credential")
        if parsed.message.operation != "outcome" or parsed.message.state not in {
            "succeeded",
            "failed",
        }:
            raise ValueError("Recovery callback ceiling")
        with self.original.connection() as db:
            if db.execute("SELECT 1 FROM callbacks").fetchone():
                raise ValueError("No callback replay")
            db.execute(
                "INSERT INTO callbacks VALUES(?)",
                (canonical(parsed.model_dump(mode="json")),),
            )
        if self.lost_reply:
            self.status_unavailable = True
            raise ConnectionError("Lost terminal reply")
        return self.status(parsed.operation_id)


class CompletedRecoveryTests(unittest.TestCase):
    setUp = fixture.RuntimeTests.setUp
    run_receiver = fixture.RuntimeTests.run_receiver
    calls = fixture.RuntimeTests.calls

    def complete_without_delivery(self):
        with patch.object(
            self.server, "callback", side_effect=ConnectionError("No delivery")
        ):
            with self.assertRaises(ConnectionError):
                self.run_receiver()
        with self.receiver._ledger() as db:
            row = db.execute("SELECT * FROM operations").fetchone()
            self.assertEqual(row["phase"], "complete")
            return row["callback"]

    def recovery_receiver(self, secret=RECOVERY_SECRET):
        server = RecoveryServer(self.server, secret)
        return ReferenceReceiver(self.root, server, secret), server

    def test_completed_outcome_resigns_same_event_without_any_action_port(self):
        original = self.complete_without_delivery()
        receiver, server = self.recovery_receiver()
        with patch.object(
            receiver.custody,
            "verify",
            side_effect=AssertionError("No custody admission"),
        ):
            result = receiver.recover_completed(
                self.message.operation_id, self.message.binding_digest
            )
        self.assertEqual(result["counted_actions"], 1)
        self.assertTrue(result["callback_delivered"])
        self.assertEqual(server.sends, 1)
        with receiver._ledger() as db:
            self.assertEqual(
                db.execute("SELECT callback FROM operations").fetchone()[0], original
            )
            candidate = db.execute("SELECT envelope FROM recovery_outbox").fetchone()[0]
        before, after = json.loads(original), json.loads(candidate)
        self.assertNotEqual(before.pop("signature"), after.pop("signature"))
        self.assertEqual(before, after)
        self.assertNotIn(RECOVERY_SECRET, (self.root / "receiver.sqlite3").read_bytes())

    def test_original_accepted_ack_recovered_with_status_only_after_restart(self):
        self.server.fail_callback = True
        self.server.fail_ack_recovery = True
        with self.assertRaises(ConnectionError):
            self.run_receiver()
        self.server.fail_callback = False
        self.server.fail_ack_recovery = False
        receiver, server = self.recovery_receiver()
        result = receiver.recover_completed(
            self.message.operation_id, self.message.binding_digest
        )
        self.assertTrue(result["callback_delivered"])
        self.assertEqual(server.sends, 0)
        with receiver._ledger() as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM recovery_outbox").fetchone()[0], 0
            )

    def test_lost_recovery_reply_then_rotation_recognizes_exact_candidate(self):
        self.complete_without_delivery()
        receiver, server = self.recovery_receiver()
        server.lost_reply = True
        with self.assertRaises(ConnectionError):
            receiver.recover_completed(
                self.message.operation_id, self.message.binding_digest
            )
        receiver, rotated = self.recovery_receiver(ROTATED_SECRET)
        result = receiver.recover_completed(
            self.message.operation_id, self.message.binding_digest
        )
        self.assertTrue(result["callback_delivered"])
        self.assertEqual(result["counted_actions"], 1)
        self.assertEqual(rotated.sends, 0)
        with receiver._ledger() as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM recovery_outbox").fetchone()[0], 1
            )

    def test_unfinished_or_uncertain_phase_never_becomes_completed(self):
        self.complete_without_delivery()
        receiver, server = self.recovery_receiver()
        for phase in ("intent", "received", "action_started", "reconcile"):
            with self.subTest(phase=phase):
                with receiver._ledger() as db:
                    db.execute("UPDATE operations SET phase=?", (phase,))
                    db.commit()
                with self.assertRaises(ReceiverConflict):
                    receiver.recover_completed(
                        self.message.operation_id, self.message.binding_digest
                    )
                self.assertEqual(server.sends, 0)

    def test_terminal_conflicting_ack_never_resigns_or_sends(self):
        self.complete_without_delivery()
        receiver, server = self.recovery_receiver()
        server.override = lambda value: {
            **value,
            "state": "succeeded",
            "callback_ack": {
                "sequence": 1,
                "nonce": "different",
                "envelope_digest": digest(b"different"),
            },
        }
        with self.assertRaises(ReceiverConflict):
            receiver.recover_completed(
                self.message.operation_id, self.message.binding_digest
            )
        self.assertEqual(server.sends, 0)
        with receiver._ledger() as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM recovery_outbox").fetchone()[0], 0
            )

    def test_changed_binding_receipt_or_marker_denies(self):
        self.complete_without_delivery()
        receiver, server = self.recovery_receiver()
        with self.assertRaises(ReceiverConflict):
            receiver.recover_completed(self.message.operation_id, digest(b"wrong"))
        original_status = server.status
        server.status = lambda operation_id: {
            **original_status(operation_id),
            "receipt": None,
        }
        with self.assertRaises(ReceiverConflict):
            receiver.recover_completed(
                self.message.operation_id, self.message.binding_digest
            )
        server.status = original_status
        with receiver._ledger() as db:
            db.execute(
                "UPDATE synthetic_markers SET artifact_digest=?", (digest(b"wrong"),)
            )
            db.commit()
        with self.assertRaises(ReceiverConflict):
            receiver.recover_completed(
                self.message.operation_id, self.message.binding_digest
            )
        self.assertEqual(server.sends, 0)

    def test_process_restart_after_terminal_delivery_recognizes_prior_rotation(self):
        import subprocess
        import sys

        original = self.complete_without_delivery()
        code = """
import json,os,sys
from pathlib import Path
from infra_automation.receiver_runtime import ReferenceReceiver
from tests.test_infra_automation.test_receiver_runtime import Server
from tests.test_infra_automation.test_receiver_completed_recovery import RecoveryServer,RECOVERY_SECRET,ROTATED_SECRET
root=Path(sys.argv[1])
secret=RECOVERY_SECRET if sys.argv[2]=='crash' else ROTATED_SECRET
server=RecoveryServer(Server(root),secret)
def checkpoint(name):
    if sys.argv[2]=='crash' and name=='recovery_callback':
        os._exit(73)
receiver=ReferenceReceiver(root/'receiver',server,secret,checkpoint=checkpoint)
spec=json.loads((root/'bootstrap.json').read_text())
result=receiver.recover_completed(spec['message']['operation_id'],spec['message']['binding_digest'])
print(json.dumps({'actions':result['counted_actions'],'delivered':result['callback_delivered'],'sends':server.sends}))
"""
        crashed = subprocess.run(
            [sys.executable, "-c", code, str(self.directory), "crash"],
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(crashed.returncode, 73, crashed.stderr.decode())
        recovered = subprocess.run(
            [sys.executable, "-c", code, str(self.directory), "recover"],
            capture_output=True,
            timeout=20,
            check=True,
        )
        self.assertEqual(
            json.loads(recovered.stdout), {"actions": 1, "delivered": True, "sends": 0}
        )
        with self.receiver._ledger() as db:
            self.assertEqual(
                db.execute("SELECT callback FROM operations").fetchone()[0], original
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM recovery_outbox").fetchone()[0], 1
            )

    def test_outbox_limit_denies_new_signature_but_preserves_exact_ack_recovery(self):
        original_raw = self.complete_without_delivery()
        original = json.loads(original_raw)
        receiver, server = self.recovery_receiver()
        candidates = []
        with receiver._ledger() as db:
            for index in range(1, 101):
                value = dict(original)
                value["signature"] = (
                    "sha256:"
                    + hmac.new(
                        ("synthetic-candidate-key-" + str(index)).encode(),
                        callback_signing_bytes(original),
                        hashlib.sha256,
                    ).hexdigest()
                )
                raw = canonical(value)
                candidates.append(raw)
                db.execute(
                    "INSERT INTO recovery_outbox VALUES(?,?,?,?)",
                    (self.message.operation_id, index, digest(raw), raw),
                )
            db.commit()
        with self.assertRaises(ReceiverConflict):
            receiver.recover_completed(
                self.message.operation_id, self.message.binding_digest
            )
        self.assertEqual(server.sends, 0)
        with self.server.connection() as db:
            db.execute("INSERT INTO callbacks VALUES(?)", (candidates[0],))
        result = receiver.recover_completed(
            self.message.operation_id, self.message.binding_digest
        )
        self.assertTrue(result["callback_delivered"])
        self.assertEqual(server.sends, 0)

    def test_unavailable_status_cannot_create_a_candidate_or_send(self):
        self.complete_without_delivery()
        receiver, server = self.recovery_receiver()
        server.status_unavailable = True
        with self.assertRaises(ConnectionError):
            receiver.recover_completed(
                self.message.operation_id, self.message.binding_digest
            )
        self.assertEqual(server.sends, 0)
        with receiver._ledger() as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM recovery_outbox").fetchone()[0], 0
            )

    def test_saved_plan_receipt_recovers_without_reopening_custody(self):
        from infra_automation.receiver_protocol import (
            ReceiverMessage,
            receiver_binding_digest,
        )

        payload = {"version": 1, "receiver_action": "saved_plan_receipt"}
        binding = self.message.binding.model_dump(mode="json")
        binding["payload_digest"] = digest(canonical(payload))
        self.message = ReceiverMessage.model_validate(
            {
                **self.message.model_dump(mode="json"),
                "binding": binding,
                "binding_digest": receiver_binding_digest(binding),
            }
        )
        spec = json.loads((self.directory / "bootstrap.json").read_text())
        spec.update(message=self.message.model_dump(mode="json"), payload=payload)
        (self.directory / "bootstrap.json").write_text(json.dumps(spec))
        self.server = fixture.Server(self.directory)
        self.receiver = ReferenceReceiver(
            self.root, self.server, fixture.SECRET, action_mode="saved_plan_receipt"
        )
        self.complete_without_delivery()
        server = RecoveryServer(self.server, RECOVERY_SECRET)
        receiver = ReferenceReceiver(
            self.root, server, RECOVERY_SECRET, action_mode="saved_plan_receipt"
        )
        with patch.object(
            receiver.custody,
            "verify",
            side_effect=AssertionError("No new custody access"),
        ):
            result = receiver.recover_completed(
                self.message.operation_id, self.message.binding_digest
            )
        self.assertTrue(result["callback_delivered"])
        self.assertEqual(result["verified_plan_receipts"], 1)
        self.assertFalse(result["deployment_performed"])
        self.assertEqual(result["counted_actions"], 0)


if __name__ == "__main__":
    unittest.main()
