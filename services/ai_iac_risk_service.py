"""AI-assisted IaC provenance qualification and deterministic risk labels."""

from __future__ import annotations

import re
from typing import Any

from analysis.risk_scorer import RiskAssessment, RiskContributor
from evidence.models import EvidenceItem, Finding

_AI_CONTENT_MARKER = re.compile(
    r"""(?im)^\s*(?:\#|//|/\*+|\*|<!--)?\s*
    (?:
        ai[- ](?:generated|assisted)
        |
        generated\s+(?:by|with)\s+
        (?:chatgpt|claude|gemini|copilot|an?\s+ai|ai)
    )
    \b""",
    re.VERBOSE,
)
_AUTHORSHIP_VALUES = {"human-authored", "ai-assisted", "unknown"}
_AUTHORSHIP_NOTE = (
    "Available signals suggest AI assistance; this does not establish authorship."
)
_AI_RISK_TITLE_PREFIX = "AI-assisted IaC risk:"
_SECURITY_FLAG_PATTERNS = {
    "Overly permissive IAM policy detected (AmazonS3FullAccess).": (
        "broad IAM permissions",
    ),
    "Public endpoint access enabled.": ("public ingress",),
    "KMS encryption appears disabled.": ("unsafe defaults",),
    "Operational logging appears disabled.": ("unsafe defaults",),
    "Open security group rule detected (protocol -1 / 0.0.0.0/0).": ("public ingress",),
}


def _content_marker_signals(
    raw_files: dict[str, bytes | None],
) -> list[str]:
    signals: list[str] = []
    for file_name, raw_content in raw_files.items():
        if not raw_content:
            continue
        content = raw_content.decode("utf-8", errors="ignore")
        if _AI_CONTENT_MARKER.search(content):
            signals.append(f"content-marker:{file_name}")
    return signals


def assess_iac_provenance(
    raw_files: dict[str, bytes | None],
    *,
    audit_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return qualified authorship metadata without claiming certainty."""
    context = audit_context or {}
    declared = str(context.get("iac_authorship") or "").strip().lower()
    declared = declared if declared in _AUTHORSHIP_VALUES else ""
    signals = [f"declared:{declared}"] if declared else []
    suggestion_signals = _content_marker_signals(raw_files)

    signals.extend(suggestion_signals)
    signals = list(dict.fromkeys(signals))

    if declared == "human-authored" and suggestion_signals:
        return {
            "authorship": "unknown",
            "authorship_certainty": "conflicting",
            "authorship_signals": signals,
            "authorship_note": (
                "Declared human authorship conflicts with AI-assistance signals; "
                "authorship remains unknown."
            ),
        }
    if declared == "unknown" and suggestion_signals:
        return {
            "authorship": "ai-assisted",
            "authorship_certainty": "suggested",
            "authorship_signals": signals,
            "authorship_note": _AUTHORSHIP_NOTE,
        }
    if declared:
        note = (
            "Authorship is preserved from caller-declared provenance and was not "
            "independently verified."
        )
        return {
            "authorship": declared,
            "authorship_certainty": "declared",
            "authorship_signals": signals,
            "authorship_note": note,
        }
    if suggestion_signals:
        return {
            "authorship": "ai-assisted",
            "authorship_certainty": "suggested",
            "authorship_signals": signals,
            "authorship_note": _AUTHORSHIP_NOTE,
        }
    return {
        "authorship": "unknown",
        "authorship_certainty": "unknown",
        "authorship_signals": [],
        "authorship_note": (
            "No reliable authorship provenance was supplied or detected."
        ),
    }


def _risk_patterns(contributor: RiskContributor) -> list[str]:
    patterns = [
        pattern
        for security_flag in contributor.security_flags
        for pattern in _SECURITY_FLAG_PATTERNS.get(security_flag, ())
    ]
    if contributor.environment == "unknown":
        patterns.append("missing environment scoping")
    return list(dict.fromkeys(patterns))


def _linked_deterministic_evidence_items(
    finding: Finding,
    evidence_by_id: dict[str, EvidenceItem],
) -> list[EvidenceItem]:
    return [
        evidence_by_id[evidence_ref]
        for evidence_ref in finding.evidence_refs
        if evidence_ref in evidence_by_id and evidence_by_id[evidence_ref].deterministic
    ]


def _evidence_matches_contributor(
    evidence_item: EvidenceItem,
    contributor: RiskContributor,
) -> bool:
    return (
        evidence_item.artifact == contributor.source_file
        and evidence_item.resource == contributor.resource_id
        and evidence_item.operation
        in {contributor.action, contributor.normalized_action}
    )


def _finding_contributor(
    finding: Finding,
    assessment: RiskAssessment,
    linked_evidence_items: list[EvidenceItem],
) -> RiskContributor | None:
    evidence_refs = set(finding.evidence_refs)
    candidates = [
        contributor
        for contributor in assessment.contributors
        if (contributor.evidence_id and contributor.evidence_id in evidence_refs)
        or any(
            _evidence_matches_contributor(evidence_item, contributor)
            for evidence_item in linked_evidence_items
        )
    ]
    return candidates[0] if len(candidates) == 1 else None


def _provenance_suggests_ai_assistance(
    provenance: dict[str, Any],
) -> bool:
    if provenance.get("authorship") == "ai-assisted":
        return True
    return any(
        str(signal).startswith("content-marker:")
        for signal in provenance.get("authorship_signals") or []
    )


def label_ai_iac_risk_findings(
    findings: list[Finding],
    *,
    assessment: RiskAssessment,
    evidence_items: list[EvidenceItem],
    provenance_by_artifact: dict[str, dict[str, Any]],
) -> list[Finding]:
    """Label evidence-backed risk patterns when provenance suggests AI assistance."""
    evidence_by_id = {
        evidence_item.evidence_id: evidence_item for evidence_item in evidence_items
    }
    labeled: list[Finding] = []
    for finding in findings:
        if (
            finding.title.startswith(_AI_RISK_TITLE_PREFIX)
            or not finding.deterministic
            or finding.evidence_classification != "deterministic"
        ):
            labeled.append(finding)
            continue
        linked_evidence_items = _linked_deterministic_evidence_items(
            finding,
            evidence_by_id,
        )
        contributor = _finding_contributor(
            finding,
            assessment,
            linked_evidence_items,
        )
        patterns = _risk_patterns(contributor) if contributor is not None else []
        provenance = next(
            (
                provenance_by_artifact.get(evidence_item.artifact, {})
                for evidence_item in linked_evidence_items
                if _provenance_suggests_ai_assistance(
                    provenance_by_artifact.get(evidence_item.artifact, {})
                )
            ),
            None,
        )
        if not patterns or provenance is None:
            labeled.append(finding)
            continue

        note = str(provenance.get("authorship_note") or _AUTHORSHIP_NOTE)
        pattern_summary = ", ".join(patterns)
        uncertainty_note = " ".join(
            value for value in (finding.uncertainty_note, note) if value
        )
        guidance = list(finding.guidance)
        ai_review_guidance = "Treat AI-assisted IaC as untrusted input"
        if ai_review_guidance not in guidance:
            guidance.append(ai_review_guidance)
        labeled.append(
            finding.model_copy(
                update={
                    "title": f"{_AI_RISK_TITLE_PREFIX} {finding.title}",
                    "description": (
                        f"{finding.description} AI-assisted IaC risk patterns: "
                        f"{pattern_summary}. {note}"
                    ),
                    "uncertainty_note": uncertainty_note,
                    "guidance": guidance,
                }
            )
        )
    return labeled
