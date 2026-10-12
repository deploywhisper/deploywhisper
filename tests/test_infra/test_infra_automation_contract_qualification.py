"""Executed synthetic v1 wire qualification; no production automation routes."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "tests/fixtures/infra_automation/qualification/16_0/contracts"
spec = importlib.util.spec_from_file_location(
    "qualification_contracts", BASE / "prototype.py"
)
contracts = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = contracts
spec.loader.exec_module(contracts)


class InfraAutomationContractQualificationTests(unittest.TestCase):
    def setUp(self):
        self.vectors = json.loads((BASE / "valid.json").read_text())

    def test_valid_closed_wire_vectors(self):
        for kind, values in self.vectors.items():
            for value in values:
                with self.subTest(kind=kind):
                    contracts.validate(kind, value)

    def test_unknown_versions_and_fields_and_boolean_versions_deny(self):
        for kind, values in self.vectors.items():
            for value in values:
                for change in ({"version": 2}, {"version": True}, {"unexpected": "x"}):
                    with self.subTest(kind=kind, change=change):
                        with self.assertRaises(ValueError):
                            contracts.validate(kind, {**value, **change})

    def test_invalid_frozen_vectors(self):
        for vector in json.loads((BASE / "invalid.json").read_text()):
            with self.subTest(case=vector["case"]):
                with self.assertRaises(ValueError):
                    contracts.validate(vector["contract"], vector["value"])

    def test_yaml_resource_and_ambiguity_limits(self):
        for raw in (
            b"a: 1\na: 2",
            b"a: &x [1]\nb: *x",
            b"a: &x [*x]",
            b"x: " + b"[" * 18 + b"0" + b"]" * 18,
            b"#" * (contracts.MAX_BYTES + 1),
        ):
            with self.subTest(raw=raw[:40]):
                with self.assertRaises(ValueError):
                    contracts.parse_workflow(raw)
        raw = json.dumps(self.vectors["workflow"][0]).encode()
        self.assertEqual(contracts.parse_workflow(raw).version, 1)
        # Bounds are enforced before parsing even on a syntactically harmless comment.
        padded = raw + b" " * (contracts.MAX_BYTES - len(raw))
        self.assertEqual(contracts.parse_workflow(padded).version, 1)

    def test_graph_coverage_cycle_reference_and_step_boundary(self):
        workflow = self.vectors["workflow"][0]
        mutations = []
        item = copy.deepcopy(workflow)
        item["steps"][0]["depends_on"] = ["handoff"]
        mutations.append(item)
        item = copy.deepcopy(workflow)
        item["steps"][-1]["depends_on"] = ["analysis"]
        mutations.append(item)
        item = copy.deepcopy(workflow)
        item["steps"][-1]["refs"]["decision"]["output"] = "report"
        mutations.append(item)
        item = copy.deepcopy(workflow)
        item["steps"][-1]["target_id"] = "different-target"
        mutations.append(item)
        for item in mutations:
            with self.assertRaises(ValueError):
                contracts.validate("workflow", item)
        item = copy.deepcopy(workflow)
        for index in range(45):
            item["steps"].append(
                {
                    "id": f"intake{index}",
                    "kind": "uploaded_intake",
                    "depends_on": [],
                    "refs": {},
                }
            )
        self.assertEqual(len(contracts.validate("workflow", item).steps), 50)
        item["steps"].append(
            {"id": "intake46", "kind": "uploaded_intake", "depends_on": [], "refs": {}}
        )
        with self.assertRaises(ValueError):
            contracts.validate("workflow", item)

    def test_numeric_and_unicode_hash_rules_and_immutable_report_bytes(self):
        value = {"version": 1, "text": "é", "number": 12}
        self.assertEqual(
            contracts.canonical_bytes(value),
            b'{"number":12,"text":"\xc3\xa9","version":1}',
        )
        self.assertEqual(
            contracts.content_digest(value),
            contracts.content_digest(dict(reversed(list(value.items())))),
        )
        for bad in (float("nan"), float("inf"), 1.0, 2**53):
            with self.assertRaises(ValueError):
                contracts.canonical_bytes({"value": bad})
        raw = b'{ "id": 1, "confidence": 0.52 }\n'
        self.assertNotEqual(
            contracts.snapshot_digest(raw),
            contracts.snapshot_digest(json.dumps(json.loads(raw)).encode()),
        )
        self.assertNotEqual(
            contracts.content_digest(value),
            contracts.content_digest({**value, "text": "e\u0301"}),
        )

    def test_scoped_current_authority_binding_and_deadlines(self):
        runner = contracts.validate("runner", self.vectors["runner"][0])
        authority = contracts.current_authority(runner)
        contracts.authorize_runner(runner, authority, "2026-10-09T11:00:00Z")
        for key in (
            "runner_id",
            "project_id",
            "workspace_id",
            "run_id",
            "step_id",
            "attempt",
            "fence",
            "coordinator_generation",
            "authorization_epoch",
            "restore_epoch",
            "audience",
        ):
            changed = dict(authority)
            changed[key] = (
                changed[key] + 1 if type(changed[key]) is int else "different"
            )
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    contracts.authorize_runner(runner, changed, "2026-10-09T11:00:00Z")
        with self.assertRaises(ValueError):
            contracts.authorize_runner(runner, authority, runner.scope.lease_deadline)
        for key, value in (
            ("profile_digest", "sha256:" + "b" * 64),
            ("capabilities", ["different"]),
            ("lease_deadline", "2026-10-09T13:00:00Z"),
        ):
            with self.subTest(authority_field=key):
                with self.assertRaises(ValueError):
                    contracts.authorize_runner(
                        runner, {**authority, key: value}, "2026-10-09T11:00:00Z"
                    )
        receiver = contracts.validate("receiver", self.vectors["receiver"][0])
        live = {
            "available": True,
            "membership": True,
            "target_enabled": True,
            "feature_enabled": True,
            "authorization_epoch": 1,
            "restore_epoch": 1,
        }
        contracts.authorize_receiver(receiver, live, "2026-10-09T11:00:00Z")
        for key in live:
            changed = {**live, key: False if type(live[key]) is bool else 2}
            with self.assertRaises(ValueError):
                contracts.authorize_receiver(receiver, changed, "2026-10-09T11:00:00Z")

    def test_permission_non_disclosure_and_cursor_vectors(self):
        for vector in json.loads((BASE / "permissions.json").read_text())["cases"]:
            self.assertEqual(
                contracts.permission(**vector["input"]), vector["expected"]
            )
        for state in ("delivery_unknown", "succeeded", "waiting_approval"):
            contracts.validate(
                "state", {"version": 1, "run_state": state, "attempt_state": "running"}
            )
        with self.assertRaises(ValueError):
            contracts.validate(
                "state",
                {"version": 1, "run_state": "accepted", "attempt_state": "running"},
            )

    def test_existing_api_and_agent_consumers_drop_descriptive_metadata(self):
        from api.schemas import PersistedReportData
        from services.agent_interface_service import build_agent_report_data
        from tests.test_api.test_schemas import ApiSchemaTests

        payload = ApiSchemaTests()._persisted_report_payload()
        payload["confidence"] = 0.52
        base_api = PersistedReportData.model_validate(payload).model_dump(mode="json")
        base_agent = build_agent_report_data(payload).model_dump(mode="json")
        for provenance in (
            self.vectors["provenance"][0],
            {"version": 99},
            {"version": 1, "authority": True},
        ):
            augmented = {**payload, "infra_automation_provenance": provenance}
            self.assertEqual(
                PersistedReportData.model_validate(augmented).model_dump(mode="json"),
                base_api,
            )
            self.assertEqual(
                build_agent_report_data(augmented).model_dump(mode="json"), base_agent
            )
        self.assertTrue(base_agent["advisory_only"])
        self.assertFalse(base_agent["deployment_approval"])

    def test_every_receiver_binding_field_mutation_requires_fresh_binding(self):
        original = self.vectors["receiver"][0]
        for key, value in original["binding"].items():
            changed = copy.deepcopy(original)
            if type(value) is int:
                replacement = value + 1
            elif type(value) is str:
                replacement = (
                    ("sha256:" + "b" * 64) if value.startswith("sha256:") else "changed"
                )
            elif type(value) is list:
                replacement = ["sha256:" + "b" * 64]
            else:
                replacement = {**value, "unknown": True}
            changed["binding"][key] = replacement
            with self.subTest(field=key):
                with self.assertRaises(ValueError):
                    contracts.validate("receiver", changed)

    def test_wire_errors_use_existing_api_error_envelope(self):
        from api.errors import build_error

        for item in self.vectors["error"]:
            envelope = build_error(
                item["code"],
                item["message"],
                {
                    "retryable": item["retryable"],
                    "correlation_id": item["correlation_id"],
                },
            )
            self.assertEqual(envelope["error"]["code"], item["code"])
            self.assertEqual(
                envelope["error"]["details"]["retryable"], item["retryable"]
            )
            self.assertEqual(
                envelope["error"]["details"]["correlation_id"], item["correlation_id"]
            )

    def test_committed_schema_and_fixture_digest_manifest(self):
        import hashlib

        manifest = json.loads(
            (ROOT / "schemas/infra-automation/frozen-v1.json").read_text()
        )
        for relative, expected in manifest["files"].items():
            self.assertEqual(
                "sha256:" + hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(),
                expected,
            )
        for kind, model in contracts.MODELS.items():
            schema = json.loads(
                (ROOT / f"schemas/infra-automation/{kind}-v1.json").read_text()
            )
            self.assertEqual(model.model_json_schema(), schema)

    def test_report_snapshot_captures_existing_report_fixture_without_lossy_model_roundtrip(
        self,
    ):
        from tests.test_api.test_schemas import ApiSchemaTests

        payload = ApiSchemaTests()._persisted_report_payload()
        payload["confidence"] = 0.52
        payload["synthetic_descriptive_extra"] = {"future": "must survive capture"}
        raw, digest = contracts.freeze_report_snapshot(payload)
        self.assertEqual(json.loads(raw), payload)
        self.assertEqual(digest, contracts.snapshot_digest(raw))
        self.assertNotEqual(digest, contracts.snapshot_digest(raw + b"\n"))
        payload["confidence"] = float("nan")
        with self.assertRaises(ValueError):
            contracts.freeze_report_snapshot(payload)

    def test_enrollment_one_use_requires_actual_boolean_true(self):
        original = self.vectors["enrollment"][0]
        for value in (1, 0, False, "true"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    contracts.validate("enrollment", {**original, "one_use": value})

    def test_reference_errors_are_closed_regardless_of_step_order(self):
        for original in self.vectors["workflow"]:
            reversed_workflow = copy.deepcopy(original)
            reversed_workflow["steps"].reverse()
            contracts.validate("workflow", reversed_workflow)
            for kind in ("human_decision", "policy_evaluation", "shared_analysis"):
                changed = copy.deepcopy(reversed_workflow)
                next(step for step in changed["steps"] if step["kind"] == kind)[
                    "refs"
                ] = {}
                with self.subTest(
                    authorization=original["steps"][-1]["authorization_kind"], step=kind
                ):
                    with self.assertRaises(ValueError):
                        contracts.validate("workflow", changed)
