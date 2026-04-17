"""Incident match rendering."""

from __future__ import annotations

from analysis.incident_matcher import IncidentMatch
from nicegui import ui
from ui.formatters.risk_labels import render_risk_badge


def render_incident_matches(matches: list[IncidentMatch]) -> None:
    """Render incident similarity context."""
    with ui.card().classes("w-full dw-panel shadow-none"):
        ui.label("Incident similarity").classes("text-lg font-medium dw-text")
        if not matches:
            ui.label("No similar incidents found.").classes("text-sm dw-muted")
            return
        with ui.column().classes("w-full gap-3"):
            for match in matches:
                with ui.row().classes("w-full items-start gap-3 dw-panel-soft px-3 py-3"):
                    ui.label(f"{round(match.similarity * 100)}%").classes("text-sm font-medium dw-accent-text")
                    with ui.column().classes("gap-1"):
                        date_label = f" · {match.incident_date}" if match.incident_date else ""
                        with ui.row().classes("items-center gap-2"):
                            ui.label(match.title).classes("text-sm font-medium dw-text")
                            render_risk_badge(match.severity, match.severity)
                            if date_label:
                                ui.label(date_label.replace(" · ", "")).classes("text-xs dw-muted")
                        ui.label(match.summary).classes("text-sm dw-muted")
