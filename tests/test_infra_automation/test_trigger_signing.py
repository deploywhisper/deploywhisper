"""Signed trigger v1 authenticates bounded exact bytes without parsing them."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from infra_automation.trigger_contracts import (
    TriggerKeyManifest,
    TriggerListRequest,
    TriggerRequest,
    TriggerStatusRequest,
    trigger_json_schema,
)
from infra_automation.trigger_signing import (
    DOMAIN,
    SIGNED_PATHS,
    TriggerSignatureError,
    sign_request,
    signing_bytes,
    verify_request,
)

SECRET = b"synthetic-trigger-key-material!!"  # exactly32 public fixture bytes
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
PARAMETERS = {
    "key_id": "fixture-key",
    "method": "POST",
    "path": "/api/v1/infra-automation/triggers/webhook",
    "timestamp": str(int(NOW.timestamp())),
    "nonce": "synthetic-nonce-0001",
    "body": b'{"version":1,"inputs":{"size":2}}',
}


def request():
    return {
        "version": 1,
        "workflow_revision_id": "revision-1",
        "project_id": 3,
        "workspace_id": 4,
        "source": {
            "repository_id": "repository-1",
            "commit_sha": "a" * 40,
            "origin": "webhook",
        },
        "inputs": {"size": 2, "enabled": True, "stage": "test"},
        "idempotency_key": "request-1",
    }


def manifest():
    return {
        "version": 1,
        "keys": [
            {
                "key_id": "fixture-key",
                "principal_id": "service-1",
                "principal_type": "service",
                "project_id": 3,
                "workspace_id": 4,
                "allowed_revision_ids": ["revision-1"],
                "allowed_sources": [
                    {"repository_id": "repository-1", "commit_sha": "a" * 40}
                ],
                "allowed_origins": ["webhook", "cli"],
                "authentication_version": 2,
                "membership_version": 1,
                "restore_epoch": 1,
                "expires_at": "2026-11-06T12:00:00Z",
                "secret_env_ref": "DEPLOYWHISPER_FIXTURE_TRIGGER_SECRET",
            }
        ],
    }


class TriggerContractTests(unittest.TestCase):
    def test_closed_strict_request_and_typed_inputs(self):
        self.assertEqual(TriggerRequest.model_validate(request()).inputs["size"], 2)
        changes = [
            lambda v: v.pop("version"),
            lambda v: v.update(version=True),
            lambda v: v.update(version=2),
            lambda v: v.update(project_id="3"),
            lambda v: v.update(actor="admin"),
            lambda v: v["source"].update(branch="main"),
            lambda v: v["source"].update(commit_sha="main"),
            lambda v: v["source"].update(origin="manual"),
            lambda v: v.update(inputs={"nested": {"unsafe": True}}),
            lambda v: v.update(inputs={"float": 1.25}),
            lambda v: v.update(inputs={f"i{i}": i for i in range(33)}),
            lambda v: v.update(inputs={"huge": 2**53}),
        ]
        for change in changes:
            value = request()
            change(value)
            with self.subTest(change=change), self.assertRaises(ValidationError):
                TriggerRequest.model_validate(value)

    def test_pull_request_reference_is_bounded_metadata_not_an_origin_override(self):
        value = request()
        value["source"].update(origin="pull_request", pr_ref="refs/pull/42/head")
        self.assertEqual(
            TriggerRequest.model_validate(value).source.pr_ref, "refs/pull/42/head"
        )
        for origin, reference in [
            ("pull_request", None),
            ("webhook", "42"),
            ("cli", "42"),
            ("pull_request", "https://example.invalid/pull/42"),
            ("pull_request", "refs/../secret"),
            ("pull_request", "refs/pull/42\nsecret"),
        ]:
            candidate = copy.deepcopy(value)
            candidate["source"].update(origin=origin, pr_ref=reference)
            with (
                self.subTest(origin=origin, reference=reference),
                self.assertRaises(ValidationError),
            ):
                TriggerRequest.model_validate(candidate)

    def test_manifest_is_closed_bounded_and_has_no_raw_key_slot(self):
        valid = TriggerKeyManifest.model_validate_json(json.dumps(manifest()))
        self.assertEqual(valid.keys[0].authentication_version, 2)
        changes = [
            lambda v: v["keys"].append(copy.deepcopy(v["keys"][0])),
            lambda v: v["keys"][0].update(principal_type="human"),
            lambda v: v["keys"][0].update(secret="do-not-store"),
            lambda v: v["keys"][0].update(secret_env_ref="secret=value"),
            lambda v: v["keys"][0].update(authentication_version=True),
            lambda v: v["keys"][0].update(expires_at="2026-99-99T12:00:00Z"),
            lambda v: v["keys"][0].update(allowed_revision_ids=[]),
            lambda v: v["keys"][0].update(allowed_revision_ids=["r"] * 2),
            lambda v: v["keys"][0].update(
                allowed_sources=v["keys"][0]["allowed_sources"] * 2
            ),
            lambda v: v["keys"][0].update(allowed_origins=["webhook"] * 2),
        ]
        for change in changes:
            value = manifest()
            change(value)
            with self.subTest(change=change), self.assertRaises(ValidationError):
                TriggerKeyManifest.model_validate_json(json.dumps(value))
        value = manifest()
        value["keys"] = [dict(value["keys"][0], key_id=f"key-{i}") for i in range(32)]
        self.assertEqual(
            len(TriggerKeyManifest.model_validate_json(json.dumps(value)).keys), 32
        )
        value["keys"].append(dict(value["keys"][0], key_id="extra"))
        with self.assertRaises(ValidationError):
            TriggerKeyManifest.model_validate_json(json.dumps(value))

    def test_status_list_and_generated_schema_match(self):
        self.assertEqual(TriggerStatusRequest(version=1, run_id="run").run_id, "run")
        self.assertEqual(TriggerListRequest(version=1).limit, 25)
        for kwargs in ({"limit": 101}, {"limit": True}, {"actor": "admin"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                TriggerListRequest(version=1, **kwargs)
        path = (
            Path(__file__).resolve().parents[2]
            / "schemas/infra-automation/trigger-v1.json"
        )
        self.assertEqual(json.loads(path.read_text()), trigger_json_schema())


class TriggerSigningTests(unittest.TestCase):
    def test_length_delimited_wire_vector(self):
        self.assertEqual(DOMAIN, b"deploywhisper-signed-trigger-v1\x00")
        self.assertEqual(
            sign_request(SECRET, **PARAMETERS),
            "sha256=afe1247de2a7d5fd6f92e61c6eaccc6c760316c43d5788450d787691c4d900b9",
        )
        fields = [
            PARAMETERS["key_id"].encode(),
            b"POST",
            PARAMETERS["path"].encode(),
            PARAMETERS["timestamp"].encode(),
            PARAMETERS["nonce"].encode(),
            hashlib.sha256(PARAMETERS["body"]).digest(),
        ]
        expected = DOMAIN + b"".join(
            struct.pack(">I", len(item)) + item for item in fields
        )
        self.assertEqual(signing_bytes(**PARAMETERS), expected)
        self.assertEqual(
            sign_request(SECRET, **PARAMETERS),
            "sha256=" + hmac.new(SECRET, expected, hashlib.sha256).hexdigest(),
        )

    def test_verified_expiry_and_constant_time_comparison(self):
        signature = sign_request(SECRET, **PARAMETERS)
        with patch(
            "infra_automation.trigger_signing.hmac.compare_digest",
            wraps=hmac.compare_digest,
        ) as compare:
            verified = verify_request(
                SECRET, signature=signature, now=NOW, **PARAMETERS
            )
        compare.assert_called_once()
        self.assertEqual(verified.key_id, PARAMETERS["key_id"])
        self.assertEqual(verified.nonce, PARAMETERS["nonce"])
        self.assertEqual(
            verified.body_digest,
            "sha256:" + hashlib.sha256(PARAMETERS["body"]).hexdigest(),
        )
        self.assertEqual(verified.expires_at, NOW + timedelta(seconds=300))
        with patch(
            "infra_automation.trigger_signing.hmac.compare_digest",
            wraps=hmac.compare_digest,
        ) as compare:
            with self.assertRaises(TriggerSignatureError):
                verify_request(b"x" * 32, signature=signature, now=NOW, **PARAMETERS)
        compare.assert_called_once()

    def test_raw_bytes_reencoding_and_every_bound_field_change_fail(self):
        signature = sign_request(SECRET, **PARAMETERS)
        mutations = [
            {"body": json.dumps(json.loads(PARAMETERS["body"])).encode()},
            {"body": PARAMETERS["body"] + b" "},
            {"key_id": "other-key"},
            {"path": "/api/v1/infra-automation/triggers/cli/run"},
            {"timestamp": str(int(PARAMETERS["timestamp"]) + 1)},
            {"nonce": "synthetic-nonce-0002"},
        ]
        for changes in mutations:
            with (
                self.subTest(changes=changes),
                self.assertRaises(TriggerSignatureError),
            ):
                verify_request(
                    SECRET, signature=signature, now=NOW, **{**PARAMETERS, **changes}
                )

    def test_skew_is_exclusive_and_future_expiry_retains_original_window(self):
        signature = sign_request(SECRET, **PARAMETERS)
        for delta in (-300, 300, -301, 301):
            with self.subTest(delta=delta), self.assertRaises(TriggerSignatureError):
                verify_request(
                    SECRET,
                    signature=signature,
                    now=NOW + timedelta(seconds=delta),
                    **PARAMETERS,
                )
        for delta in (-299, 299):
            verified = verify_request(
                SECRET,
                signature=signature,
                now=NOW + timedelta(seconds=delta),
                **PARAMETERS,
            )
            self.assertEqual(verified.expires_at, NOW + timedelta(seconds=300))
        with self.assertRaises(TriggerSignatureError):
            verify_request(
                SECRET, signature=signature, now=NOW.replace(tzinfo=None), **PARAMETERS
            )

    def test_bounds_fixed_paths_and_safe_errors(self):
        for path in SIGNED_PATHS:
            self.assertTrue(
                sign_request(SECRET, **{**PARAMETERS, "path": path}).startswith(
                    "sha256="
                )
            )
        changes = [
            {"method": "post"},
            {"method": "GET"},
            {"path": PARAMETERS["path"] + "/"},
            {"path": PARAMETERS["path"] + "?scope=other"},
            {"path": "/api/v1/infra-automation/triggers/%77ebhook"},
            {"timestamp": "0" + PARAMETERS["timestamp"]},
            {"timestamp": str(2**53)},
            {"timestamp": "-1"},
            {"nonce": "short"},
            {"nonce": "a" * 129},
            {"nonce": "secret\nheader"},
            {"key_id": "secret value"},
            {"body": b"x" * 131073},
            {"body": bytearray(b"x")},
        ]
        for change in changes:
            with (
                self.subTest(change=change),
                self.assertRaises(TriggerSignatureError) as caught,
            ):
                sign_request(SECRET, **{**PARAMETERS, **change})
            self.assertEqual(
                str(caught.exception), "Signed request authentication failed."
            )
        self.assertTrue(sign_request(SECRET, **{**PARAMETERS, "body": b"x" * 131072}))
        for secret in (b"x" * 31, b"x" * 33, "secret-not-bytes"):
            with (
                self.subTest(secret_type=type(secret)),
                self.assertRaises(TriggerSignatureError) as caught,
            ):
                sign_request(secret, **PARAMETERS)
            self.assertNotIn("secret-not-bytes", str(caught.exception))

    def test_authentication_never_parses_json(self):
        parameters = {**PARAMETERS, "body": b"{not-json"}
        signature = sign_request(SECRET, **parameters)
        with patch("json.loads", side_effect=AssertionError("parsing occurred")):
            verify_request(SECRET, signature=signature, now=NOW, **parameters)
        for signature in (
            "",
            "sha256=" + "A" * 64,
            "sha256=" + "0" * 63,
            "secret",
            None,
        ):
            with (
                self.subTest(signature=signature),
                self.assertRaises(TriggerSignatureError) as caught,
            ):
                verify_request(SECRET, signature=signature, now=NOW, **PARAMETERS)
            self.assertEqual(
                str(caught.exception), "Signed request authentication failed."
            )

    def test_adjacent_fields_cannot_share_a_signing_representation(self):
        left = {**PARAMETERS, "timestamp": "12", "nonce": "34567890123456789"}
        right = {**PARAMETERS, "timestamp": "123", "nonce": "4567890123456789"}
        self.assertEqual(
            left["timestamp"] + left["nonce"], right["timestamp"] + right["nonce"]
        )
        self.assertNotEqual(signing_bytes(**left), signing_bytes(**right))
        self.assertNotEqual(sign_request(SECRET, **left), sign_request(SECRET, **right))

    def test_unrepresentable_expiry_has_only_the_closed_error(self):
        now = datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        parameters = {**PARAMETERS, "timestamp": str(int(now.timestamp()))}
        with self.assertRaises(TriggerSignatureError) as caught:
            verify_request(
                SECRET,
                signature=sign_request(SECRET, **parameters),
                now=now,
                **parameters,
            )
        self.assertEqual(str(caught.exception), "Signed request authentication failed.")
