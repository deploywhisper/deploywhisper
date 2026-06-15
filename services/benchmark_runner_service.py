"""Benchmark corpus execution against the shared analysis core."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Literal
import json
import re

from pydantic import BaseModel, Field
import yaml

from analysis.risk_scorer import RiskAssessment
from evidence.models import EvidenceItem, Finding
from parsers.base import ParseBatchResult, UnifiedChange
from parsers.cloudformation_parser import load_cloudformation_template
from services.analysis_service import (
    AnalysisArtifacts,
    build_analysis_artifacts,
)
from services.benchmark_corpus_service import (
    BenchmarkExpectedEvidence,
    BenchmarkExpectedFinding,
    ExpectedVerdict,
    load_benchmark_corpus,
)
from services.benchmark_failure_report_service import (
    BenchmarkHonestFailureReport,
    generate_honest_failure_report,
)
from services.confidence_ledger import EvidenceLawStatus, evidence_law_status
from services.submission_manifest import SubmissionManifest


ScenarioStatus = Literal["passed", "failed", "unsupported"]
ObservedVerdict = Literal[
    "go", "warn", "stop", "unsupported", "insufficient_context", "error"
]

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class BenchmarkObservedFinding(BaseModel):
    """Finding detail captured from one benchmark scenario run."""

    finding_id: str
    title: str
    severity: str
    deterministic: bool
    confidence: float
    evidence_refs: list[str] = Field(default_factory=list)


class BenchmarkScenarioRunResult(BaseModel):
    """Execution result for one benchmark scenario."""

    id: str
    name: str
    path: str
    passed: bool
    status: ScenarioStatus
    expected_verdict: ExpectedVerdict
    actual_verdict: ObservedVerdict
    actual_recommendation: str
    actual_severity: str
    actual_score: int
    expected_finding_count: int
    actual_finding_count: int
    finding_coverage: float
    missing_expected_finding_ids: list[str] = Field(default_factory=list)
    expected_evidence_count: int
    actual_evidence_count: int
    evidence_coverage: float
    missing_expected_evidence_ids: list[str] = Field(default_factory=list)
    evidence_law_status: EvidenceLawStatus
    evidence_law_detail: str
    evidence_law_violations: list[str] = Field(default_factory=list)
    latency_ms: float
    unsupported: bool
    unsupported_reasons: list[str] = Field(default_factory=list)
    coverage_warnings: list[str] = Field(default_factory=list)
    findings: list[BenchmarkObservedFinding] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BenchmarkRunSummary(BaseModel):
    """Aggregate benchmark run summary."""

    corpus_id: str
    version: str
    scenario_count: int
    passed_count: int
    failed_count: int
    unsupported_count: int
    total_latency_ms: float
    generated_at: str


class BenchmarkRunResult(BaseModel):
    """Complete benchmark run result."""

    passed: bool
    summary: BenchmarkRunSummary
    scenarios: list[BenchmarkScenarioRunResult]
    honest_failure_report: BenchmarkHonestFailureReport | None = None


def _timestamp() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _scenario_files(
    *, corpus_root: Path, scenario_path: str, artifacts: list
) -> list[tuple[str, bytes | None]]:
    root = corpus_root.resolve()
    scenario_dir = (root / scenario_path).resolve().parent
    files: list[tuple[str, bytes | None]] = []
    for artifact in artifacts:
        artifact_path = (scenario_dir / artifact.path).resolve()
        try:
            artifact_path.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"benchmark artifact escapes corpus: {artifact.path}"
            ) from exc
        if artifact_path.is_symlink() or not artifact_path.is_file():
            raise ValueError(f"benchmark artifact must be a file: {artifact.path}")
        files.append((artifact.path, artifact_path.read_bytes()))
    return files


def _manifest_coverage_warnings(manifest: SubmissionManifest) -> list[str]:
    warnings: list[str] = []
    for item in manifest.items:
        if item.status == "accepted":
            continue
        warnings.append(f"{item.name}: {item.status} - {item.message}")
    return warnings


def _unsupported_reasons(manifest: SubmissionManifest) -> list[str]:
    reasons = _manifest_coverage_warnings(manifest)
    if manifest.analyzed_artifact_count == 0:
        reasons.append("No benchmark artifacts were parsed by supported parsers.")
    return reasons


def _actual_verdict(
    assessment: RiskAssessment, *, unsupported: bool
) -> ObservedVerdict:
    if unsupported:
        return "unsupported"
    if assessment.context_completeness.insufficient_context:
        return "insufficient_context"
    if assessment.recommendation == "go" and assessment.severity == "low":
        return "go"
    if assessment.recommendation == "no-go" and assessment.severity == "critical":
        return "stop"
    return "warn"


def _expected_verdict_matches(
    expected: ExpectedVerdict,
    *,
    actual: ObservedVerdict,
    unsupported: bool,
) -> bool:
    if expected == "unsupported":
        return unsupported and actual == "unsupported"
    if expected == "insufficient_context":
        return actual == "insufficient_context"
    if expected == "go":
        return actual == "go"
    if expected == "stop":
        return actual == "stop"
    return actual == "warn"


def _normalize_match_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains_expected_text(*, haystack: str, needle: str) -> bool:
    return _normalize_match_text(needle) in _normalize_match_text(haystack)


def _evidence_match_text(item: EvidenceItem) -> str:
    return "\n".join(
        (
            item.source_ref,
            item.location,
            item.resource,
            item.operation,
            item.summary,
        )
    )


def _matching_brace_block(content: str, start_index: int) -> str:
    brace_index = content.find("{", start_index)
    if brace_index == -1:
        return ""
    depth = 0
    in_quote: str | None = None
    escaped = False
    for index in range(brace_index, len(content)):
        character = content[index]
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if in_quote:
            if character == in_quote:
                in_quote = None
            continue
        if character in {"'", '"'}:
            in_quote = character
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return content[start_index : index + 1]
    return content[start_index:]


def _yaml_key_block(content: str, key: str) -> str:
    pattern = re.compile(
        rf"(?m)^(?P<indent>\s*){re.escape(key)}\s*:\s*(?:#.*)?$",
    )
    match = pattern.search(content)
    if not match:
        return ""
    base_indent = len(match.group("indent"))
    end_index = len(content)
    for line_match in re.finditer(r"(?m)^(?P<indent>\s*)\S.*$", content[match.end() :]):
        line_indent = len(line_match.group("indent"))
        if line_indent <= base_indent:
            end_index = match.end() + line_match.start()
            break
    return content[match.start() : end_index].rstrip()


def _yaml_key_inline_block(content: str, key: str) -> str:
    pattern = re.compile(
        rf"(?m)^(?P<indent>\s*){re.escape(key)}\s*:\s*\S.*$",
    )
    match = pattern.search(content)
    if not match:
        return ""
    return match.group(0).rstrip()


def _yaml_top_level_key_block(content: str, key: str) -> str:
    pattern = re.compile(
        rf"(?m)^{re.escape(key)}\s*:\s*(?:#.*)?$",
    )
    match = pattern.search(content)
    if not match:
        return ""
    end_index = len(content)
    for line_match in re.finditer(r"(?m)^\S.*$", content[match.end() :]):
        end_index = match.end() + line_match.start()
        break
    return content[match.start() : end_index].rstrip()


def _yaml_sequence_name_block(content: str, name: str, occurrence: int = 0) -> str:
    pattern = re.compile(
        rf"(?m)^(?P<indent>\s*)-\s+name\s*:\s*['\"]?{re.escape(name)}['\"]?\s*(?:#.*)?$",
    )
    matches = list(pattern.finditer(content))
    match = matches[occurrence] if occurrence < len(matches) else None
    if not match:
        return ""
    base_indent = len(match.group("indent"))
    end_index = len(content)
    for line_match in re.finditer(
        r"(?m)^(?P<indent>\s*)-\s+\S.*$", content[match.end() :]
    ):
        line_indent = len(line_match.group("indent"))
        if line_indent <= base_indent:
            end_index = match.end() + line_match.start()
            break
    return content[match.start() : end_index].rstrip()


def _terraform_change_text(change: UnifiedChange, content: str) -> str:
    resource_type, _, resource_name = change.resource_id.partition(".")
    if not resource_type or not resource_name:
        return ""
    pattern = re.compile(
        r"resource\s+['\"]"
        + re.escape(resource_type)
        + r"['\"]\s+['\"]"
        + re.escape(resource_name)
        + r"['\"]\s*\{",
        re.IGNORECASE,
    )
    match = pattern.search(content)
    return _matching_brace_block(content, match.start()) if match else ""


def _cloudformation_change_text(change: UnifiedChange, content: str) -> str:
    prefix, _, resource_name = change.resource_id.partition("/")
    if prefix != "resource" or not resource_name:
        return ""
    try:
        payload = load_cloudformation_template(content)
    except (json.JSONDecodeError, yaml.YAMLError):
        return ""
    resources = payload.get("Resources", {}) if isinstance(payload, dict) else {}
    if not isinstance(resources, dict) or resource_name not in resources:
        return ""
    resource = resources[resource_name]
    if isinstance(resource, dict | list):
        return yaml.safe_dump(resource, sort_keys=True)
    return str(resource)


def _ansible_change_text(
    change: UnifiedChange, content: str, *, occurrence: int = 0
) -> str:
    return _yaml_sequence_name_block(content, change.resource_id, occurrence)


def _kubernetes_change_text(
    change: UnifiedChange, content: str, *, occurrence: int = 0
) -> str:
    kind, _, resource_name = change.resource_id.partition("/")
    if not kind or not resource_name:
        return ""
    documents = re.split(r"(?m)^---[ \t]*(?:#.*)?$", content)
    matched_count = 0
    for document in documents:
        try:
            payload = yaml.safe_load(document) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(payload, dict):
            continue
        metadata = payload.get("metadata", {})
        if (
            payload.get("kind") == kind
            and isinstance(metadata, dict)
            and metadata.get("name") == resource_name
        ):
            if matched_count != occurrence:
                matched_count += 1
                continue
            return document
    return ""


def _jenkins_change_text(
    change: UnifiedChange, content: str, *, occurrence: int = 0
) -> str:
    prefix, _, stage_name = change.resource_id.partition("/")
    if prefix != "stage" or not stage_name:
        return ""
    pattern = re.compile(
        r"stage\s*\(\s*['\"]" + re.escape(stage_name) + r"['\"]\s*\)",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(content))
    match = matches[occurrence] if occurrence < len(matches) else None
    return _matching_brace_block(content, match.start()) if match else ""


def _change_local_text(
    change: UnifiedChange,
    raw_artifact_text_by_path: dict[str, str],
    *,
    occurrence: int = 0,
) -> str:
    content = raw_artifact_text_by_path.get(change.source_file, "")
    if change.tool == "terraform":
        local_text = _terraform_change_text(change, content)
    elif change.tool == "cloudformation":
        local_text = _cloudformation_change_text(change, content)
    elif change.tool == "ansible":
        local_text = _ansible_change_text(change, content, occurrence=occurrence)
    elif change.tool == "kubernetes":
        local_text = _kubernetes_change_text(change, content, occurrence=occurrence)
    elif change.tool == "jenkins":
        local_text = _jenkins_change_text(change, content, occurrence=occurrence)
    else:
        local_text = content
    metadata_text = (
        json.dumps(change.metadata, sort_keys=True) if change.metadata else ""
    )
    return "\n".join(
        part
        for part in (change.resource_id, change.summary, metadata_text, local_text)
        if part
    )


def _change_local_text_by_id(
    parse_batch: ParseBatchResult,
    raw_artifact_text_by_path: dict[str, str],
) -> dict[str, str]:
    local_text_by_id: dict[str, str] = {}
    occurrence_by_key: dict[tuple[str, str, str], int] = {}
    for file_result in parse_batch.files:
        for change in file_result.changes:
            occurrence_key = (change.source_file, change.tool, change.resource_id)
            occurrence = occurrence_by_key.get(occurrence_key, 0)
            local_text_by_id[change.change_id] = _change_local_text(
                change,
                raw_artifact_text_by_path,
                occurrence=occurrence,
            )
            occurrence_by_key[occurrence_key] = occurrence + 1
    return local_text_by_id


def _evidence_local_match_text(
    item: EvidenceItem,
    change_local_text_by_id: dict[str, str],
) -> str:
    return "\n".join(
        [_evidence_match_text(item)]
        + [
            change_local_text_by_id[change_id]
            for change_id in item.related_change_ids
            if change_id in change_local_text_by_id
        ]
    )


def _finding_match_text(finding: Finding) -> str:
    return "\n".join(
        (
            finding.finding_id,
            finding.title,
            finding.description,
            finding.explanation,
            finding.category,
        )
    )


def _evidence_match_map(
    expected_evidence: list[BenchmarkExpectedEvidence],
    evidence_items: list[EvidenceItem],
    change_local_text_by_id: dict[str, str],
) -> dict[str, set[str]]:
    """Map observed evidence IDs to the expected evidence IDs they satisfy."""

    matched: dict[str, set[str]] = {}
    unmatched_items = [
        item
        for item in evidence_items
        if item.deterministic and item.source_type == "artifact"
    ]
    used_observed_ids: set[str] = set()
    for expected in expected_evidence:
        for item in unmatched_items:
            if item.evidence_id in used_observed_ids:
                continue
            if expected.artifact_path != item.artifact:
                continue
            match_text = _evidence_local_match_text(item, change_local_text_by_id)
            if not _contains_expected_text(
                haystack=match_text, needle=expected.selector
            ):
                continue
            matched.setdefault(item.evidence_id, set()).add(expected.id)
            used_observed_ids.add(item.evidence_id)
            break
    return matched


def _finding_coverage(
    expected_findings: list[BenchmarkExpectedFinding],
    findings: list[Finding],
    *,
    matched_expected_evidence_by_observed_id: dict[str, set[str]],
) -> tuple[float, list[str]]:
    if not expected_findings:
        return 1.0, []
    used_finding_ids: set[str] = set()
    missing: list[str] = []
    for expected in expected_findings:
        expected_order = SEVERITY_ORDER[expected.severity]
        matched = None
        for finding in findings:
            if finding.finding_id in used_finding_ids:
                continue
            if SEVERITY_ORDER[finding.severity] < expected_order:
                continue
            if not _contains_expected_text(
                haystack=_finding_match_text(finding),
                needle=expected.title,
            ):
                continue
            covered_expected_evidence_ids = set()
            for evidence_ref in finding.evidence_refs:
                covered_expected_evidence_ids.update(
                    matched_expected_evidence_by_observed_id.get(evidence_ref, set())
                )
            if not set(expected.evidence_ids).issubset(covered_expected_evidence_ids):
                continue
            matched = finding
            break
        if matched is None:
            missing.append(expected.id)
        else:
            used_finding_ids.add(matched.finding_id)
    covered = len(expected_findings) - len(missing)
    return round(covered / len(expected_findings), 2), missing


def _evidence_coverage(
    expected_evidence: list[BenchmarkExpectedEvidence],
    evidence_items: list[EvidenceItem],
    change_local_text_by_id: dict[str, str],
) -> tuple[float, list[str], dict[str, set[str]]]:
    if not expected_evidence:
        return 1.0, [], {}
    matched_expected_by_observed_id = _evidence_match_map(
        expected_evidence, evidence_items, change_local_text_by_id
    )
    covered_expected_ids = {
        expected_id
        for expected_ids in matched_expected_by_observed_id.values()
        for expected_id in expected_ids
    }
    missing = [
        expected.id
        for expected in expected_evidence
        if expected.id not in covered_expected_ids
    ]
    covered = len(expected_evidence) - len(missing)
    return (
        round(covered / len(expected_evidence), 2),
        missing,
        matched_expected_by_observed_id,
    )


def _unsupported_expected_evidence_coverage(
    expected_evidence: list[BenchmarkExpectedEvidence],
    manifest: SubmissionManifest,
    raw_artifact_text_by_path: dict[str, str],
) -> tuple[float, list[str], dict[str, set[str]]]:
    if not expected_evidence:
        return 1.0, [], {}
    unavailable_artifact_paths = {
        item.name for item in manifest.items if item.status != "accepted"
    }
    covered_expected_ids_by_artifact: dict[str, set[str]] = {}
    for expected in expected_evidence:
        if expected.artifact_path not in unavailable_artifact_paths:
            continue
        if not _contains_expected_text(
            haystack=raw_artifact_text_by_path.get(expected.artifact_path, ""),
            needle=expected.selector,
        ):
            continue
        covered_expected_ids_by_artifact.setdefault(expected.artifact_path, set()).add(
            expected.id
        )
    covered_expected_ids = {
        expected_id
        for expected_ids in covered_expected_ids_by_artifact.values()
        for expected_id in expected_ids
    }
    missing = [
        expected.id
        for expected in expected_evidence
        if expected.id not in covered_expected_ids
    ]
    covered = len(expected_evidence) - len(missing)
    return (
        round(covered / len(expected_evidence), 2),
        missing,
        covered_expected_ids_by_artifact,
    )


def _unsupported_observed_findings(
    manifest: SubmissionManifest,
    *,
    covered_expected_evidence_ids_by_artifact: dict[str, set[str]],
) -> list[BenchmarkObservedFinding]:
    findings: list[BenchmarkObservedFinding] = []
    unavailable_items = [item for item in manifest.items if item.status != "accepted"]
    for index, item in enumerate(unavailable_items, start=1):
        findings.append(
            BenchmarkObservedFinding(
                finding_id=f"unsupported-{index}",
                title=f"Unsupported artifact: {item.name}",
                severity="info",
                deterministic=True,
                confidence=1.0,
                evidence_refs=sorted(
                    covered_expected_evidence_ids_by_artifact.get(item.name, set())
                ),
            )
        )
    return findings


def _unsupported_expected_finding_coverage(
    expected_findings: list[BenchmarkExpectedFinding],
    *,
    observed_findings: list[BenchmarkObservedFinding],
) -> tuple[float, list[str]]:
    if not expected_findings:
        return 1.0, []
    used_finding_ids: set[str] = set()
    missing: list[str] = []
    for expected in expected_findings:
        expected_order = SEVERITY_ORDER[expected.severity]
        matched = None
        for finding in observed_findings:
            if finding.finding_id in used_finding_ids:
                continue
            if SEVERITY_ORDER[finding.severity] < expected_order:
                continue
            if not _contains_expected_text(
                haystack=finding.title,
                needle=expected.title,
            ):
                continue
            if not set(expected.evidence_ids).issubset(set(finding.evidence_refs)):
                continue
            matched = finding
            break
        if matched is None:
            missing.append(expected.id)
        else:
            used_finding_ids.add(matched.finding_id)
    covered = len(expected_findings) - len(missing)
    return round(covered / len(expected_findings), 2), missing


def _report_payload(
    *,
    assessment: RiskAssessment,
    findings: list[Finding],
    evidence_items: list[EvidenceItem],
) -> dict:
    return {
        "risk_score": assessment.score,
        "severity": assessment.severity,
        "recommendation": assessment.recommendation,
        "confidence": assessment.confidence,
        "top_risk": assessment.top_risk,
        "warnings": assessment.warnings,
        "contributors": [
            contributor.model_dump(mode="json")
            for contributor in assessment.contributors
        ],
        "context_completeness": assessment.context_completeness.model_dump(mode="json"),
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "evidence_items": [
            evidence_item.model_dump(mode="json") for evidence_item in evidence_items
        ],
    }


def _run_analysis_core(files: list[tuple[str, bytes | None]]) -> AnalysisArtifacts:
    return build_analysis_artifacts(
        files,
        include_topology_context=False,
        include_incident_context=False,
        include_narrative=False,
        allow_llm_assistance=False,
    )


def _observed_findings(findings: list[Finding]) -> list[BenchmarkObservedFinding]:
    return [
        BenchmarkObservedFinding(
            finding_id=finding.finding_id,
            title=finding.title,
            severity=finding.severity,
            deterministic=finding.deterministic,
            confidence=finding.confidence,
            evidence_refs=finding.evidence_refs,
        )
        for finding in findings
    ]


def _run_scenario(
    *,
    corpus_root: Path,
    scenario_path: str,
    scenario,
) -> BenchmarkScenarioRunResult:
    start = perf_counter()
    errors: list[str] = []
    try:
        files = _scenario_files(
            corpus_root=corpus_root,
            scenario_path=scenario_path,
            artifacts=scenario.artifacts,
        )
        raw_artifact_text_by_path = {
            name: (content or b"").decode("utf-8", errors="replace")
            for name, content in files
        }
        analysis_artifacts = _run_analysis_core(files)
        change_local_text_by_id = _change_local_text_by_id(
            analysis_artifacts.parse_batch,
            raw_artifact_text_by_path,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = round((perf_counter() - start) * 1000, 2)
        return BenchmarkScenarioRunResult(
            id=scenario.id,
            name=scenario.name,
            path=scenario_path,
            passed=False,
            status="failed",
            expected_verdict=scenario.expected_verdict,
            actual_verdict="error",
            actual_recommendation="unknown",
            actual_severity="unknown",
            actual_score=0,
            expected_finding_count=len(scenario.expected_findings),
            actual_finding_count=0,
            finding_coverage=0.0,
            missing_expected_finding_ids=[
                finding.id for finding in scenario.expected_findings
            ],
            expected_evidence_count=len(scenario.expected_evidence),
            actual_evidence_count=0,
            evidence_coverage=0.0,
            missing_expected_evidence_ids=[
                evidence.id for evidence in scenario.expected_evidence
            ],
            evidence_law_status="Needs review",
            evidence_law_detail="Scenario execution failed before Evidence Law evaluation.",
            evidence_law_violations=["Scenario execution failed."],
            latency_ms=elapsed_ms,
            unsupported=False,
            unsupported_reasons=[],
            coverage_warnings=[],
            findings=[],
            errors=[str(exc)],
        )

    evidence_items = analysis_artifacts.evidence_items
    findings = analysis_artifacts.findings
    assessment = analysis_artifacts.assessment
    manifest = analysis_artifacts.submission_manifest
    coverage_warnings = _manifest_coverage_warnings(manifest)
    unsupported = manifest.accepted_artifact_count == 0
    unsupported_reasons = _unsupported_reasons(manifest) if unsupported else []
    actual_verdict = _actual_verdict(assessment, unsupported=unsupported)
    if unsupported:
        (
            evidence_coverage,
            missing_evidence,
            covered_expected_evidence_ids_by_artifact,
        ) = _unsupported_expected_evidence_coverage(
            scenario.expected_evidence, manifest, raw_artifact_text_by_path
        )
        observed_findings = _unsupported_observed_findings(
            manifest,
            covered_expected_evidence_ids_by_artifact=covered_expected_evidence_ids_by_artifact,
        )
        finding_coverage, missing_findings = _unsupported_expected_finding_coverage(
            scenario.expected_findings,
            observed_findings=observed_findings,
        )
    else:
        observed_findings = _observed_findings(findings)
        (
            evidence_coverage,
            missing_evidence,
            matched_expected_evidence,
        ) = _evidence_coverage(
            scenario.expected_evidence,
            evidence_items,
            change_local_text_by_id,
        )
        finding_coverage, missing_findings = _finding_coverage(
            scenario.expected_findings,
            findings,
            matched_expected_evidence_by_observed_id=matched_expected_evidence,
        )
    evidence_status, evidence_detail = evidence_law_status(
        _report_payload(
            assessment=assessment,
            findings=findings,
            evidence_items=evidence_items,
        )
    )
    evidence_violations = [] if evidence_status == "Satisfied" else [evidence_detail]
    verdict_matches = _expected_verdict_matches(
        scenario.expected_verdict,
        actual=actual_verdict,
        unsupported=unsupported,
    )
    if scenario.expected_verdict == "unsupported":
        passed = (
            unsupported
            and verdict_matches
            and finding_coverage == 1.0
            and evidence_coverage == 1.0
            and not errors
        )
    else:
        passed = (
            verdict_matches
            and finding_coverage == 1.0
            and evidence_coverage == 1.0
            and not evidence_violations
            and not errors
            and not unsupported
        )
    status: ScenarioStatus = (
        "unsupported" if unsupported and passed else "passed" if passed else "failed"
    )
    elapsed_ms = round((perf_counter() - start) * 1000, 2)
    return BenchmarkScenarioRunResult(
        id=scenario.id,
        name=scenario.name,
        path=scenario_path,
        passed=passed,
        status=status,
        expected_verdict=scenario.expected_verdict,
        actual_verdict=actual_verdict,
        actual_recommendation=assessment.recommendation,
        actual_severity=assessment.severity,
        actual_score=assessment.score,
        expected_finding_count=len(scenario.expected_findings),
        actual_finding_count=len(observed_findings),
        finding_coverage=finding_coverage,
        missing_expected_finding_ids=missing_findings,
        expected_evidence_count=len(scenario.expected_evidence),
        actual_evidence_count=len(evidence_items),
        evidence_coverage=evidence_coverage,
        missing_expected_evidence_ids=missing_evidence,
        evidence_law_status=evidence_status,
        evidence_law_detail=evidence_detail,
        evidence_law_violations=evidence_violations,
        latency_ms=elapsed_ms,
        unsupported=unsupported,
        unsupported_reasons=unsupported_reasons,
        coverage_warnings=coverage_warnings,
        findings=observed_findings,
        errors=errors,
    )


def run_benchmark_corpus(corpus_root: Path | str | None = None) -> BenchmarkRunResult:
    """Execute the benchmark corpus using the same parse and scoring core."""

    corpus = load_benchmark_corpus(corpus_root)
    root = Path(corpus.root)
    scenarios = [
        _run_scenario(
            corpus_root=root,
            scenario_path=loaded.path,
            scenario=loaded.scenario,
        )
        for loaded in corpus.scenarios
    ]
    passed_count = sum(1 for scenario in scenarios if scenario.status == "passed")
    unsupported_count = sum(
        1 for scenario in scenarios if scenario.status == "unsupported"
    )
    failed_count = sum(1 for scenario in scenarios if scenario.status == "failed")
    total_latency_ms = round(sum(scenario.latency_ms for scenario in scenarios), 2)
    summary = BenchmarkRunSummary(
        corpus_id=corpus.manifest.corpus_id,
        version=corpus.manifest.version,
        scenario_count=len(scenarios),
        passed_count=passed_count,
        failed_count=failed_count,
        unsupported_count=unsupported_count,
        total_latency_ms=total_latency_ms,
        generated_at=_timestamp(),
    )
    result = BenchmarkRunResult(
        passed=all(scenario.passed for scenario in scenarios),
        summary=summary,
        scenarios=scenarios,
    )
    result.honest_failure_report = generate_honest_failure_report(result)
    return result
