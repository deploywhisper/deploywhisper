"""Independent field mutation and byte identity proof for decision packets."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest

from pydantic import ValidationError

from infra_automation.decisions import (
    DecisionBinding,
    binding_digest,
    content_digest,
    freeze_report_snapshot,
)
from tests.test_infra_automation.test_decisions import binding_payload


class DecisionBindingAdversarialTests(unittest.TestCase):
    def collected(self):
        payload = binding_payload()
        payload["authorization_kind"] = "exact_plan"
        payload["provenance"] = {
            "version": 1,
            "authorization_kind": "exact_plan",
            "source": {
                "version": 1,
                "kind": "collected",
                "repository_id": "source-repo",
                "commit_sha": "a" * 40,
                "collector_id": "collector",
                "profile_digest": "sha256:" + "a" * 64,
                "screened_transport_digest": payload["screened_artifact_digests"][0],
                "redaction_version": payload["redaction_version"],
                "collected_at": "2026-10-29T00:00:00Z",
                "source_deadline": "2026-10-29T01:00:00Z",
            },
            "custody": {
                "version": 1,
                "handle": "local-plan",
                "raw_local_digest": "sha256:" + "a" * 64,
                "expires_at": "2026-10-29T01:00:00Z",
            },
        }
        return payload

    def test_every_leaf_mutation_changes_identity_or_rejects(self):
        original = self.collected()
        digest = binding_digest(
            DecisionBinding.model_validate_json(json.dumps(original))
        )

        def leaves(value, path=()):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield from leaves(item, (*path, key))
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    yield from leaves(item, (*path, index))
            else:
                yield path, value

        count = 0
        for path, value in leaves(original):
            count += 1
            changed = deepcopy(original)
            container = changed
            for component in path[:-1]:
                container = container[component]
            if isinstance(value, int):
                replacement = value + 1
            elif value.startswith("sha256:"):
                replacement = "sha256:" + "b" * 64
            elif len(value) == 40:
                replacement = "b" * 40
            elif value.endswith("Z"):
                replacement = "2026-10-29T00:30:00Z"
            else:
                replacement = value + "-changed"
            container[path[-1]] = replacement
            with self.subTest(field=path):
                try:
                    typed = DecisionBinding.model_validate_json(json.dumps(changed))
                except ValidationError:
                    continue
                self.assertNotEqual(binding_digest(typed), digest)
        self.assertGreater(count, 40)

    def test_unknown_fields_and_coerced_versions_cannot_authorize(self):
        for path in (
            (),
            ("provenance",),
            ("provenance", "source"),
            ("provenance", "custody"),
        ):
            for key, value in (
                ("unexpected", "bypass"),
                ("version", True),
                ("version", "1"),
                ("version", 2),
            ):
                changed = self.collected()
                container = changed
                for component in path:
                    container = container[component]
                container[key] = value
                with (
                    self.subTest(path=path, key=key, value=value),
                    self.assertRaises(ValidationError),
                ):
                    DecisionBinding.model_validate_json(json.dumps(changed))

    def test_report_identity_hashes_stored_bytes_without_reserialization(self):
        report = {
            "report_schema_version": "v2",
            "should_block": False,
            "recommendation": "no-go",
            "confidence": 0.73123456789,
        }
        before = deepcopy(report)
        raw, digest = freeze_report_snapshot(report)
        self.assertEqual(report, before)
        self.assertEqual(content_digest(raw), digest)
        self.assertNotEqual(content_digest(raw + b"\n"), digest)
        self.assertEqual(json.loads(raw), before)
        self.assertFalse(json.loads(raw)["should_block"])
        for bad in (float("nan"), float("inf")):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                freeze_report_snapshot({**report, "confidence": bad})
