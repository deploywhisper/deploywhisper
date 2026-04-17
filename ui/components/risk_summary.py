"""Risk summary helpers."""

from __future__ import annotations

from analysis.risk_scorer import RiskAssessment
from llm.narrator import NarrativeResult
from nicegui import ui
from ui.formatters.recommendations import render_recommendation_label
from ui.formatters.risk_labels import render_risk_badge


def build_risk_summary_lines(assessment: RiskAssessment) -> list[str]:
    """Return compact summary lines suitable for UI, API, or CLI reuse."""
    lines = [
        f"Risk score: {assessment.score}",
        f"Severity: {assessment.severity}",
        f"Recommendation: {assessment.recommendation}",
        f"Top risk: {assessment.top_risk}",
    ]
    lines.extend(assessment.warnings)
    return lines


def render_risk_brief(assessment: RiskAssessment, narrative: NarrativeResult) -> None:
    """Render a verdict-first risk briefing block."""
    with ui.card().classes("w-full dw-panel shadow-none"):
        with ui.row().classes("items-center gap-3"):
            render_risk_badge(assessment.severity, f"{assessment.severity.upper()} · {assessment.score}")
            render_recommendation_label(assessment.recommendation)
        ui.label(narrative.opening_sentence).classes("text-xl font-medium dw-text")
        ui.label(narrative.explanation).classes("text-sm dw-muted")
        for guidance_item in narrative.guidance:
            ui.label(f"• {guidance_item}").classes("text-sm dw-muted")
        for warning in narrative.warnings:
            ui.label(warning).classes("text-xs dw-warning-text")
