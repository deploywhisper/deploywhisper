"""Incident match rendering."""

from __future__ import annotations

from analysis.incident_matcher import IncidentMatch
from nicegui import ui
from ui.formatters.risk_labels import render_risk_badge


def render_incident_matches(matches: list[IncidentMatch]) -> None:
    """Render incident similarity context."""
    with ui.card().classes("w-full dw-panel shadow-none"):
        ui.label("Incident and risk pattern similarity").classes(
            "text-lg font-medium dw-text"
        )
        if not matches:
            ui.label("No organization-specific incident match found.").classes(
                "text-sm dw-muted"
            )
            return
        has_organization_match = any(
            match.match_type == "organization_incident" for match in matches
        )
        if not has_organization_match:
            ui.label(
                "No organization-specific incident match found. Public risk patterns are general guidance, not prior incidents."
            ).classes("text-sm dw-muted")
        with ui.column().classes("w-full gap-3"):
            for match in matches:
                with ui.row().classes(
                    "w-full items-start gap-3 dw-panel-soft px-3 py-3"
                ):
                    ui.label(f"{round(match.confidence * 100)}% confidence").classes(
                        "text-sm font-medium dw-accent-text"
                    )
                    with ui.column().classes("gap-1"):
                        date_label = (
                            f" · {match.incident_date}" if match.incident_date else ""
                        )
                        with ui.row().classes("items-center gap-2"):
                            ui.label(match.title).classes("text-sm font-medium dw-text")
                            render_risk_badge(match.severity, match.severity)
                            if match.match_type == "organization_incident":
                                ui.label("Organization incident").classes(
                                    "text-xs dw-muted"
                                )
                            if match.match_type == "public_risk_pattern":
                                ui.label("Public risk pattern").classes(
                                    "text-xs dw-muted"
                                )
                            if date_label:
                                ui.label(date_label.replace(" · ", "")).classes(
                                    "text-xs dw-muted"
                                )
                        ui.label(match.summary).classes("text-sm dw-muted")
                        if match.reason:
                            ui.label(match.reason).classes("text-sm dw-muted")
                        if match.matched_signals:
                            ui.label(
                                f"Matched signals: {', '.join(match.matched_signals)}"
                            ).classes("text-xs dw-muted")
                        if match.affected_services:
                            ui.label(
                                f"Affected services: {', '.join(match.affected_services)}"
                            ).classes("text-xs dw-muted")
                        if match.prevention_notes:
                            ui.label("Prevention notes:").classes(
                                "text-xs font-medium dw-text"
                            )
                            for note in match.prevention_notes:
                                ui.label(note).classes("text-xs dw-muted")
                        for evidence in match.evidence:
                            ui.label(f"Evidence: {evidence}").classes(
                                "text-xs dw-muted"
                            )
                        for guidance in match.verification_guidance:
                            ui.label(guidance).classes("text-xs dw-muted")
