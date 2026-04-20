"""Map evidence-backed scoring output into reviewer-facing findings."""

from __future__ import annotations

import hashlib

from analysis.interaction_risk import InteractionRisk
from analysis.risk_scorer import RiskAssessment
from evidence.models import EvidenceItem, Finding

INFERRED_CONFIDENCE_FLOOR = 0.55


def resolve_finding_confidence(
    *,
    deterministic: bool,
    source_confidence: float | None = None,
    heuristic_floor: float = INFERRED_CONFIDENCE_FLOOR,
) -> float:
    """Return the displayed confidence for one finding."""
    if deterministic:
        return 1.0
    if source_confidence is not None:
        return round(source_confidence, 2)
    return heuristic_floor


def _finding_id(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"finding-{digest}"


def _title_from_resource(resource_id: str, severity: str) -> str:
    return f"{severity.upper()}: {resource_id}"


def _uncertainty_note(
    *,
    deterministic: bool,
    source_confidence: float | None = None,
) -> str | None:
    if deterministic:
        return None
    if source_confidence is not None:
        return f"Confidence is inferred from model-assisted output ({source_confidence:.2f})."
    return f"Confidence uses the heuristic floor ({INFERRED_CONFIDENCE_FLOOR:.2f}) because this finding is inferred."


def _matching_evidence_refs(
    interaction_risk: InteractionRisk,
    evidence_items: list[EvidenceItem],
) -> list[str]:
    refs: list[str] = []
    for item in evidence_items:
        if any(
            resource in item.source_ref
            for resource in interaction_risk.contributing_resources
        ) or any(
            file_name in item.source_ref
            for file_name in interaction_risk.contributing_files
        ):
            refs.append(item.evidence_id)
    return refs


def build_findings(
    *,
    assessment: RiskAssessment,
    evidence_items: list[EvidenceItem],
    interaction_confidence_overrides: dict[str, float] | None = None,
) -> list[Finding]:
    """Build reviewer-facing findings from scored contributors and interactions."""
    evidence_by_id = {item.evidence_id: item for item in evidence_items}
    findings: list[Finding] = []

    for contributor in assessment.contributors:
        evidence = (
            evidence_by_id.get(contributor.evidence_id)
            if contributor.evidence_id is not None
            else None
        )
        deterministic = evidence.deterministic if evidence is not None else True
        source_confidence = evidence.confidence if evidence is not None else None
        findings.append(
            Finding(
                finding_id=_finding_id(
                    "|".join(
                        (
                            contributor.evidence_id or contributor.resource_id,
                            contributor.action,
                            contributor.severity,
                        )
                    )
                ),
                analysis_id=0,
                title=_title_from_resource(
                    contributor.resource_id, contributor.severity
                ),
                description=contributor.reasoning or contributor.summary,
                severity=contributor.severity,
                category=contributor.resource_category,
                deterministic=deterministic,
                confidence=resolve_finding_confidence(
                    deterministic=deterministic,
                    source_confidence=source_confidence,
                ),
                uncertainty_note=_uncertainty_note(
                    deterministic=deterministic,
                    source_confidence=source_confidence,
                ),
                evidence_refs=(
                    [contributor.evidence_id] if contributor.evidence_id else []
                ),
                skill_id=None,
            )
        )

    overrides = interaction_confidence_overrides or {}
    for interaction in assessment.interaction_risks:
        llm_confidence = overrides.get(interaction.key)
        findings.append(
            Finding(
                finding_id=_finding_id(
                    "|".join(
                        (
                            interaction.key,
                            *interaction.contributing_resources,
                            *interaction.contributing_files,
                        )
                    )
                ),
                analysis_id=0,
                title="Interaction risk: " + interaction.key.replace("-", " "),
                description=interaction.summary,
                severity=assessment.severity,
                category="cross-tool interaction",
                deterministic=False,
                confidence=resolve_finding_confidence(
                    deterministic=False,
                    source_confidence=llm_confidence,
                ),
                uncertainty_note=_uncertainty_note(
                    deterministic=False,
                    source_confidence=llm_confidence,
                ),
                evidence_refs=_matching_evidence_refs(interaction, evidence_items),
                skill_id=None,
            )
        )

    return findings
