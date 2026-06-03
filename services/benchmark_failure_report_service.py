"""Honest benchmark failure report generation."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field


BenchmarkIssueCategory = Literal[
    "material_miss", "false_reassurance", "regression", "false_positive"
]

VERDICT_ORDER = {"go": 0, "warn": 1, "stop": 2}


class BenchmarkReportSummary(BaseModel):
    """Aggregate benchmark report identity and outcome."""

    corpus_id: str
    version: str
    scenario_count: int
    passed_count: int
    failed_count: int
    unsupported_count: int
    evidence_law_violation_count: int
    generated_at: str


class BenchmarkReportScenario(BaseModel):
    """Scenario entry included in an honest failure report category."""

    id: str
    name: str
    path: str
    status: str
    expected_verdict: str
    actual_verdict: str
    expected_finding_count: int
    actual_finding_count: int
    finding_coverage: float
    missing_expected_finding_ids: list[str] = Field(default_factory=list)
    expected_evidence_count: int
    actual_evidence_count: int
    evidence_coverage: float
    missing_expected_evidence_ids: list[str] = Field(default_factory=list)
    issue_refs: list[str] = Field(default_factory=list)


class BenchmarkEvidenceCoverageReport(BaseModel):
    """Aggregate evidence coverage for a benchmark run."""

    expected_evidence_count: int
    actual_evidence_count: int
    covered_expected_evidence_count: int
    missing_expected_evidence_count: int
    average_evidence_coverage: float
    scenarios_below_full_coverage: list[str] = Field(default_factory=list)
    missing_expected_evidence_ids: list[str] = Field(default_factory=list)


class BenchmarkContextLimitation(BaseModel):
    """Limitation that constrains benchmark interpretation."""

    scope: str
    scenario_id: str | None = None
    message: str


class BenchmarkLinkedIssue(BaseModel):
    """Deterministic local issue record for a benchmark failure."""

    issue_id: str
    link: str
    scenario_id: str
    category: BenchmarkIssueCategory
    severity: str
    title: str
    missing_expected_finding_ids: list[str] = Field(default_factory=list)
    missing_expected_evidence_ids: list[str] = Field(default_factory=list)


class BenchmarkHonestFailureReport(BaseModel):
    """Honest benchmark report including misses and report limitations."""

    summary: BenchmarkReportSummary
    improvements: list[BenchmarkReportScenario] = Field(default_factory=list)
    regressions: list[BenchmarkReportScenario] = Field(default_factory=list)
    detected_scenarios: list[BenchmarkReportScenario] = Field(default_factory=list)
    missed_scenarios: list[BenchmarkReportScenario] = Field(default_factory=list)
    false_reassurance: list[BenchmarkReportScenario] = Field(default_factory=list)
    false_positives: list[BenchmarkReportScenario] = Field(default_factory=list)
    unsupported_scenarios: list[BenchmarkReportScenario] = Field(default_factory=list)
    evidence_coverage: BenchmarkEvidenceCoverageReport
    context_limitations: list[BenchmarkContextLimitation] = Field(default_factory=list)
    linked_issues: list[BenchmarkLinkedIssue] = Field(default_factory=list)


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "scenario"


def _expected_more_severe_than_actual(scenario: Any) -> bool:
    expected = _get(scenario, "expected_verdict")
    actual = _get(scenario, "actual_verdict")
    if expected not in VERDICT_ORDER:
        return False
    if actual not in VERDICT_ORDER:
        return expected in {"warn", "stop"}
    return VERDICT_ORDER[expected] > VERDICT_ORDER[actual]


def _is_unsupported(scenario: Any) -> bool:
    return (
        bool(_get(scenario, "unsupported")) or _get(scenario, "status") == "unsupported"
    )


def _is_out_of_scope_unsupported(scenario: Any) -> bool:
    return (
        _is_unsupported(scenario)
        and _get(scenario, "expected_verdict") == "unsupported"
    )


def _is_false_positive(scenario: Any) -> bool:
    return (
        _get(scenario, "expected_verdict") == "go"
        and not _get(scenario, "passed", False)
        and (
            _get(scenario, "actual_verdict") in {"warn", "stop"}
            or _get(scenario, "actual_finding_count", 0)
            > _get(scenario, "expected_finding_count", 0)
        )
    )


def _is_missed(scenario: Any) -> bool:
    if _is_out_of_scope_unsupported(scenario) or _is_false_positive(scenario):
        return False
    return (
        bool(_get(scenario, "missing_expected_finding_ids", []))
        or bool(_get(scenario, "missing_expected_evidence_ids", []))
        or _expected_more_severe_than_actual(scenario)
        or _get(scenario, "actual_verdict") == "error"
    )


def _is_false_reassurance(scenario: Any) -> bool:
    if _is_out_of_scope_unsupported(scenario) or _is_false_positive(scenario):
        return False
    return _get(scenario, "expected_verdict") in {
        "warn",
        "stop",
    } and _expected_more_severe_than_actual(scenario)


def _scenario_entry(
    scenario: Any, *, issue_refs: list[str] | None = None
) -> BenchmarkReportScenario:
    return BenchmarkReportScenario(
        id=_get(scenario, "id"),
        name=_get(scenario, "name"),
        path=_get(scenario, "path"),
        status=_get(scenario, "status"),
        expected_verdict=_get(scenario, "expected_verdict"),
        actual_verdict=_get(scenario, "actual_verdict"),
        expected_finding_count=_get(scenario, "expected_finding_count", 0),
        actual_finding_count=_get(scenario, "actual_finding_count", 0),
        finding_coverage=_get(scenario, "finding_coverage", 0.0),
        missing_expected_finding_ids=list(
            _get(scenario, "missing_expected_finding_ids", [])
        ),
        expected_evidence_count=_get(scenario, "expected_evidence_count", 0),
        actual_evidence_count=_get(scenario, "actual_evidence_count", 0),
        evidence_coverage=_get(scenario, "evidence_coverage", 0.0),
        missing_expected_evidence_ids=list(
            _get(scenario, "missing_expected_evidence_ids", [])
        ),
        issue_refs=issue_refs or [],
    )


def _issue_category(scenario: Any) -> BenchmarkIssueCategory:
    if _get(scenario, "missing_expected_finding_ids", []) or _get(
        scenario, "missing_expected_evidence_ids", []
    ):
        return "material_miss"
    if _is_false_reassurance(scenario):
        return "false_reassurance"
    if _is_false_positive(scenario):
        return "false_positive"
    if _get(scenario, "status") == "failed":
        return "material_miss"
    return "regression"


def _linked_issue(scenario: Any) -> BenchmarkLinkedIssue:
    issue_id = f"benchmark-issue-{_slug(_get(scenario, 'id'))}"
    return BenchmarkLinkedIssue(
        issue_id=issue_id,
        link=f"benchmark://issues/{issue_id}",
        scenario_id=_get(scenario, "id"),
        category=_issue_category(scenario),
        severity=_get(scenario, "actual_severity", "unknown"),
        title=f"Benchmark miss: {_get(scenario, 'name')}",
        missing_expected_finding_ids=list(
            _get(scenario, "missing_expected_finding_ids", [])
        ),
        missing_expected_evidence_ids=list(
            _get(scenario, "missing_expected_evidence_ids", [])
        ),
    )


def _evidence_coverage(scenarios: list[Any]) -> BenchmarkEvidenceCoverageReport:
    expected_count = sum(
        _get(scenario, "expected_evidence_count", 0) for scenario in scenarios
    )
    actual_count = sum(
        _get(scenario, "actual_evidence_count", 0) for scenario in scenarios
    )
    missing_ids = [
        evidence_id
        for scenario in scenarios
        for evidence_id in _get(scenario, "missing_expected_evidence_ids", [])
    ]
    coverage_values = [
        _get(scenario, "evidence_coverage", 0.0) for scenario in scenarios
    ]
    average = (
        round(sum(coverage_values) / len(coverage_values), 2)
        if coverage_values
        else 1.0
    )
    return BenchmarkEvidenceCoverageReport(
        expected_evidence_count=expected_count,
        actual_evidence_count=actual_count,
        covered_expected_evidence_count=max(expected_count - len(missing_ids), 0),
        missing_expected_evidence_count=len(missing_ids),
        average_evidence_coverage=average,
        scenarios_below_full_coverage=[
            _get(scenario, "id")
            for scenario in scenarios
            if _get(scenario, "evidence_coverage", 0.0) < 1.0
        ],
        missing_expected_evidence_ids=missing_ids,
    )


def _evidence_law_violation_count(scenarios: list[Any]) -> int:
    return sum(
        len(_get(scenario, "evidence_law_violations", [])) for scenario in scenarios
    )


def _context_limitations(scenarios: list[Any]) -> list[BenchmarkContextLimitation]:
    limitations = [
        BenchmarkContextLimitation(
            scope="benchmark_baseline",
            message=(
                "Historical baseline not configured; improvements and regressions "
                "are derived from the current benchmark run outcome."
            ),
        )
    ]
    for scenario in scenarios:
        scenario_id = _get(scenario, "id")
        for warning in _get(scenario, "coverage_warnings", []):
            limitations.append(
                BenchmarkContextLimitation(
                    scope="coverage_warning",
                    scenario_id=scenario_id,
                    message=warning,
                )
            )
        for reason in _get(scenario, "unsupported_reasons", []):
            limitations.append(
                BenchmarkContextLimitation(
                    scope="unsupported",
                    scenario_id=scenario_id,
                    message=reason,
                )
            )
        for error in _get(scenario, "errors", []):
            limitations.append(
                BenchmarkContextLimitation(
                    scope="scenario_error",
                    scenario_id=scenario_id,
                    message=error,
                )
            )
        for violation in _get(scenario, "evidence_law_violations", []):
            limitations.append(
                BenchmarkContextLimitation(
                    scope="evidence_law",
                    scenario_id=scenario_id,
                    message=violation,
                )
            )
    return limitations


def generate_honest_failure_report(run_result: Any) -> BenchmarkHonestFailureReport:
    """Generate an honest failure report from a benchmark run result."""

    summary = _get(run_result, "summary")
    scenarios = list(_get(run_result, "scenarios", []))
    linked_issues = [
        _linked_issue(scenario)
        for scenario in scenarios
        if _is_missed(scenario) and not _is_out_of_scope_unsupported(scenario)
    ]
    issue_refs_by_scenario = {
        issue.scenario_id: [issue.link] for issue in linked_issues
    }
    return BenchmarkHonestFailureReport(
        summary=BenchmarkReportSummary(
            corpus_id=_get(summary, "corpus_id"),
            version=_get(summary, "version"),
            scenario_count=_get(summary, "scenario_count", 0),
            passed_count=_get(summary, "passed_count", 0),
            failed_count=_get(summary, "failed_count", 0),
            unsupported_count=_get(summary, "unsupported_count", 0),
            evidence_law_violation_count=_evidence_law_violation_count(scenarios),
            generated_at=_get(summary, "generated_at"),
        ),
        improvements=[
            _scenario_entry(scenario)
            for scenario in scenarios
            if _get(scenario, "passed", False) and not _is_unsupported(scenario)
        ],
        regressions=[
            _scenario_entry(
                scenario,
                issue_refs=issue_refs_by_scenario.get(_get(scenario, "id"), []),
            )
            for scenario in scenarios
            if _is_missed(scenario)
        ],
        detected_scenarios=[
            _scenario_entry(scenario)
            for scenario in scenarios
            if not _is_unsupported(scenario)
            and not _is_false_positive(scenario)
            and _get(scenario, "finding_coverage", 0.0) == 1.0
            and _get(scenario, "evidence_coverage", 0.0) == 1.0
        ],
        missed_scenarios=[
            _scenario_entry(
                scenario,
                issue_refs=issue_refs_by_scenario.get(_get(scenario, "id"), []),
            )
            for scenario in scenarios
            if _is_missed(scenario)
        ],
        false_reassurance=[
            _scenario_entry(
                scenario,
                issue_refs=issue_refs_by_scenario.get(_get(scenario, "id"), []),
            )
            for scenario in scenarios
            if _is_false_reassurance(scenario)
        ],
        false_positives=[
            _scenario_entry(scenario)
            for scenario in scenarios
            if _is_false_positive(scenario)
        ],
        unsupported_scenarios=[
            _scenario_entry(scenario)
            for scenario in scenarios
            if _is_unsupported(scenario)
        ],
        evidence_coverage=_evidence_coverage(scenarios),
        context_limitations=_context_limitations(scenarios),
        linked_issues=linked_issues,
    )
