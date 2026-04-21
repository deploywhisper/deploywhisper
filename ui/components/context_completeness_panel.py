"""Context completeness panel rendering."""

from __future__ import annotations

from nicegui import ui

from services.topology_service import STALE_AFTER_DAYS
from ui.formatters.context_completeness import render_context_completeness_badge
from ui.formatters.datetime import format_history_timestamp


def _topology_age_text(context: dict) -> str:
    freshness = context.get("topology_freshness_days")
    if freshness is None:
        return "Unknown"
    freshness_days = int(freshness)
    if freshness_days == 0:
        return "Imported today"
    unit = "day" if freshness_days == 1 else "days"
    return f"{freshness_days} {unit} old"


def _last_import_text(context: dict) -> str:
    imported_at = context.get("topology_last_imported_at")
    if not imported_at:
        return "Unavailable"
    try:
        return format_history_timestamp(str(imported_at))
    except ValueError:
        return str(imported_at)


def _metric_card(label: str, value: str, detail: str | None = None) -> None:
    with ui.card().classes("dw-panel-soft shadow-none min-w-[180px] flex-1"):
        with ui.column().classes("gap-1 p-3"):
            ui.label(label).classes(
                "text-[11px] font-semibold uppercase tracking-[0.08em] dw-muted"
            )
            ui.label(value).classes("text-lg font-semibold dw-text")
            if detail:
                ui.label(detail).classes("text-xs dw-muted leading-5")


def _topology_needs_settings_fix(context: dict) -> bool:
    freshness = context.get("topology_freshness_days")
    if freshness is None:
        return True
    return int(freshness) > STALE_AFTER_DAYS


def render_context_completeness_panel(
    context: dict | None,
    *,
    link_target: str = "/settings",
) -> None:
    """Render reviewer-facing context completeness details."""
    details = context or {}
    parser_success_by_tool = dict(details.get("parser_success_by_tool") or {})
    low_context = float(details.get("context_score", 1.0)) < 0.7
    stale_topology = _topology_needs_settings_fix(details)

    with ui.card().classes("w-full dw-panel shadow-none p-4"):
        with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
            with ui.column().classes("gap-2 min-w-0 flex-1"):
                ui.label("Context completeness").classes("text-lg font-medium dw-text")
                ui.label(
                    "Review how much topology, incident history, and parser coverage supported this report."
                ).classes("text-sm dw-muted leading-6")
            render_context_completeness_badge(details)

        if low_context:
            with ui.row().classes(
                "w-full items-center justify-between gap-3 flex-wrap mt-3 rounded-[18px] border border-[color:var(--dw-accent-line)] bg-[color:var(--dw-accent-soft)] px-4 py-3"
            ):
                ui.label(
                    "Context warning: supporting topology or incident history may be stale."
                ).classes("text-sm font-semibold dw-accent-text")
                ui.link("Fix in settings", link_target).classes(
                    "text-sm font-semibold dw-accent-text"
                )
        elif stale_topology:
            with ui.row().classes(
                "w-full items-center justify-between gap-3 flex-wrap mt-3 rounded-[18px] border border-[color:var(--dw-line)] bg-[color:var(--dw-surface-soft)] px-4 py-3"
            ):
                ui.label(
                    "Topology context is stale or missing. Refresh it in settings to keep blast radius and context details current."
                ).classes("text-sm font-semibold dw-text")
                ui.link("Fix in settings", link_target).classes(
                    "text-sm font-semibold dw-accent-text"
                )

        with ui.row().classes("w-full gap-3 flex-wrap mt-3"):
            _metric_card(
                "Topology freshness",
                _topology_age_text(details),
                "Age of the imported topology snapshot used for blast radius.",
            )
            _metric_card(
                "Last import",
                _last_import_text(details),
                "Most recent topology import timestamp recorded for this report.",
            )
            _metric_card(
                "Incident index",
                str(int(details.get("incident_index_size", 0))),
                "Stored incidents available for similarity matching.",
            )
            _metric_card(
                "Parser success",
                f"{float(details.get('parser_success_rate', 1.0)):.2f}",
                "Overall fraction of analyzed artifacts parsed successfully.",
            )

        with ui.card().classes("w-full dw-panel-soft shadow-none mt-3"):
            with ui.column().classes("gap-2 p-3"):
                ui.label("Parser success by tool").classes(
                    "text-sm font-semibold dw-text"
                )
                if parser_success_by_tool:
                    with ui.row().classes("w-full gap-2 flex-wrap"):
                        for tool_name, score in sorted(parser_success_by_tool.items()):
                            with ui.column().classes(
                                "min-w-[132px] flex-1 rounded-[16px] border border-[color:var(--dw-line)] px-3 py-2"
                            ):
                                ui.label(tool_name.title()).classes(
                                    "text-sm font-semibold dw-text"
                                )
                                ui.label(f"{float(score):.2f}").classes(
                                    "text-xs dw-muted"
                                )
                else:
                    ui.label(
                        "Per-tool parser coverage is unavailable for this report."
                    ).classes("text-xs dw-muted")
