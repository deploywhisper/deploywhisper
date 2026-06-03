"""Tests for benchmark corpus execution."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from analysis.risk_scorer import RiskAssessment
from evidence.models import EvidenceItem, Finding
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange
import services.benchmark_runner_service as benchmark_runner_module
from services.benchmark_runner_service import run_benchmark_corpus
from services.submission_manifest import build_submission_manifest


def _write_single_scenario_corpus(
    root: Path, *, selector: str = "expected marker"
) -> None:
    scenario_dir = root / "scenarios" / "single"
    artifact_dir = scenario_dir / "artifacts"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "main.tf").write_text(
        f"resource fixture\n{selector}\n", encoding="utf-8"
    )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "corpus_id": "single-scenario-corpus",
                "version": "1.0.0",
                "description": "Synthetic single scenario fixture.",
                "scenarios": ["scenarios/single/scenario.json"],
            }
        ),
        encoding="utf-8",
    )
    (scenario_dir / "scenario.json").write_text(
        json.dumps(
            {
                "id": "single-risk",
                "name": "Single expected risk",
                "description": "Synthetic benchmark scenario with one expected finding.",
                "labels": ["terraform"],
                "artifacts": [
                    {
                        "path": "artifacts/main.tf",
                        "type": "terraform",
                        "description": "Synthetic Terraform fixture.",
                    }
                ],
                "expected_findings": [
                    {
                        "id": "finding-expected-risk",
                        "title": "Expected risk",
                        "severity": "high",
                        "evidence_ids": ["evidence-expected-marker"],
                        "rationale": "The expected risk must be tied to expected evidence.",
                    }
                ],
                "expected_evidence": [
                    {
                        "id": "evidence-expected-marker",
                        "artifact_path": "artifacts/main.tf",
                        "selector": selector,
                        "description": "Expected marker evidence.",
                    }
                ],
                "expected_verdict": "warn",
                "expected_verdict_rationale": "Warn on the expected risk.",
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


def _write_unsupported_corpus(root: Path) -> None:
    scenario_dir = root / "scenarios" / "notes-only"
    artifact_dir = scenario_dir / "artifacts"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "notes.txt").write_text(
        "not a supported deployment artifact\n",
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "corpus_id": "unsupported-corpus",
                "version": "1.0.0",
                "description": "Unsupported benchmark fixture.",
                "scenarios": ["scenarios/notes-only/scenario.json"],
            }
        ),
        encoding="utf-8",
    )
    (scenario_dir / "scenario.json").write_text(
        json.dumps(
            {
                "id": "notes-only",
                "name": "Unsupported notes fixture",
                "description": "Synthetic unsupported benchmark scenario.",
                "labels": ["unsupported"],
                "artifacts": [
                    {
                        "path": "artifacts/notes.txt",
                        "type": "notes",
                        "description": "Plain text notes, not a supported artifact.",
                    }
                ],
                "expected_findings": [
                    {
                        "id": "finding-unsupported",
                        "title": "Unsupported artifact",
                        "severity": "info",
                        "evidence_ids": ["evidence-notes"],
                        "rationale": "The runner should record unsupported artifacts explicitly.",
                    }
                ],
                "expected_evidence": [
                    {
                        "id": "evidence-notes",
                        "artifact_path": "artifacts/notes.txt",
                        "selector": "not a supported deployment artifact",
                        "description": "Plain text fixture content.",
                    }
                ],
                "expected_verdict": "unsupported",
                "expected_verdict_rationale": "Unsupported inputs should be recorded instead of hidden.",
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


def _write_unsupported_two_artifact_corpus(root: Path) -> None:
    scenario_dir = root / "scenarios" / "notes-pair"
    artifact_dir = scenario_dir / "artifacts"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "one.txt").write_text(
        "first unsupported deployment note\n",
        encoding="utf-8",
    )
    (artifact_dir / "two.txt").write_text(
        "second unsupported deployment note\n",
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "corpus_id": "unsupported-pair-corpus",
                "version": "1.0.0",
                "description": "Unsupported benchmark fixture with two artifacts.",
                "scenarios": ["scenarios/notes-pair/scenario.json"],
            }
        ),
        encoding="utf-8",
    )
    (scenario_dir / "scenario.json").write_text(
        json.dumps(
            {
                "id": "notes-pair",
                "name": "Unsupported notes pair fixture",
                "description": "Synthetic unsupported benchmark scenario with two artifacts.",
                "labels": ["unsupported"],
                "artifacts": [
                    {
                        "path": "artifacts/one.txt",
                        "type": "notes",
                        "description": "First unsupported notes fixture.",
                    },
                    {
                        "path": "artifacts/two.txt",
                        "type": "notes",
                        "description": "Second unsupported notes fixture.",
                    },
                ],
                "expected_findings": [
                    {
                        "id": "finding-one",
                        "title": "Unsupported artifact: artifacts/one.txt",
                        "severity": "info",
                        "evidence_ids": ["evidence-one"],
                        "rationale": "First unsupported artifact should carry only its evidence.",
                    },
                    {
                        "id": "finding-two-mismatched",
                        "title": "Unsupported artifact: artifacts/two.txt",
                        "severity": "info",
                        "evidence_ids": ["evidence-one"],
                        "rationale": "This intentionally mismatches evidence to prove per-artifact attribution.",
                    },
                ],
                "expected_evidence": [
                    {
                        "id": "evidence-one",
                        "artifact_path": "artifacts/one.txt",
                        "selector": "first unsupported deployment note",
                        "description": "First unsupported note content.",
                    },
                    {
                        "id": "evidence-two",
                        "artifact_path": "artifacts/two.txt",
                        "selector": "second unsupported deployment note",
                        "description": "Second unsupported note content.",
                    },
                ],
                "expected_verdict": "unsupported",
                "expected_verdict_rationale": "Unsupported inputs should be recorded instead of hidden.",
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


def _write_supported_parse_failure_corpus(root: Path) -> None:
    scenario_dir = root / "scenarios" / "broken-terraform"
    artifact_dir = scenario_dir / "artifacts"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "main.tf").write_text(
        'resource "aws_security_group_rule" "broken" {\n'
        '  cidr_blocks = ["0.0.0.0/0"]\n',
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "corpus_id": "supported-parse-failure-corpus",
                "version": "1.0.0",
                "description": "Supported benchmark fixture with parser failure.",
                "scenarios": ["scenarios/broken-terraform/scenario.json"],
            }
        ),
        encoding="utf-8",
    )
    (scenario_dir / "scenario.json").write_text(
        json.dumps(
            {
                "id": "broken-terraform",
                "name": "Broken Terraform fixture",
                "description": "Synthetic supported artifact that fails parsing.",
                "labels": ["terraform", "parse-failure"],
                "artifacts": [
                    {
                        "path": "artifacts/main.tf",
                        "type": "terraform",
                        "description": "Malformed Terraform fixture.",
                    }
                ],
                "expected_findings": [
                    {
                        "id": "finding-parse-failure",
                        "title": "Terraform parse failure",
                        "severity": "info",
                        "evidence_ids": ["evidence-public-cidr"],
                        "rationale": "Accepted but malformed artifacts must fail the benchmark instead of passing as unsupported.",
                    }
                ],
                "expected_evidence": [
                    {
                        "id": "evidence-public-cidr",
                        "artifact_path": "artifacts/main.tf",
                        "selector": 'cidr_blocks = ["0.0.0.0/0"]',
                        "description": "Selector present in an artifact that cannot be parsed.",
                    }
                ],
                "expected_verdict": "unsupported",
                "expected_verdict_rationale": "This fixture guards against accepted parser failures being counted as unsupported passes.",
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


def _write_mixed_partial_corpus(root: Path) -> None:
    _write_single_scenario_corpus(root)
    scenario_path = root / "scenarios" / "single" / "scenario.json"
    notes_path = root / "scenarios" / "single" / "artifacts" / "notes.txt"
    notes_path.write_text("operator note only\n", encoding="utf-8")
    scenario_payload = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenario_payload["artifacts"].append(
        {
            "path": "artifacts/notes.txt",
            "type": "notes",
            "description": "Unsupported auxiliary notes fixture.",
        }
    )
    scenario_path.write_text(json.dumps(scenario_payload), encoding="utf-8")


def _analysis_result(
    *,
    evidence_summary: str = "Expected marker evidence cites expected marker.",
    evidence_artifact: str = "artifacts/main.tf",
    evidence_tool: str = "terraform",
    evidence_resource: str = "resource.expected",
    finding_title: str = "HIGH: Expected risk",
    finding_evidence_refs: list[str] | None = None,
    assessment_severity: str = "high",
    assessment_recommendation: str = "no-go",
    assessment_score: int = 72,
    change_metadata: dict | None = None,
    files: list[tuple[str, bytes | None]] | None = None,
):
    evidence = EvidenceItem(
        evidence_id="ev-expected",
        analysis_id=0,
        finding_id="pending:expected",
        source_type="artifact",
        source_ref=f"{evidence_tool}://{evidence_artifact}#{evidence_resource}?action=modify",
        artifact=evidence_artifact,
        location=f"{evidence_artifact}#{evidence_resource}",
        resource=evidence_resource,
        operation="modify",
        summary=evidence_summary,
        severity_hint="high",
        deterministic=True,
        confidence=1.0,
        related_change_ids=["chg-expected"],
    )
    finding = Finding(
        finding_id="finding-expected",
        analysis_id=0,
        title=finding_title,
        description=finding_title,
        explanation=finding_title,
        severity="high",
        category="networking/ingress",
        deterministic=True,
        confidence=1.0,
        evidence_refs=finding_evidence_refs
        if finding_evidence_refs is not None
        else [evidence.evidence_id],
    )
    assessment = RiskAssessment(
        score=assessment_score,
        severity=assessment_severity,
        recommendation=assessment_recommendation,
        top_risk=finding_title,
        partial_context=False,
    )
    parse_batch = ParseBatchResult(
        files=[
            ParsedFileResult(
                file_name=evidence_artifact,
                tool="terraform",
                status="parsed",
                changes=[
                    UnifiedChange(
                        change_id="chg-expected",
                        source_file=evidence_artifact,
                        tool=evidence_tool,
                        resource_id=evidence_resource,
                        action="modify",
                        summary="Synthetic expected benchmark change.",
                        metadata=change_metadata
                        if change_metadata is not None
                        else {"selector": "expected marker"},
                    )
                ],
            )
        ]
    )
    manifest = build_submission_manifest(
        files
        if files is not None
        else [("artifacts/main.tf", b"resource fixture\nexpected marker\n")],
        parse_batch=parse_batch,
    )
    return SimpleNamespace(
        parse_batch=parse_batch,
        submission_manifest=manifest,
        evidence_items=[evidence],
        findings=[finding],
        assessment=assessment,
    )


def _analysis_result_with_changes(
    *,
    artifact_path: str,
    tool: str,
    resource_id: str,
    changes: list[UnifiedChange],
    related_change_id: str,
    files: list[tuple[str, bytes | None]],
):
    evidence = EvidenceItem(
        evidence_id="ev-expected",
        analysis_id=0,
        finding_id="pending:expected",
        source_type="artifact",
        source_ref=f"{tool}://{artifact_path}#{resource_id}?action=modify",
        artifact=artifact_path,
        location=f"{artifact_path}#{resource_id}",
        resource=resource_id,
        operation="modify",
        summary="Observed duplicate-name resource evidence.",
        severity_hint="high",
        deterministic=True,
        confidence=1.0,
        related_change_ids=[related_change_id],
    )
    finding = Finding(
        finding_id="finding-expected",
        analysis_id=0,
        title="HIGH: Expected risk",
        description="HIGH: Expected risk",
        explanation="HIGH: Expected risk",
        severity="high",
        category="networking/ingress",
        deterministic=True,
        confidence=1.0,
        evidence_refs=[evidence.evidence_id],
    )
    parse_batch = ParseBatchResult(
        files=[
            ParsedFileResult(
                file_name=artifact_path,
                tool=tool,
                status="parsed",
                changes=changes,
            )
        ]
    )
    manifest = build_submission_manifest(files, parse_batch=parse_batch)
    return SimpleNamespace(
        parse_batch=parse_batch,
        submission_manifest=manifest,
        evidence_items=[evidence],
        findings=[finding],
        assessment=RiskAssessment(
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="HIGH: Expected risk",
            partial_context=False,
        ),
    )


class BenchmarkRunnerServiceTests(unittest.TestCase):
    def test_bundled_corpus_records_scenario_results(self) -> None:
        result = run_benchmark_corpus()

        self.assertEqual(result.summary.corpus_id, "deploywhisper-benchmark-corpus-v1")
        self.assertGreaterEqual(result.summary.scenario_count, 3)
        self.assertEqual(len(result.scenarios), result.summary.scenario_count)
        self.assertGreaterEqual(result.summary.total_latency_ms, 0.0)

        scenario = result.scenarios[0]
        self.assertIn(scenario.status, {"passed", "failed", "unsupported"})
        self.assertIsInstance(scenario.passed, bool)
        self.assertGreaterEqual(scenario.latency_ms, 0.0)
        self.assertGreaterEqual(scenario.actual_finding_count, 0)
        self.assertGreaterEqual(scenario.actual_evidence_count, 0)
        self.assertGreaterEqual(scenario.finding_coverage, 0.0)
        self.assertLessEqual(scenario.finding_coverage, 1.0)
        self.assertGreaterEqual(scenario.evidence_coverage, 0.0)
        self.assertLessEqual(scenario.evidence_coverage, 1.0)
        self.assertIn(
            scenario.evidence_law_status,
            {"Satisfied", "Needs review", "Reconciled", "Detail omitted"},
        )
        self.assertIsInstance(scenario.evidence_law_violations, list)
        self.assertIsInstance(scenario.unsupported, bool)
        self.assertIsInstance(scenario.unsupported_reasons, list)
        self.assertIsInstance(scenario.findings, list)
        supported_scenarios = [
            scenario for scenario in result.scenarios if not scenario.unsupported
        ]
        self.assertTrue(supported_scenarios)
        for scenario in supported_scenarios:
            self.assertNotEqual(scenario.actual_verdict, "insufficient_context")

    def test_expected_unsupported_scenario_records_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_unsupported_corpus(corpus_root)

            result = run_benchmark_corpus(corpus_root)

        self.assertTrue(result.passed)
        self.assertEqual(result.summary.unsupported_count, 1)
        self.assertEqual(result.summary.failed_count, 0)
        scenario = result.scenarios[0]
        self.assertTrue(scenario.passed)
        self.assertEqual(scenario.status, "unsupported")
        self.assertEqual(scenario.actual_verdict, "unsupported")
        self.assertTrue(scenario.unsupported)
        self.assertTrue(scenario.unsupported_reasons)
        self.assertEqual(scenario.actual_finding_count, 1)
        self.assertTrue(scenario.findings)
        self.assertEqual(scenario.evidence_coverage, 1.0)
        self.assertEqual(scenario.finding_coverage, 1.0)

    def test_supported_parse_failure_fails_instead_of_passing_as_unsupported(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_supported_parse_failure_corpus(corpus_root)

            result = run_benchmark_corpus(corpus_root)

        self.assertFalse(result.passed)
        self.assertEqual(result.summary.failed_count, 1)
        self.assertEqual(result.summary.unsupported_count, 0)
        scenario = result.scenarios[0]
        self.assertFalse(scenario.passed)
        self.assertEqual(scenario.status, "failed")
        self.assertFalse(scenario.unsupported)
        self.assertEqual(scenario.unsupported_reasons, [])
        self.assertTrue(scenario.coverage_warnings)
        self.assertIn("artifacts/main.tf: failed", scenario.coverage_warnings[0])
        self.assertEqual(scenario.evidence_coverage, 0.0)
        self.assertEqual(scenario.finding_coverage, 0.0)

    def test_mixed_partial_input_records_warnings_without_becoming_unsupported(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_mixed_partial_corpus(corpus_root)

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    files=[
                        ("artifacts/main.tf", b"resource fixture\nexpected marker\n"),
                        ("artifacts/notes.txt", b"operator note only\n"),
                    ]
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertTrue(result.passed)
        self.assertEqual(result.summary.unsupported_count, 0)
        scenario = result.scenarios[0]
        self.assertFalse(scenario.unsupported)
        self.assertEqual(scenario.unsupported_reasons, [])
        self.assertEqual(scenario.status, "passed")
        self.assertTrue(scenario.coverage_warnings)
        self.assertIn("artifacts/notes.txt: excluded", scenario.coverage_warnings[0])

    def test_evidence_coverage_uses_raw_artifact_selector_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="expected marker")

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    evidence_summary="Observed unrelated marker only."
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertTrue(result.passed)
        scenario = result.scenarios[0]
        self.assertTrue(scenario.passed)
        self.assertEqual(scenario.evidence_coverage, 1.0)
        self.assertEqual(scenario.missing_expected_evidence_ids, [])

    def test_evidence_coverage_requires_observed_evidence_for_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="expected marker")

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    evidence_artifact="artifacts/other.tf",
                    files=[("artifacts/other.tf", b"expected marker\n")],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertFalse(result.passed)
        scenario = result.scenarios[0]
        self.assertFalse(scenario.passed)
        self.assertEqual(scenario.status, "failed")
        self.assertEqual(scenario.evidence_coverage, 0.0)
        self.assertEqual(
            scenario.missing_expected_evidence_ids, ["evidence-expected-marker"]
        )

    def test_evidence_coverage_does_not_match_selector_from_unrelated_same_file_change(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(
                corpus_root, selector="marker from other resource"
            )

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    evidence_resource="resource.one",
                    change_metadata={"selector": "observed resource one"},
                    files=[
                        (
                            "artifacts/main.tf",
                            b"resource fixture\nmarker from other resource\n",
                        )
                    ],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertFalse(result.passed)
        scenario = result.scenarios[0]
        self.assertFalse(scenario.passed)
        self.assertEqual(scenario.evidence_coverage, 0.0)
        self.assertEqual(
            scenario.missing_expected_evidence_ids, ["evidence-expected-marker"]
        )

    def test_evidence_coverage_falls_back_to_artifact_text_for_unscoped_tool(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="expected marker")
            (corpus_root / "scenarios" / "single" / "artifacts" / "main.tf").write_text(
                "Resources:\n  TemplateResource:\n    expected marker\n",
                encoding="utf-8",
            )

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    evidence_summary="Observed generic parser evidence.",
                    evidence_tool="cloudformation",
                    evidence_resource="resource/TemplateResource",
                    change_metadata={},
                    files=[
                        (
                            "artifacts/main.tf",
                            b"Resources:\n  TemplateResource:\n    expected marker\n",
                        )
                    ],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertTrue(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.evidence_coverage, 1.0)
        self.assertEqual(scenario.missing_expected_evidence_ids, [])

    def test_cloudformation_evidence_does_not_match_selector_from_wrong_resource(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="wrong resource marker")
            (corpus_root / "scenarios" / "single" / "artifacts" / "main.tf").write_text(
                "Resources:\n"
                "  TemplateResource:\n"
                "    Type: AWS::S3::Bucket\n"
                "  OtherResource:\n"
                "    wrong resource marker\n",
                encoding="utf-8",
            )

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    evidence_summary="Observed CloudFormation resource evidence.",
                    evidence_tool="cloudformation",
                    evidence_resource="resource/TemplateResource",
                    change_metadata={},
                    files=[
                        (
                            "artifacts/main.tf",
                            b"Resources:\n"
                            b"  TemplateResource:\n"
                            b"    Type: AWS::S3::Bucket\n"
                            b"  OtherResource:\n"
                            b"    wrong resource marker\n",
                        )
                    ],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertFalse(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.evidence_coverage, 0.0)
        self.assertEqual(
            scenario.missing_expected_evidence_ids, ["evidence-expected-marker"]
        )

    def test_cloudformation_yaml_scope_ignores_same_key_outside_resources(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="wrong section marker")
            (corpus_root / "scenarios" / "single" / "artifacts" / "main.tf").write_text(
                "Parameters:\n"
                "  TemplateResource:\n"
                "    wrong section marker\n"
                "Resources:\n"
                "  TemplateResource:\n"
                "    Type: AWS::S3::Bucket\n",
                encoding="utf-8",
            )

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    evidence_summary="Observed CloudFormation resource evidence.",
                    evidence_tool="cloudformation",
                    evidence_resource="resource/TemplateResource",
                    change_metadata={},
                    files=[
                        (
                            "artifacts/main.tf",
                            b"Parameters:\n"
                            b"  TemplateResource:\n"
                            b"    wrong section marker\n"
                            b"Resources:\n"
                            b"  TemplateResource:\n"
                            b"    Type: AWS::S3::Bucket\n",
                        )
                    ],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertFalse(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.evidence_coverage, 0.0)
        self.assertEqual(
            scenario.missing_expected_evidence_ids, ["evidence-expected-marker"]
        )

    def test_cloudformation_json_scope_ignores_same_key_outside_resources(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="wrong section marker")
            cloudformation_json = json.dumps(
                {
                    "TemplateResource": {
                        "Description": "wrong section marker",
                    },
                    "Resources": {
                        "TemplateResource": {
                            "Type": "AWS::S3::Bucket",
                        }
                    },
                }
            )
            (corpus_root / "scenarios" / "single" / "artifacts" / "main.tf").write_text(
                cloudformation_json,
                encoding="utf-8",
            )

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    evidence_summary="Observed CloudFormation resource evidence.",
                    evidence_tool="cloudformation",
                    evidence_resource="resource/TemplateResource",
                    change_metadata={},
                    files=[("artifacts/main.tf", cloudformation_json.encode("utf-8"))],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertFalse(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.evidence_coverage, 0.0)
        self.assertEqual(
            scenario.missing_expected_evidence_ids, ["evidence-expected-marker"]
        )

    def test_cloudformation_top_level_inline_resources_map_matches_selector(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="inline marker")
            cloudformation_yaml = (
                "Resources: {TemplateResource: {Type: AWS::S3::Bucket, "
                "Description: inline marker}}\n"
            )
            (corpus_root / "scenarios" / "single" / "artifacts" / "main.tf").write_text(
                cloudformation_yaml,
                encoding="utf-8",
            )

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    evidence_summary="Observed CloudFormation inline resource evidence.",
                    evidence_tool="cloudformation",
                    evidence_resource="resource/TemplateResource",
                    change_metadata={},
                    files=[("artifacts/main.tf", cloudformation_yaml.encode("utf-8"))],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertTrue(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.evidence_coverage, 1.0)
        self.assertEqual(scenario.missing_expected_evidence_ids, [])

    def test_cloudformation_yaml_scope_matches_direct_resource_not_nested_key(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="expected marker")
            cloudformation_yaml = (
                "Resources:\n"
                "  OtherResource:\n"
                "    Type: AWS::S3::Bucket\n"
                "    Properties:\n"
                "      TemplateResource:\n"
                "        Description: wrong nested marker\n"
                "  TemplateResource:\n"
                "    Type: AWS::S3::Bucket\n"
                "    Description: expected marker\n"
            )
            (corpus_root / "scenarios" / "single" / "artifacts" / "main.tf").write_text(
                cloudformation_yaml,
                encoding="utf-8",
            )

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    evidence_summary="Observed CloudFormation resource evidence.",
                    evidence_tool="cloudformation",
                    evidence_resource="resource/TemplateResource",
                    change_metadata={},
                    files=[("artifacts/main.tf", cloudformation_yaml.encode("utf-8"))],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertTrue(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.evidence_coverage, 1.0)
        self.assertEqual(scenario.missing_expected_evidence_ids, [])

    def test_kubernetes_evidence_uses_metadata_name_for_document_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="wrong nested marker")
            kubernetes_yaml = (
                "apiVersion: apps/v1\n"
                "kind: Deployment\n"
                "metadata:\n"
                "  name: other\n"
                "spec:\n"
                "  template:\n"
                "    spec:\n"
                "      containers:\n"
                "        - name: Expected\n"
                "          image: wrong nested marker\n"
                "---\n"
                "apiVersion: apps/v1\n"
                "kind: Deployment\n"
                "metadata:\n"
                "  name: Expected\n"
                "spec: {}\n"
            )
            (corpus_root / "scenarios" / "single" / "artifacts" / "main.tf").write_text(
                kubernetes_yaml,
                encoding="utf-8",
            )

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    evidence_summary="Observed Kubernetes resource evidence.",
                    evidence_tool="kubernetes",
                    evidence_resource="Deployment/Expected",
                    change_metadata={},
                    files=[("artifacts/main.tf", kubernetes_yaml.encode("utf-8"))],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertFalse(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.evidence_coverage, 0.0)
        self.assertEqual(
            scenario.missing_expected_evidence_ids, ["evidence-expected-marker"]
        )

    def test_kubernetes_document_separator_comments_preserve_document_scope(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="expected marker")
            kubernetes_yaml = (
                "apiVersion: apps/v1\n"
                "kind: Deployment\n"
                "metadata:\n"
                "  name: other\n"
                "spec:\n"
                "  note: wrong marker\n"
                "--- # second document\n"
                "apiVersion: apps/v1\n"
                "kind: Deployment\n"
                "metadata:\n"
                "  name: Expected\n"
                "spec:\n"
                "  note: expected marker\n"
            )
            (corpus_root / "scenarios" / "single" / "artifacts" / "main.tf").write_text(
                kubernetes_yaml,
                encoding="utf-8",
            )

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    evidence_summary="Observed Kubernetes resource evidence.",
                    evidence_tool="kubernetes",
                    evidence_resource="Deployment/Expected",
                    change_metadata={},
                    files=[("artifacts/main.tf", kubernetes_yaml.encode("utf-8"))],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertTrue(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.evidence_coverage, 1.0)
        self.assertEqual(scenario.missing_expected_evidence_ids, [])

    def test_cloudformation_inline_yaml_resource_matches_expected_selector(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="inline marker")
            (corpus_root / "scenarios" / "single" / "artifacts" / "main.tf").write_text(
                "Resources:\n"
                "  TemplateResource: {Type: AWS::S3::Bucket, Description: inline marker}\n",
                encoding="utf-8",
            )

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    evidence_summary="Observed CloudFormation inline resource evidence.",
                    evidence_tool="cloudformation",
                    evidence_resource="resource/TemplateResource",
                    change_metadata={},
                    files=[
                        (
                            "artifacts/main.tf",
                            b"Resources:\n"
                            b"  TemplateResource: {Type: AWS::S3::Bucket, Description: inline marker}\n",
                        )
                    ],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertTrue(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.evidence_coverage, 1.0)
        self.assertEqual(scenario.missing_expected_evidence_ids, [])

    def test_kubernetes_duplicate_kind_name_uses_related_change_occurrence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(
                corpus_root, selector="expected namespace marker"
            )
            kubernetes_yaml = (
                "apiVersion: apps/v1\n"
                "kind: Deployment\n"
                "metadata:\n"
                "  name: checkout\n"
                "  namespace: default\n"
                "spec:\n"
                "  note: wrong namespace marker\n"
                "---\n"
                "apiVersion: apps/v1\n"
                "kind: Deployment\n"
                "metadata:\n"
                "  name: checkout\n"
                "  namespace: payments\n"
                "spec:\n"
                "  note: expected namespace marker\n"
            )
            (corpus_root / "scenarios" / "single" / "artifacts" / "main.tf").write_text(
                kubernetes_yaml,
                encoding="utf-8",
            )
            changes = [
                UnifiedChange(
                    change_id="chg-first",
                    source_file="artifacts/main.tf",
                    tool="kubernetes",
                    resource_id="Deployment/checkout",
                    action="apply",
                    summary="First duplicate deployment.",
                ),
                UnifiedChange(
                    change_id="chg-second",
                    source_file="artifacts/main.tf",
                    tool="kubernetes",
                    resource_id="Deployment/checkout",
                    action="apply",
                    summary="Second duplicate deployment.",
                ),
            ]

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result_with_changes(
                    artifact_path="artifacts/main.tf",
                    tool="kubernetes",
                    resource_id="Deployment/checkout",
                    changes=changes,
                    related_change_id="chg-second",
                    files=[("artifacts/main.tf", kubernetes_yaml.encode("utf-8"))],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertTrue(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.evidence_coverage, 1.0)
        self.assertEqual(scenario.missing_expected_evidence_ids, [])

    def test_ansible_duplicate_task_name_uses_related_change_occurrence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="expected task marker")
            playbook_yaml = (
                "- hosts: all\n"
                "  tasks:\n"
                "    - name: Restart service\n"
                "      debug:\n"
                "        msg: wrong task marker\n"
                "    - name: Restart service\n"
                "      debug:\n"
                "        msg: expected task marker\n"
            )
            (corpus_root / "scenarios" / "single" / "artifacts" / "main.tf").write_text(
                playbook_yaml,
                encoding="utf-8",
            )
            changes = [
                UnifiedChange(
                    change_id="chg-first",
                    source_file="artifacts/main.tf",
                    tool="ansible",
                    resource_id="Restart service",
                    action="modify",
                    summary="First duplicate task.",
                ),
                UnifiedChange(
                    change_id="chg-second",
                    source_file="artifacts/main.tf",
                    tool="ansible",
                    resource_id="Restart service",
                    action="modify",
                    summary="Second duplicate task.",
                ),
            ]

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result_with_changes(
                    artifact_path="artifacts/main.tf",
                    tool="ansible",
                    resource_id="Restart service",
                    changes=changes,
                    related_change_id="chg-second",
                    files=[("artifacts/main.tf", playbook_yaml.encode("utf-8"))],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertTrue(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.evidence_coverage, 1.0)
        self.assertEqual(scenario.missing_expected_evidence_ids, [])

    def test_jenkins_duplicate_stage_name_uses_related_change_occurrence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="expected stage marker")
            jenkinsfile = (
                'stage("Deploy") { steps { echo "wrong stage marker" } }\n'
                'stage("Deploy") { steps { echo "expected stage marker" } }\n'
            )
            (corpus_root / "scenarios" / "single" / "artifacts" / "main.tf").write_text(
                jenkinsfile,
                encoding="utf-8",
            )
            changes = [
                UnifiedChange(
                    change_id="chg-first",
                    source_file="artifacts/main.tf",
                    tool="jenkins",
                    resource_id="stage/Deploy",
                    action="modify",
                    summary="First duplicate stage.",
                ),
                UnifiedChange(
                    change_id="chg-second",
                    source_file="artifacts/main.tf",
                    tool="jenkins",
                    resource_id="stage/Deploy",
                    action="modify",
                    summary="Second duplicate stage.",
                ),
            ]

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result_with_changes(
                    artifact_path="artifacts/main.tf",
                    tool="jenkins",
                    resource_id="stage/Deploy",
                    changes=changes,
                    related_change_id="chg-second",
                    files=[("artifacts/main.tf", jenkinsfile.encode("utf-8"))],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertTrue(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.evidence_coverage, 1.0)
        self.assertEqual(scenario.missing_expected_evidence_ids, [])

    def test_one_observed_evidence_cannot_cover_multiple_expected_evidence_ids(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="first marker")
            scenario_path = corpus_root / "scenarios" / "single" / "scenario.json"
            scenario_payload = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario_payload["expected_evidence"].append(
                {
                    "id": "evidence-second-marker",
                    "artifact_path": "artifacts/main.tf",
                    "selector": "second marker",
                    "description": "Second expected marker evidence.",
                }
            )
            scenario_payload["expected_findings"][0]["evidence_ids"] = [
                "evidence-expected-marker",
                "evidence-second-marker",
            ]
            scenario_path.write_text(json.dumps(scenario_payload), encoding="utf-8")
            (corpus_root / "scenarios" / "single" / "artifacts" / "main.tf").write_text(
                "resource fixture\nfirst marker\nsecond marker\n",
                encoding="utf-8",
            )

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    evidence_summary="Observed evidence covers first marker and second marker.",
                    files=[
                        (
                            "artifacts/main.tf",
                            b"resource fixture\nfirst marker\nsecond marker\n",
                        )
                    ],
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertFalse(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.evidence_coverage, 0.5)
        self.assertEqual(
            scenario.missing_expected_evidence_ids, ["evidence-second-marker"]
        )
        self.assertEqual(scenario.finding_coverage, 0.0)

    def test_finding_coverage_requires_expected_finding_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="expected marker")

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(finding_title="HIGH: Different risk"),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertFalse(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.evidence_coverage, 1.0)
        self.assertEqual(scenario.finding_coverage, 0.0)
        self.assertEqual(
            scenario.missing_expected_finding_ids, ["finding-expected-risk"]
        )

    def test_warn_expectation_fails_on_stop_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="expected marker")

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                return_value=_analysis_result(
                    assessment_severity="critical",
                    assessment_recommendation="no-go",
                    assessment_score=92,
                ),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertFalse(result.passed)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.expected_verdict, "warn")
        self.assertEqual(scenario.actual_verdict, "stop")
        self.assertFalse(scenario.passed)

    def test_failed_expected_unsupported_scenario_counts_as_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_unsupported_corpus(corpus_root)
            scenario_path = corpus_root / "scenarios" / "notes-only" / "scenario.json"
            scenario_payload = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario_payload["expected_findings"][0]["title"] = "Different finding"
            scenario_path.write_text(json.dumps(scenario_payload), encoding="utf-8")

            result = run_benchmark_corpus(corpus_root)

        self.assertFalse(result.passed)
        self.assertEqual(result.summary.failed_count, 1)
        self.assertEqual(result.summary.unsupported_count, 0)
        scenario = result.scenarios[0]
        self.assertTrue(scenario.unsupported)
        self.assertEqual(scenario.status, "failed")
        self.assertEqual(scenario.finding_coverage, 0.0)

    def test_unsupported_finding_coverage_requires_artifact_specific_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_unsupported_two_artifact_corpus(corpus_root)

            result = run_benchmark_corpus(corpus_root)

        self.assertFalse(result.passed)
        self.assertEqual(result.summary.failed_count, 1)
        self.assertEqual(result.summary.unsupported_count, 0)
        scenario = result.scenarios[0]
        self.assertTrue(scenario.unsupported)
        self.assertEqual(scenario.status, "failed")
        self.assertEqual(scenario.evidence_coverage, 1.0)
        self.assertEqual(scenario.finding_coverage, 0.5)
        self.assertEqual(
            scenario.missing_expected_finding_ids, ["finding-two-mismatched"]
        )
        refs_by_title = {
            finding.title: finding.evidence_refs for finding in scenario.findings
        }
        self.assertEqual(
            refs_by_title["Unsupported artifact: artifacts/one.txt"], ["evidence-one"]
        )
        self.assertEqual(
            refs_by_title["Unsupported artifact: artifacts/two.txt"], ["evidence-two"]
        )

    def test_unsupported_evidence_coverage_requires_selector_in_current_artifact_text(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_unsupported_corpus(corpus_root)

            with patch(
                "services.benchmark_runner_service._scenario_files",
                return_value=[("artifacts/notes.txt", b"different unsupported note\n")],
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertFalse(result.passed)
        self.assertEqual(result.summary.failed_count, 1)
        self.assertEqual(result.summary.unsupported_count, 0)
        scenario = result.scenarios[0]
        self.assertTrue(scenario.unsupported)
        self.assertEqual(scenario.evidence_coverage, 0.0)
        self.assertEqual(scenario.finding_coverage, 0.0)
        self.assertEqual(scenario.missing_expected_evidence_ids, ["evidence-notes"])

    def test_scenario_file_read_rejects_artifact_paths_that_escape_corpus(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            scenario_dir = corpus_root / "scenarios" / "single"
            scenario_dir.mkdir(parents=True)
            (corpus_root.parent / "outside.txt").write_text(
                "outside marker",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "escapes corpus"):
                benchmark_runner_module._scenario_files(
                    corpus_root=corpus_root,
                    scenario_path="scenarios/single/scenario.json",
                    artifacts=[SimpleNamespace(path="../../../outside.txt")],
                )

    def test_execution_failure_does_not_count_as_unsupported_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_root = Path(tmpdir)
            _write_single_scenario_corpus(corpus_root, selector="expected marker")

            with patch(
                "services.benchmark_runner_service._run_analysis_core",
                side_effect=RuntimeError("analysis core crashed"),
            ):
                result = run_benchmark_corpus(corpus_root)

        self.assertFalse(result.passed)
        self.assertEqual(result.summary.failed_count, 1)
        self.assertEqual(result.summary.unsupported_count, 0)
        scenario = result.scenarios[0]
        self.assertEqual(scenario.status, "failed")
        self.assertEqual(scenario.actual_verdict, "error")
        self.assertFalse(scenario.unsupported)
        self.assertEqual(scenario.unsupported_reasons, [])
        self.assertEqual(scenario.errors, ["analysis core crashed"])

    def test_runner_uses_shared_analysis_artifact_builder(self) -> None:
        with patch(
            "services.benchmark_runner_service.build_analysis_artifacts",
            wraps=__import__(
                "services.analysis_service", fromlist=["build_analysis_artifacts"]
            ).build_analysis_artifacts,
        ) as build_analysis_artifacts:
            result = run_benchmark_corpus()

        self.assertEqual(
            build_analysis_artifacts.call_count, result.summary.scenario_count
        )
        for call in build_analysis_artifacts.call_args_list:
            self.assertFalse(call.kwargs["include_topology_context"])
            self.assertFalse(call.kwargs["include_incident_context"])
            self.assertFalse(call.kwargs["include_narrative"])
            self.assertFalse(call.kwargs["allow_llm_assistance"])

    def test_benchmark_profile_skips_ambient_topology_narrative_and_llm(self) -> None:
        def fail_ambient_call(*args, **kwargs):
            raise AssertionError("benchmark run touched ambient service state")

        with (
            patch(
                "services.analysis_service.load_topology", side_effect=fail_ambient_call
            ),
            patch(
                "services.analysis_service.get_topology_status",
                side_effect=fail_ambient_call,
            ),
            patch(
                "services.analysis_service.generate_narrative",
                side_effect=fail_ambient_call,
            ),
            patch(
                "analysis.risk_scorer.generate_completion_with_settings",
                side_effect=fail_ambient_call,
            ),
        ):
            result = run_benchmark_corpus()

        self.assertEqual(result.summary.scenario_count, len(result.scenarios))
