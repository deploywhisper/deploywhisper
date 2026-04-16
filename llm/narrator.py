"""Narrative orchestration."""

from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel, Field

from analysis.risk_scorer import RiskAssessment
from llm.prompts import build_system_prompt, build_user_payload
from llm.providers import NarrativeProviderError, generate_completion_with_settings
from llm.skill_context import build_skill_context
from services.settings_service import resolve_provider_runtime

logger = logging.getLogger(__name__)


class NarrativeResult(BaseModel):
    opening_sentence: str = Field(..., description="First-scan deploy briefing sentence")
    explanation: str = Field(..., description="Extended plain-English explanation")
    guidance: list[str] = Field(default_factory=list, description="Actionable guidance")
    degraded: bool = Field(..., description="Whether fallback mode was used")
    warnings: list[str] = Field(default_factory=list, description="Narrative warnings")


def _fallback_narrative(assessment: RiskAssessment, error_message: str | None = None) -> NarrativeResult:
    warnings = list(assessment.warnings)
    if error_message:
        warnings.append(f"Narrative provider unavailable: {error_message}")
    explanation = (
        f"The deployment is currently rated {assessment.severity} with a recommendation of "
        f"{assessment.recommendation}. {assessment.top_risk}"
    )
    guidance = [
        "Review the top risk and contributor list before deployment.",
        "Inspect rollback guidance before shipping higher-risk changes.",
    ]
    if assessment.partial_context:
        guidance.append("Investigate parser failures because the analysis used partial context.")
    return NarrativeResult(
        opening_sentence=f"{assessment.recommendation.upper()}: {assessment.top_risk}",
        explanation=explanation,
        guidance=guidance,
        degraded=True,
        warnings=warnings,
    )


def generate_narrative(
    assessment: RiskAssessment,
    completion_client=None,
) -> NarrativeResult:
    if not assessment.contributors:
        return _fallback_narrative(assessment)

    skill_context = build_skill_context(assessment)
    messages = [
        {"role": "system", "content": build_system_prompt(skill_context)},
        {"role": "user", "content": build_user_payload(assessment)},
    ]

    try:
        runtime = resolve_provider_runtime()
        prompt_messages = messages
        logger.info("llm_narrative_prompt=%s", json.dumps(prompt_messages))
        raw_content = generate_completion_with_settings(
            prompt_messages,
            provider=runtime["provider"],
            model=runtime["model"],
            api_base=runtime["api_base"],
            api_key=runtime["api_key"],
            local_mode=runtime["local_mode"],
            completion_client=completion_client,
        )
        payload = json.loads(raw_content)
        known_scopes = {contributor.downstream_scope for contributor in assessment.contributors if contributor.downstream_scope is not None}

        def sanitize_scope_claims(text: str) -> str:
            def replace_numeric_scope(match: re.Match[str]) -> str:
                number = int(match.group("count"))
                if number in known_scopes:
                    return match.group(0)
                return "unknown downstream impact — standalone manifest without cluster context"

            sanitized = re.sub(
                r"(?i)(affects?|impacts?)\s+(?P<count>\d+)\s+downstream\s+(services?|workloads?|resources?)",
                replace_numeric_scope,
                text,
            )
            sanitized = re.sub(
                r"(?i)(?P<count>\d+)\s+downstream\s+(services?|workloads?|resources?)",
                replace_numeric_scope,
                sanitized,
            )
            if not known_scopes:
                sanitized = re.sub(
                    r"(?i)\b(high|wide|large)\s+blast\s+radius\b",
                    "unknown downstream impact",
                    sanitized,
                )
            return sanitized

        return NarrativeResult(
            opening_sentence=sanitize_scope_claims(payload["opening_sentence"]),
            explanation=sanitize_scope_claims(payload["explanation"]),
            guidance=[sanitize_scope_claims(item) for item in list(payload.get("guidance", []))],
            degraded=False,
            warnings=list(assessment.warnings),
        )
    except (Exception, KeyError, json.JSONDecodeError, TypeError) as exc:
        return _fallback_narrative(assessment, str(exc))
