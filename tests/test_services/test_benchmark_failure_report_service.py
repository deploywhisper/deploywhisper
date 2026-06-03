"""Tests for honest benchmark failure report generation."""

from __future__ import annotations

import unittest

from services.benchmark_failure_report_service import generate_honest_failure_report
from services.benchmark_runner_service import (
    BenchmarkRunResult,
    BenchmarkRunSummary,
    BenchmarkScenarioRunResult,
)


def _summary(*, scenario_count: int = 3) -> BenchmarkRunSummary:
    return BenchmarkRunSummary(
        corpus_id="honest-report-corpus",
        version="1.0.0",
        scenario_count=scenario_count,
        passed_count=1,
        failed_count=1,
        unsupported_count=1,
        total_latency_ms=42.0,
        generated_at="2026-06-03T00:00:00Z",
    )


def _scenario(
    *,
    scenario_id: str,
    name: str,
    passed: bool,
    status: str,
    expected_verdict: str,
    actual_verdict: str,
    expected_finding_count: int = 1,
    actual_finding_count: int = 1,
    finding_coverage: float = 1.0,
    missing_expected_finding_ids: list[str] | None = None,
    expected_evidence_count: int = 1,
    actual_evidence_count: int = 1,
    evidence_coverage: float = 1.0,
    missing_expected_evidence_ids: list[str] | None = None,
    unsupported: bool = False,
    unsupported_reasons: list[str] | None = None,
    coverage_warnings: list[str] | None = None,
    errors: list[str] | None = None,
    evidence_law_violations: list[str] | None = None,
) -> BenchmarkScenarioRunResult:
    return BenchmarkScenarioRunResult(
        id=scenario_id,
        name=name,
        path=f"scenarios/{scenario_id}/scenario.json",
        passed=passed,
        status=status,  # type: ignore[arg-type]
        expected_verdict=expected_verdict,  # type: ignore[arg-type]
        actual_verdict=actual_verdict,  # type: ignore[arg-type]
        actual_recommendation="go" if actual_verdict == "go" else "no-go",
        actual_severity="low" if actual_verdict == "go" else "high",
        actual_score=10 if actual_verdict == "go" else 80,
        expected_finding_count=expected_finding_count,
        actual_finding_count=actual_finding_count,
        finding_coverage=finding_coverage,
        missing_expected_finding_ids=missing_expected_finding_ids or [],
        expected_evidence_count=expected_evidence_count,
        actual_evidence_count=actual_evidence_count,
        evidence_coverage=evidence_coverage,
        missing_expected_evidence_ids=missing_expected_evidence_ids or [],
        evidence_law_status="Satisfied",
        evidence_law_detail="Evidence Law satisfied.",
        evidence_law_violations=evidence_law_violations or [],
        latency_ms=1.0,
        unsupported=unsupported,
        unsupported_reasons=unsupported_reasons or [],
        coverage_warnings=coverage_warnings or [],
        findings=[],
        errors=errors or [],
    )


