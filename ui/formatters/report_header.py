"""Verdict-first report header signal helpers."""

from __future__ import annotations

from typing import Any

from ui.formatters.confidence import coerce_confidence, confidence_bucket


def report_verdict_text(report: dict[str, Any]) -> str:
    recommendation = str(report.get("recommendation") or "review").upper()
    severity = str(report.get("severity") or "unknown").upper()
    return f"{recommendation} · {severity} RISK"


def report_confidence_text(report: dict[str, Any]) -> str:
    confidence = coerce_confidence(report.get("confidence"))
    if confidence is None:
        return "Unavailable"
    return f"{confidence_bucket(confidence).title()} ({confidence:.2f})"


def severe_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        finding
        for finding in report.get("findings", [])
        if isinstance(finding, dict)
        and str(finding.get("severity") or "").lower() in {"high", "critical"}
    ]


def _is_severe_report(report: dict[str, Any]) -> bool:
    return str(report.get("severity") or "").lower() in {"high", "critical"}


def _is_deterministic_evidence(evidence: dict[str, Any]) -> bool:
    determinism_level = str(
        evidence.get("determinism_level") or "deterministic"
    ).lower()
    return (
        evidence.get("deterministic") is True and determinism_level == "deterministic"
    )


def _has_linked_deterministic_evidence(
    finding: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
) -> bool:
    evidence_refs = [
        str(evidence_ref)
        for evidence_ref in finding.get("evidence_refs", [])
        if evidence_ref
    ]
    if not evidence_refs:
        return False
    return any(
        _is_deterministic_evidence(evidence_by_id[evidence_ref])
        for evidence_ref in evidence_refs
        if evidence_ref in evidence_by_id
    )


def evidence_law_status(report: dict[str, Any]) -> tuple[str, str]:
    warnings = [
        str(warning)
        for warning in report.get("warnings", [])
        if "Evidence Law" in str(warning)
    ]
    if warnings:
        return (
            "Reconciled",
            "Evidence Law adjusted unsupported or inconsistent severe claims.",
        )
    severe = severe_findings(report)
    if not severe:
        if _is_severe_report(report):
            return (
                "Needs review",
                "The report is severe, but no high or critical finding is visible for Evidence Law verification.",
            )
        return (
            "Satisfied",
            "No high or critical finding requires deterministic evidence.",
        )
    evidence_by_id = {
        str(evidence.get("evidence_id")): evidence
        for evidence in report.get("evidence_items", [])
        if isinstance(evidence, dict) and evidence.get("evidence_id")
    }
    if all(
        _has_linked_deterministic_evidence(finding, evidence_by_id)
        for finding in severe
    ):
        return (
            "Satisfied",
            "High and critical findings are backed by deterministic evidence.",
        )
    return (
        "Needs review",
        "A severe finding lacks linked deterministic evidence support.",
    )


def next_action_text(report: dict[str, Any], evidence_status: str) -> str:
    if evidence_status == "Needs review":
        return "Review linked evidence before treating severe claims as release risk."
    recommendation = str(report.get("recommendation") or "").lower()
    if recommendation == "no-go":
        return "Review linked evidence and rollback readiness before release."
    if recommendation == "caution":
        return "Review linked evidence and resolve open context before release."
    return "Continue normal release review; this advisory is not an approval."
