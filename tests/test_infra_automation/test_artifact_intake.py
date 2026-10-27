"""Synthetic upload screening corpus for the automation intake boundary."""

from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from infra_automation.artifact_intake import (
    collect_screened_artifact,
    screen_artifacts,
    screen_metadata,
)
from infra_automation.lifecycle import LifecycleError


class ArtifactIntakeTests(unittest.TestCase):
    terraform = b'resource "aws_s3_bucket" "sample" { bucket = "synthetic" }'
    corpus_fixture = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "fixtures/infra_automation/preflight_v1/sensitive-corpus.json"
        ).read_text(encoding="utf-8")
    )
    corpus = tuple(case["value"].encode() for case in corpus_fixture["cases"])

    def assert_rejected(self, files, *, status=422, **kwargs):
        with self.assertRaises(LifecycleError) as caught:
            screen_artifacts(files, **kwargs)
        self.assertEqual(caught.exception.status_code, status)
        self.assertEqual(str(caught.exception), LifecycleError(status).message)

    def test_supported_formats_retain_exact_bytes_and_relative_names(self):
        files = [
            ("modules/main.tf", self.terraform),
            (
                "deployment.yaml",
                b"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: synthetic\n",
            ),
            ("playbook.yml", b"hosts: all\ntasks: []\n"),
            ("template.json", b'{"Resources": {}}'),
            ("Jenkinsfile", b"pipeline { agent any; stages {} }"),
            ("plan.json", b'{"resource_changes": []}'),
        ]
        self.assertEqual(screen_artifacts(files), tuple(files))

    def test_empty_unsupported_duplicate_and_noncanonical_names_fail_closed(self):
        for name in (
            "../main.tf",
            "/main.tf",
            "a/../main.tf",
            "a\\main.tf",
            "a//main.tf",
            "./main.tf",
            "a/./main.tf",
            " main.tf",
            "main.tf ",
            "C:/main.tf",
            "__unsafe_path__/main.tf",
            "main.txt",
            "",
            "a\x00.tf",
            "a\n.tf",
            "x" * 257 + ".tf",
        ):
            with self.subTest(name=name):
                self.assert_rejected([(name, self.terraform)])
        self.assert_rejected([])
        self.assert_rejected([("main.tf", b"")])
        self.assert_rejected([("main.tf", None)])
        self.assert_rejected([("main.tf", self.terraform)] * 2)
        self.assert_rejected([(f"{index}.tf", self.terraform) for index in range(33)])

    def test_forbidden_artifacts_are_blocked_even_with_supported_suffix(self):
        for name in (
            "terraform.tfstate",
            "terraform.tfstate.json",
            "credentials.tf",
            "key.pem",
            "id_rsa.tf",
            "saved.tfplan",
        ):
            with self.subTest(name=name):
                self.assert_rejected([(name, self.terraform)])
        for raw in (
            b"PK\x03\x04saved-plan",
            b"binary\x00plan",
            b"binary\x01plan",
            b"\xff\xfeinvalid",
            b'{"version":4,"terraform_version":"1.0","serial":1,"lineage":"synthetic","resources":[]}',
        ):
            with self.subTest(raw=raw):
                self.assert_rejected([("main.tf", raw)])

    def test_lone_surrogate_names_are_rejected_before_classification(self):
        for name in ("\ud800.tf", "modules/\udfff/main.tf", "main\ud800.tf"):
            with (
                self.subTest(name=ascii(name)),
                patch(
                    "infra_automation.artifact_intake.detect_tool_type",
                    side_effect=AssertionError(
                        "No classification before UTF-8 screening"
                    ),
                ),
            ):
                self.assert_rejected([(name, self.terraform)])

    def test_inline_sensitive_corpus_is_rejected_without_reflection(self):
        for secret in self.corpus:
            with self.subTest(secret=secret):
                self.assert_rejected([("main.tf", self.terraform + b"\n" + secret)])
        self.assert_rejected([("password=synthetic-filename.tf", self.terraform)])
        with patch(
            "services.content_security.configured_credential_values",
            return_value=("synthetic-configured-provider-value",),
        ):
            self.assert_rejected(
                [
                    (
                        "main.tf",
                        self.terraform + b"\n# synthetic-configured-provider-value",
                    )
                ]
            )

    def test_bom_and_legacy_state_cannot_hide_under_source_suffix(self):
        for raw in (
            b'\xef\xbb\xbf{"version":4,"terraform_version":"1.0","serial":1,"lineage":"synthetic","resources":[]}',
            b'{"version":1,"modules":[]}',
            b' \n\xef\xbb\xbf{"version":1,"modules":[]}',
        ):
            with self.subTest(raw=raw):
                self.assert_rejected([("main.tf", raw)])

    def test_structured_sensitive_content_is_rejected(self):
        self.assert_rejected(
            [
                (
                    "secret.yaml",
                    b"apiVersion: v1\nkind: Secret\ndata:\n  value: c3ludGhldGlj\n",
                )
            ]
        )
        self.assert_rejected(
            [
                (
                    "plan.json",
                    json.dumps(
                        {
                            "resource_changes": [
                                {
                                    "change": {
                                        "after": {"value": "synthetic-hidden"},
                                        "after_sensitive": {"value": True},
                                    }
                                }
                            ]
                        }
                    ).encode(),
                )
            ]
        )

    def test_aggregate_byte_limit_is_checked_before_decode_or_detection(self):
        with patch(
            "infra_automation.artifact_intake.detect_tool_type",
            side_effect=AssertionError("No classification before size bound"),
        ):
            self.assert_rejected(
                [("a.tf", b"abc"), ("b.tf", b"def")], max_bytes=5, status=429
            )
        for bound in (0, -1, True, 8388609, "10"):
            with self.subTest(bound=bound):
                self.assert_rejected([("main.tf", self.terraform)], max_bytes=bound)

    def test_chunk_boundaries_never_release_unscreened_content(self):
        for secret in self.corpus:
            raw = self.terraform + b"\n" + secret
            for offset in range(len(self.terraform), len(raw)):
                with self.subTest(secret=secret, offset=offset):
                    with self.assertRaises(LifecycleError):
                        collect_screened_artifact(
                            "main.tf", (raw[:offset], raw[offset:])
                        )
        self.assertEqual(
            collect_screened_artifact(
                "main.tf", (self.terraform[:7], self.terraform[7:])
            ),
            ("main.tf", self.terraform),
        )
        with self.assertRaises(LifecycleError) as caught:
            collect_screened_artifact("main.tf", (b"abc", b"def"), max_bytes=5)
        self.assertEqual(caught.exception.status_code, 429)

    def test_metadata_and_errors_are_screened_as_a_whole(self):
        safe = {"source": "synthetic", "exit_code": 0, "details": ["safe"]}
        self.assertEqual(screen_metadata(safe), safe)
        for secret in self.corpus:
            with self.subTest(secret=secret), self.assertRaises(LifecycleError):
                screen_metadata({"error": secret.decode()})
        with self.assertRaises(LifecycleError):
            screen_metadata(
                {"password": "synthetic-hidden", "error": "synthetic-hidden"}
            )
        with self.assertRaises(LifecycleError):
            screen_metadata({"error": "x" * 17000})


if __name__ == "__main__":
    unittest.main()
