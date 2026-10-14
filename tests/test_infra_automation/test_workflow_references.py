import unittest
import json
from pathlib import Path
from infra_automation.contracts import RegistryContract
from infra_automation.workflow_schema import (
    Workflow,
    InputReference,
    ProjectReference,
    RunReference,
    StepReference,
)
from infra_automation.workflow_validation import (
    IssueCollector,
    _validate_scalar_references,
    normalize_identifier,
    prepare_resolution,
    resolve_value,
    ResolutionError,
)
from tests.test_infra_automation.test_workflow_schema import workflow


class ReferenceTests(unittest.TestCase):
    def test_resolution_rechecks_semantics_instead_of_accepting_shape_only(self):
        fixtures = (
            Path(__file__).resolve().parents[1]
            / "fixtures/infra_automation/workflow_v2/valid.json"
        )
        cases = json.loads(fixtures.read_text())
        metadata = {
            "project_id": "project-demo",
            "workspace_id": "workspace-prod",
            "environment": "production",
        }
        raw = cases[0]["definition"]
        raw["inputs"]["target"]["type"] = "string"
        with self.assertRaises(ResolutionError):
            prepare_resolution(Workflow.model_validate(raw), {}, metadata)
        raw["inputs"]["target"]["type"] = "identifier"
        raw["steps"][-1]["depends_on"] = []
        with self.assertRaises(ResolutionError):
            prepare_resolution(Workflow.model_validate(raw), {}, metadata)
        collected = Workflow.model_validate(cases[1]["definition"])
        with self.assertRaises(ResolutionError):
            prepare_resolution(collected, {}, metadata)
        registry = RegistryContract.model_validate_json(
            json.dumps({"profiles": cases[1]["profiles"]})
        )
        context = prepare_resolution(
            collected, {}, metadata, registry_contract=registry
        )
        self.assertEqual(
            resolve_value(InputReference(ref="input", name="target"), context),
            "delivery",
        )

    def definition(self):
        raw = workflow()
        raw["inputs"] = {
            "stage": {"type": "identifier", "required": False, "default": "prod"},
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 600,
                "required": False,
                "default": 10,
            },
        }
        raw["environment"] = {"ref": "input", "name": "stage"}
        raw["steps"][0]["parameters"] = {
            "timeout_seconds": {"ref": "input", "name": "count"}
        }
        return raw

    def test_nominal_types_and_entire_integer_range(self):
        raw = self.definition()
        issues = IssueCollector()
        _validate_scalar_references(
            Workflow.model_validate(raw), RegistryContract(), issues
        )
        self.assertFalse(issues.errors)
        for change in ["string", "unknown", "wide"]:
            raw = self.definition()
            if change == "string":
                raw["inputs"]["stage"]["type"] = "string"
            if change == "unknown":
                raw["environment"]["name"] = "missing"
            if change == "wide":
                raw["inputs"]["count"]["maximum"] = 601
            issues = IssueCollector()
            _validate_scalar_references(
                Workflow.model_validate(raw), RegistryContract(), issues
            )
            self.assertTrue(issues.errors)

    def test_metadata_symbolic_normalization(self):
        parsed = Workflow.model_validate(self.definition())
        self.assertEqual(
            normalize_identifier(ProjectReference(ref="project", field="id"), parsed),
            "project-1",
        )
        self.assertEqual(
            normalize_identifier(RunReference(ref="run", field="environment"), parsed),
            parsed.environment,
        )
        self.assertIsNone(
            normalize_identifier(
                ProjectReference(ref="project", field="workspace_id"), parsed
            )
        )

    def test_defaults_and_only_requested_output_required(self):
        parsed = Workflow.model_validate(self.definition())
        values = {}
        metadata = {
            "project_id": "project-1",
            "workspace_id": "workspace-1",
            "environment": "prod",
        }
        outputs = [
            {
                "step_id": "intake",
                "output": "screened_artifacts",
                "handle": "opaque-handle",
            }
        ]
        context = prepare_resolution(parsed, values, metadata, outputs)
        values["stage"] = "other"
        metadata["environment"] = "other"
        outputs[0]["handle"] = "mutated"
        self.assertEqual(
            resolve_value(InputReference(ref="input", name="stage"), context), "prod"
        )
        self.assertEqual(
            resolve_value(RunReference(ref="run", field="workspace_id"), context),
            "workspace-1",
        )
        self.assertEqual(
            resolve_value(
                StepReference(
                    ref="step", step_id="intake", output="screened_artifacts"
                ),
                context,
            ).handle,
            "opaque-handle",
        )
        empty = prepare_resolution(
            parsed,
            {},
            {"project_id": "project-1", "workspace_id": None, "environment": "prod"},
        )
        with self.assertRaises(ResolutionError):
            resolve_value(
                StepReference(
                    ref="step", step_id="intake", output="screened_artifacts"
                ),
                empty,
            )

    def test_inputs_metadata_and_outputs_fail_closed(self):
        parsed = Workflow.model_validate(self.definition())
        meta = {"project_id": "project-1", "workspace_id": None, "environment": "prod"}
        for values in [
            {"unknown": "secret"},
            {"count": True},
            {"count": 601},
            {"stage": "bad/path"},
            {"count": {}},
        ]:
            with self.subTest(values=values), self.assertRaises(ResolutionError):
                prepare_resolution(parsed, values, meta)
        for field, value in [
            ("project_id", "other"),
            ("environment", "other"),
            ("extra", "secret"),
        ]:
            with self.subTest(field=field), self.assertRaises(ResolutionError):
                prepare_resolution(parsed, {}, {**meta, field: value})
        good = {"step_id": "intake", "output": "screened_artifacts", "handle": "handle"}
        for outputs in [
            [good, good],
            [{**good, "step_id": "missing"}],
            [{**good, "output": "report"}],
            [{**good, "handle": object()}],
            [{**good, "secret": "bad"}],
        ]:
            with self.subTest(outputs=outputs), self.assertRaises(ResolutionError):
                prepare_resolution(parsed, {}, meta, outputs)
        raw = self.definition()
        raw["workspace_id"] = "one"
        parsed = Workflow.model_validate(raw)
        with self.assertRaises(ResolutionError):
            prepare_resolution(parsed, {}, meta)

    def test_missing_required_and_invalid_unused_input(self):
        raw = workflow()
        raw["inputs"] = {"unused": {"type": "string", "max_length": 2}}
        parsed = Workflow.model_validate(raw)
        meta = {
            "project_id": "project-1",
            "workspace_id": None,
            "environment": "production",
        }
        for values in [{}, {"unused": "abc"}, {"unused": "\ud800"}]:
            with self.subTest(values=values), self.assertRaises(ResolutionError):
                prepare_resolution(parsed, values, meta)
        prepare_resolution(parsed, {"unused": ""}, meta)

    def test_reference_construct_bypass_and_forged_context_are_revalidated(self):
        from infra_automation.workflow_validation import ResolutionContext, OutputHandle

        parsed = Workflow.model_validate(self.definition())
        context = prepare_resolution(
            parsed,
            {},
            {"project_id": "project-1", "workspace_id": None, "environment": "prod"},
        )
        for reference in [
            ProjectReference.model_construct(ref="project", field="environment"),
            RunReference.model_construct(ref="run", field="id"),
            InputReference.model_construct(ref="input", name="bad/path"),
        ]:
            with self.subTest(reference=reference), self.assertRaises(ResolutionError):
                resolve_value(reference, context)
        for forged in [
            ResolutionContext(
                (("x", object()),), context.metadata, (), context.producers
            ),
            ResolutionContext(
                context.inputs,
                context.metadata,
                (OutputHandle("intake", "report", "handle"),),
                context.producers,
            ),
        ]:
            with self.subTest(forged=forged), self.assertRaises(ResolutionError):
                resolve_value("literal", forged)

    def test_supplied_value_and_output_budgets(self):
        raw = workflow()
        raw["inputs"] = {"text": {"type": "string", "max_length": 1024}}
        parsed = Workflow.model_validate(raw)
        metadata = {
            "project_id": "project-1",
            "workspace_id": None,
            "environment": "production",
        }
        self.assertEqual(
            resolve_value(
                InputReference(ref="input", name="text"),
                prepare_resolution(parsed, {"text": "x" * 1024}, metadata),
            ),
            "x" * 1024,
        )
        with self.assertRaises(ResolutionError):
            prepare_resolution(parsed, {"text": "x" * 1025}, metadata)
        with self.assertRaises(ResolutionError):
            prepare_resolution(parsed, {"text": ""}, metadata, [{}] * 51)
        with self.assertRaises(ResolutionError):
            prepare_resolution(parsed, {f"i{i}": 0 for i in range(33)}, metadata)
