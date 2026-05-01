"""History route rendering."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from services.project_service import get_active_project
from services.backtesting_service import fetch_calibration_dashboard_seed
from services.report_service import (
    fetch_analysis_report,
    fetch_filtered_analysis_history_page,
    fetch_report_comparison,
    fetch_risk_trends,
    remove_analysis_report,
    remove_analysis_reports,
)
from ui.components.analysis_history_row import render_analysis_history_row
from ui.components.report_detail_page import render_report_detail_page
from ui.components.review_accessibility import (
    decorate_modal_card,
    decorate_modal_close,
)
from ui.components.topology_freshness_banner import render_topology_freshness_banner
from ui.theme import apply_theme, build_navigation_shell, build_page_header


def page_selection_state(
    visible_ids: set[int], selected_ids: set[int]
) -> tuple[bool, int]:
    """Return whether a page is fully selected and how many visible rows are selected."""
    if not visible_ids:
        return False, 0
    selected_on_page = len(visible_ids & selected_ids)
    return selected_on_page == len(visible_ids), selected_on_page


def build_history_page() -> None:
    """Render a scanable history view with direct report retrieval."""
    apply_theme()
    content_refresh = {"fn": lambda *_: None}

    def handle_project_change(*_) -> None:
        refresh_shell()
        content_refresh["fn"]()

    refresh_shell = build_navigation_shell(
        "history",
        on_project_change=handle_project_change,
    )

    @ui.refreshable
    def render_history_content() -> None:
        active_project = get_active_project()
        active_project_id = active_project.id if active_project is not None else None
        reports_page = fetch_filtered_analysis_history_page(
            project_id=active_project_id,
            page=1,
            page_size=5,
        )
        reports = reports_page["items"]
        total_report_count = reports_page["total_count"]
        trends = fetch_risk_trends(project_id=active_project_id)
        calibration = fetch_calibration_dashboard_seed(project_id=active_project_id)
        selected_ids: set[int] = set()
        page_state = {"page": 1, "page_size": 5}
        card_checkboxes: dict[int, Any] = {}
        selection_sync = {"active": False}

        with ui.column().classes("dw-main-content dw-shell gap-5"):
            with ui.card().classes("w-full dw-panel dw-page-header shadow-none"):
                build_page_header(
                    eyebrow="History",
                    title="Analysis history",
                    subtitle=(
                        "Review earlier deploy briefings, audit metadata, and risk trends."
                        if active_project is None
                        else f"Project-scoped history for {active_project.display_name} ({active_project.project_key})."
                    ),
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
                    ).classes("text-lg font-medium dw-text leading-6")
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
            with ui.card().classes("w-full dw-panel shadow-none p-4"):
                with ui.column().classes("gap-0"):
                    ui.label("Calibration snapshot").classes("dw-eyebrow mb-1")
                    ui.label(
                        f"{calibration['failed_deploy_count']} failed deploys · "
                        f"{calibration['warned_failed_deploy_count']} warned"
                    ).classes("text-lg font-medium dw-text leading-6")
                    ui.label(
                        f"Precision {calibration['overall_precision']:.2f} · "
                        f"Recall {calibration['overall_recall']:.2f} · "
                        f"{calibration['window']['days']}d window"
                    ).classes("mt-[2px] text-sm dw-muted")
            search_input = (
                ui.input(placeholder="Search top risk or summary")
                .props("outlined dense clearable prepend-icon=search")
                .classes("w-full dw-search-input")
            )
            actions_row = ui.row().classes(
                "w-full items-center justify-between gap-4 flex-wrap"
            )
            history_column = ui.column().classes("w-full gap-3")

            def refresh_data(query: str | None = None) -> list[dict]:
                nonlocal reports, trends, total_report_count, calibration
                page_payload = fetch_filtered_analysis_history_page(
                    project_id=active_project_id,
                    search=query,
                    page=page_state["page"],
                    page_size=page_state["page_size"],
                )
                reports = page_payload["items"]
                total_report_count = page_payload["total_count"]
                trends = fetch_risk_trends(project_id=active_project_id)
                calibration = fetch_calibration_dashboard_seed(
                    project_id=active_project_id
                )
                max_page = max(
                    1, (total_report_count - 1) // page_state["page_size"] + 1
                )
                page_state["page"] = min(page_state["page"], max_page)
                return reports

            def current_page_reports() -> list[dict]:
                return reports

            def open_report(report_id: int) -> None:
                ui.navigate.to(f"/history/{report_id}")

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
                    ui.notify(
                        f"Deleted {removed} analysis report(s).", color="positive"
                    )
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
                with (
                    ui.dialog() as dialog,
                    ui.card().classes(
                        "w-[420px] dw-panel shadow-none p-6 gap-3"
                    ) as dialog_card,
                ):
                    decorate_modal_card(dialog_card, label="Delete analysis report")
                    ui.label(
                        f"Are you sure you want to delete {count} selected {report_label}?"
                    ).classes("text-lg font-medium dw-text")
                    ui.label("This action cannot be undone.").classes(
                        "text-sm dw-muted"
                    )
                    with ui.row().classes("w-full justify-end gap-3 mt-4"):
                        cancel_button = ui.button(
                            "Cancel", on_click=dialog.close
                        ).props("outline no-caps")
                        decorate_modal_close(cancel_button)
                        ui.button(
                            "Confirm Delete",
                            on_click=lambda: (
                                dialog.close(),
                                perform_delete(report_ids),
                            ),
                        ).props("outline no-caps").classes("dw-danger-button")
                dialog.open()

            def render_actions() -> None:
                actions_row.clear()
                with actions_row:
                    visible_reports = current_page_reports()
                    visible_ids = {report["id"] for report in visible_reports}
                    all_visible_selected, _ = page_selection_state(
                        visible_ids, selected_ids
                    )
                    with ui.row().classes("items-center gap-3 flex-wrap"):
                        select_all = ui.checkbox(value=all_visible_selected).props(
                            "dense"
                        )
                        select_all.on_value_change(
                            lambda event: toggle_select_all(bool(event.value))
                        )
                        if not visible_reports:
                            select_all.disable()
                        ui.label("Select all on page").classes("text-sm dw-text")
                        start = (
                            0
                            if not reports
                            else (page_state["page"] - 1) * page_state["page_size"] + 1
                        )
                        end = start - 1 + len(reports)
                        ui.label(
                            f"Showing {start}-{end} of {total_report_count} reports · {len(selected_ids)} selected"
                        ).classes("text-sm dw-muted")
                    with ui.row().classes("items-center justify-end gap-4 flex-wrap"):
                        prev_button = ui.button("Previous", color="primary").props(
                            "flat no-caps"
                        )
                        if page_state["page"] == 1:
                            prev_button.disable()
                        prev_button.on("click", lambda _: change_page(-1))
                        ui.label(
                            f"Page {page_state['page']} / {max(1, (total_report_count - 1) // page_state['page_size'] + 1)}"
                        ).classes("text-sm dw-muted")
                        next_button = ui.button("Next", color="primary").props(
                            "flat no-caps"
                        )
                        if page_state["page"] >= max(
                            1,
                            (total_report_count - 1) // page_state["page_size"] + 1,
                        ):
                            next_button.disable()
                        next_button.on("click", lambda _: change_page(1))
                        bulk_delete = ui.button("Delete selected").props(
                            "outline no-caps"
                        )
                        bulk_delete.classes("dw-danger-button")
                        if not selected_ids:
                            bulk_delete.disable()
                        bulk_delete.on("click", lambda _: delete_selected())

            def render_history() -> None:
                history_column.clear()
                card_checkboxes.clear()
                visible_reports = current_page_reports()
                with history_column:
                    if not visible_reports:
                        ui.label("No reports match the current filters.").classes(
                            "text-sm dw-muted"
                        )
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
                max_page = max(
                    1, (total_report_count - 1) // page_state["page_size"] + 1
                )
                page_state["page"] = min(max(1, page_state["page"] + delta), max_page)
                refresh_data(search_input.value.strip() if search_input.value else None)
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

    content_refresh["fn"] = lambda *_: render_history_content.refresh()
    render_history_content()


def _render_history_comparison_items(
    heading: str,
    items: list[dict[str, Any]],
    *,
    empty_message: str,
) -> None:
    with ui.column().classes("gap-3"):
        ui.label(heading).classes("text-lg font-medium dw-text")
        if not items:
            ui.label(empty_message).classes("text-sm dw-muted")
            return
        for item in items:
            with ui.card().classes("w-full dw-panel-soft shadow-none"):
                with ui.column().classes("gap-2 p-4"):
                    title = str(item.get("title") or item.get("source_type") or "")
                    ui.label(title).classes("text-sm font-semibold dw-text")
                    if item.get("finding_title"):
                        ui.label(str(item["finding_title"])).classes("text-xs dw-muted")
                    description = str(
                        item.get("description") or item.get("summary") or ""
                    )
                    if description:
                        ui.label(description).classes("text-sm dw-muted leading-6")
                    if item.get("source_ref"):
                        ui.label(str(item["source_ref"])).classes(
                            "text-xs dw-muted break-all"
                        )


def _render_history_report_comparison(
    report_id: int,
    comparison: dict[str, Any] | None,
) -> None:
    with ui.card().classes("w-full dw-panel shadow-none p-5") as compare_card:
        decorate_modal_card(compare_card, label="Report comparison")
        with ui.row().classes("w-full items-center justify-between gap-3 flex-wrap"):
            ui.label("Report comparison").classes("text-lg font-medium dw-text")
            ui.button(
                "Back to report overview",
                on_click=lambda: ui.navigate.to(f"/history/{report_id}"),
            ).props("flat no-caps").classes("dw-theme-button")
        if comparison is None:
            ui.label(
                "No previous comparable report was found for this analysis yet."
            ).classes("text-sm dw-muted")
            return

        score_delta = int(comparison.get("risk_score_delta") or 0)
        score_prefix = "+" if score_delta > 0 else ""
        score_class = (
            "dw-danger-text"
            if score_delta > 0
            else "dw-success-text"
            if score_delta < 0
            else "dw-muted"
        )
        with ui.row().classes("w-full items-start justify-between gap-4 flex-wrap"):
            with ui.column().classes("gap-1 min-w-0 flex-1"):
                ui.label(
                    f"Comparison with report #{int(comparison['previous_report']['id'])}"
                ).classes("text-xl font-semibold dw-text")
                ui.label(
                    "Side-by-side changes against the previous saved scan of the same analyzed artifacts."
                ).classes("text-sm dw-muted leading-6")
            with ui.column().classes("gap-1 shrink-0"):
                ui.label("Risk score delta").classes(
                    "text-[11px] font-semibold uppercase tracking-[0.08em] dw-muted"
                )
                ui.label(f"{score_prefix}{score_delta}").classes(
                    f"text-3xl font-semibold {score_class}"
                )
                ui.label(
                    f"{int(comparison['previous_report']['risk_score'])} -> {int(comparison['current_report']['risk_score'])}"
                ).classes("text-xs dw-muted")
        with ui.row().classes("w-full gap-4 flex-wrap mt-2"):
            with ui.card().classes("dw-panel-soft shadow-none min-w-[260px] flex-1"):
                with ui.column().classes("gap-2 p-4"):
                    ui.label("Previous report").classes("text-sm font-semibold dw-text")
                    ui.label(
                        f"#{int(comparison['previous_report']['id'])} · "
                        f"{str(comparison['previous_report']['severity']).upper()} · "
                        f"{str(comparison['previous_report']['recommendation']).upper()}"
                    ).classes("text-xs dw-muted")
                    render_topology_freshness_banner(
                        comparison["previous_report"].get("context_completeness") or {}
                    )
                    _render_history_comparison_items(
                        "Findings removed",
                        comparison["findings"]["removed"],
                        empty_message="No findings were removed.",
                    )
                    _render_history_comparison_items(
                        "Evidence removed",
                        comparison["evidence"]["removed"],
                        empty_message="No evidence was removed.",
                    )
            with ui.card().classes("dw-panel-soft shadow-none min-w-[260px] flex-1"):
                with ui.column().classes("gap-2 p-4"):
                    ui.label("Current report").classes("text-sm font-semibold dw-text")
                    ui.label(
                        f"#{int(comparison['current_report']['id'])} · "
                        f"{str(comparison['current_report']['severity']).upper()} · "
                        f"{str(comparison['current_report']['recommendation']).upper()}"
                    ).classes("text-xs dw-muted")
                    render_topology_freshness_banner(
                        comparison["current_report"].get("context_completeness") or {}
                    )
                    _render_history_comparison_items(
                        "Findings added",
                        comparison["findings"]["added"],
                        empty_message="No findings were added.",
                    )
                    _render_history_comparison_items(
                        "Evidence added",
                        comparison["evidence"]["added"],
                        empty_message="No evidence was added.",
                    )
        with ui.card().classes("w-full dw-panel-soft shadow-none mt-4"):
            with ui.column().classes("gap-3 p-4"):
                ui.label("Severity changes").classes("text-sm font-semibold dw-text")
                changes = comparison["findings"]["severity_changed"]
                if not changes:
                    ui.label("No finding severity changed.").classes("text-sm dw-muted")
                else:
                    for item in changes:
                        with ui.row().classes(
                            "w-full items-start justify-between gap-3 flex-wrap"
                        ):
                            with ui.column().classes("min-w-0 flex-1 gap-1"):
                                ui.label(
                                    str(item.get("title") or "Untitled finding")
                                ).classes("text-sm font-semibold dw-text")
                                ui.label(str(item.get("description") or "")).classes(
                                    "text-sm dw-muted leading-6"
                                )
                            ui.label(
                                f"{str(item.get('previous_severity') or 'unknown').upper()} → "
                                f"{str(item.get('current_severity') or 'unknown').upper()}"
                            ).classes("text-sm font-semibold dw-text")


def build_history_detail_page(report_id: int, *, show_comparison: bool = False) -> None:
    """Render one persisted report on a dedicated detail page."""
    apply_theme()
    content_refresh = {"fn": lambda *_: None}

    def handle_project_change(*_) -> None:
        refresh_shell()
        content_refresh["fn"]()

    refresh_shell = build_navigation_shell(
        "history",
        on_project_change=handle_project_change,
    )

    @ui.refreshable
    def render_history_detail_content() -> None:
        active_project = get_active_project()
        active_project_id = active_project.id if active_project is not None else None
        report = fetch_analysis_report(report_id, project_id=active_project_id)
        comparison = (
            fetch_report_comparison(report_id, project_id=active_project_id)
            if show_comparison
            else None
        )

        with ui.column().classes("dw-main-content dw-shell gap-5"):
            with ui.card().classes("w-full dw-panel dw-page-header shadow-none"):
                if report is None:
                    build_page_header(
                        eyebrow="History",
                        title="Analysis report not found",
                        subtitle="The requested report could not be loaded. It may have been deleted.",
                        back_href="/history",
                        back_label="Back to History",
                    )
                else:
                    build_page_header(
                        eyebrow="History",
                        title="Analysis report detail",
                        subtitle="Full-width report review with readable findings, context quality, blast radius, rollback guidance, and audit metadata.",
                        back_href="/history",
                        back_label="Back to History",
                    )
            if report is None:
                with ui.card().classes("w-full dw-panel shadow-none p-6"):
                    ui.label(
                        "This report is unavailable. Return to history and choose another saved analysis."
                    ).classes("text-sm dw-muted")
                return
            with ui.card().classes("w-full dw-panel shadow-none p-4"):
                if show_comparison:
                    _render_history_report_comparison(report_id, comparison)
                else:
                    with ui.row().classes(
                        "w-full items-center justify-between gap-3 flex-wrap"
                    ):
                        ui.label(
                            "Open a persisted diff against the previous comparable report."
                        ).classes("text-sm dw-muted")
                        ui.button(
                            "Compare with previous",
                            on_click=lambda: ui.navigate.to(
                                f"/history/{report_id}/compare#report-comparison"
                            ),
                        ).props("flat no-caps").classes("dw-theme-button")
            render_report_detail_page(
                report,
                on_feedback_change=render_history_detail_content.refresh,
            )

    content_refresh["fn"] = lambda *_: render_history_detail_content.refresh()
    render_history_detail_content()
