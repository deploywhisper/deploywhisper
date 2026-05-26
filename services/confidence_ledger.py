"""Shared confidence-ledger derivation for persisted reports."""

from __future__ import annotations

import math
from typing import Any, Literal

EvidenceLawStatus = Literal["Satisfied", "Needs review", "Reconciled", "Detail omitted"]

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
SEVERITY_THRESHOLDS = {
    "low": ("medium", 42),
    "medium": ("high", 70),
    "high": ("critical", 90),
}
LEDGER_KEYS = (
    "contributors",
    "confidence_factors",
    "why_not_lower",
    "why_not_higher",
    "uncertainty_drivers",
)


def coerce_confidence(value: object) -> float | None:
    """Return a bounded confidence value or None when the value is unusable."""
    if value is None:
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(confidence) or confidence < 0.0 or confidence > 1.0:
        return None
    return confidence


def confidence_bucket(confidence: float) -> str:
    """Map a confidence score to the report's reviewer-facing bucket."""
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.60:
        return "medium"
    return "low"


def confidence_label(value: object) -> str:
    """Format confidence for report surfaces."""
    confidence = coerce_confidence(value)
    if confidence is None:
        return "Unavailable"
    return f"{confidence_bucket(confidence).title()} ({confidence:.2f})"


def _numeric_value(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _format_number(value: object) -> str:
    number = _numeric_value(value)
    if number is None:
        return "unknown"
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _contribution_sort_key(contributor: dict[str, Any]) -> tuple[float, str]:
    contribution = _numeric_value(contributor.get("contribution"))
    return (
        contribution if contribution is not None else float("-inf"),
        str(contributor.get("resource_id") or ""),
    )


def _sorted_contributors(
    contributors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(contributors, key=_contribution_sort_key, reverse=True)


def _primary_finding(findings: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not findings:
        return None
    return max(
        findings,
        key=lambda finding: (
            SEVERITY_ORDER.get(str(finding.get("severity") or "").lower(), 0),
            coerce_confidence(finding.get("confidence")) or 0.0,
            str(finding.get("title") or ""),
        ),
    )


def _contributor_line(contributor: dict[str, Any]) -> str:
    resource_id = str(contributor.get("resource_id") or "unknown resource")
    severity = str(contributor.get("severity") or "unknown").upper()
    contribution = _format_number(contributor.get("contribution"))
    source_file = str(contributor.get("source_file") or "unknown source")
    return f"{resource_id} · {severity} · contribution {contribution} · {source_file}"


def severe_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return severe findings visible in the serialized report."""
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


def evidence_law_status(
    report: dict[str, Any],
    *,
    evidence_detail_available: bool = True,
) -> tuple[EvidenceLawStatus, str]:
    """Return the Evidence Law status for serialized report payloads."""
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
    if not evidence_detail_available:
        return (
            "Detail omitted",
            "Evidence rows are not included in this summary view; open the report to inspect deterministic evidence.",
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


def _context_score(context: dict[str, Any]) -> float | None:
    score = _numeric_value(context.get("context_score"))
    if score is None or score < 0.0 or score > 1.0:
        return None
    return score


def _finding_confidence_factor(findings: list[dict[str, Any]]) -> str | None:
    confidences = [
        confidence
        for finding in findings
        if (confidence := coerce_confidence(finding.get("confidence"))) is not None
    ]
    if not confidences:
        return None
    deterministic_count = sum(1 for finding in findings if finding.get("deterministic"))
    return (
        f"Finding confidence range is {min(confidences):.2f}-{max(confidences):.2f}; "
        f"{deterministic_count} deterministic findings are linked to the verdict."
    )


def _confidence_factors(
    report: dict[str, Any],
    *,
    evidence_detail_available: bool,
) -> list[str]:
    context = report.get("context_completeness") or {}
    findings = [item for item in report.get("findings", []) if isinstance(item, dict)]
    evidence_status, evidence_detail = evidence_law_status(
        report,
        evidence_detail_available=evidence_detail_available,
    )
    factors = [f"Report confidence is {confidence_label(report.get('confidence'))}."]
    score = _context_score(context)
    context_level = str(context.get("confidence_level") or "").strip().lower()
    if score is not None or context_level:
        if score is None:
            factors.append(f"Context confidence is {context_level or 'unknown'}.")
        else:
            factors.append(
                f"Context confidence is {context_level or 'unknown'} with score {score:.2f}."
            )
    factors.append(f"Evidence Law: {evidence_status} - {evidence_detail}")
    finding_factor = _finding_confidence_factor(findings)
    if finding_factor:
        factors.append(finding_factor)
    if report.get("narrative_available", True):
        factors.append("Narrative is available and secondary to deterministic scoring.")
    else:
        factors.append("Narrative is degraded; deterministic scoring remains primary.")
    return factors


def _why_not_lower(
    report: dict[str, Any],
    contributors: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> list[str]:
    severity = str(report.get("severity") or "unknown").lower()
    score = _numeric_value(report.get("risk_score"))
    primary_contributor = contributors[0] if contributors else None
    primary_finding = _primary_finding(findings)
    reasons: list[str] = []
    if primary_contributor is not None:
        reasons.append(
            "Severity stays elevated because "
            f"{primary_contributor.get('resource_id') or 'the top contributor'} "
            f"contributes {_format_number(primary_contributor.get('contribution'))} "
            f"risk points from {primary_contributor.get('source_file') or 'recorded evidence'}."
        )
    if primary_finding is not None:
        reasons.append(
            "The top finding remains "
            f"{str(primary_finding.get('severity') or severity).upper()} with "
            f"{confidence_label(primary_finding.get('confidence'))} finding confidence."
        )
    if score is not None:
        reasons.append(
            f"The risk score is {_format_number(score)}, which supports the {severity.upper()} verdict."
        )
    if not reasons:
        reasons.append(
            "The verdict is not lower because the persisted report still records material deployment risk."
        )
    return reasons


def _why_not_higher(
    report: dict[str, Any],
    contributors: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    *,
    evidence_detail_available: bool,
) -> list[str]:
    severity = str(report.get("severity") or "unknown").lower()
    confidence = coerce_confidence(report.get("confidence"))
    context = report.get("context_completeness") or {}
    score = _numeric_value(report.get("risk_score"))
    primary_contributor = contributors[0] if contributors else None
    primary_finding = _primary_finding(findings)
    reasons: list[str] = []
    if severity == "critical":
        reasons.append("The verdict is already at the highest severity level.")
    else:
        next_severity, threshold = SEVERITY_THRESHOLDS.get(severity, ("the next", None))
        if score is not None and threshold is not None:
            if score < threshold:
                reasons.append(
                    "The verdict is not higher because "
                    f"the risk score is {_format_number(score)}, below the {next_severity.upper()} threshold of {threshold}."
                )
            else:
                reasons.append(
                    "The verdict is not higher because "
                    f"the persisted {severity.upper()} verdict is not paired with "
                    f"{next_severity.upper()} finding and evidence context, even though "
                    f"the risk score is {_format_number(score)}."
                )
        else:
            reasons.append(
                "The verdict is not higher because persisted scoring did not provide evidence for the next severity boundary."
            )
    if primary_finding is not None:
        reasons.append(
            "The strongest finding shown is "
            f"{str(primary_finding.get('severity') or 'unknown').upper()} "
            f"({primary_finding.get('title') or 'untitled finding'}), "
            "so the boundary is tied to the recorded finding severity."
        )
    if primary_contributor is not None:
        reasons.append(
            "The largest recorded contributor is "
            f"{primary_contributor.get('resource_id') or 'unknown resource'} "
            f"at {_format_number(primary_contributor.get('contribution'))} risk points, "
            "not an unbounded escalation signal."
        )
    if confidence is not None and confidence < 0.85:
        reasons.append(
            f"Report confidence is {confidence_label(confidence)}, so the explanation avoids overstating certainty."
        )
    if str(context.get("uncertainty") or "").strip():
        reasons.append(
            "Context uncertainty is present, so the report recommends review rather than escalation by assumption."
        )
    evidence_status, _ = evidence_law_status(
        report,
        evidence_detail_available=evidence_detail_available,
    )
    if evidence_status in {"Needs review", "Reconciled"}:
        reasons.append(
            "Evidence Law does not provide support for a stronger severity claim."
        )
    return reasons


def _is_uncertainty_warning(warning: str) -> bool:
    warning_text = warning.lower()
    if "evidence law" in warning_text:
        return False
    if "manifest" in warning_text and "context" not in warning_text:
        return False
    uncertainty_keywords = (
        "uncertainty",
        "context",
        "parser",
        "topology",
        "confidence metadata",
        "narrative",
    )
    return any(keyword in warning_text for keyword in uncertainty_keywords)


def _uncertainty_drivers(report: dict[str, Any]) -> list[str]:
    context = report.get("context_completeness") or {}
    findings = [item for item in report.get("findings", []) if isinstance(item, dict)]
    drivers: list[str] = []
    uncertainty = str(context.get("uncertainty") or "").strip()
    if uncertainty:
        drivers.append(uncertainty)
    score = _context_score(context)
    if score is not None and score < 0.7:
        drivers.append(f"Context completeness score is {score:.2f}.")
    if bool(context.get("insufficient_context")):
        drivers.append("Context is marked insufficient for full certainty.")
    for finding in findings:
        note = str(finding.get("uncertainty_note") or "").strip()
        if note and note not in drivers:
            drivers.append(note)
    for warning in report.get("warnings", []):
        warning_text = str(warning or "").strip()
        if (
            warning_text
            and _is_uncertainty_warning(warning_text)
            and warning_text not in drivers
        ):
            drivers.append(warning_text)
    if not report.get("narrative_available", True):
        drivers.append("Narrative generation was degraded or unavailable.")
    return drivers or ["No additional uncertainty drivers were recorded."]


def _coerce_ledger_items(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return []


def normalize_confidence_ledger_payload(
    payload: object,
    *,
    fallback_ledger: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Normalize ledger payloads without iterating malformed strings as chars."""
    fallback = fallback_ledger or {}
    source = payload if isinstance(payload, dict) else {}
    normalized: dict[str, list[str]] = {}
    for key in LEDGER_KEYS:
        items = _coerce_ledger_items(source.get(key))
        normalized[key] = items or list(fallback.get(key, []))
    return normalized


def build_confidence_ledger(
    report: dict[str, Any],
    *,
    evidence_detail_available: bool = True,
) -> dict[str, list[str]]:
    """Build report reasoning details from persisted evidence and context."""
    contributors = _sorted_contributors(
        [item for item in report.get("contributors", []) if isinstance(item, dict)]
    )
    findings = [item for item in report.get("findings", []) if isinstance(item, dict)]
    visible_contributors = contributors[:5]
    return {
        "contributors": [_contributor_line(item) for item in visible_contributors],
        "confidence_factors": _confidence_factors(
            report,
            evidence_detail_available=evidence_detail_available,
        ),
        "why_not_lower": _why_not_lower(report, visible_contributors, findings),
        "why_not_higher": _why_not_higher(
            report,
            visible_contributors,
            findings,
            evidence_detail_available=evidence_detail_available,
        ),
        "uncertainty_drivers": _uncertainty_drivers(report),
    }
