"""Independent shape, scalar and default qualification for workflow major 2."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from infra_automation.contracts import (
    ProfileContract,
    RegistryContract,
    ValidationLimits,
)
from infra_automation.workflow_schema import Workflow


def workflow():
    return {
        "workflow_version": 2,
        "project_id": "project-1",
        "environment": "production",
        "steps": [
            {
                "id": "intake",
                "kind": "uploaded_intake",
                "depends_on": [],
                "source": {"kind": "uploaded"},
            }
        ],
    }


class WorkflowSchemaTests(unittest.TestCase):
    def test_exported_input_map_is_closed(self):
        inputs = Workflow.model_json_schema()["properties"]["inputs"]
        self.assertIs(inputs.get("additionalProperties"), False)

    @unittest.skipUnless(
        importlib.util.find_spec("jsonschema"),
        "optional JSON Schema validator unavailable",
    )
    def test_exported_input_names_match_runtime_validation(self):
        from jsonschema import Draft202012Validator

        schema = Workflow.model_json_schema()
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for name in ["stage", "A" * 128, "a_.:-0"]:
            raw = {**workflow(), "inputs": {name: {"type": "identifier"}}}
            with self.subTest(valid_name=name):
                Workflow.model_validate(raw)
                self.assertTrue(validator.is_valid(raw))
        for name in ["bad/key", "_stage", "é", "", "x" * 129, "stage\n"]:
            for declaration in [{"type": "identifier"}, {"command": "forbidden"}]:
                raw = {**workflow(), "inputs": {name: declaration}}
                with self.subTest(invalid_name=name, declaration=declaration):
                    with self.assertRaises(ValidationError):
                        Workflow.model_validate(raw)
                    self.assertFalse(validator.is_valid(raw))

    @unittest.skipUnless(
        importlib.util.find_spec("jsonschema"),
        "optional JSON Schema validator unavailable",
    )
    def test_exported_patterns_reject_trailing_newlines(self):
        from jsonschema import Draft202012Validator

        validator = Draft202012Validator(Workflow.model_json_schema())
        raw = workflow()
        raw["steps"][0].update(
            kind="admitted_collection",
            source={
                "kind": "collected",
                "repository_id": "repository",
                "commit_sha": "a" * 40,
                "profile_digest": "sha256:" + "b" * 64,
            },
        )
        Workflow.model_validate(raw)
        self.assertTrue(validator.is_valid(raw))
        for path in [
            ("project_id",),
            ("steps", 0, "id"),
            ("steps", 0, "source", "repository_id"),
            ("steps", 0, "source", "commit_sha"),
            ("steps", 0, "source", "profile_digest"),
        ]:
            broken = copy.deepcopy(raw)
            cursor = broken
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] += "\n"
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    Workflow.model_validate(broken)
                self.assertFalse(validator.is_valid(broken))
        corpus = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "fixtures/infra_automation/workflow_v2/valid.json"
            ).read_text()
        )
        for case in corpus:
            with self.subTest(case=case["case"]):
                self.assertTrue(validator.is_valid(case["definition"]))

    def test_defaults_materialize(self):
        actual = Workflow.model_validate(workflow()).model_dump(mode="json")
        self.assertEqual(actual["workspace_id"], None)
        self.assertEqual(actual["inputs"], {})
        self.assertEqual(
            actual["steps"][0]["parameters"],
            {"max_artifact_bytes": 8388608, "timeout_seconds": 600},
        )
        self.assertEqual(
            actual["steps"][0]["source"],
            {
                "kind": "uploaded",
                "repository_id": None,
                "commit_sha": None,
                "limitation": "Uploaded evidence does not establish repository identity or exact-plan custody.",
            },
        )

    def test_version_is_explicit_strict_major_two(self):
        for value in [None, True, False, 2.0, "2", 1, 3]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Workflow.model_validate({**workflow(), "workflow_version": value})
        raw = workflow()
        del raw["workflow_version"]
        with self.assertRaises(ValidationError):
            Workflow.model_validate(raw)

    def test_unknown_fields_reject_at_every_object_boundary(self):
        paths = [
            (),
            ("steps", 0),
            ("steps", 0, "source"),
            ("steps", 0, "parameters"),
            ("inputs", "stage"),
        ]
        for path in paths:
            raw = workflow()
            raw["steps"][0]["parameters"] = {}
            raw["inputs"] = {"stage": {"type": "identifier"}}
            cursor = raw
            for key in path:
                cursor = cursor[key]
            cursor["execute"] = "forbidden"
            with self.subTest(path=path), self.assertRaises(ValidationError):
                Workflow.model_validate(raw)

    def test_identifier_and_collection_boundaries(self):
        for value in ["a", "A" * 128, "a_.:-0"]:
            Workflow.model_validate({**workflow(), "project_id": value})
        for value in ["", "x" * 129, "é", " x", "x/y", "x\n", "_x", True, 123]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Workflow.model_validate({**workflow(), "project_id": value})
        for field, ceiling in [
            ("max_artifact_bytes", 8388608),
            ("timeout_seconds", 600),
        ]:
            for value in [1, ceiling, {"ref": "input", "name": "quota"}]:
                raw = workflow()
                raw["steps"][0]["parameters"] = {field: value}
                Workflow.model_validate(raw)
            for value in [0, -1, ceiling + 1, True, 1.0, "1", None]:
                raw = workflow()
                raw["steps"][0]["parameters"] = {field: value}
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaises(ValidationError),
                ):
                    Workflow.model_validate(raw)

    def test_input_declaration_defaults_and_nominal_shapes(self):
        valid = [
            {"type": "identifier", "required": False, "default": "prod"},
            {"type": "commit_sha", "required": False, "default": "a" * 40},
            {"type": "string", "required": False, "default": ""},
            {"type": "integer", "required": False, "default": 9007199254740991},
            {"type": "boolean", "required": False, "default": False},
        ]
        for declaration in valid:
            raw = workflow()
            raw["inputs"] = {"value": declaration}
            self.assertEqual(
                Workflow.model_validate(raw).inputs["value"].default,
                declaration["default"],
            )
        for kind in ["identifier", "commit_sha", "string", "integer", "boolean"]:
            raw = workflow()
            raw["inputs"] = {"value": {"type": kind}}
            self.assertTrue(Workflow.model_validate(raw).inputs["value"].required)
        invalid = [
            {"type": "string", "default": "x"},
            {"type": "string", "required": False},
            {"type": "string", "required": False, "default": None},
            {"type": "string", "required": False, "default": "xx", "max_length": 1},
            {"type": "string", "max_length": 1025},
            {"type": "string", "max_length": 0},
            {"type": "string", "max_length": True},
            {"type": "integer", "required": False, "default": True},
            {"type": "integer", "minimum": 2, "maximum": 1},
            {"type": "integer", "maximum": 9007199254740992},
            {"type": "integer", "required": False, "default": -1, "minimum": 0},
            {"type": "boolean", "required": False, "default": 0},
            {"type": "identifier", "required": "true"},
            {"type": "identifier", "required": False, "default": "bad/path"},
            {"type": "commit_sha", "required": False, "default": "A" * 40},
            {"type": "object"},
            {"type": "identifier", "minimum": 0},
        ]
        for declaration in invalid:
            raw = workflow()
            raw["inputs"] = {"value": declaration}
            with (
                self.subTest(declaration=declaration),
                self.assertRaises(ValidationError),
            ):
                Workflow.model_validate(raw)

    def test_sources_are_closed_and_collection_profile_is_literal(self):
        raw = workflow()
        raw["steps"][0].update(
            kind="admitted_collection",
            source={
                "kind": "collected",
                "repository_id": {"ref": "project", "field": "id"},
                "commit_sha": {"ref": "input", "name": "commit"},
                "profile_digest": "sha256:" + "a" * 64,
            },
        )
        Workflow.model_validate(raw)
        for key, value in [
            ("profile_digest", {"ref": "input", "name": "profile"}),
            ("commit_sha", "a" * 39),
            ("commit_sha", "A" * 40),
            ("commit_sha", {"ref": "run", "field": "environment"}),
            ("repository_id", "bad/path"),
        ]:
            broken = copy.deepcopy(raw)
            broken["steps"][0]["source"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValidationError):
                Workflow.model_validate(broken)
        for key, value in [
            ("repository_id", "repo"),
            ("commit_sha", "a" * 40),
            ("limitation", "trusted"),
        ]:
            broken = workflow()
            broken["steps"][0]["source"][key] = value
            with self.subTest(key=key), self.assertRaises(ValidationError):
                Workflow.model_validate(broken)

    def test_closed_reference_and_step_shapes(self):
        raw = workflow()
        raw["steps"] += [
            {
                "id": "analysis",
                "kind": "shared_analysis",
                "depends_on": ["intake"],
                "artifact": {
                    "ref": "step",
                    "step_id": "intake",
                    "output": "screened_artifacts",
                },
            },
            {
                "id": "gate",
                "kind": "policy_evaluation",
                "depends_on": ["analysis"],
                "report": {"ref": "step", "step_id": "analysis", "output": "report"},
                "target_id": {"ref": "project", "field": "id"},
                "environment": {"ref": "run", "field": "environment"},
                "authorization_kind": "advisory_request",
            },
            {
                "id": "decision",
                "kind": "human_decision",
                "depends_on": ["gate"],
                "binding": {
                    "ref": "step",
                    "step_id": "gate",
                    "output": "action_binding",
                },
            },
            {
                "id": "handoff",
                "kind": "registered_github_handoff",
                "depends_on": ["decision"],
                "binding": {
                    "ref": "step",
                    "step_id": "gate",
                    "output": "action_binding",
                },
                "decision": {
                    "ref": "step",
                    "step_id": "decision",
                    "output": "decision_receipt",
                },
                "target_id": "target",
                "environment": "prod",
                "authorization_kind": "exact_plan",
            },
        ]
        Workflow.model_validate(raw)
        for value in [
            "report-id",
            {"ref": "step", "step_id": "intake", "output": "unknown"},
            {"ref": "input", "name": "artifact"},
            {
                "ref": "step",
                "step_id": "intake",
                "output": "screened_artifacts",
                "path": "x",
            },
        ]:
            broken = copy.deepcopy(raw)
            broken["steps"][1]["artifact"] = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Workflow.model_validate(broken)
        for value in [
            {"ref": "run", "field": "id"},
            {"ref": "project", "field": "id"},
            {"ref": "step", "step_id": "intake", "output": "report"},
        ]:
            with (
                self.subTest(root_environment=value),
                self.assertRaises(ValidationError),
            ):
                Workflow.model_validate({**workflow(), "environment": value})

    def test_container_bounds(self):
        for count in [1, 50]:
            raw = workflow()
            raw["steps"] = [{**raw["steps"][0], "id": f"s{i}"} for i in range(count)]
            Workflow.model_validate(raw)
        for count in [0, 51]:
            raw = workflow()
            raw["steps"] *= count
            with self.subTest(steps=count), self.assertRaises(ValidationError):
                Workflow.model_validate(raw)
        for count in [32, 33]:
            raw = workflow()
            raw["inputs"] = {f"i{i}": {"type": "identifier"} for i in range(count)}
            if count == 32:
                Workflow.model_validate(raw)
            else:
                with self.assertRaises(ValidationError):
                    Workflow.model_validate(raw)

    def test_schema_artifact_matches_generated_contract(self):
        path = (
            Path(__file__).resolve().parents[2]
            / "schemas/infra-automation/workflow-v2.json"
        )
        self.assertEqual(json.loads(path.read_text()), Workflow.model_json_schema())


class RegistryAndLimitsTests(unittest.TestCase):
    def test_limits_may_only_lower_hard_ceilings(self):
        expected = {
            "max_bytes": 131072,
            "max_depth": 16,
            "max_steps": 50,
            "max_inputs": 32,
            "max_errors": 50,
        }
        self.assertEqual(ValidationLimits().model_dump(), expected)
        for key, ceiling in expected.items():
            ValidationLimits(**{key: 1})
            for value in [0, ceiling + 1, True, 1.0, "1"]:
                with (
                    self.subTest(key=key, value=value),
                    self.assertRaises(ValidationError),
                ):
                    ValidationLimits(**{key: value})

    def test_registry_is_bounded_unique_frozen_and_data_only(self):
        self.assertEqual(RegistryContract().profiles, ())
        profile = ProfileContract(
            digest="sha256:" + "a" * 64,
            tool="opentofu",
            authorization_kinds=("advisory_request", "exact_plan"),
        )
        registry = RegistryContract(profiles=(profile,))
        with self.assertRaises(ValidationError):
            registry.profiles = ()
        for values in [
            (profile, profile),
            tuple(
                ProfileContract(
                    digest=f"sha256:{i:064x}",
                    tool="terraform",
                    authorization_kinds=("advisory_request",),
                )
                for i in range(17)
            ),
        ]:
            with self.assertRaises(ValidationError):
                RegistryContract(profiles=values)
        for kwargs in [
            {"authorization_kinds": ()},
            {"authorization_kinds": ("exact_plan", "exact_plan")},
            {"tool": "shell"},
            {"handler": "execute"},
        ]:
            payload = profile.model_dump()
            payload.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                ProfileContract(**payload)
