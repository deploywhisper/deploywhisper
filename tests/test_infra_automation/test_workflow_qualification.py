"""Cross-artifact compatibility, consumer and repeatable measurement evidence."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from infra_automation.contracts import RegistryContract
from infra_automation.workflow_validation import (
    WorkflowValidationResult,
    validate_workflow,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests/fixtures/infra_automation/workflow_v2/valid.json"


def registry(row):
    return RegistryContract.model_validate_json(
        json.dumps({"profiles": row["profiles"]})
    )


def benchmark_module():
    spec = importlib.util.spec_from_file_location(
        "workflow_benchmark", ROOT / "scripts/benchmark_workflow_validation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkflowQualificationTests(unittest.TestCase):
    def test_qualification_import_uses_tomli_when_tomllib_is_unavailable(self):
        import tomli

        spec = importlib.util.spec_from_file_location(
            "workflow_qualification_compat", Path(__file__)
        )
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"tomllib": None, "tomli": tomli}):
            spec.loader.exec_module(module)
            module.WorkflowQualificationTests(
                "test_new_package_and_test_lane_are_registered_for_shipping"
            ).test_new_package_and_test_lane_are_registered_for_shipping()

    def test_separate_manifests_match_every_frozen_file(self):
        for name in ("frozen-v1.json", "workflow-v2-manifest.json"):
            manifest = json.loads(
                (ROOT / "schemas/infra-automation" / name).read_text()
            )
            for path, expected in manifest["files"].items():
                with self.subTest(manifest=name, path=path):
                    self.assertEqual(
                        "sha256:"
                        + hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
                        expected,
                    )
        v2 = json.loads(
            (ROOT / "schemas/infra-automation/workflow-v2-manifest.json").read_text()
        )
        self.assertEqual(v2["workflow_version"], 2)
        self.assertEqual(v2["default_admitted_profiles"], [])
        self.assertEqual(
            v2["independent_protocol_versions"],
            {
                "runner": 1,
                "enrollment": 1,
                "receiver": 1,
                "provenance": 1,
                "state": 1,
                "error": 1,
                "cursor": 1,
                "report": 2,
            },
        )
        self.assertFalse(
            set(v2["files"])
            & set(
                json.loads(
                    (ROOT / "schemas/infra-automation/frozen-v1.json").read_text()
                )["files"]
            )
        )

    def test_public_consumer_admits_all_v2_vectors_and_rejects_hostile_vectors(self):
        for filename, valid, minimum in (
            ("valid.json", True, 8),
            ("invalid.json", False, 21),
        ):
            rows = json.loads((CORPUS.parent / filename).read_text())
            self.assertGreaterEqual(len(rows), minimum)
            for row in rows:
                with self.subTest(case=row["case"]):
                    result = validate_workflow(
                        json.dumps(row["definition"]).encode(),
                        registry_contract=registry(row),
                    )
                    self.assertEqual(result.valid, valid, result.errors)
                    if valid:
                        self.assertEqual(result.definition.workflow_version, 2)
                        self.assertEqual(
                            result.digest,
                            "sha256:"
                            + hashlib.sha256(result.canonical_bytes).hexdigest(),
                        )
                    else:
                        self.assertTrue(result.errors)
                        self.assertIsNone(result.definition)
                        self.assertIsNone(result.canonical_bytes)
                        self.assertIsNone(result.digest)
                        self.assertEqual(result.topological_order, ())

    def test_authoring_template_and_definition_consumer_negotiate_major_explicitly(
        self,
    ):
        template = json.loads(CORPUS.read_text())[0]
        for version in (1, 3, True, "2", None):
            payload = copy.deepcopy(template["definition"])
            payload["workflow_version"] = version
            with self.subTest(version=version):
                result = validate_workflow(
                    json.dumps(payload).encode(), registry_contract=registry(template)
                )
                self.assertFalse(result.valid)
                self.assertEqual(result.errors[0].code, "schema_version")
        payload.pop("workflow_version")
        self.assertFalse(validate_workflow(json.dumps(payload).encode()).valid)
        collected = next(
            row
            for row in json.loads(CORPUS.read_text())
            if row["case"] == "collected-exact-plan"
        )
        self.assertFalse(
            validate_workflow(json.dumps(collected["definition"]).encode()).valid
        )
        self.assertTrue(
            validate_workflow(
                json.dumps(collected["definition"]).encode(),
                registry_contract=registry(collected),
            ).valid
        )

    def test_new_package_and_test_lane_are_registered_for_shipping(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertIn(
            "infra_automation",
            metadata["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"],
        )
        for name in ("scripts/ci-local.sh", ".github/workflows/ci.yml"):
            with self.subTest(file=name):
                self.assertIn("tests/test_infra_automation", (ROOT / name).read_text())
        self.assertRegex(
            (ROOT / "Dockerfile").read_text(),
            r"COPY(?:\s+--\S+)*\s+infra_automation/?\s+\./infra_automation/?",
        )

    def test_benchmark_import_is_inert_and_small_run_reports_actual_limits(self):
        with (
            patch.object(Path, "read_bytes", side_effect=AssertionError("import read")),
            patch.object(Path, "read_text", side_effect=AssertionError("import read")),
        ):
            module = benchmark_module()
        report = module.run_benchmark(CORPUS, warmup=1, samples=2)
        self.assertEqual(report["step_count"], 50)
        self.assertEqual(report["failures"], {"warmup": 0, "measured": 0})
        self.assertFalse(report["qualified"])
        self.assertLessEqual(report["p50_ms"], report["p95_ms"])
        self.assertLessEqual(report["p95_ms"], report["p99_ms"])
        self.assertEqual(
            report["corpus_file_digest"], module.digest(CORPUS.read_bytes())
        )
        self.assertIn("workflow_validation.py", report["source_files"])
        self.assertIn("cgroup_controls", report["environment"])
        self.assertIn("rlimit_address_space_bytes", report["environment"])
        self.assertTrue(
            any("1000" in reason for reason in report["qualification_failures"])
        )

    def test_benchmark_counts_correctness_failures_and_writes_machine_readable_result(
        self,
    ):
        module = benchmark_module()
        original = module.validate_workflow
        calls = 0

        def fail_one(*args, **kwargs):
            nonlocal calls
            calls += 1
            return (
                WorkflowValidationResult() if calls == 3 else original(*args, **kwargs)
            )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            with (
                patch.object(module, "validate_workflow", side_effect=fail_one),
                patch("builtins.print"),
            ):
                code = module.main(
                    [
                        "--corpus",
                        str(CORPUS),
                        "--output",
                        str(output),
                        "--warmup",
                        "1",
                        "--samples",
                        "2",
                    ]
                )
            report = json.loads(output.read_text())
        self.assertEqual(code, 1)
        self.assertEqual(report["failures"], {"warmup": 0, "measured": 1})
        self.assertFalse(report["qualified"])

    def test_benchmark_rejects_invalid_measurement_configuration(self):
        module = benchmark_module()
        for kwargs in ({"samples": 0}, {"warmup": -1}, {"samples": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                module.run_benchmark(CORPUS, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            path.write_text("[]")
            with self.assertRaises(ValueError):
                module.run_benchmark(path, samples=1, warmup=0)
