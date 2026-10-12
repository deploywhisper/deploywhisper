"""Synthetic receiver fault qualification; no deployment execution."""

from __future__ import annotations

import copy
import importlib.util
import hashlib
import hmac
import json
from pathlib import Path

# Fixed local interpreter and owned crash harness only.
import subprocess  # nosec B404
import sys
import tempfile
import unittest

MODULE = (
    Path(__file__).resolve().parents[1]
    / "fixtures/infra_automation/qualification/16_0/receiver/prototype.py"
)
spec = importlib.util.spec_from_file_location("receiver_qualification", MODULE)
prototype = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prototype)


class ReceiverQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.receiver = prototype.Receiver(self.root)
        self.binding = prototype.binding()
        self.authority = prototype.authority()

    def test_every_binding_field_invalidates_grant(self):
        self.receiver.issue("grant", self.binding)
        for field in self.binding:
            altered = copy.deepcopy(self.binding)
            altered[field] = "changed"
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.receiver.accept("grant", altered, self.authority)
        self.assertEqual(self.receiver.action_count(), 0)

    def test_unknown_protocol_kind_and_advisory_apply_deny(self):
        for field, value in [
            ("major", 2),
            ("authorization_kind", "other"),
            ("action", "apply"),
        ]:
            item = prototype.binding()
            item[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.receiver.issue("grant", item)

    def test_live_authority_denies_admission_and_resume(self):
        mutations = {
            "membership": False,
            "target_enabled": False,
            "feature_enabled": False,
            "available": False,
            "authorization_epoch": 2,
            "restore_epoch": 2,
        }
        for index, (field, value) in enumerate(mutations.items()):
            other = prototype.Receiver(self.root / str(index))
            other.issue("grant", self.binding)
            changed = {**self.authority, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                other.accept("grant", self.binding, changed)
            operation = other.accept("grant", self.binding, self.authority)
            with self.subTest(field=field), self.assertRaises(ValueError):
                other.start(operation, changed)
            self.assertEqual(other.action_count(), 0)
            self.assertTrue(other.locked())
        expired = {**self.authority, "now": 1000}
        self.receiver.issue("grant", self.binding)
        with self.assertRaises(ValueError):
            self.receiver.accept("grant", self.binding, expired)

    def test_custody_restart_digest_expiry_and_credentials(self):
        custody = prototype.Custody(self.root / "custody")
        handle, digest = custody.finalize(b"harmless synthetic bytes", "collector")
        reopened = prototype.Custody(self.root / "custody")
        self.assertEqual(
            reopened.read(handle, digest, 10, "receiver"), b"harmless synthetic bytes"
        )
        for digest_value, now, credential in [
            (digest, 1000, "receiver"),
            ("wrong", 10, "receiver"),
            (digest, 10, "collector"),
        ]:
            with self.assertRaises(ValueError):
                reopened.read(handle, digest_value, now, credential)
        with self.assertRaises(ValueError):
            custody.finalize(b"other", "receiver")

    def test_custody_tamper_symlink_and_path_swap_deny(self):
        custody = prototype.Custody(self.root / "custody")
        handle, digest = custody.finalize(b"original", "collector")
        path = custody.root / handle
        path.chmod(0o600)
        path.write_bytes(b"tampered")
        path.chmod(0o400)
        with self.assertRaises(ValueError):
            custody.read(handle, digest, 10, "receiver")
        path.unlink()
        outside = self.root / "outside"
        outside.write_bytes(b"original")
        path.symlink_to(outside)
        with self.assertRaises(ValueError):
            custody.read(handle, digest, 10, "receiver")
        path.unlink()
        path.write_bytes(b"original")
        path.chmod(0o400)
        with self.assertRaises(ValueError):
            custody.read(handle, digest, 10, "receiver")
        with self.assertRaises(ValueError):
            custody.read("../outside", digest, 10, "receiver")

    def test_atomic_finalization_refuses_overwrite(self):
        custody = prototype.Custody(self.root / "custody")
        handle, digest = custody.finalize(b"original", "collector")
        with self.assertRaises(FileExistsError):
            custody.finalize(b"changed", "collector", handle=handle)
        self.assertEqual(custody.read(handle, digest, 10, "receiver"), b"original")
        self.assertFalse(list(custody.root.glob("pending-*")))

    def test_exact_plan_requires_original_synthetic_bytes_at_admission_and_start(self):
        custody = prototype.Custody(self.root / "custody")
        handle, raw_digest = custody.finalize(b"not a real binary plan", "collector")
        item = {
            **self.binding,
            "authorization_kind": "exact_plan",
            "custody_handle": handle,
            "raw_digest": raw_digest,
            "sanitized_digest": prototype.digest({"screened": "synthetic"}),
        }
        self.assertNotEqual(item["raw_digest"], item["sanitized_digest"])
        self.receiver.issue("grant", item)
        with self.assertRaises(ValueError):
            self.receiver.accept("grant", item, self.authority)
        self.receiver.custody = custody
        operation = self.receiver.accept("grant", item, self.authority)
        path = custody.root / handle
        path.chmod(0o600)
        path.write_bytes(b"replacement")
        with self.assertRaises(ValueError):
            self.receiver.start(operation, self.authority)
        self.assertEqual(self.receiver.action_count(), 0)
        self.assertTrue(self.receiver.locked())

    def test_duplicate_dropped_response_receipts_and_locks(self):
        self.receiver.issue("grant", self.binding)
        operation = self.receiver.accept("grant", self.binding, self.authority)
        self.assertEqual(
            self.receiver.accept("grant", self.binding, self.authority), operation
        )
        self.assertEqual(self.receiver.status(operation), "accepted")
        self.receiver.cancel(operation)
        self.receiver.expire_lease(operation)
        self.assertTrue(self.receiver.locked())
        self.receiver.start(operation, self.authority)
        with self.assertRaises(ValueError):
            self.receiver.start(operation, self.authority)
        receipt = self.receiver.receipt(operation, "succeeded", 1)
        tampered = {**receipt, "state": "accepted"}
        with self.assertRaises(ValueError):
            self.receiver.reconcile(tampered)
        for field, value in {
            "operation": "unrelated-operation",
            "binding_digest": "unrelated-binding",
            "source_commit": "unrelated-source",
            "receiver": "unrelated-receiver",
            "state": "future-state",
        }.items():
            altered = {key: val for key, val in receipt.items() if key != "signature"}
            altered[field] = value
            altered["signature"] = hmac.new(
                self.receiver.key,
                json.dumps(altered, sort_keys=True).encode(),
                hashlib.sha256,
            ).hexdigest()
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.receiver.reconcile(altered)
        self.receiver.reconcile(receipt)
        with self.assertRaises(ValueError):
            self.receiver.reconcile(receipt)
        self.assertFalse(self.receiver.locked())
        self.assertEqual(self.receiver.action_count(), 1)

    def test_dispatch_cannot_claim_success_or_break_authority(self):
        self.receiver.issue("grant", self.binding)
        operation = self.receiver.accept("grant", self.binding, self.authority)
        with self.assertRaises(ValueError):
            self.receiver.reconcile(self.receiver.receipt(operation, "succeeded", 1))
        self.receiver.break_lock(operation, "synthetic privileged reconciliation")
        with self.assertRaises(ValueError):
            self.receiver.start(operation, self.authority)
        self.assertEqual(self.receiver.action_count(), 0)

    def test_receiver_identity_is_registered_and_bound_through_terminal_receipt(self):
        item = {**self.binding, "receiver": "other-receiver"}
        with self.assertRaises(ValueError):
            self.receiver.issue("wrong-receiver", item)
        other = prototype.Receiver(
            self.root / "other", receiver_identity="other-receiver"
        )
        other.issue("grant", item)
        operation = other.accept("grant", item, self.authority)
        other.start(operation, self.authority)
        receipt = other.receipt(operation, "succeeded", 1)
        self.assertEqual(receipt["receiver"], "other-receiver")
        wrong = {key: value for key, value in receipt.items() if key != "signature"}
        wrong["receiver"] = "synthetic"
        wrong["signature"] = hmac.new(
            other.key, json.dumps(wrong, sort_keys=True).encode(), hashlib.sha256
        ).hexdigest()
        with self.assertRaises(ValueError):
            other.reconcile(wrong)
        self.assertTrue(other.locked())
        self.assertEqual(other.status(operation), "action_completed")
        other.reconcile(receipt)
        self.assertFalse(other.locked())

    def test_receipt_types_and_unknown_fields_fail_closed(self):
        self.receiver.issue("grant", self.binding)
        operation = self.receiver.accept("grant", self.binding, self.authority)
        self.receiver.start(operation, self.authority)
        receipt = self.receiver.receipt(operation, "succeeded", 1)
        for field, value in {
            "sequence": True,
            "state": ["succeeded"],
            "operation": None,
            "signature": 123,
            "future_field": "unknown",
        }.items():
            altered = {**receipt, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.receiver.reconcile(altered)
            self.assertTrue(self.receiver.locked())
        with self.assertRaises(ValueError):
            self.receiver.reconcile(None)

    def test_real_abrupt_child_crashes_never_repeat_uncertain_action(self):
        for point, expected in [
            ("before_consume", 0),
            ("after_consume", 0),
            ("after_start", 0),
            ("after_action", 1),
            ("after_completion", 1),
        ]:
            with self.subTest(point=point):
                root = self.root / point
                receiver = prototype.Receiver(root)
                receiver.issue("grant", self.binding)
                # Owned local file, private temp directory, fixed test case values.
                result = subprocess.run(  # nosec B603
                    [sys.executable, str(MODULE), str(root), point], check=False
                )  # noqa: S603
                self.assertEqual(result.returncode, 73)
                restarted = prototype.Receiver(root)
                operation = restarted.accept("grant", self.binding, self.authority)
                self.assertEqual(restarted.action_count(), expected)
                if point in {"before_consume", "after_consume"}:
                    restarted.start(operation, self.authority)
                    self.assertEqual(restarted.action_count(), 1)
                elif point != "after_completion":
                    self.assertEqual(restarted.status(operation), "delivery_unknown")
                    self.assertTrue(restarted.locked())
                    with self.assertRaises(ValueError):
                        restarted.start(operation, self.authority)
                    self.assertEqual(restarted.action_count(), expected)
                    receipt = restarted.receipt(operation, "succeeded", 1)
                    if point == "after_action":
                        restarted.reconcile(receipt)
                        self.assertEqual(restarted.status(operation), "succeeded")
                        self.assertFalse(restarted.locked())
                        self.assertEqual(restarted.action_count(), 1)
                    else:
                        with self.assertRaises(ValueError):
                            restarted.reconcile(receipt)
                        self.assertTrue(restarted.locked())
                else:
                    self.assertEqual(restarted.status(operation), "action_completed")
