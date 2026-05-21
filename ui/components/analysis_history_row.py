"""Scannable history row rendering."""

from __future__ import annotations

from nicegui import ui

from ui.formatters.confidence import coerce_confidence, render_confidence_badge
from ui.formatters.datetime import format_history_timestamp
from ui.formatters.recommendations import render_recommendation_label
from ui.formatters.risk_labels import render_risk_badge
from ui.formatters.topology_freshness import (
    TOPOLOGY_MANAGEMENT_LINK,
    topology_freshness_age_text,
    topology_freshness_badge_text,
    topology_freshness_level,
)


def _freshness_badge_style(level: str) -> str:
    palette = {
        "unknown": ("rgba(69, 81, 99, 0.1)", "#455163", "rgba(69, 81, 99, 0.25)"),
        "current": ("rgba(83, 194, 107, 0.12)", "#53c26b", "rgba(83, 194, 107, 0.35)"),
        "stale": ("rgba(216, 164, 50, 0.12)", "#d8a432", "rgba(216, 164, 50, 0.35)"),
        "critical": ("rgba(207, 63, 63, 0.12)", "#cf3f3f", "rgba(207, 63, 63, 0.35)"),
    }
    background, color, border = palette[level]
    return (
        f"background:{background};"
        f"color:{color};"
        f"border:1px solid {border};"
        "border-radius:999px;"
        "padding:2px 8px;"
        "font-size:0.68rem;"
        "line-height:1.1;"
        "font-weight:700;"
        "letter-spacing:0.04em;"
        "text-transform:uppercase;"
    )


def _report_confidence(report: dict) -> float | None:
    return coerce_confidence(report.get("confidence"))


def _scope_label(report: dict) -> str:
    project = report.get("project") or {}
    workspace = report.get("workspace") or {}
    project_label = str(
        project.get("display_name") or project.get("project_key") or "Unassigned"
    )
    if not workspace:
        return f"Project: {project_label} · Workspace: All"
    workspace_label = str(
        workspace.get("display_name") or workspace.get("workspace_key") or "Workspace"
    )
    return f"Project: {project_label} · Workspace: {workspace_label}"


def render_analysis_history_row(
    report: dict, on_open, *, on_toggle=None, on_delete=None, selected: bool = False
):
    """Render a compact clickable history row."""
    interface = report.get("audit", {}).get("source_interface") or "unknown"
    previous_scan_diff = report.get("previous_scan_diff") or {}
    card_classes = "w-full dw-panel dw-history-card shadow-none cursor-pointer p-4"
    if selected:
        card_classes += " dw-history-card-selected"
    with ui.card().classes(card_classes) as card:
        card.on("click", lambda *_: on_open(report["id"]))
        with ui.row().classes("w-full items-center gap-4"):
            with ui.row().classes("items-center gap-3 shrink-0"):
                checkbox = ui.checkbox(value=selected)
                checkbox.on("click.stop", lambda *_: None)
                if on_toggle:
                    checkbox.on_value_change(
                        lambda event: on_toggle(report["id"], bool(event.value))
                    )
                ui.label(format_history_timestamp(report["created_at"])).classes(
                    "w-[170px] text-sm dw-muted"
                )
                render_risk_badge(report["severity"])
                ui.label(interface.upper()).classes(
                    "w-10 text-xs font-semibold tracking-[0.08em] dw-muted text-center"
                )
            with ui.column().classes("min-w-0 flex-1 gap-2"):
                with ui.row().classes("w-full items-start justify-between gap-3"):
                    ui.label(report["top_risk"]).classes(
                        "min-w-0 flex-1 text-sm font-medium dw-text leading-5"
                    )
                    render_recommendation_label(report["recommendation"])
                summary = (
                    report.get("narrative_opening") or report.get("parse_summary") or ""
                )
                if summary:
                    ui.label(summary).classes("text-xs dw-muted leading-5")
                tool_mix = report.get("tool_mix") or ["unknown"]
                with ui.row().classes(
                    "w-full items-center gap-2 flex-wrap text-[11px] leading-5"
                ):
                    ui.label(_scope_label(report)).classes("dw-muted")
                    ui.label(f"Tools: {', '.join(tool_mix)}").classes("dw-muted")
                    ui.label(
                        f"Schema: {report.get('report_schema_version') or 'unknown'}"
                    ).classes("dw-muted")
                    ui.label(
                        f"Status: {report.get('analysis_status') or 'complete'}"
                    ).classes("dw-muted")
                context = report.get("context_completeness") or {}
                with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                    ui.label("Topology freshness").classes(
                        "text-[11px] font-semibold uppercase tracking-[0.08em] dw-muted"
                    )
                    ui.label(topology_freshness_age_text(context)).classes(
                        "text-xs font-semibold dw-text"
                    )
                    ui.label(topology_freshness_badge_text(context)).style(
                        _freshness_badge_style(topology_freshness_level(context))
                    )
                    manage_link = ui.link(
                        "Manage topology", TOPOLOGY_MANAGEMENT_LINK
                    ).classes("text-[11px] font-semibold dw-accent-text")
                    manage_link.on("click.stop", lambda *_: None)
                if previous_scan_diff:
                    delta = int(previous_scan_diff.get("score_delta", 0))
                    delta_prefix = "+" if delta > 0 else ""
                    delta_class = (
                        "dw-danger-text"
                        if delta > 0
                        else "dw-success-text"
                        if delta < 0
                        else "dw-muted"
                    )
                    severity_transition = (
                        f"{str(previous_scan_diff.get('previous_severity', 'unknown')).upper()}"
                        f" → {str(previous_scan_diff.get('current_severity', report['severity'])).upper()}"
                    )
                    recommendation_transition = (
                        f"{str(previous_scan_diff.get('previous_recommendation', 'unknown')).upper()}"
                        f" → {str(previous_scan_diff.get('current_recommendation', report['recommendation'])).upper()}"
                    )
                    with ui.row().classes(
                        "w-full items-center gap-2 flex-wrap text-[11px] leading-5"
                    ):
                        ui.label("Rescan diff").classes(
                            "font-semibold uppercase tracking-[0.08em] dw-accent-text"
                        )
                        ui.label(
                            f"{delta_prefix}{delta} risk vs report #{previous_scan_diff['previous_report_id']}"
                        ).classes(f"font-semibold {delta_class}")
                        ui.label(severity_transition).classes("dw-muted")
                        if (
                            recommendation_transition.split(" → ")[0]
                            != recommendation_transition.split(" → ")[1]
                        ):
                            ui.label(recommendation_transition).classes("dw-muted")
                confidence = _report_confidence(report)
                if confidence is not None:
                    with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                        render_confidence_badge(confidence)
                provenance = (
                    f"Risk: {report.get('assessment_source') or 'unknown'} · "
                    f"Narrative: {report.get('narrative_source') or 'unknown'}"
                )
                if report.get("narrative_provider"):
                    provenance += f" · {report['narrative_provider']}"
                ui.label(provenance).classes("text-[11px] dw-muted leading-5")
                if on_delete:
                    with ui.row().classes("w-full justify-end"):
                        delete_button = ui.button("Delete").props("flat no-caps dense")
                        delete_button.classes("px-0 dw-danger-text font-medium")
                    delete_button.on("click.stop", lambda *_: on_delete(report["id"]))
    return checkbox
