"""Upload panel component."""

from __future__ import annotations

from collections.abc import Callable
from math import ceil

from nicegui import events, run, ui

from analysis.blast_radius import compute_blast_radius
from analysis.incident_matcher import find_incident_matches
from analysis.rollback_planner import generate_rollback_plan
from llm.narrator import generate_narrative
from parsers.base import ParseBatchResult, UnifiedChange
from parsers.registry import detect_tool_type
from services.analysis_service import evaluate_parse_batch
from services.intake_service import build_parse_batch, build_pending_analysis, is_sensitive_file
from services.report_service import fetch_active_dashboard_report, persist_analysis_report
from services.topology_service import load_topology
from ui.formatters.recommendations import render_recommendation_label
from ui.formatters.risk_labels import render_risk_badge


STATUS_STYLES = {
    "ready": "color: #53c26b;",
    "unsupported": "color: #d8a432;",
    "sensitive": "color: #cf3f3f;",
}


def process_uploaded_files(
    current_files: dict[str, bytes],
    uploads: list[tuple[str, bytes]],
):
    """Merge uploaded files into state and return the pending-analysis summary."""
    for name, raw_content in uploads:
        current_files[name] = raw_content
    return build_pending_analysis(current_files.items())


def _collect_changes(parse_batch: ParseBatchResult) -> list[UnifiedChange]:
    changes: list[UnifiedChange] = []
    for file_result in parse_batch.files:
        if file_result.status == "parsed":
            changes.extend(file_result.changes)
    return changes


def _accepted_files(files: dict[str, bytes]) -> list[tuple[str, bytes]]:
    accepted: list[tuple[str, bytes]] = []
    for name, raw_content in files.items():
        if is_sensitive_file(name):
            continue
        if detect_tool_type(name, raw_content) == "unsupported":
            continue
        accepted.append((name, raw_content))
    return accepted


def _format_countdown_label(seconds: int) -> str:
    minutes, remainder = divmod(max(seconds, 0), 60)
    return f"Disappears in {minutes}m {remainder}s"


