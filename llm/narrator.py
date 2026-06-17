"""Narrative orchestration."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

from config import settings
from analysis.risk_scorer import RiskAssessment
from evidence.models import Finding
from llm.prompts import build_system_prompt, build_user_payload
from llm.providers import generate_completion_with_settings
from llm.skill_context import build_skill_context, resolve_skills
from services.settings_service import resolve_provider_runtime

_NON_VISIBLE_TEXT_CATEGORIES = {"Cc", "Cf", "Mc", "Me", "Mn"}


class NarrativeResult(BaseModel):
    available: bool = Field(
        default=True, description="Whether narrative text is available"
    )
    opening_sentence: str = Field(
        default="", description="First-scan deploy briefing sentence"
    )
    explanation: str = Field(
        default="", description="Extended plain-English explanation"
    )
    guidance: list[str] = Field(default_factory=list, description="Actionable guidance")
    degraded: bool = Field(..., description="Whether fallback mode was used")
    warnings: list[str] = Field(default_factory=list, description="Narrative warnings")
    failure_notice: str | None = Field(
        default=None,
        description="Visible explanation when narrative generation was unavailable",
    )
    source: Literal["llm", "fallback"] = Field(
        default="fallback",
        description="Whether the narrative came from the LLM or local fallback logic",
    )
    provider: str | None = Field(
        default=None,
        description="Provider used for narrative generation when applicable",
    )
    model: str | None = Field(
        default=None, description="Model used for narrative generation when applicable"
    )
    local_mode: bool | None = Field(
        default=None, description="Whether local-only mode was active for the narrative"
    )
    skills_applied: list[str] = Field(
        default_factory=list,
        description="Resolved skill names applied to the narrative prompt",
    )


def _has_visible_text(value: str) -> bool:
    return any(
        not character.isspace()
        and unicodedata.category(character) not in _NON_VISIBLE_TEXT_CATEGORIES
        for character in value
    )


def _normalize_guidance_items(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if _has_visible_text(value) else []
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(_normalize_guidance_items(item))
        return items
    if isinstance(value, dict):
        items = []
        for item in value.values():
            items.extend(_normalize_guidance_items(item))
        return items

    text = str(value)
    return [text] if _has_visible_text(text) else []


def _fallback_narrative(
    assessment: RiskAssessment,
    findings: list[Finding],
    error_message: str | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    local_mode: bool | None = None,
    skills_applied: list[str] | None = None,
    failure_prefix: str = "Narrative provider unavailable",
) -> NarrativeResult:
    warnings = list(assessment.warnings)
    failure_notice = None
    if error_message:
        failure_notice = f"{failure_prefix}: {error_message}"
        warnings.append(failure_notice)
    return NarrativeResult(
        available=False,
        opening_sentence="",
        explanation="",
        guidance=[],
        degraded=True,
        warnings=warnings,
        failure_notice=failure_notice,
        source="fallback",
        provider=provider,
        model=model,
        local_mode=local_mode,
        skills_applied=list(skills_applied or []),
    )


def _resolve_skill_names_safely(
    assessment: RiskAssessment,
    *,
    raw_files: dict[str, bytes | None] | None = None,
) -> list[str]:
    try:
        return [skill.name for skill in resolve_skills(assessment, raw_files=raw_files)]
    except Exception:  # noqa: BLE001
        return []


def generate_narrative(
    assessment: RiskAssessment,
    findings: list[Finding],
    completion_client=None,
    raw_files: dict[str, bytes | None] | None = None,
) -> NarrativeResult:
    runtime = resolve_provider_runtime()
    if not settings.narrator_enabled:
        applied_skills = _resolve_skill_names_safely(assessment, raw_files=raw_files)
        return _fallback_narrative(
            assessment,
            findings,
            "Narrator disabled by configuration.",
            provider=runtime["provider"],
            model=runtime["model"],
            local_mode=runtime["local_mode"],
            skills_applied=applied_skills,
            failure_prefix="Narrative unavailable",
        )
    if not assessment.contributors:
        applied_skills = _resolve_skill_names_safely(assessment, raw_files=raw_files)
        return _fallback_narrative(
            assessment,
            findings,
            provider=runtime["provider"],
            model=runtime["model"],
            local_mode=runtime["local_mode"],
            skills_applied=applied_skills,
        )

    applied_skills: list[str] = []
    try:
        applied_skills = [
            skill.name for skill in resolve_skills(assessment, raw_files=raw_files)
        ]
        skill_context = build_skill_context(assessment, raw_files=raw_files)
        messages = [
            {"role": "system", "content": build_system_prompt(skill_context)},
            {"role": "user", "content": build_user_payload(assessment, findings)},
        ]
    except Exception as exc:  # noqa: BLE001
        return _fallback_narrative(
            assessment,
            findings,
            str(exc),
            provider=runtime["provider"],
            model=runtime["model"],
            local_mode=runtime["local_mode"],
            skills_applied=applied_skills,
            failure_prefix="Narrative setup unavailable",
        )

    try:
        raw_content = generate_completion_with_settings(
            messages,
            provider=runtime["provider"],
            model=runtime["model"],
            api_base=runtime["api_base"],
            api_key=runtime["api_key"],
            local_mode=runtime["local_mode"],
            request_timeout_seconds=runtime.get("request_timeout_seconds", 30.0),
            completion_client=completion_client,
        )
        payload = json.loads(raw_content)
        known_scopes = {
            contributor.downstream_scope
            for contributor in assessment.contributors
            if contributor.downstream_scope is not None
        }

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

        opening_sentence = sanitize_scope_claims(payload["opening_sentence"])
        explanation = sanitize_scope_claims(payload["explanation"])
        if not (_has_visible_text(opening_sentence) or _has_visible_text(explanation)):
            raise ValueError("Narrative provider returned empty output.")
        guidance_payload = _normalize_guidance_items(payload.get("guidance", []))

        return NarrativeResult(
            available=True,
            opening_sentence=opening_sentence,
            explanation=explanation,
            guidance=[sanitize_scope_claims(item) for item in guidance_payload],
            degraded=False,
            warnings=list(assessment.warnings),
            failure_notice=None,
            source="llm",
            provider=runtime["provider"],
            model=runtime["model"],
            local_mode=runtime["local_mode"],
            skills_applied=applied_skills,
        )
    except (Exception, KeyError, json.JSONDecodeError, TypeError) as exc:
        return _fallback_narrative(
            assessment,
            findings,
            str(exc),
            provider=runtime["provider"],
            model=runtime["model"],
            local_mode=runtime["local_mode"],
            skills_applied=applied_skills,
        )
