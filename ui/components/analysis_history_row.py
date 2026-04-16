"""Scannable history row rendering."""

from __future__ import annotations

from nicegui import ui

from ui.formatters.datetime import format_history_timestamp
from ui.formatters.recommendations import render_recommendation_label
from ui.formatters.risk_labels import render_risk_badge


def render_analysis_history_row(report: dict, on_open, *, on_toggle=None, on_delete=None, selected: bool = False):
    """Render a compact clickable history row."""
    interface = report.get("audit", {}).get("source_interface") or "unknown"
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
                    checkbox.on_value_change(lambda event: on_toggle(report["id"], bool(event.value)))
                ui.label(format_history_timestamp(report["created_at"])).classes("w-[170px] text-sm dw-muted")
                render_risk_badge(report["severity"])
                ui.label(interface.upper()).classes("w-10 text-xs font-semibold tracking-[0.08em] dw-muted text-center")
            with ui.column().classes("min-w-0 flex-1 gap-2"):
                with ui.row().classes("w-full items-start justify-between gap-3"):
                    ui.label(report["top_risk"]).classes("min-w-0 flex-1 text-sm font-medium text-[#1D2420] leading-5")
                    render_recommendation_label(report["recommendation"])
                summary = report.get("narrative_opening") or report.get("parse_summary") or ""
                if summary:
                    ui.label(summary).classes("text-xs dw-muted leading-5")
                if on_delete:
                    with ui.row().classes("w-full justify-end"):
                        delete_button = ui.button("Delete").props("flat no-caps dense")
                        delete_button.classes("px-0 text-[#C24141] font-medium")
                    delete_button.on("click.stop", lambda *_: on_delete(report["id"]))
    return checkbox
