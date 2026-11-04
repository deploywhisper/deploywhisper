"""Process-death and process-race qualification of the real durable receiver."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from infra_automation.receiver_custody import canonical, digest
from infra_automation.receiver_http_contracts import (
    CallbackEnvelope,
    callback_signing_bytes,
)
from infra_automation.receiver_protocol import ReceiverMessage, receiver_binding_digest
from infra_automation.receiver_runtime import ReferenceReceiver, ReceiverConflict
from tests.test_infra_automation.test_receiver_custody import binding_for

SECRET = b"synthetic-callback-secret-key-32-bytes"


class Server:
    """Authenticated test port with independently durable original server receipt."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.spec = json.loads((self.directory / "bootstrap.json").read_text())
        self.fail_callback = False
        self.fail_ack_recovery = False

    def connection(self):
        return sqlite3.connect(self.directory / "server.sqlite3")

    def bootstrap(self, operation_id, binding_digest):
        assert operation_id == self.spec["message"]["operation_id"]
        assert binding_digest == self.spec["message"]["binding_digest"]
        with self.connection() as db:
            db.execute("INSERT INTO calls VALUES('bootstrap')")
        return self.spec

    def consume(self, message, grant_token):
        assert grant_token == "never-store-grant"
        receipt = {
            **message.model_dump(mode="json"),
            "operation": "receipt",
            "sequence": 1,
        }
        with self.connection() as db:
            db.execute("INSERT INTO calls VALUES('consume')")
            db.execute("UPDATE authority SET receipt=?", (json.dumps(receipt),))
        return self.status(message.operation_id)

    def status(self, operation_id):
        with self.connection() as db:
            receipt, allowed = db.execute(
                "SELECT receipt,allowed FROM authority"
            ).fetchone()
            callback = db.execute("SELECT envelope FROM callbacks").fetchone()
        if callback and self.fail_ack_recovery:
            raise ConnectionError("Status unavailable after callback")
        ack = None
        if callback:
            envelope = json.loads(callback[0])
            ack = {
                "sequence": envelope["sequence"],
                "nonce": envelope["nonce"],
                "envelope_digest": digest(callback[0]),
            }
        return {
            "id": operation_id,
            "state": "consumed",
            "broken": False,
            "receiver_binding_digest": self.spec["message"]["binding_digest"],
            "receipt": json.loads(receipt) if receipt else None,
            "allowed": bool(allowed),
            "callback_ack": ack,
        }

    def authorize_action(self, operation_id):
        result = self.status(operation_id)
        with self.connection() as db:
            db.execute("INSERT INTO calls VALUES('authorize')")
        if not result["allowed"]:
            raise ValueError("Server disabled authority")
        return result

    def callback(self, envelope):
        envelope = CallbackEnvelope.model_validate(envelope).model_dump(mode="json")
        expected = (
            "sha256:"
            + hmac.new(
                SECRET, callback_signing_bytes(envelope), hashlib.sha256
            ).hexdigest()
        )
        assert hmac.compare_digest(expected, envelope["signature"])
        with self.connection() as db:
            previous = db.execute("SELECT envelope FROM callbacks").fetchone()
            if previous:
                assert previous[0] == canonical(envelope)
                raise ValueError("Server deliberately denies duplicate callbacks")
            else:
                db.execute("INSERT INTO callbacks VALUES(?)", (canonical(envelope),))
        if self.fail_callback:
            raise ConnectionError("Response lost after durable callback")
        return self.status(envelope["operation_id"])


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.root = self.directory / "receiver"
        receiver = ReferenceReceiver(self.root, None, SECRET)
        binding = binding_for(receiver.custody)
        self.payload = {"version": 1, "synthetic": True}
        value = binding.model_dump(mode="json")
        value["payload_digest"] = digest(canonical(self.payload))
        self.message = ReceiverMessage.model_validate(
            {
                "version": 1,
                "operation": "consume",
                "operation_id": "synthetic-operation",
                "audience": "receiver-operation-v1",
                "binding": value,
                "binding_digest": receiver_binding_digest(value),
                "sequence": 1,
                "state": "consumed",
            }
        )
        spec = {
            "message": self.message.model_dump(mode="json"),
            "payload": self.payload,
            "grant_token": "never-store-grant",
            "run_id": "synthetic-run",
        }
        (self.directory / "bootstrap.json").write_text(json.dumps(spec))
        with sqlite3.connect(self.directory / "server.sqlite3") as db:
            db.executescript(
                "CREATE TABLE authority(receipt TEXT,allowed INTEGER); INSERT INTO authority VALUES(NULL,1); CREATE TABLE calls(name TEXT); CREATE TABLE callbacks(envelope BLOB);"
            )
        self.server = Server(self.directory)
        self.receiver = ReferenceReceiver(self.root, self.server, SECRET)

    def run_receiver(self):
        return self.receiver.run(self.message.operation_id, self.message.binding_digest)

    def child(self, checkpoint=""):
        environment = dict(
            os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2])
        )
        return subprocess.Popen(
            [sys.executable, __file__, "--child", str(self.directory), checkpoint],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def calls(self, name):
        with self.server.connection() as db:
            return db.execute(
                "SELECT count(*) FROM calls WHERE name=?", (name,)
            ).fetchone()[0]

    def test_identical_replay_and_callback_retry_preserve_one_effect_and_envelope(self):
        self.server.fail_callback = True
        self.server.fail_ack_recovery = True
        with self.assertRaises(ConnectionError):
            self.run_receiver()
        with self.server.connection() as db:
            original = db.execute("SELECT envelope FROM callbacks").fetchone()[0]
        self.server.fail_callback = False
        self.server.fail_ack_recovery = False
        result = self.run_receiver()
        self.assertEqual(result, self.run_receiver())
        self.assertEqual(result["counted_actions"], 1)
        self.assertEqual(self.calls("consume"), 1)
        self.assertEqual(self.calls("authorize"), 1)
        with self.server.connection() as db:
            self.assertEqual(
                db.execute("SELECT envelope FROM callbacks").fetchone()[0], original
            )
        self.assertEqual(self.receiver.flush_callbacks(), [])
        with self.assertRaises(ReceiverConflict):
            self.receiver.run(self.message.operation_id, digest(b"different"))
        self.assertNotIn(
            b"never-store-grant", (self.root / "receiver.sqlite3").read_bytes()
        )

    def test_persisted_payload_tamper_conflicts_before_resumed_action(self):
        child = self.child("local_receipt")
        child.communicate(timeout=20)
        self.assertEqual(child.returncode, 73)
        with self.receiver._ledger() as db:
            db.execute(
                "UPDATE operations SET payload=?", (canonical({"altered": True}),)
            )
            db.commit()
        with self.assertRaises(ReceiverConflict):
            self.run_receiver()
        self.assertEqual(self.calls("authorize"), 0)
        self.assertEqual(self.calls("consume"), 1)

    def test_callback_ack_requires_exact_persisted_envelope_proof(self):
        self.server.fail_callback = True
        self.server.fail_ack_recovery = True
        with self.assertRaises(ConnectionError):
            self.run_receiver()
        self.server.fail_callback = False
        self.server.fail_ack_recovery = False
        original_status = self.server.status

        def wrong_ack(operation_id):
            result = original_status(operation_id)
            result["callback_ack"]["envelope_digest"] = digest(b"different-callback")
            return result

        self.server.status = wrong_ack
        with self.assertRaises(ValueError):
            self.run_receiver()
        with self.receiver._ledger() as db:
            result = self.receiver._result(db, self.message.operation_id)
            self.assertFalse(result["callback_delivered"])
            self.assertEqual(result["counted_actions"], 1)
        self.server.status = original_status
        self.assertTrue(self.run_receiver()["callback_delivered"])

    def test_actual_process_death_at_every_boundary(self):
        # Each case gets its own real custody bundle, server and local ledger.
        for checkpoint, expected_count, phase in (
            ("intent", 0, "intent"),
            ("server_consume", 1, "complete"),
            ("local_receipt", 1, "complete"),
            ("action_fence", 0, "reconcile"),
            ("effect", 1, "reconcile"),
            ("completion", 1, "complete"),
        ):
            with self.subTest(checkpoint=checkpoint):
                case = RuntimeTests("test_concurrent_processes_count_at_most_once")
                case.setUp()
                try:
                    child = case.child(checkpoint)
                    stdout, stderr = child.communicate(timeout=20)
                    self.assertEqual(child.returncode, 73, (stdout, stderr))
                    result = case.run_receiver()
                    self.assertEqual(result["counted_actions"], expected_count)
                    self.assertEqual(result["phase"], phase)
                    self.assertLessEqual(case.calls("consume"), 1)
                    self.assertEqual(case.calls("bootstrap"), 1)
                finally:
                    case.doCleanups()

    def test_concurrent_processes_count_at_most_once(self):
        children = [self.child() for _ in range(4)]
        for child in children:
            stdout, stderr = child.communicate(timeout=20)
            self.assertEqual(child.returncode, 0, (stdout, stderr))
        self.assertEqual(self.run_receiver()["counted_actions"], 1)
        self.assertEqual(self.calls("consume"), 1)

    def test_resumed_action_rechecks_server_and_custody(self):
        child = self.child("local_receipt")
        child.communicate(timeout=20)
        self.assertEqual(child.returncode, 73)
        with self.server.connection() as db:
            db.execute("UPDATE authority SET allowed=0")
        with self.assertRaises(ValueError):
            self.run_receiver()
        with self.receiver._ledger() as db:
            self.assertEqual(
                self.receiver._result(db, self.message.operation_id)["counted_actions"],
                0,
            )
        with self.server.connection() as db:
            db.execute("UPDATE authority SET allowed=1")
        artifact = self.root / "custody/synthetic-plan/artifact"
        artifact.chmod(0o600)
        artifact.write_bytes(b"tampered")
        artifact.chmod(0o400)
        with self.assertRaises(ValueError):
            self.run_receiver()
        self.assertEqual(self.calls("consume"), 1)

    def test_expiry_after_action_fence_prevents_effect_and_requires_reconcile(self):
        expired = False

        def checkpoint(name):
            nonlocal expired
            if name == "action_fence":
                expired = True

        self.receiver.checkpoint = checkpoint
        with patch(
            "infra_automation.receiver_runtime.datetime", wraps=datetime
        ) as clock:
            clock.now.side_effect = lambda tz: (
                datetime.now(timezone.utc)
                + (timedelta(hours=2) if expired else timedelta())
            )
            with self.assertRaises(ValueError):
                self.run_receiver()
        result = self.run_receiver()
        self.assertEqual(result["counted_actions"], 0)
        self.assertEqual(result["phase"], "reconcile")
        self.assertEqual(self.calls("consume"), 1)

    def test_final_authority_check_runs_after_custody_verification(self):
        child = self.child("local_receipt")
        child.communicate(timeout=20)
        self.assertEqual(child.returncode, 73)
        original = self.receiver.custody.verify

        @contextmanager
        def revoke_during_verification(binding):
            with original(binding) as artifact:
                with self.server.connection() as db:
                    db.execute("UPDATE authority SET allowed=0")
                yield artifact

        self.receiver.custody.verify = revoke_during_verification
        with self.assertRaises(ValueError):
            self.run_receiver()
        with self.receiver._ledger() as db:
            result = self.receiver._result(db, self.message.operation_id)
            self.assertEqual(result["counted_actions"], 0)
            self.assertEqual(result["phase"], "received")

    def test_advisory_cannot_authorize_and_ledger_links_are_denied(self):
        spec = self.server.spec
        advisory = spec["message"]["binding"]
        advisory["authorization_kind"] = "advisory_request"
        advisory["provenance"]["authorization_kind"] = "advisory_request"
        spec["message"]["binding_digest"] = receiver_binding_digest(advisory)
        with self.assertRaises(ValueError):
            self.receiver.run(
                self.message.operation_id, spec["message"]["binding_digest"]
            )
        self.assertEqual(self.calls("consume"), 0)
        ledger = self.root / "receiver.sqlite3"
        os.link(ledger, self.root / "ledger-alias")
        with self.assertRaises(ValueError):
            self.run_receiver()
        (self.root / "ledger-alias").unlink()
        ledger.unlink()
        ledger.symlink_to(self.directory / "server.sqlite3")
        with self.assertRaises(OSError):
            self.run_receiver()

    def test_malformed_bootstrap_grants_never_consume_or_persist_intent(self):
        for token in (
            None,
            42,
            True,
            b"bytes",
            "",
            "x" * 257,
            "two words",
            "newline\n",
            "unicode-\u2603",
        ):
            with self.subTest(token=repr(token)):
                self.server.spec["grant_token"] = token
                with self.assertRaises(ReceiverConflict):
                    self.run_receiver()
                self.assertEqual(self.calls("consume"), 0)
                with self.receiver._ledger() as db:
                    self.assertEqual(
                        db.execute("SELECT count(*) FROM operations").fetchone()[0], 0
                    )

    def test_missing_custody_and_altered_bootstrap_bytes_never_consume(self):
        path = self.directory / "bootstrap.json"
        spec = json.loads(path.read_text())
        spec["payload"]["synthetic"] = False
        path.write_text(json.dumps(spec))
        self.receiver.server = Server(self.directory)
        with self.assertRaises(ReceiverConflict):
            self.run_receiver()
        self.receiver.server = self.server
        (self.root / "custody/synthetic-plan/artifact").unlink()
        with self.assertRaises(FileNotFoundError):
            self.run_receiver()
        self.assertEqual(self.calls("consume"), 0)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--child":
    directory = Path(sys.argv[2])
    crash = sys.argv[3]
    server = Server(directory)

    def checkpoint(name):
        if name == crash:
            os._exit(73)

    receiver = ReferenceReceiver(
        directory / "receiver", server, SECRET, checkpoint=checkpoint
    )
    receiver.run(
        server.spec["message"]["operation_id"], server.spec["message"]["binding_digest"]
    )
elif __name__ == "__main__":
    unittest.main()
