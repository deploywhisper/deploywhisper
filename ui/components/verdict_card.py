"""Verdict card rendering helpers."""

from __future__ import annotations

from nicegui import ui

from ui.formatters.confidence import coerce_confidence, render_confidence_badge
from ui.formatters.context_completeness import render_context_completeness_badge
from ui.formatters.narrative import extract_llm_notice
from ui.formatters.report_header import (
    evidence_law_status,
    next_action_text,
    report_confidence_text,
    report_verdict_text,
)
from ui.formatters.recommendations import render_recommendation_label
from ui.formatters.risk_labels import render_risk_badge
from ui.components.topology_freshness_banner import render_topology_freshness_banner
from ui.components.review_accessibility import (
    decorate_review_section,
    register_review_accessibility,
)


def _primary_confidence(report: dict) -> float | None:
    return coerce_confidence(report.get("confidence"))


def _has_limited_context(context: dict) -> bool:
    if bool(context.get("insufficient_context")):
        return True
    if str(context.get("uncertainty") or "").strip():
        return True
    try:
        return float(context.get("context_score", 1.0)) < 0.7
    except (TypeError, ValueError):
        return False


def _context_warning_text(context: dict) -> str:
    uncertainty = str(context.get("uncertainty") or "").strip()
    if uncertainty:
        return uncertainty
    return (
        "Context warning: supporting topology, evidence, parser, or incident context "
        "may be incomplete."
    )


def _verdict_signal(label: str, value: str, detail: str) -> None:
    with ui.element("div").classes("dw-panel-soft dw-report-signal p-3"):
        with ui.column().classes("gap-1 min-w-0"):
            ui.label(label).classes(
                "text-[11px] font-semibold uppercase tracking-[0.08em] dw-muted"
            )
            ui.label(value).classes(
                "dw-report-signal-value text-sm font-semibold dw-text leading-5"
            )
            ui.label(detail).classes(
                "dw-report-signal-detail text-xs dw-muted leading-5"
            )


def render_verdict_card(report: dict) -> None:
    """Render the above-the-fold verdict card for the current report."""
    register_review_accessibility()
    context = report.get("context_completeness") or {}
    confidence = _primary_confidence(report)
    evidence_status, evidence_detail = evidence_law_status(report)
    llm_notice = extract_llm_notice(
        report.get("warnings", []), report.get("narrative_failure_notice")
    )

    with ui.card().classes("w-full dw-panel dw-verdict-card shadow-none") as card:
        decorate_review_section(card, section="verdict", label="Verdict card")
        with ui.row().classes("w-full items-start justify-between gap-5 flex-wrap"):
            with ui.column().classes("gap-3 min-w-0 flex-1"):
                ui.label("5-second verdict").classes("dw-eyebrow").props(
                    "role=heading aria-level=2"
                )
                with ui.row().classes("items-start gap-4 flex-wrap"):
                    with ui.column().classes("dw-verdict-score-block shrink-0 gap-1"):
                        ui.label(str(report.get("risk_score", "—"))).classes(
                            "dw-verdict-score-value"
                        )
                        ui.label("Risk score").classes("dw-verdict-score-label")
                    with ui.column().classes("min-w-0 flex-1 gap-2"):
                        with ui.row().classes("items-center gap-2 flex-wrap"):
                            render_recommendation_label(
                                report["recommendation"], size="base"
                            )
                            render_risk_badge(
                                report["severity"], f"{report['severity'].upper()} RISK"
                            )
                        ui.label(report["top_risk"]).classes("dw-verdict-top-risk")
                        render_topology_freshness_banner(context)
            with ui.column().classes("gap-2 min-w-[220px]"):
                ui.label("Key signals").classes("text-xs font-semibold dw-muted")
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    if confidence is not None:
                        render_confidence_badge(confidence)
                    else:
                        ui.label("CONFIDENCE UNAVAILABLE").classes("text-xs dw-muted")
                    render_context_completeness_badge(context)

        with ui.element("div").classes("dw-report-signal-grid w-full mt-3"):
            _verdict_signal(
                "Verdict",
                report_verdict_text(report),
                "Advisory orientation, not an approval or automatic block.",
            )
            _verdict_signal(
                "Advisory posture",
                "Advisory only",
                "Human release review remains responsible for the decision.",
            )
            _verdict_signal(
                "Evidence Law",
                evidence_status,
                evidence_detail,
            )
            _verdict_signal(
                "Confidence",
                report_confidence_text(report),
                "Overall report confidence captured with the verdict.",
            )
            _verdict_signal(
                "Next action",
                next_action_text(report, evidence_status),
                "Suggested human review step before release action.",
            )

        if llm_notice:
            ui.label("Narrative note: " + llm_notice).classes(
                "text-sm dw-warning-text leading-5 mt-2"
            )
        if _has_limited_context(context):
            ui.label(_context_warning_text(context)).classes(
                "text-sm dw-warning-text font-semibold leading-5 mt-1"
            )
