"""History route rendering."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from services.report_service import (
    fetch_analysis_history,
    fetch_analysis_report,
    fetch_filtered_analysis_history,
    fetch_risk_trends,
    remove_analysis_report,
    remove_analysis_reports,
)
from ui.components.analysis_history_row import render_analysis_history_row
from ui.formatters.recommendations import render_recommendation_label
from ui.formatters.risk_labels import render_risk_badge
from ui.theme import apply_theme, build_navigation_shell, build_page_header


def page_selection_state(visible_ids: set[int], selected_ids: set[int]) -> tuple[bool, int]:
    """Return whether a page is fully selected and how many visible rows are selected."""
    if not visible_ids:
        return False, 0
    selected_on_page = len(visible_ids & selected_ids)
    return selected_on_page == len(visible_ids), selected_on_page


def build_history_page() -> None:
    """Render a scanable history view with direct report retrieval."""
    apply_theme()
    build_navigation_shell("history")
    reports = fetch_analysis_history()
    trends = fetch_risk_trends()
    selected_ids: set[int] = set()
    page_state = {"page": 1, "page_size": 5}
    card_checkboxes: dict[int, Any] = {}
    selection_sync = {"active": False}
    report_dialog = ui.dialog()

    with ui.column().classes("dw-main-content dw-shell gap-5"):
        with ui.card().classes("w-full dw-panel shadow-none"):
            build_page_header(
                eyebrow="History",
                title="Analysis history",
                subtitle="Review earlier deploy briefings, audit metadata, and risk trends.",
                back_href="/",
                back_label="Back to dashboard",
            )
        with ui.card().classes("w-full dw-panel shadow-none p-4"):
            with ui.column().classes("gap-0"):
                ui.label("Risk trends").classes("dw-eyebrow mb-1")
                ui.label(
                    f"{trends['total_reports']} reports · "
                    f"{trends['severity_counts'].get('critical', 0)} critical · "
                    f"{trends['severity_counts'].get('high', 0)} high"
                ).classes("text-lg font-medium text-[#1D2420] leading-6")
                ui.label(
                    "Top tools: "
                    + ", ".join(
                        f"{tool} ({count})"
                        for tool, count in sorted(
                            trends["tool_counts"].items(),
                            key=lambda item: item[1],
                            reverse=True,
                        )[:3]
                    )
                ).classes("mt-[2px] text-sm dw-muted")
        search_input = (
            ui.input(placeholder="Search top risk or summary")
            .props("outlined dense clearable prepend-icon=search")
            .classes("w-full dw-search-input")
        )
        actions_row = ui.row().classes("w-full items-center justify-between gap-4 flex-wrap")
        history_column = ui.column().classes("w-full gap-3")

        def refresh_data(query: str | None = None) -> list[dict]:
            nonlocal reports, trends
            reports = fetch_filtered_analysis_history(search=query)
            trends = fetch_risk_trends()
            max_page = max(1, (len(reports) - 1) // page_state["page_size"] + 1)
            page_state["page"] = min(page_state["page"], max_page)
            return reports

        def current_page_reports() -> list[dict]:
            start = (page_state["page"] - 1) * page_state["page_size"]
            end = start + page_state["page_size"]
            return reports[start:end]

        def open_report(report_id: int) -> None:
            report = fetch_analysis_report(report_id)
            if report is None:
                ui.notify("Report not found", color="negative")
                return
            report_dialog.clear()
            audit = report.get("audit", {})
            with report_dialog, ui.card().classes("dw-panel shadow-none w-[min(760px,92vw)] max-h-[85vh] overflow-y-auto p-6"):
                with ui.row().classes("w-full items-start justify-between gap-4"):
                    with ui.column().classes("gap-3 min-w-0"):
                        with ui.row().classes("items-center gap-3 flex-wrap"):
                            render_risk_badge(report["severity"])
                            render_recommendation_label(report["recommendation"], size="base")
                        ui.label(report["top_risk"]).classes("text-xl font-medium text-[#1D2420] leading-7")
                    ui.button(icon="close", on_click=report_dialog.close).props("flat round dense")
                with ui.column().classes("mt-2 gap-4"):
                    with ui.column().classes("gap-1"):
                        ui.label("Description").classes("text-sm font-semibold text-[#1D2420]")
                        ui.label(report["top_risk"]).classes("text-sm leading-6 text-[#1D2420]")
                    with ui.column().classes("gap-1"):
                        ui.label("Advisory").classes("text-sm font-semibold text-[#1D2420]")
                        ui.label(report["narrative_opening"]).classes("text-sm leading-6 dw-muted")
                    with ui.column().classes("gap-1"):
                        ui.label("Processing summary").classes("text-sm font-semibold text-[#1D2420]")
                        ui.label(report["parse_summary"]).classes("text-sm leading-6 dw-muted")
                    with ui.column().classes("gap-1"):
                        ui.label("Audit metadata").classes("text-sm font-semibold text-[#1D2420]")
                        ui.label(
                            f"Interface: {audit.get('source_interface') or 'unknown'} · "
                            f"Provider: {audit.get('llm_provider') or 'unknown'}"
                        ).classes("text-sm dw-muted")
                        if audit.get("trigger_type") or audit.get("trigger_id"):
                            ui.label(
                                f"Trigger: {audit.get('trigger_type') or 'unknown'}"
                                + (f" · {audit.get('trigger_id')}" if audit.get("trigger_id") else "")
                            ).classes("text-sm dw-muted")
                        if audit.get("files_analyzed"):
                            ui.label("Files analyzed:").classes("text-sm font-semibold text-[#1D2420] mt-1")
                            for file_name in audit["files_analyzed"]:
                                ui.label(file_name).classes("text-sm dw-muted")
                    contributors = report.get("contributors", [])
                    if contributors:
                        with ui.column().classes("gap-2"):
                            ui.label("Resource severity breakdown").classes("text-sm font-semibold text-[#1D2420]")
                            for contributor in contributors:
                                with ui.card().classes("w-full border border-[#D8DDD4] shadow-none bg-[#FAFBF8]"):
                                    with ui.row().classes("w-full items-start justify-between gap-3 p-3 flex-wrap"):
                                        with ui.column().classes("min-w-0 flex-1 gap-1"):
                                            ui.label(contributor["resource_id"]).classes("text-sm font-medium text-[#1D2420]")
                                            ui.label(
                                                f"{contributor['resource_category']} · {contributor['normalized_action']} · "
                                                f"{contributor['environment']} · scope {contributor['downstream_scope']}"
                                            ).classes("text-xs dw-muted")
                                            ui.label(contributor["reasoning"]).classes("text-xs dw-muted leading-5")
                                            for security_flag in contributor.get("security_flags", []):
                                                ui.label(security_flag).classes("text-xs text-[#C24141]")
                                        render_risk_badge(contributor["severity"])
                with ui.row().classes("w-full justify-end mt-4"):
                    ui.button("Close", on_click=report_dialog.close).props("outline no-caps")
            report_dialog.open()

        def toggle_selection(report_id: int, selected: bool) -> None:
            if selected:
                selected_ids.add(report_id)
            else:
                selected_ids.discard(report_id)
            if selection_sync["active"]:
                return
            render_history()
            render_actions()

        def toggle_select_all(selected: bool) -> None:
            selection_sync["active"] = True
            for report in current_page_reports():
                if selected:
                    selected_ids.add(report["id"])
                else:
                    selected_ids.discard(report["id"])
                checkbox = card_checkboxes.get(report["id"])
                if checkbox is not None and checkbox.value != selected:
                    checkbox.set_value(selected)
                    checkbox.update()
            selection_sync["active"] = False
            render_history()
            render_actions()

        def delete_one(report_id: int) -> None:
            prompt_delete([report_id])

        def perform_delete(report_ids: list[int]) -> None:
            if len(report_ids) == 1:
                removed = 1 if remove_analysis_report(report_ids[0]) else 0
            else:
                removed = remove_analysis_reports(report_ids)
            for report_id in report_ids:
                selected_ids.discard(report_id)
            if removed:
                ui.notify(f"Deleted {removed} analysis report(s).", color="positive")
            else:
                ui.notify("Report not found.", color="warning")
            apply_filters()

        def delete_selected() -> None:
            prompt_delete(sorted(selected_ids))

        def prompt_delete(report_ids: list[int]) -> None:
            if not report_ids:
                return
            count = len(report_ids)
            report_label = "report" if count == 1 else "reports"
            with ui.dialog() as dialog, ui.card().classes("w-[420px] dw-panel shadow-none p-6 gap-3"):
                ui.label(f"Are you sure you want to delete {count} selected {report_label}?").classes(
                    "text-lg font-medium text-[#1D2420]"
                )
                ui.label("This action cannot be undone.").classes("text-sm dw-muted")
                with ui.row().classes("w-full justify-end gap-3 mt-4"):
                    ui.button("Cancel", on_click=dialog.close).props("outline no-caps")
                    ui.button(
                        "Confirm Delete",
                        on_click=lambda: (dialog.close(), perform_delete(report_ids)),
                    ).props("outline no-caps").classes("border border-[#C24141] bg-white text-[#C24141]")
            dialog.open()

        def render_actions() -> None:
            actions_row.clear()
            with actions_row:
                visible_reports = current_page_reports()
                visible_ids = {report["id"] for report in visible_reports}
                all_visible_selected, _ = page_selection_state(visible_ids, selected_ids)
                with ui.row().classes("items-center gap-3 flex-wrap"):
                    select_all = ui.checkbox(value=all_visible_selected).props("dense")
                    select_all.on_value_change(lambda event: toggle_select_all(bool(event.value)))
                    if not visible_reports:
                        select_all.disable()
                    ui.label("Select all on page").classes("text-sm text-[#1D2420]")
                    start = 0 if not reports else (page_state["page"] - 1) * page_state["page_size"] + 1
                    end = min(page_state["page"] * page_state["page_size"], len(reports))
                    ui.label(f"Showing {start}-{end} of {len(reports)} reports · {len(selected_ids)} selected").classes(
                        "text-sm dw-muted"
                    )
                with ui.row().classes("items-center justify-end gap-4 flex-wrap"):
                    prev_button = ui.button("Previous", color="primary").props("flat no-caps")
                    if page_state["page"] == 1:
                        prev_button.disable()
                    prev_button.on("click", lambda _: change_page(-1))
                    ui.label(
                        f"Page {page_state['page']} / {max(1, (len(reports) - 1) // page_state['page_size'] + 1)}"
                    ).classes("text-sm dw-muted")
                    next_button = ui.button("Next", color="primary").props("flat no-caps")
                    if page_state["page"] >= max(1, (len(reports) - 1) // page_state["page_size"] + 1):
                        next_button.disable()
                    next_button.on("click", lambda _: change_page(1))
                    bulk_delete = ui.button("Delete selected").props("outline no-caps")
                    bulk_delete.classes("border border-[#C24141] bg-white text-[#C24141]")
                    if not selected_ids:
                        bulk_delete.disable()
                    bulk_delete.on("click", lambda _: delete_selected())

        def render_history() -> None:
            history_column.clear()
            card_checkboxes.clear()
            visible_reports = current_page_reports()
            with history_column:
                if not visible_reports:
                    ui.label("No reports match the current filters.").classes("text-sm dw-muted")
                    return
                for report in visible_reports:
                    checkbox = render_analysis_history_row(
                        report,
                        open_report,
                        on_toggle=toggle_selection,
                        on_delete=delete_one,
                        selected=report["id"] in selected_ids,
                    )
                    card_checkboxes[report["id"]] = checkbox

        def change_page(delta: int) -> None:
            max_page = max(1, (len(reports) - 1) // page_state["page_size"] + 1)
            page_state["page"] = min(max(1, page_state["page"] + delta), max_page)
            render_history()
            render_actions()

        def apply_filters() -> None:
            query = search_input.value.strip() if search_input.value else None
            page_state["page"] = 1
            refresh_data(query)
            render_history()
            render_actions()

        search_input.on("update:model-value", lambda *_: apply_filters())
        render_history()
        render_actions()
