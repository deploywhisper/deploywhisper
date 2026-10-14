"""Closed graph, canonical result and semantic compatibility qualification."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import yaml

from infra_automation.contracts import RegistryContract, ValidationLimits
from infra_automation.workflow_validation import validate_workflow


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/infra_automation/workflow_v2"


class WorkflowGraphTests(unittest.TestCase):
    def setUp(self):
        self.valid = json.loads((FIXTURES / "valid.json").read_text())
        self.invalid = json.loads((FIXTURES / "invalid.json").read_text())

    def check(self, case, **kwargs):
        return validate_workflow(
            json.dumps(case["definition"], ensure_ascii=False).encode(),
            registry_contract=RegistryContract.model_validate_json(
                json.dumps({"profiles": case["profiles"]})
            ),
            **kwargs,
        )

    def test_all_positive_contract_vectors_and_negative_vectors(self):
        for case in self.valid:
            with self.subTest(case=case["case"]):
                result = self.check(case)
                self.assertTrue(result.valid, result.errors)
                self.assertEqual(
                    len(result.topological_order), len(case["definition"]["steps"])
                )
        for case in self.invalid:
            with self.subTest(case=case["case"]):
                result = self.check(case)
                self.assertFalse(result.valid)
                self.assertTrue(result.errors)
                self.assertIsNone(result.definition)
                self.assertIsNone(result.canonical_bytes)
                self.assertIsNone(result.digest)

    def test_canonical_defaults_bytes_and_digest_are_stable(self):
        result = self.check(self.valid[0])
        self.assertEqual(result.canonicalization, "tuple-json-utf8-v1")
        self.assertEqual(
            result.digest,
            "sha256:" + hashlib.sha256(result.canonical_bytes).hexdigest(),
        )
        canonical = json.loads(result.canonical_bytes)
        self.assertEqual(canonical["steps"][0]["source"]["repository_id"], None)
        self.assertEqual(canonical["steps"][0]["parameters"]["timeout_seconds"], 600)
        self.assertEqual(
            result.canonical_bytes,
            json.dumps(
                canonical,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode(),
        )
        reordered = copy.deepcopy(self.valid[0])
        reordered["definition"] = dict(reversed(list(reordered["definition"].items())))
        self.assertEqual(self.check(reordered).digest, result.digest)
        reordered["definition"]["steps"].reverse()
        reverse = self.check(reordered)
        self.assertTrue(reverse.valid)
        self.assertEqual(reverse.topological_order, result.topological_order)
        self.assertNotEqual(reverse.digest, result.digest)

    def test_yaml_corpus_matches_json_canonical_content(self):
        for case in self.valid:
            with self.subTest(case=case["case"]):
                result = validate_workflow(
                    yaml.safe_dump(case["definition"]).encode(),
                    registry_contract=RegistryContract.model_validate_json(
                        json.dumps({"profiles": case["profiles"]})
                    ),
                )
                self.assertTrue(result.valid, result.errors)
                self.assertEqual(
                    result.canonical_bytes, self.check(case).canonical_bytes
                )
                self.assertEqual(result.digest, self.check(case).digest)

    def test_returned_definition_cannot_mutate_canonical_authority(self):
        result = self.check(self.valid[0])
        original = result.canonical_bytes
        view = result.definition
        view.steps.clear()
        view.inputs.clear()
        self.assertEqual(len(result.definition.steps), 5)
        self.assertEqual(result.canonical_bytes, original)

    def test_unicode_is_not_normalized(self):
        cases = []
        for value in ("é", "e\u0301"):
            case = copy.deepcopy(self.valid[0])
            case["definition"]["inputs"]["note"] = {
                "type": "string",
                "required": False,
                "default": value,
            }
            result = self.check(case)
            self.assertTrue(result.valid, result.errors)
            cases.append(result.digest)
        self.assertNotEqual(*cases)

    def test_profile_authorization_applies_to_standalone_advisory_gate(self):
        case = copy.deepcopy(self.valid[1])
        case["definition"]["steps"] = case["definition"]["steps"][:3]
        case["definition"]["steps"][2]["authorization_kind"] = "advisory_request"
        case["profiles"][0]["authorization_kinds"] = ["exact_plan"]
        result = self.check(case)
        self.assertFalse(result.valid)
        self.assertEqual(result.errors[0].code, "profile_unsupported")

    def test_graph_errors_are_field_located_and_do_not_reflect_ids(self):
        case = copy.deepcopy(self.valid[0])
        case["definition"]["steps"][1]["depends_on"] = ["PRIVATE_REFERENCE"]
        result = self.check(case)
        self.assertFalse(result.valid)
        self.assertEqual(result.errors[0].path, ("steps", 1, "depends_on", 0))
        self.assertNotIn("PRIVATE_REFERENCE", repr(result.errors))
        case = copy.deepcopy(self.valid[0])
        case["definition"]["steps"][0]["depends_on"] = ["handoff"]
        result = self.check(case)
        self.assertFalse(result.valid)
        self.assertEqual(result.errors[0].code, "graph_cycle")

    def test_duplicate_and_self_dependencies_reject(self):
        for deps in (["source", "source"], ["analysis"]):
            case = copy.deepcopy(self.valid[0])
            case["definition"]["steps"][1]["depends_on"] = deps
            with self.subTest(deps=deps):
                result = self.check(case)
                self.assertFalse(result.valid)
                self.assertEqual(result.errors[0].code, "dependency_invalid")

    def test_missing_reference_in_reversed_wire_order_never_crashes(self):
        for index, field in (
            (4, "decision"),
            (3, "binding"),
            (2, "report"),
            (1, "artifact"),
        ):
            case = copy.deepcopy(self.valid[0])
            del case["definition"]["steps"][index][field]
            case["definition"]["steps"].reverse()
            with self.subTest(field=field):
                result = self.check(case)
                self.assertFalse(result.valid)
                self.assertTrue(result.errors)

    def test_effect_free_valid_and_hostile_validation(self):
        raw = json.dumps(self.valid[0]["definition"]).encode()
        with (
            patch("builtins.open", side_effect=AssertionError("file access")),
            patch("pathlib.Path.open", side_effect=AssertionError("file access")),
            patch("socket.socket", side_effect=AssertionError("network access")),
            patch("subprocess.run", side_effect=AssertionError("execution")),
        ):
            self.assertTrue(validate_workflow(raw).valid)
            self.assertFalse(
                validate_workflow(
                    b"!!python/object/apply:os.system [echo forbidden]"
                ).valid
            )

    def test_limits_registry_and_output_budget_fail_closed(self):
        raw = json.dumps(self.valid[0]["definition"]).encode()
        for kwargs in (
            {"limits": ValidationLimits.model_construct(max_errors=999)},
            {"registry_contract": {"handler": "execute"}},
            {
                "registry_contract": RegistryContract.model_construct(
                    profiles=("invalid",)
                )
            },
        ):
            with self.subTest(kwargs=list(kwargs)):
                result = validate_workflow(raw, **kwargs)
                self.assertFalse(result.valid)
                self.assertLessEqual(len(result.errors), 50)
        fully_typed = self.check(self.valid[0]).canonical_bytes
        self.assertTrue(
            validate_workflow(
                fully_typed, limits=ValidationLimits(max_bytes=len(fully_typed))
            ).valid
        )
        self.assertFalse(
            validate_workflow(raw, limits=ValidationLimits(max_bytes=len(raw))).valid
        )

    def test_error_cap_on_semantic_errors(self):
        case = copy.deepcopy(self.valid[0])
        for step in case["definition"]["steps"]:
            step["depends_on"] = ["absent"]
        result = self.check(case, limits=ValidationLimits(max_errors=2))
        self.assertFalse(result.valid)
        self.assertEqual(len(result.errors), 2)
        self.assertTrue(result.truncated)
