"""Evidence-aware risk scoring logic."""

from __future__ import annotations

from typing import Any
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
    SEVERITY_ORDER,
    SEVERITY_SCORE,
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


def _evidence_to_change(
    item: EvidenceItem,
    *,
    change_metadata_by_id: dict[str, dict[str, Any]] | None = None,
) -> UnifiedChange:
    tool, source_file, resource_id, action = _parse_source_ref(item.source_ref)
    change_id = item.related_change_ids[0] if item.related_change_ids else ""
    metadata = (
        dict(change_metadata_by_id.get(change_id, {})) if change_metadata_by_id else {}
    )
    return UnifiedChange(
        change_id=change_id,
        source_file=source_file,
        tool=tool,
        resource_id=resource_id,
        action=action,
        summary=item.summary,
        metadata=metadata,
    )


def _evidence_weighted_contribution(
    contributor: RiskContributor,
    item: EvidenceItem,
    *,
    baseline_contribution: int,
) -> int:
    confidence_weight = 0.3 + (item.confidence * 0.4)
    severity_alignment_weight = 0.25 + (item.confidence * 0.15)
    trace_bonus = min(len(item.related_change_ids), 3)
    deterministic_bonus = 2 if item.deterministic else 0
    weighted_baseline = round(baseline_contribution * confidence_weight)
    severity_floor = round(
        SEVERITY_SCORE[contributor.severity] * severity_alignment_weight
    )
    return min(
        100,
        max(
            0,
            max(weighted_baseline, severity_floor) + trace_bonus + deterministic_bonus,
        ),
    )


def _apply_evidence_fields(
    contributor: RiskContributor,
    item: EvidenceItem,
) -> RiskContributor:
    baseline_contribution = contributor.contribution
    contributor.evidence_id = item.evidence_id
    contributor.summary = item.summary
    contributor.severity = _severity_max(contributor.severity, item.severity_hint)
    contributor.contribution = _evidence_weighted_contribution(
        contributor,
        item,
        baseline_contribution=baseline_contribution,
    )
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


def _contributor_sort_key(contributor: RiskContributor) -> tuple[int, int, str]:
    return (
        SEVERITY_ORDER[contributor.severity],
        contributor.contribution,
        contributor.evidence_id or "",
    )


def score_evidence(
    evidence_items: list[EvidenceItem],
    partial_context: bool = False,
    *,
    topology: dict | None = None,
    raw_files: dict[str, bytes | None] | None = None,
    change_metadata_by_id: dict[str, dict[str, Any]] | None = None,
    supplemental_changes: list[UnifiedChange] | None = None,
    completion_client=None,
    allow_llm_assistance: bool = True,
) -> RiskAssessment:
    changes = [
        _evidence_to_change(item, change_metadata_by_id=change_metadata_by_id)
        for item in evidence_items
    ]
    changes.extend(supplemental_changes or [])
    contributors = [
        _apply_evidence_fields(
            _build_contributor(change, topology=topology, raw_files=raw_files),
            item,
        )
        for item, change in zip(evidence_items, changes, strict=False)
    ]
    contributors.extend(
        _build_contributor(change, topology=topology, raw_files=raw_files)
        for change in changes[len(evidence_items) :]
    )
    if allow_llm_assistance:
        contributors, llm_warning, llm_used = _apply_llm_scores(
            contributors,
            partial_context=partial_context,
            completion_client=completion_client,
        )
    else:
        llm_warning = None
        llm_used = False
    evidence_contributor_count = len(evidence_items)
    contributors = [
        _apply_evidence_fields(contributor, item)
        for contributor, item in zip(
            contributors[:evidence_contributor_count],
            evidence_items,
            strict=False,
        )
    ] + contributors[evidence_contributor_count:]
    contributors.sort(key=_contributor_sort_key, reverse=True)
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
