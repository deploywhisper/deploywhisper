"""Prompt builders for narrative generation."""

from __future__ import annotations

import json

from analysis.risk_scorer import RiskAssessment


def build_system_prompt(skill_context: str) -> str:
    sections = [
        "You are DeployWhisper, a calm senior SRE reviewer.",
        "Summarize deployment risk in plain English for engineers reviewing whether to ship.",
        "The severity and GO/NO-GO verdict are already decided by the structured assessment input; do not override them.",
        "Use the contributor severity matrix, security flags, downstream scope, and environment hints when explaining why the verdict was reached.",
        "Never invent downstream service counts, blast-radius numbers, or dependency scope not present in the assessment input.",
        "If downstream impact is unknown, explicitly say 'unknown downstream impact — standalone manifest without cluster context'.",
        "Be concrete: mention exact tools, resource IDs, and the main operational consequence when possible.",
        "Do not use vague filler such as 'specific resource', 'centered around', or 'primarily due to' when concrete details are available.",
        "The opening sentence must read like a sharp approval-thread headline grounded in the highest-impact change.",
        "The explanation must connect the change to operational impact, not just restate that a modification happened.",
        "Guidance should tell the reviewer what to verify or discuss next.",
        "Never invent raw file content or hidden context.",
        "Return valid JSON with keys: opening_sentence, explanation, guidance.",
    ]
    if skill_context:
        sections.append("Relevant AI Skills:\n" + skill_context)
    return "\n\n".join(sections)


def build_user_payload(assessment: RiskAssessment) -> str:
    payload = {
        "score": assessment.score,
        "severity": assessment.severity,
        "recommendation": assessment.recommendation,
        "top_risk": assessment.top_risk,
        "top_risk_contributors": assessment.top_risk_contributors,
        "partial_context": assessment.partial_context,
        "warnings": assessment.warnings,
        "interaction_risks": [
            {
                "key": interaction.key,
                "summary": interaction.summary,
                "contributing_files": interaction.contributing_files,
                "contributing_resources": interaction.contributing_resources,
                "contribution_bonus": interaction.contribution_bonus,
            }
            for interaction in assessment.interaction_risks
        ],
        "contributors": [
            {
                "evidence_id": contributor.evidence_id,
                "source_file": contributor.source_file,
                "tool": contributor.tool,
                "resource_id": contributor.resource_id,
                "action": contributor.action,
                "contribution": contributor.contribution,
                "summary": contributor.summary,
                "normalized_action": contributor.normalized_action,
                "resource_category": contributor.resource_category,
                "blast_radius": contributor.blast_radius,
                "downstream_scope": contributor.downstream_scope,
                "security_flags": contributor.security_flags,
                "environment": contributor.environment,
                "severity": contributor.severity,
                "reasoning": contributor.reasoning,
            }
            for contributor in assessment.contributors
        ],
    }
    return json.dumps(payload, indent=2)