def build_upload_panel(on_analysis_complete: Callable[[], None] | None = None) -> None:
    """Render the upload intake component for pending analyses."""
    state: dict[str, object] = {
        "files": {},
        "summary": build_pending_analysis([]),
        "is_running": False,
        "progress_value": 0,
        "progress_message": "Waiting to analyze",
        "result_token": 0,
        "active_result": None,
    }

    with ui.column().classes("w-full gap-4"):
        upload_card = ui.card().classes("w-full dw-panel shadow-none")
        result_mount = ui.column().classes("w-full gap-4 mt-4")

    with upload_card:
        ui.label("Upload deployment artifacts").classes("text-lg font-medium text-[#1D2420]")
        ui.label(
            "Drop Terraform (.tf/.tfvars/.hcl), Kubernetes YAML, Ansible YAML, Jenkinsfile, or CloudFormation YAML/JSON "
            "artifacts. DeployWhisper now recognizes CloudFormation by template signatures such as Resources, "
            "Parameters, Outputs, AWSTemplateFormatVersion, and intrinsic references."
        ).classes("text-sm dw-muted")

        summary_row = ui.row().classes("w-full items-center gap-2 text-sm dw-muted")
        detail_column = ui.column().classes("w-full gap-2")
        upload_error = ui.label("").classes("text-xs text-[#D8A432]")
        action_column = ui.column().classes("w-full gap-2")

    progress_bar = None
    progress_label = None

    def clear_result_if_current(token: int) -> None:
        if token != state["result_token"]:
            return
        state["active_result"] = None
        result_mount.clear()

    def render_result_card(report: dict, *, remaining_seconds: int | None = None) -> None:
        token = int(state["result_token"]) + 1
        state["result_token"] = token
        state["active_result"] = report
        result_mount.clear()
        result_card = ui.card().classes("w-full dw-panel shadow-none p-5")
        countdown_label = ui.label("").classes("text-xs dw-muted")
        timer_state = {"remaining": max(int(remaining_seconds or report.get("dashboard_remaining_seconds") or report.get("dashboard_display_duration_seconds") or 0), 0)}

        def update_countdown() -> None:
            if token != state["result_token"]:
                return
            if timer_state["remaining"] <= 0:
                clear_result_if_current(token)
                return
            countdown_label.set_text(_format_countdown_label(timer_state["remaining"]))
            timer_state["remaining"] -= 1

        with result_mount:
            with result_card:
                with ui.row().classes("w-full items-start justify-between gap-4 flex-wrap"):
                    with ui.row().classes("items-center gap-3 flex-wrap"):
                        render_risk_badge(report["severity"])
                        render_recommendation_label(report["recommendation"], size="base")
                    countdown_label
                ui.label(report["top_risk"]).classes("text-lg font-medium text-[#1D2420] leading-6")
                ui.label(report["narrative_opening"]).classes("text-sm dw-muted leading-6")
                ui.label(report["parse_summary"]).classes("text-xs dw-muted")
                contributors = report.get("contributors", [])
                if contributors:
                    with ui.column().classes("mt-3 gap-2"):
                        ui.label("Resource severity breakdown").classes("text-sm font-semibold text-[#1D2420]")
                        for contributor in contributors[:5]:
                            with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
                                with ui.column().classes("min-w-0 flex-1 gap-1"):
                                    ui.label(contributor["resource_id"]).classes("text-sm font-medium text-[#1D2420]")
                                    ui.label(contributor["reasoning"]).classes("text-xs dw-muted leading-5")
                                render_risk_badge(contributor["severity"])
            ui.timer(1.0, update_countdown)
        update_countdown()

    def render_actions() -> None:
        nonlocal progress_bar, progress_label
        action_column.clear()
        summary = state["summary"]
        with action_column:
            if state["is_running"]:
                with ui.row().classes("items-center gap-3"):
                    ui.spinner(size="sm", color="primary")
                    progress_label = ui.label(
                        f"{int(state['progress_value'])}% · {state['progress_message']}"
                    ).classes("text-sm text-[#1D2420]")
                progress_bar = ui.linear_progress(value=float(state["progress_value"]) / 100).classes("w-full")
                ui.label("Uploads are disabled while analysis is running.").classes("text-xs dw-muted")
                return

            progress_bar = None
            progress_label = None
            analyze_button = ui.button("Analyze", on_click=run_analysis, color="primary").props("unelevated")
            if summary.ready_count == 0:
                analyze_button.disable()

    def update_progress(value: int, message: str) -> None:
        state["progress_value"] = value
        state["progress_message"] = message
        if progress_label is not None:
            progress_label.set_text(f"{value}% · {message}")
        if progress_bar is not None:
            progress_bar.set_value(value / 100)

    def render_summary() -> None:
        summary_row.clear()
        detail_column.clear()
        upload_error.set_text("")
        summary = state["summary"]
        ready_count = summary.ready_count
        total_count = len(summary.items)
        with summary_row:
            ui.label(f"{total_count} files").classes("text-sm text-[#1D2420]")
            ui.label("·").classes("text-sm dw-muted")
            ui.label(f"{ready_count} accepted").classes("text-sm dw-muted")

        for item in summary.items:
            with detail_column:
                with ui.row().classes("w-full items-center justify-between dw-panel-soft px-3 py-2"):
                    ui.label(item.name).classes("text-sm text-[#1D2420]")
                    with ui.row().classes("items-center gap-3"):
                        ui.label(item.tool).classes("text-xs uppercase dw-muted")
                        ui.label(item.status).style(STATUS_STYLES[item.status]).classes("text-xs font-medium uppercase")
                ui.label(item.message).classes("text-xs dw-muted")

        render_actions()

    async def run_analysis() -> None:
        summary = state["summary"]
        if state["is_running"] or summary.ready_count == 0:
            return

        files = _accepted_files(state["files"])
        if not files:
            ui.notify("No supported artifacts are ready for analysis.", color="warning")
            return

        state["is_running"] = True
        upload_widget.disable()
        render_actions()
        update_progress(5, "Preparing analysis")

        try:
            raw_files = dict(state["files"])
            parse_batch = await run.io_bound(build_parse_batch, list(raw_files.items()))
            update_progress(
                30,
                f"Parsed {parse_batch.parsed_count} file(s), {parse_batch.failed_count} failed, {parse_batch.skipped_count} skipped",
            )

            changes = _collect_changes(parse_batch)
            topology, topology_warning = await run.io_bound(load_topology)
            assessment = await run.io_bound(
                evaluate_parse_batch,
                parse_batch,
                topology=topology,
                raw_files=raw_files,
            )
            update_progress(45, "Scored deployment risk with enriched context")
            await run.io_bound(compute_blast_radius, changes, topology, topology_warning)
            update_progress(60, "Computed blast radius")
            await run.io_bound(generate_rollback_plan, changes, parse_batch.has_partial_context)
            update_progress(72, "Generated rollback guidance")
            await run.io_bound(find_incident_matches, changes)
            update_progress(84, "Checked similar incidents")
            narrative = await run.io_bound(generate_narrative, assessment)
            update_progress(96, "Generated advisory narrative")

            persisted_report = await run.io_bound(
                persist_analysis_report,
                parse_batch,
                assessment,
                narrative,
                {"source_interface": "ui", "trigger_type": "dashboard_upload"},
            )
            update_progress(100, "Saved analysis report")

            render_result_card(
                persisted_report,
                remaining_seconds=persisted_report.get("dashboard_display_duration_seconds"),
            )
            state["files"] = {}
            state["summary"] = build_pending_analysis([])
            upload_widget.reset()
            render_summary()
            if parse_batch.has_partial_context:
                ui.notify(
                    f"Analysis completed with partial context: {parse_batch.failed_count} file(s) failed to parse.",
                    color="warning",
                )
            else:
                ui.notify(
                    f"Analysis completed for {parse_batch.parsed_count} file(s).",
                    color="positive",
                )
            if on_analysis_complete:
                on_analysis_complete()
        except Exception as exc:  # noqa: BLE001
            result_mount.clear()
            with result_mount:
                with ui.card().classes("w-full dw-panel shadow-none p-5"):
                    ui.label("Analysis failed").classes("text-base font-semibold text-[#C24141]")
                    ui.label(str(exc)).classes("text-sm dw-muted")
            ui.notify("Analysis failed. Review the dashboard error card for details.", color="negative")
        finally:
            state["is_running"] = False
            upload_widget.enable()
            render_actions()

    async def handle_multi_upload(event: events.MultiUploadEventArguments) -> None:
        if state["is_running"]:
            upload_error.set_text("Wait for the current analysis to finish before uploading more artifacts.")
            return
        uploads = [(uploaded_file.name, await uploaded_file.read()) for uploaded_file in event.files]
        state["summary"] = process_uploaded_files(state["files"], uploads)
        render_summary()

    def handle_rejected(_: events.UiEventArguments) -> None:
        upload_error.set_text("One or more files were rejected by the uploader. Check file type or size.")

    with upload_card:
        upload_widget = ui.upload(
            on_multi_upload=handle_multi_upload,
            on_rejected=handle_rejected,
            auto_upload=True,
            multiple=True,
            label="Select deployment artifacts",
            max_file_size=50_000_000,
        ).props("accept=.json,.yaml,.yml,.tf,.tfvars,.hcl,Jenkinsfile").classes(
            "w-full"
        )

    active_report = fetch_active_dashboard_report()
    if active_report is not None:
        render_result_card(active_report, remaining_seconds=active_report["dashboard_remaining_seconds"])
    render_summary()
