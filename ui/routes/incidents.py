"""Incidents route rendering."""

from __future__ import annotations

from nicegui import ui

from services.incident_service import get_incident_ingestion_status
from services.project_service import ProjectAuthorizationError
from ui.project_authorization import (
    require_ui_project_capability,
    resolve_authorized_ui_active_project,
)
from ui.components.dashboard_shell import build_app_shell, workspace_content
from ui.theme import build_page_header


def _empty_status(project_id: int | None) -> dict:
    return {
        "project_id": project_id or 0,
        "workspace_id": None,
        "indexed_count": 0,
        "rejected_count": 0,
        "last_indexed_at": None,
        "index_version": "incidents:empty",
        "redaction_status": "unknown",
        "freshness_status": "empty",
        "sources": [],
    }


def _status_for_project(project_id: int | None) -> dict:
    if project_id is None:
        return _empty_status(project_id)
    return get_incident_ingestion_status(project_id=project_id).model_dump(mode="json")


def build_incidents_page() -> None:
    """Render incident ingestion/index management."""
    content_refresh = {"fn": lambda *_: None}

    def handle_project_change(*_) -> None:
        content_refresh["fn"]()

    build_app_shell("incidents", on_project_change=handle_project_change)

    @ui.refreshable
    def render_incidents_content() -> None:
        _, active_project, authorization_error = resolve_authorized_ui_active_project()
        if authorization_error is None and active_project is not None:
            try:
                require_ui_project_capability(
                    capability="incident.manage",
                    project_key=active_project.project_key,
                )
            except ProjectAuthorizationError as exc:
                authorization_error = exc.message
        status = (
            _empty_status(active_project.id if active_project is not None else None)
            if authorization_error is not None
            else _status_for_project(
                active_project.id if active_project is not None else None
            )
        )
        project_name = (
            active_project.display_name if active_project is not None else "Unassigned"
        )

        with workspace_content(aria_label="Incident ingestion workspace"):
            with ui.card().classes("w-full dw-panel dw-page-header shadow-none"):
                build_page_header(
                    eyebrow="Incidents",
                    title="Incident ingestion management",
                    subtitle=(
                        "Manage project incident memory indexing, freshness, and "
                        "actionable import failures."
                    ),
                    back_href="/",
                    back_label="Back to dashboard",
                )
            if authorization_error is not None:
                with ui.card().classes("w-full dw-panel shadow-none"):
                    ui.label("Project authorization unavailable").classes(
                        "text-lg font-medium dw-text"
                    )
                    ui.label(authorization_error).classes("text-sm dw-muted")
                return

            with ui.card().classes("w-full dw-panel shadow-none"):
                ui.label(project_name).classes("dw-eyebrow")
                with ui.row().classes("w-full gap-3 flex-wrap mt-3"):
                    for value, label in (
                        (status["indexed_count"], "Indexed incidents"),
                        (status["rejected_count"], "Rejected records"),
                        (status["redaction_status"], "Redaction status"),
                        (status["freshness_status"], "Index freshness"),
                    ):
                        with ui.column().classes("dw-mini-stat flex-1 min-w-[140px]"):
                            ui.label(str(value)).classes(
                                "font-semibold text-lg dw-text"
                            )
                            ui.label(label).classes(
                                "text-xs dw-muted uppercase tracking-[0.08em]"
                            )
                ui.label(
                    f"Last indexed: {status['last_indexed_at'] or 'none yet'}"
                ).classes("text-sm dw-muted mt-3")

            with ui.card().classes("w-full dw-panel shadow-none"):
                ui.label("Incident sources").classes("text-lg font-medium dw-text")
                if not status["sources"]:
                    ui.label(
                        "No incident sources indexed for this project yet."
                    ).classes("text-sm dw-muted")
                    return
                for source in status["sources"]:
                    with ui.column().classes(
                        "w-full gap-2 dw-panel-soft rounded-lg p-4"
                    ):
                        with ui.row().classes(
                            "w-full items-start justify-between gap-3"
                        ):
                            with ui.column().classes("gap-1 min-w-0"):
                                ui.label(source["import_source"]).classes(
                                    "font-semibold dw-text"
                                )
                                if source.get("title"):
                                    ui.label(source["title"]).classes(
                                        "text-sm dw-muted"
                                    )
                            ui.label(source["freshness_status"]).classes(
                                "text-xs font-semibold uppercase dw-success-text"
                            )
                        ui.label(
                            "Scope {scope} · indexed {indexed} · rejected {rejected} · redaction {redaction}".format(
                                scope=source.get("scope_label") or "Project",
                                indexed=source["indexed_count"],
                                rejected=source["rejected_count"],
                                redaction=source["redaction_status"],
                            )
                        ).classes("text-sm dw-muted")
                        ui.label(
                            f"Last indexed: {source['last_indexed_at'] or 'none yet'}"
                        ).classes("text-xs dw-muted")
                        if source["failure_summaries"]:
                            for failure in source["failure_summaries"]:
                                ui.label(
                                    "{field}: {message} Correction: {correction}".format(
                                        field=failure["field"],
                                        message=failure["message"],
                                        correction=failure["correction_path"],
                                    )
                                ).classes("text-sm dw-warning-text")

    content_refresh["fn"] = lambda *_: render_incidents_content.refresh()
    render_incidents_content()
