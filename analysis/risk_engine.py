"""Evidence-aware risk scoring logic."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from analysis.interaction_risk import detect_interaction_risks
from analysis.risk_scorer import (
    RiskAssessment,
    RiskContributor,
    _apply_llm_scores,
    _build_contributor,
    _build_top_risk,
    _overall_recommendation,
    _overall_score,
    _severity_max,
)
from evidence.models import EvidenceItem
from parsers.base import UnifiedChange


def _parse_source_ref(source_ref: str) -> tuple[str, str, str, str]:
    parsed = urlparse(source_ref)
    resource_fragment, _, fragment_query = parsed.fragment.partition("?")
    query = parse_qs(fragment_query, keep_blank_values=True)
    source_file = unquote(f"{parsed.netloc}{parsed.path}") or "unknown"
    resource_id = unquote(resource_fragment) or "unknown"
    action = unquote(query.get("action", ["modify"])[0]) or "modify"
    return parsed.scheme or "unknown", source_file, resource_id, action


def _evidence_to_change(item: EvidenceItem) -> UnifiedChange:
    tool, source_file, resource_id, action = _parse_source_ref(item.source_ref)
    return UnifiedChange(
        change_id=item.related_change_ids[0] if item.related_change_ids else "",
        source_file=source_file,
        tool=tool,
        resource_id=resource_id,
        action=action,
        summary=item.summary,
    )


def _evidence_weighted_contribution(
    contributor: RiskContributor,
    item: EvidenceItem,
) -> int:
    confidence_weight = 0.3 + (item.confidence * 0.4)
    trace_bonus = min(len(item.related_change_ids), 3)
    deterministic_bonus = 2 if item.deterministic else 0
    return min(
        100,
        max(
            0,
            round(contributor.contribution * confidence_weight)
            + trace_bonus
            + deterministic_bonus,
        ),
    )


def _apply_evidence_fields(
    contributor: RiskContributor,
    item: EvidenceItem,
) -> RiskContributor:
    contributor.evidence_id = item.evidence_id
    contributor.summary = item.summary
    contributor.severity = _severity_max(contributor.severity, item.severity_hint)
    contributor.contribution = _evidence_weighted_contribution(contributor, item)
    return contributor


def _top_risk_contributors(contributors: list[RiskContributor]) -> list[str]:
    seen: set[str] = set()
    evidence_ids: list[str] = []
    for contributor in contributors:
        if not contributor.evidence_id or contributor.evidence_id in seen:
            continue
        seen.add(contributor.evidence_id)
        evidence_ids.append(contributor.evidence_id)
        if len(evidence_ids) == 3:
            break
    return evidence_ids


def score_evidence(
    evidence_items: list[EvidenceItem],
    partial_context: bool = False,
    *,
    topology: dict | None = None,
    raw_files: dict[str, bytes | None] | None = None,
    completion_client=None,
) -> RiskAssessment:
    changes = [_evidence_to_change(item) for item in evidence_items]
    contributors = [
        _apply_evidence_fields(
            _build_contributor(change, topology=topology, raw_files=raw_files),
            item,
        )
        for item, change in zip(evidence_items, changes, strict=False)
    ]
    contributors, llm_warning, llm_used = _apply_llm_scores(
        contributors,
        partial_context=partial_context,
        completion_client=completion_client,
    )
    contributors = [
        _apply_evidence_fields(contributor, item)
        for contributor, item in zip(contributors, evidence_items, strict=False)
    ]
    contributors.sort(
        key=lambda contributor: (
            contributor.contribution,
            contributor.evidence_id or "",
        ),
        reverse=True,
    )
    interaction_risks = detect_interaction_risks(changes)
    warnings: list[str] = []
    if partial_context:
        warnings.append(
            "Analysis used partial context because one or more files failed to parse."
        )
    if llm_warning:
        warnings.append(llm_warning)

    score = _overall_score(contributors, interaction_risks)
    severity = contributors[0].severity if contributors else "low"
    recommendation = _overall_recommendation(contributors)
    top_risk = _build_top_risk(contributors, interaction_risks)

    return RiskAssessment(
        score=score,
        severity=severity,
        recommendation=recommendation,
        top_risk=top_risk,
        top_risk_contributors=_top_risk_contributors(contributors),
        contributors=contributors,
        interaction_risks=interaction_risks,
        partial_context=partial_context,
        warnings=warnings,
        source="heuristic+llm" if llm_used else "heuristic-only",
    )
