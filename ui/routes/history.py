"""History route rendering."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from nicegui import ui

from services.backtesting_service import fetch_calibration_dashboard_seed
from services.project_service import ProjectResolutionError, list_workspaces
from services.report_service import (
    fetch_analysis_report,
    fetch_filtered_analysis_history_page,
    fetch_history_toolchains,
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
from ui.components.dashboard_shell import build_app_shell, workspace_content
from ui.project_authorization import resolve_authorized_ui_active_project
from ui.project_authorization import load_authorized_ui_projects
from ui.theme import build_page_header

_RISK_TREND_HISTORY_FILTERS = frozenset(
    {"workspace", "time_range", "severity", "toolchain", "outcome"}
)


def page_selection_state(
    visible_ids: set[int], selected_ids: set[int]
) -> tuple[bool, int]:
    """Return whether a page is fully selected and how many visible rows are selected."""
    if not visible_ids:
        return False, 0
    selected_on_page = len(visible_ids & selected_ids)
    return selected_on_page == len(visible_ids), selected_on_page


def resolve_history_active_project():
    """Return the effective active project allowed for the current UI actor."""
    _, active_project, _ = resolve_authorized_ui_active_project()
    return active_project


def resolve_history_project_context():
    """Return the effective project and any authorization setup error."""
    _, active_project, authorization_error = resolve_authorized_ui_active_project()
    if active_project is None and authorization_error is None:
        projects, authorization_error = load_authorized_ui_projects()
        if authorization_error is None and len(projects) == 1:
            active_project = projects[0]
    return active_project, authorization_error


def _empty_history_page() -> dict[str, Any]:
    return {"items": [], "total_count": 0}


def _empty_risk_trends() -> dict[str, Any]:
    return {
        "total_reports": 0,
        "filters": {},
        "window": {"start": None, "end": None},
        "severity_counts": {},
        "recommendation_counts": {},
        "high_critical_frequency": {"count": 0, "rate": 0.0},
        "tool_counts": {},
        "outcome_counts": {},
        "outcome_links": {
            "linked_outcome_count": 0,
            "failed_outcome_count": 0,
            "warned_failed_outcome_count": 0,
            "analysis_ids": [],
        },
        "false_positive_signals": {"count": 0, "event_count": 0, "rate": 0.0},
        "false_reassurance_signals": {
            "count": 0,
            "event_count": 0,
            "deployment_count": 0,
            "feedback_count": 0,
            "rate": 0.0,
        },
        "context_completeness": {
            "sample_size": 0,
            "missing_count": 0,
            "partial_context_count": 0,
            "partial_context_rate": 0.0,
            "average_context_score": None,
        },
        "limitations": [
            {
                "code": "no_authorized_project",
                "label": "No authorized project",
                "message": "Select an authorized project before reviewing risk trends.",
            }
        ],
        "audit_rows": [],
        "trend_windows": [],
        "trend_comparison": None,
        "trend_sample_size": 100,
    }


def _fetch_history_risk_trends(
    *,
    has_history_scope: bool,
    project_id: int | None,
    workspace_key: str | None = None,
    severity: str | None = None,
    toolchain: str | None = None,
    outcome: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> dict[str, Any]:
    if not has_history_scope:
        return _empty_risk_trends()
    return fetch_risk_trends(
        project_id=project_id,
        workspace_key=workspace_key,
        severity=severity,
        toolchain=toolchain,
        outcome=outcome,
        created_from=created_from,
        created_to=created_to,
    )


def _empty_calibration_dashboard_seed() -> dict[str, Any]:
    return {
        "project": None,
        "workspace": None,
        "window": {"start": None, "end": None, "days": 7},
        "failed_deploy_count": 0,
        "warned_failed_deploy_count": 0,
        "overall_precision": 0.0,
        "overall_recall": 0.0,
        "backtest_rows": [],
        "by_severity": {},
        "false_positive_cases": [],
        "false_reassurance_cases": [],
        "confidence_trends": {"buckets": {}, "sample_size": 0},
        "calibration_metrics": {
            "sample_size": 0,
            "feedback_event_count": 0,
            "feedback_history_event_count": 0,
            "precision": 0.0,
            "recall_proxy": 0.0,
            "false_positive_count": 0,
            "false_positive_rate": 0.0,
            "false_reassurance_count": 0,
            "false_reassurance_rate": 0.0,
            "deployment_false_reassurance_count": 0,
            "reviewer_missed_feedback_count": 0,
            "recall_proxy_signals": {
                "failed_deploy_count": 0,
                "warned_failed_deploy_count": 0,
                "failed_without_warning_count": 0,
                "missed_feedback_count": 0,
            },
        },
        "confidence_limitations": [
            {
                "code": "no_calibration_inputs",
                "label": "No calibration inputs",
                "message": "No deployment outcomes or feedback are linked yet.",
            }
        ],
        "confidence_label": "Directional only",
        "statistical_certainty": False,
    }


def _calibration_limitation_labels(calibration: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for limitation in calibration.get("confidence_limitations") or []:
        if isinstance(limitation, dict):
            label = str(limitation.get("label") or "").strip()
            if label:
                labels.append(label)
    return labels or ["Calibration evidence available"]


def _history_workspace_options(project_key: str | None) -> dict[str, str]:
    if project_key is None:
        return {"": "All workspaces"}
    try:
        workspaces = list_workspaces(project_key=project_key)
    except ProjectResolutionError:
        return {"": "All workspaces"}
    options = {"": "All workspaces"}
    options.update(
        {workspace.workspace_key: workspace.display_name for workspace in workspaces}
    )
    return options


def _history_time_bounds(value: str | None) -> tuple[datetime | None, datetime | None]:
    now = datetime.now(UTC)
    if value == "24h":
        return now - timedelta(hours=24), now
    if value == "7d":
        return now - timedelta(days=7), now
    if value == "30d":
        return now - timedelta(days=30), now
    if value == "90d":
        return now - timedelta(days=90), now
    return None, None


def _history_filter_updates_risk_trends(filter_name: str) -> bool:
    return filter_name in _RISK_TREND_HISTORY_FILTERS


def _history_toolchain_options(toolchains: list[str]) -> dict[str, str]:
    options = {"": "Any toolchain"}
    options.update({str(tool): str(tool).title() for tool in toolchains})
    return options


def build_history_page() -> None:
    """Render a scanable history view with direct report retrieval."""
    content_refresh = {"fn": lambda *_: None}

    def handle_project_change(*_) -> None:
        content_refresh["fn"]()

    build_app_shell("history", on_project_change=handle_project_change)

    @ui.refreshable
    def render_history_content() -> None:
        active_project, authorization_error = resolve_history_project_context()
        active_project_id = active_project.id if active_project is not None else None
        has_history_scope = authorization_error is None and active_project is not None
        reports_page = (
            _empty_history_page()
            if not has_history_scope
            else fetch_filtered_analysis_history_page(
                project_id=active_project_id,
                page=1,
                page_size=5,
                skip_unreadable_schema=True,
            )
        )
        reports = reports_page["items"]
        total_report_count = reports_page["total_count"]
        trends = _fetch_history_risk_trends(
            has_history_scope=has_history_scope,
            project_id=active_project_id,
        )
        calibration = (
            _empty_calibration_dashboard_seed()
            if not has_history_scope
            else fetch_calibration_dashboard_seed(project_id=active_project_id)
        )
        history_toolchains = (
            []
            if not has_history_scope
            else fetch_history_toolchains(
                project_id=active_project_id,
                skip_unreadable_schema=True,
            )
        )
        selected_ids: set[int] = set()
        page_state = {"page": 1, "page_size": 5}
        card_checkboxes: dict[int, Any] = {}
        selection_sync = {"active": False}

        with workspace_content(aria_label="Analysis history workspace"):
            with ui.card().classes("w-full dw-panel dw-page-header shadow-none"):
                build_page_header(
                    eyebrow="History",
                    title="Analysis history",
                    subtitle=(
                        authorization_error
                        if authorization_error is not None
                        else "Select a project to review historical reports."
                        if active_project is None
                        else (
                            "Project-scoped history for "
                            f"{active_project.display_name} "
                            f"({active_project.project_key})."
                        )
                    ),
                    back_href="/",
                    back_label="Back to dashboard",
                )
            risk_trends_card = ui.card().classes("w-full dw-panel shadow-none p-4")
            calibration_card = ui.card().classes("w-full dw-panel shadow-none p-4")

            def render_risk_trends_summary() -> None:
                risk_trends_card.clear()

                def count_delta(value: Any) -> str:
                    return f"{int(value or 0):+d}"

                def top_count_deltas(values: dict[str, Any], labels: list[str]) -> str:
                    parts = [
                        f"{label} {count_delta(values.get(label))}"
                        for label in labels
                        if int(values.get(label) or 0) != 0
                    ]
                    return ", ".join(parts) or "no change"

                def top_dynamic_deltas(values: dict[str, Any]) -> str:
                    changed = [
                        (str(label), int(delta or 0))
                        for label, delta in values.items()
                        if int(delta or 0) != 0
                    ]
                    changed.sort(key=lambda item: abs(item[1]), reverse=True)
                    return (
                        ", ".join(f"{label} {delta:+d}" for label, delta in changed[:3])
                        or "no change"
                    )

                with risk_trends_card, ui.column().classes("gap-0"):
                    ui.label("Risk trends").classes("dw-eyebrow mb-1")
                    ui.label(
                        f"{trends['total_reports']} reports · "
                        f"{trends['severity_counts'].get('critical', 0)} critical · "
                        f"{trends['severity_counts'].get('high', 0)} high"
                    ).classes("text-lg font-medium dw-text leading-6")
                    false_positive = trends.get("false_positive_signals", {})
                    false_reassurance = trends.get("false_reassurance_signals", {})
                    outcome_links = trends.get("outcome_links", {})
                    context = trends.get("context_completeness", {})
                    average_context = context.get("average_context_score")
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
                    outcome_counts = trends.get("outcome_counts", {})
                    ui.label(
                        "Outcomes: "
                        + (
                            ", ".join(
                                f"{outcome} ({count})"
                                for outcome, count in sorted(
                                    outcome_counts.items(),
                                    key=lambda item: item[1],
                                    reverse=True,
                                )[:3]
                            )
                            or "none linked"
                        )
                    ).classes("mt-[2px] text-sm dw-muted")
                    ui.label(
                        "Calibration signals: "
                        f"{int(false_positive.get('count') or 0)} false-positive · "
                        f"{int(false_reassurance.get('count') or 0)} false-reassurance · "
                        f"{int(outcome_links.get('linked_outcome_count') or 0)} linked outcomes"
                    ).classes("mt-[2px] text-sm dw-muted")
                    ui.label(
                        "Context completeness: "
                        f"{int(context.get('partial_context_count') or 0)} partial · "
                        + (
                            f"average {float(average_context):.2f}"
                            if average_context is not None
                            else "average unavailable"
                        )
                    ).classes("mt-[2px] text-sm dw-muted")
                    comparison = trends.get("trend_comparison") or {}
                    if comparison:
                        ui.label(
                            "Window change: "
                            f"{int(comparison.get('total_reports_delta') or 0):+d} reports · "
                            f"{int(comparison.get('high_critical_count_delta') or 0):+d} high/critical · "
                            f"{int(comparison.get('false_positive_count_delta') or 0):+d} false-positive · "
                            f"{int(comparison.get('false_reassurance_count_delta') or 0):+d} false-reassurance · "
                            f"{int(comparison.get('linked_outcome_count_delta') or 0):+d} linked outcomes"
                        ).classes("mt-[2px] text-sm dw-muted")
                        ui.label(
                            "Verdict change: "
                            + top_count_deltas(
                                comparison.get("severity_count_deltas") or {},
                                ["critical", "high", "medium", "low"],
                            )
                        ).classes("mt-[2px] text-sm dw-muted")
                        ui.label(
                            "Recommendation change: "
                            + top_count_deltas(
                                comparison.get("recommendation_count_deltas") or {},
                                ["no-go", "caution", "go"],
                            )
                        ).classes("mt-[2px] text-sm dw-muted")
                        ui.label(
                            "Outcome change: "
                            + top_dynamic_deltas(
                                comparison.get("outcome_count_deltas") or {}
                            )
                        ).classes("mt-[2px] text-sm dw-muted")
                        ui.label(
                            "Toolchain change: "
                            + top_dynamic_deltas(
                                comparison.get("tool_count_deltas") or {}
                            )
                        ).classes("mt-[2px] text-sm dw-muted")
                        context_score_delta = comparison.get(
                            "context_average_score_delta"
                        )
                        ui.label(
                            "Context change: "
                            f"{count_delta(comparison.get('context_partial_count_delta'))} partial · "
                            + (
                                f"average {float(context_score_delta):+.2f}"
                                if context_score_delta is not None
                                else "average unavailable"
                            )
                        ).classes("mt-[2px] text-sm dw-muted")
                    limitation_labels = [
                        str(item.get("label"))
                        for item in trends.get("limitations", [])
                        if isinstance(item, dict) and item.get("label")
                    ]
                    if limitation_labels:
                        ui.label(
                            "Limitations: " + " · ".join(limitation_labels)
                        ).classes("mt-[2px] text-sm dw-muted")

            def render_calibration_summary() -> None:
                calibration_card.clear()
                with calibration_card, ui.column().classes("gap-0"):
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
                    limitation_label = " · ".join(
                        _calibration_limitation_labels(calibration)
                    )
                    ui.label(
                        f"{calibration.get('confidence_label', 'Directional only')} · "
                        f"{limitation_label}"
                    ).classes("mt-[2px] text-sm dw-muted")

            def render_summaries() -> None:
                render_risk_trends_summary()
                render_calibration_summary()

            render_summaries()
            search_input = (
                ui.input(placeholder="Search top risk or summary")
                .props("outlined dense clearable prepend-icon=search")
                .classes("w-full dw-search-input")
            )
            with ui.card().classes("w-full dw-panel shadow-none p-4"):
                with ui.column().classes("gap-3"):
                    with ui.row().classes("dw-history-filter-row"):
                        with ui.column().classes(
                            "dw-history-project-filter-field min-w-[220px] flex-1 gap-1"
                        ):
                            ui.label("Project filter").classes("dw-eyebrow")
                            ui.label(
                                "Select a project"
                                if active_project is None
                                else (
                                    f"{active_project.display_name} "
                                    f"({active_project.project_key})"
                                )
                            ).classes("text-sm font-medium dw-text leading-5 truncate")
                        workspace_select = (
                            ui.select(
                                _history_workspace_options(
                                    active_project.project_key
                                    if active_project is not None
                                    else None
                                ),
                                value="",
                                label="Workspace",
                            )
                            .props("outlined dense")
                            .classes("dw-history-filter-control min-w-[170px] flex-1")
                        )
                        time_range_select = (
                            ui.select(
                                {
                                    "": "Any time",
                                    "24h": "Last 24 hours",
                                    "7d": "Last 7 days",
                                    "30d": "Last 30 days",
                                    "90d": "Last 90 days",
                                },
                                value="",
                                label="Time range",
                            )
                            .props("outlined dense")
                            .classes("dw-history-filter-control min-w-[170px] flex-1")
                        )
                        severity_select = (
                            ui.select(
                                {
                                    "": "Any risk",
                                    "critical": "Critical",
                                    "high": "High",
                                    "medium": "Medium",
                                    "low": "Low",
                                },
                                value="",
                                label="Risk verdict",
                            )
                            .props("outlined dense")
                            .classes("dw-history-filter-control min-w-[170px] flex-1")
                        )
                    with ui.row().classes("dw-history-filter-row"):
                        toolchain_select = (
                            ui.select(
                                _history_toolchain_options(history_toolchains),
                                value="",
                                label="Toolchain",
                            )
                            .props("outlined dense")
                            .classes("dw-history-filter-control min-w-[170px] flex-1")
                        )
                        status_select = (
                            ui.select(
                                {
                                    "": "Any status",
                                    "complete": "Complete",
                                    "degraded": "Degraded",
                                    "fallback": "Fallback",
                                },
                                value="",
                                label="Analysis status",
                            )
                            .props("outlined dense")
                            .classes("dw-history-filter-control min-w-[170px] flex-1")
                        )
                        outcome_select = (
                            ui.select(
                                {
                                    "": "Any outcome",
                                    "success": "Success",
                                    "failure": "Failure",
                                    "rolled_back": "Rolled back",
                                },
                                value="",
                                label="Outcome",
                            )
                            .props("outlined dense")
                            .classes("dw-history-filter-control min-w-[170px] flex-1")
                        )
            actions_row = ui.row().classes(
                "w-full items-center justify-between gap-4 flex-wrap"
            )
            history_column = ui.column().classes("w-full gap-3")

            def refresh_data(
                query: str | None = None,
                *,
                refresh_trends: bool = True,
            ) -> list[dict]:
                nonlocal reports, trends, total_report_count, calibration
                created_from, created_to = _history_time_bounds(
                    str(time_range_select.value or "")
                )
                page_payload = (
                    _empty_history_page()
                    if not has_history_scope
                    else fetch_filtered_analysis_history_page(
                        project_id=active_project_id,
                        workspace_key=str(workspace_select.value or "") or None,
                        severity=str(severity_select.value or "") or None,
                        search=query,
                        toolchain=str(toolchain_select.value or "") or None,
                        outcome=str(outcome_select.value or "") or None,
                        analysis_status=str(status_select.value or "") or None,
                        created_from=created_from,
                        created_to=created_to,
                        page=page_state["page"],
                        page_size=page_state["page_size"],
                        skip_unreadable_schema=True,
                    )
                )
                reports = page_payload["items"]
                total_report_count = page_payload["total_count"]
                if refresh_trends:
                    trends = _fetch_history_risk_trends(
                        has_history_scope=has_history_scope,
                        project_id=active_project_id,
                        workspace_key=current_workspace_key(),
                        severity=str(severity_select.value or "") or None,
                        toolchain=str(toolchain_select.value or "") or None,
                        outcome=str(outcome_select.value or "") or None,
                        created_from=created_from,
                        created_to=created_to,
                    )
                    calibration = (
                        _empty_calibration_dashboard_seed()
                        if not has_history_scope
                        else fetch_calibration_dashboard_seed(
                            project_id=active_project_id,
                            workspace_key=current_workspace_key(),
                        )
                    )
                max_page = max(
                    1, (total_report_count - 1) // page_state["page_size"] + 1
                )
                page_state["page"] = min(page_state["page"], max_page)
                return reports

            def current_workspace_key() -> str | None:
                return str(workspace_select.value or "") or None

            def sync_toolchain_options() -> None:
                selected_toolchain = str(toolchain_select.value or "")
                scoped_toolchains = (
                    []
                    if not has_history_scope
                    else fetch_history_toolchains(
                        project_id=active_project_id,
                        workspace_key=current_workspace_key(),
                        skip_unreadable_schema=True,
                    )
                )
                options = _history_toolchain_options(scoped_toolchains)
                toolchain_select.set_options(options)
                if selected_toolchain and selected_toolchain not in options:
                    toolchain_select.value = ""
                toolchain_select.update()

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
                refresh_data(
                    search_input.value.strip() if search_input.value else None,
                    refresh_trends=False,
                )
                render_history()
                render_actions()

            def apply_filters(*, refresh_trends: bool = True) -> None:
                query = search_input.value.strip() if search_input.value else None
                page_state["page"] = 1
                selected_ids.clear()
                refresh_data(query, refresh_trends=refresh_trends)
                if refresh_trends:
                    render_summaries()
                render_history()
                render_actions()

            def sync_select_value(select, event) -> None:
                if hasattr(event, "value"):
                    select.value = event.value

            def apply_select_filter(select, event, *, filter_name: str) -> None:
                sync_select_value(select, event)
                apply_filters(
                    refresh_trends=_history_filter_updates_risk_trends(filter_name)
                )

            def apply_workspace_filter(event) -> None:
                sync_select_value(workspace_select, event)
                sync_toolchain_options()
                apply_filters(
                    refresh_trends=_history_filter_updates_risk_trends("workspace")
                )

            search_input.on(
                "update:model-value",
                lambda *_: apply_filters(
                    refresh_trends=_history_filter_updates_risk_trends("search")
                ),
            )
            workspace_select.on_value_change(apply_workspace_filter)
            time_range_select.on_value_change(
                lambda event: apply_select_filter(
                    time_range_select,
                    event,
                    filter_name="time_range",
                )
            )
            severity_select.on_value_change(
                lambda event: apply_select_filter(
                    severity_select,
                    event,
                    filter_name="severity",
                )
            )
            toolchain_select.on_value_change(
                lambda event: apply_select_filter(
                    toolchain_select,
                    event,
                    filter_name="toolchain",
                )
            )
            status_select.on_value_change(
                lambda event: apply_select_filter(
                    status_select,
                    event,
                    filter_name="analysis_status",
                )
            )
            outcome_select.on_value_change(
                lambda event: apply_select_filter(
                    outcome_select,
                    event,
                    filter_name="outcome",
                )
            )
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
                    "Side-by-side changes against the previous comparable report in the same project, workspace, and workflow context."
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
        for warning in comparison.get("summary", {}).get("warnings") or []:
            ui.label(f"Comparison warning: {warning}").classes(
                "text-sm dw-warning-text leading-6"
            )
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
                        "Resolved findings",
                        comparison["findings"]["removed"],
                        empty_message="No resolved findings were found.",
                    )
                    _render_history_comparison_items(
                        "Evidence resolved",
                        comparison["evidence"]["removed"],
                        empty_message="No evidence was resolved.",
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
                        "New findings",
                        comparison["findings"]["added"],
                        empty_message="No new findings were found.",
                    )
                    _render_history_comparison_items(
                        "Evidence added",
                        comparison["evidence"]["added"],
                        empty_message="No evidence was added.",
                    )
        with ui.card().classes("w-full dw-panel-soft shadow-none mt-4"):
            with ui.column().classes("gap-3 p-4"):
                _render_history_comparison_items(
                    "Persistent findings",
                    comparison["findings"]["persistent"],
                    empty_message="No findings persisted across both reports.",
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
        with ui.card().classes("w-full dw-panel-soft shadow-none mt-4"):
            with ui.column().classes("gap-3 p-4"):
                _render_history_comparison_items(
                    "Changed context",
                    comparison["findings"]["context_changed"],
                    empty_message="No persistent findings changed evidence or context.",
                )


def build_history_detail_page(report_id: int, *, show_comparison: bool = False) -> None:
    """Render one persisted report on a dedicated detail page."""
    content_refresh = {"fn": lambda *_: None}

    def handle_project_change(*_) -> None:
        content_refresh["fn"]()

    build_app_shell("history", on_project_change=handle_project_change)

    @ui.refreshable
    def render_history_detail_content() -> None:
        active_project, authorization_error = resolve_history_project_context()
        active_project_id = active_project.id if active_project is not None else None
        report = (
            None
            if authorization_error is not None
            else fetch_analysis_report(report_id, project_id=active_project_id)
        )
        comparison = (
            None
            if authorization_error is not None or not show_comparison
            else fetch_report_comparison(report_id, project_id=active_project_id)
        )
        main_label = (
            "Analysis report unavailable"
            if report is None
            else "Analysis report workspace"
        )

        with workspace_content(aria_label=main_label):
            with ui.card().classes("w-full dw-panel dw-page-header shadow-none"):
                if report is None:
                    build_page_header(
                        eyebrow="History",
                        title=(
                            "Project authorization unavailable"
                            if authorization_error is not None
                            else "Analysis report not found"
                        ),
                        subtitle=authorization_error
                        or "The requested report could not be loaded. It may have been deleted.",
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
                        authorization_error
                        or "This report is unavailable. Return to history and choose another saved analysis."
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