class BenchmarkFailureReportServiceTests(unittest.TestCase):
    def test_report_includes_required_honest_failure_categories(self) -> None:
        detected = _scenario(
            scenario_id="detected-risk",
            name="Detected risk",
            passed=True,
            status="passed",
            expected_verdict="warn",
            actual_verdict="warn",
        )
        missed = _scenario(
            scenario_id="missed-risk",
            name="Missed risk",
            passed=False,
            status="failed",
            expected_verdict="stop",
            actual_verdict="go",
            actual_finding_count=0,
            finding_coverage=0.0,
            missing_expected_finding_ids=["finding-critical"],
            actual_evidence_count=0,
            evidence_coverage=0.0,
            missing_expected_evidence_ids=["evidence-critical"],
            coverage_warnings=["artifact.tf: accepted - partial parser coverage"],
        )
        unsupported = _scenario(
            scenario_id="unsupported-notes",
            name="Unsupported notes",
            passed=True,
            status="unsupported",
            expected_verdict="unsupported",
            actual_verdict="unsupported",
            expected_finding_count=1,
            unsupported=True,
            unsupported_reasons=[
                "No benchmark artifacts were parsed by supported parsers."
            ],
        )
        result = BenchmarkRunResult(
            passed=False,
            summary=_summary(),
            scenarios=[detected, missed, unsupported],
        )

        report = generate_honest_failure_report(result)

        self.assertEqual(report.summary.corpus_id, "honest-report-corpus")
        self.assertEqual([item.id for item in report.improvements], ["detected-risk"])
        self.assertEqual(
            [item.id for item in report.detected_scenarios], ["detected-risk"]
        )
        self.assertEqual([item.id for item in report.regressions], ["missed-risk"])
        self.assertEqual([item.id for item in report.missed_scenarios], ["missed-risk"])
        self.assertEqual(
            [item.id for item in report.false_reassurance], ["missed-risk"]
        )
        self.assertEqual(report.false_positives, [])
        self.assertEqual(
            [item.id for item in report.unsupported_scenarios],
            ["unsupported-notes"],
        )
        self.assertEqual(report.evidence_coverage.expected_evidence_count, 3)
        self.assertEqual(report.evidence_coverage.missing_expected_evidence_count, 1)
        self.assertEqual(
            report.evidence_coverage.scenarios_below_full_coverage, ["missed-risk"]
        )
        self.assertTrue(report.context_limitations)
        self.assertIn(
            "Historical baseline not configured",
            report.context_limitations[0].message,
        )

    def test_material_misses_create_linked_issues_unless_out_of_scope(self) -> None:
        missed = _scenario(
            scenario_id="missed-risk",
            name="Missed risk",
            passed=False,
            status="failed",
            expected_verdict="warn",
            actual_verdict="go",
            actual_finding_count=0,
            finding_coverage=0.0,
            missing_expected_finding_ids=["finding-risk"],
        )
        unsupported = _scenario(
            scenario_id="unsupported-notes",
            name="Unsupported notes",
            passed=True,
            status="unsupported",
            expected_verdict="unsupported",
            actual_verdict="unsupported",
            unsupported=True,
            unsupported_reasons=["Plain text is outside parser scope."],
        )
        result = BenchmarkRunResult(
            passed=False,
            summary=_summary(scenario_count=2),
            scenarios=[missed, unsupported],
        )

        report = generate_honest_failure_report(result)

        self.assertEqual(len(report.linked_issues), 1)
        issue = report.linked_issues[0]
        self.assertEqual(issue.scenario_id, "missed-risk")
        self.assertEqual(issue.category, "material_miss")
        self.assertEqual(issue.link, "benchmark://issues/benchmark-issue-missed-risk")
        self.assertIn("finding-risk", issue.missing_expected_finding_ids)
        self.assertNotIn(
            "unsupported-notes",
            {linked_issue.scenario_id for linked_issue in report.linked_issues},
        )

    def test_unexpected_unsupported_failure_is_material_miss(self) -> None:
        scenario = _scenario(
            scenario_id="expected-supported-risk",
            name="Expected supported risk",
            passed=False,
            status="failed",
            expected_verdict="warn",
            actual_verdict="unsupported",
            actual_finding_count=0,
            finding_coverage=0.0,
            missing_expected_finding_ids=["finding-supported-risk"],
            actual_evidence_count=0,
            evidence_coverage=0.0,
            missing_expected_evidence_ids=["evidence-supported-risk"],
            unsupported=True,
            unsupported_reasons=[
                "No benchmark artifacts were parsed by supported parsers."
            ],
        )
        result = BenchmarkRunResult(
            passed=False,
            summary=_summary(scenario_count=1),
            scenarios=[scenario],
        )

        report = generate_honest_failure_report(result)

        self.assertEqual(
            [item.id for item in report.missed_scenarios],
            ["expected-supported-risk"],
        )
        self.assertEqual(
            [issue.scenario_id for issue in report.linked_issues],
            ["expected-supported-risk"],
        )
        self.assertEqual(report.linked_issues[0].category, "material_miss")
        self.assertEqual(
            [item.id for item in report.unsupported_scenarios],
            ["expected-supported-risk"],
        )

    def test_expected_go_overreporting_is_false_positive_not_material_miss(
        self,
    ) -> None:
        false_positive = _scenario(
            scenario_id="clean-change",
            name="Clean change",
            passed=False,
            status="failed",
            expected_verdict="go",
            actual_verdict="warn",
            expected_finding_count=0,
            actual_finding_count=1,
            expected_evidence_count=0,
            actual_evidence_count=1,
        )
        result = BenchmarkRunResult(
            passed=False,
            summary=_summary(scenario_count=1),
            scenarios=[false_positive],
        )

        report = generate_honest_failure_report(result)

        self.assertEqual([item.id for item in report.false_positives], ["clean-change"])
        self.assertEqual(report.missed_scenarios, [])
        self.assertEqual(report.linked_issues, [])

    def test_summary_includes_evidence_law_violation_count(self) -> None:
        scenario = _scenario(
            scenario_id="unsupported-severe-claim",
            name="Unsupported severe claim",
            passed=False,
            status="failed",
            expected_verdict="warn",
            actual_verdict="error",
            evidence_law_violations=[
                "Unsupported high severity claim.",
                "Missing deterministic evidence.",
            ],
        )
        result = BenchmarkRunResult(
            passed=False,
            summary=_summary(scenario_count=1),
            scenarios=[scenario],
        )

        report = generate_honest_failure_report(result)

        self.assertEqual(report.summary.evidence_law_violation_count, 2)


if __name__ == "__main__":
    unittest.main()
