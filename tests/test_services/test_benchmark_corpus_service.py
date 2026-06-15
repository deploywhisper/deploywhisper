"""Tests for benchmark corpus validation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.benchmark_corpus_service import (
    BenchmarkCorpusValidationError,
    validate_benchmark_corpus,
)


def _write_valid_corpus(root: Path) -> None:
    scenario_dir = root / "scenarios" / "terraform-public-sg"
    artifact_dir = scenario_dir / "artifacts"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "main.tf").write_text(
        'resource "aws_security_group_rule" "demo_public_web" {\n'
        '  type = "ingress"\n'
        '  cidr_blocks = ["0.0.0.0/0"]\n'
        "  from_port = 22\n"
        "  to_port = 22\n"
        '  protocol = "tcp"\n'
        "}\n",
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "corpus_id": "benchmark-corpus-v1-test",
                "version": "1.0.0",
                "description": "Synthetic public benchmark scenarios for tests.",
                "scenarios": ["scenarios/terraform-public-sg/scenario.json"],
            }
        ),
        encoding="utf-8",
    )
    (scenario_dir / "scenario.json").write_text(
        json.dumps(
            {
                "id": "terraform-public-sg",
                "name": "Terraform public SSH ingress",
                "description": "Synthetic Terraform plan-risk scenario.",
                "labels": ["terraform", "network-exposure", "baseline"],
                "artifacts": [
                    {
                        "path": "artifacts/main.tf",
                        "type": "terraform",
                        "description": "Synthetic Terraform security group fixture.",
                    }
                ],
                "expected_findings": [
                    {
                        "id": "finding-public-ssh",
                        "title": "Public SSH ingress",
                        "severity": "high",
                        "evidence_ids": ["evidence-public-cidr"],
                        "rationale": "The artifact exposes SSH from the public internet.",
                    }
                ],
                "expected_evidence": [
                    {
                        "id": "evidence-public-cidr",
                        "artifact_path": "artifacts/main.tf",
                        "selector": 'cidr_blocks = ["0.0.0.0/0"]',
                        "description": "Public CIDR block on ingress rule.",
                    }
                ],
                "expected_verdict": "warn",
                "expected_verdict_rationale": (
                    "Warn because high-risk public SSH exposure has deterministic "
                    "artifact evidence."
                ),
                "license": {
                    "spdx_id": "CC0-1.0",
                    "source": "Original synthetic fixture authored for public benchmark use.",
                    "public_sample": True,
                },
                "safety": {
                    "synthetic": True,
                    "contains_secrets": False,
                    "contains_customer_data": False,
                    "contains_non_public_information": False,
                },
            }
        ),
        encoding="utf-8",
    )


class BenchmarkCorpusServiceTests(unittest.TestCase):
    def test_valid_corpus_reports_passed_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_valid_corpus(corpus_root)

            result = validate_benchmark_corpus(corpus_root)

        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.summary.scenario_count, 1)
        self.assertEqual(result.scenarios[0].id, "terraform-public-sg")
        self.assertEqual(result.scenarios[0].artifact_count, 1)
        self.assertEqual(result.scenarios[0].expected_finding_count, 1)
        self.assertEqual(result.scenarios[0].expected_evidence_count, 1)

    def test_bundled_v1_corpus_is_public_and_valid(self) -> None:
        result = validate_benchmark_corpus()

        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.summary.corpus_id, "deploywhisper-benchmark-corpus-v1")
        self.assertGreaterEqual(result.summary.scenario_count, 3)

    def test_validation_rejects_unsafe_or_non_public_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_valid_corpus(corpus_root)
            scenario_path = (
                corpus_root / "scenarios" / "terraform-public-sg" / "scenario.json"
            )
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario["license"]["spdx_id"] = "Proprietary"
            scenario["license"]["public_sample"] = False
            scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
            artifact_path = (
                corpus_root
                / "scenarios"
                / "terraform-public-sg"
                / "artifacts"
                / "main.tf"
            )
            artifact_path.write_text(
                'password = "super-secret"\n',
                encoding="utf-8",
            )

            with self.assertRaises(BenchmarkCorpusValidationError) as ctx:
                validate_benchmark_corpus(corpus_root)

        self.assertIn("non-public", str(ctx.exception).lower())
        self.assertIn("unsafe", str(ctx.exception).lower())

    def test_validation_rejects_unsafe_nested_scenario_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_valid_corpus(corpus_root)
            scenario_path = (
                corpus_root / "scenarios" / "terraform-public-sg" / "scenario.json"
            )
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario["expected_evidence"][0]["selector"] = 'password = "super-secret"'
            scenario["expected_findings"][0]["rationale"] = (
                "Internal only benchmark rationale."
            )
            scenario_path.write_text(json.dumps(scenario), encoding="utf-8")

            result = validate_benchmark_corpus(corpus_root, raise_on_error=False)

        self.assertFalse(result.valid)
        self.assertTrue(
            any("unsafe scenario metadata" in error for error in result.errors),
            result.errors,
        )
        self.assertTrue(
            any("non-public scenario metadata" in error for error in result.errors),
            result.errors,
        )

    def test_validation_rejects_whitespace_only_nested_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_valid_corpus(corpus_root)
            scenario_path = (
                corpus_root / "scenarios" / "terraform-public-sg" / "scenario.json"
            )
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario["artifacts"][0]["description"] = "   "
            scenario["expected_evidence"][0]["selector"] = "   "
            scenario["expected_findings"][0]["evidence_ids"] = ["   "]
            scenario["license"]["source"] = "   "
            scenario_path.write_text(json.dumps(scenario), encoding="utf-8")

            result = validate_benchmark_corpus(corpus_root, raise_on_error=False)

        self.assertFalse(result.valid)
        self.assertTrue(
            any("must not be empty" in error for error in result.errors),
            result.errors,
        )

    def test_validation_rejects_evidence_selector_missing_from_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_valid_corpus(corpus_root)
            scenario_path = (
                corpus_root / "scenarios" / "terraform-public-sg" / "scenario.json"
            )
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario["expected_evidence"][0]["selector"] = "missing selector text"
            scenario_path.write_text(json.dumps(scenario), encoding="utf-8")

            result = validate_benchmark_corpus(corpus_root, raise_on_error=False)

        self.assertFalse(result.valid)
        self.assertTrue(
            any("selector not found" in error for error in result.errors),
            result.errors,
        )

    def test_validation_does_not_scan_artifacts_that_escape_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_valid_corpus(corpus_root)
            (corpus_root / "outside.tf").write_text(
                'password = "super-secret"\n',
                encoding="utf-8",
            )
            scenario_path = (
                corpus_root / "scenarios" / "terraform-public-sg" / "scenario.json"
            )
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario["artifacts"][0]["path"] = "../../outside.tf"
            scenario["expected_evidence"][0]["artifact_path"] = "../../outside.tf"
            scenario_path.write_text(json.dumps(scenario), encoding="utf-8")

            result = validate_benchmark_corpus(corpus_root, raise_on_error=False)

        self.assertFalse(result.valid)
        self.assertTrue(
            any("must not escape" in error for error in result.errors),
            result.errors,
        )
        self.assertFalse(
            any("secret-like assignment" in error for error in result.errors),
            result.errors,
        )


if __name__ == "__main__":
    unittest.main()
