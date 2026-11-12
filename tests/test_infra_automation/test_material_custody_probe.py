"""Live split-custody probe verifies exact bytes without exposing them to app code."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import socket
import struct
import tempfile
import threading
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from infra_automation.decisions import DecisionBinding
from infra_automation.material_probe import (
    MAX_MESSAGE_BYTES,
    MaterialCustodyProbeServer,
    SignedCustodyResult,
    CustodyResult,
    UnixMaterialCustodyProbe,
    _send,
    _wire,
)
from infra_automation.receiver_custody import ProtectedCustody
from infra_automation.receiver_protocol import receiver_binding_from_decision
from services.infra_automation_support import digest as service_digest
from tests.test_infra_automation.test_decisions import D, binding_payload


class Record:
    state = "active"

    def __init__(self, custody):
        self.custody_handle = custody.handle
        self.raw_local_digest = custody.raw_local_digest
        self.expires_at = custody.expires_at


class MaterialCustodyProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.expiry = self.now + timedelta(minutes=5)
        self.source_deadline = self.now + timedelta(minutes=10)
        self.raw = b"synthetic protected plan bytes"
        source = {
            "kind": "collected",
            "repository_id": "synthetic-repo",
            "commit_sha": "b" * 40,
            "collector_id": "runner-one",
            "profile_digest": D,
            "screened_transport_digest": D,
            "redaction_version": 1,
            "collected_at": self.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_deadline": self.source_deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.custody_store = ProtectedCustody(self.root / "custody")
        self.custody = self.custody_store.publish(
            "material-one",
            self.raw,
            source,
            self.expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        values = binding_payload()
        values.update(
            authorization_kind="exact_plan",
            provenance={
                "authorization_kind": "exact_plan",
                "source": source,
                "custody": self.custody.model_dump(mode="json"),
            },
            screened_artifact_digests=(D,),
            evidence_deadline=self.expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
            approval_deadline=self.expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        self.binding = receiver_binding_from_decision(
            DecisionBinding.model_validate(values)
        )
        self.record = Record(self.custody)
        self.collection = type("Collection", (), {"custody": self.custody})()
        self.private = Ed25519PrivateKey.generate()
        self.socket_path = self.root / "probe" / "custody.sock"

    def run_server(self, server):
        result = []

        def serve():
            result.append(server.serve_once())

        thread = threading.Thread(target=serve)
        thread.start()
        return thread, result

    def test_live_probe_verifies_actual_descriptor_and_signature(self):
        with MaterialCustodyProbeServer(
            self.socket_path,
            self.root / "custody",
            self.private,
            socket_gid=os.getgid(),
        ) as server:
            self.assertEqual(self.socket_path.stat().st_mode & 0o777, 0o660)
            self.assertEqual(self.socket_path.parent.stat().st_mode & 0o777, 0o710)
            self.assertEqual(self.socket_path.parent.stat().st_gid, os.getgid())
            thread, result = self.run_server(server)
            client = UnixMaterialCustodyProbe(
                self.socket_path, self.private.public_key()
            )
            self.assertTrue(client(self.record, self.collection, self.binding))
            thread.join(5)
            self.assertEqual(result, [True])

    def test_idle_timeout_does_not_break_a_later_live_probe(self):
        with MaterialCustodyProbeServer(
            self.socket_path,
            self.root / "custody",
            self.private,
            timeout=0.05,
        ) as server:
            with self.assertRaises(TimeoutError):
                server.serve_once()
            thread, result = self.run_server(server)
            client = UnixMaterialCustodyProbe(
                self.socket_path, self.private.public_key(), timeout=1
            )
            self.assertTrue(client(self.record, self.collection, self.binding))
            thread.join(5)
            self.assertEqual(result, [True])

    def test_missing_custody_and_wrong_verification_key_fail_closed(self):
        artifact = self.root / "custody" / "material-one" / "artifact"
        artifact.unlink()
        with MaterialCustodyProbeServer(
            self.socket_path, self.root / "custody", self.private
        ) as server:
            thread, result = self.run_server(server)
            client = UnixMaterialCustodyProbe(
                self.socket_path, self.private.public_key(), timeout=1
            )
            with self.assertRaises((ValueError, OSError)):
                client(self.record, self.collection, self.binding)
            thread.join(5)
            self.assertEqual(result, [False])

        # Recreate custody for a signature mismatch check.
        self.custody_store = ProtectedCustody(self.root / "custody-two")
        source = self.binding.provenance.source.model_dump(mode="json")
        custody = self.custody_store.publish(
            "material-two",
            self.raw,
            source,
            self.expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        binding = self.binding.model_copy(
            update={
                "provenance": self.binding.provenance.model_copy(
                    update={"custody": custody}
                )
            }
        )
        with MaterialCustodyProbeServer(
            self.socket_path, self.root / "custody-two", self.private
        ) as server:
            thread, _ = self.run_server(server)
            wrong = UnixMaterialCustodyProbe(
                self.socket_path, Ed25519PrivateKey.generate().public_key()
            )
            with self.assertRaises(ValueError):
                wrong(Record(custody), type("C", (), {"custody": custody})(), binding)
            thread.join(5)

    def test_replay_nonce_and_oversize_response_reject(self):
        parent = self.socket_path.parent
        parent.mkdir(mode=0o700)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.socket_path))
        self.socket_path.chmod(0o600)
        listener.listen(1)

        def stale():
            connection, _ = listener.accept()
            with connection:
                header = connection.recv(4)
                length = struct.unpack("!I", header)[0]
                connection.recv(length)
                result = CustodyResult(
                    nonce="0" * 64,
                    binding_digest=service_digest(
                        json.dumps(
                            self.binding.model_dump(mode="json"), sort_keys=True
                        ).encode()
                    ),
                )
                envelope = SignedCustodyResult(
                    result=result,
                    signature=self.private.sign(_wire(result)).hex(),
                )
                _send(connection, _wire(envelope))

        thread = threading.Thread(target=stale)
        thread.start()
        client = UnixMaterialCustodyProbe(self.socket_path, self.private.public_key())
        with self.assertRaises(ValueError):
            client(self.record, self.collection, self.binding)
        thread.join(5)
        listener.close()
        self.socket_path.unlink()

        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.socket_path))
        self.socket_path.chmod(0o600)
        listener.listen(1)

        def oversized():
            connection, _ = listener.accept()
            with connection:
                connection.recv(4)
                connection.sendall(struct.pack("!I", MAX_MESSAGE_BYTES + 1))

        thread = threading.Thread(target=oversized)
        thread.start()
        with self.assertRaises(ValueError):
            client(self.record, self.collection, self.binding)
        thread.join(5)
        listener.close()


if __name__ == "__main__":
    unittest.main()
