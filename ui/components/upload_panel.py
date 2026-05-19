"""Upload panel component."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import events, run, ui

from analysis.blast_radius import BlastRadiusResult
from analysis.rollback_planner import RollbackPlan
from parsers.registry import detect_tool_type
from services.analysis_service import AnalysisPersistenceError, analyze_uploaded_files
from services.intake_service import (
    MAX_TOTAL_UPLOAD_BYTES,
    build_pending_analysis,
    is_sensitive_file,
    total_upload_bytes,
    uniquify_artifact_names,
)
from services.project_service import (
    get_active_project,
    has_active_project_selection,
)
from services.report_service import (
    fetch_active_dashboard_report,
)
from ui.components.context_completeness_panel import (
    render_context_completeness_panel,
)
from ui.components.project_workspace_switcher import (
    build_project_options,
    open_create_project_dialog as show_create_project_dialog,
)
from ui.components.blast_radius_graph import render_blast_radius_panel
from ui.components.change_table import (
    format_change_metadata_lines,
    render_change_table,
)
from ui.components.report_detail_page import (
    format_submission_manifest_fallback_summary,
    format_submission_manifest_partial_notice,
    format_submission_manifest_summary,
    render_reviewer_feedback_panel,
)
from ui.components.rollback_plan import render_rollback_plan
from ui.components.review_accessibility import (
    decorate_modal_card,
    decorate_modal_close,
)
from ui.project_authorization import (
    load_authorized_ui_projects,
    resolve_authorized_active_project_selection,
    set_authorized_ui_project,
)
from ui.components.topology_freshness_banner import render_topology_freshness_banner
from services.settings_service import check_provider_readiness
from ui.components.findings_table import render_findings_table
from ui.formatters.confidence import coerce_confidence, render_confidence_badge
from ui.formatters.narrative import (
    extract_llm_notice,
    extract_submission_manifest_notice,
)
from ui.formatters.recommendations import render_recommendation_label
from ui.formatters.risk_labels import render_risk_badge


STATUS_STYLES = {
    "ready": "color: #53c26b;",
    "unsupported": "color: #d8a432;",
    "sensitive": "color: #cf3f3f;",
}


def process_uploaded_files(
    current_files: list[tuple[str, bytes]],
    uploads: list[tuple[str, bytes]],
):
    """Merge uploaded files into state and return the pending-analysis summary."""
    normalized_uploads = uniquify_artifact_names(
        uploads,
        existing_names=[name for name, _ in current_files],
    )
    current_files.extend(
        (name, raw_content) for name, raw_content in normalized_uploads
    )
    return build_pending_analysis(current_files)


def _accepted_files(files: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    accepted: list[tuple[str, bytes]] = []
    for name, raw_content in files:
        if is_sensitive_file(name):
            continue
        if detect_tool_type(name, raw_content) == "unsupported":
            continue
        accepted.append((name, raw_content))
    return accepted


def _format_countdown_label(seconds: int) -> str:
    minutes, remainder = divmod(max(seconds, 0), 60)
    return f"Disappears in {minutes}m {remainder}s"


def run_uploaded_analysis(
    files: list[tuple[str, bytes]],
    *,
    project_key: str | None = None,
    completion_client=None,
):
    """Run the shared upload analysis pipeline with the dashboard audit context."""
    return analyze_uploaded_files(
        files,
        completion_client=completion_client,
        project_key=project_key,
        audit_context={
            "source_interface": "ui",
            "trigger_type": "dashboard_upload",
            "actor": "ui_local_user",
        },
    )


def format_analysis_failure(exc: Exception) -> tuple[str, str, str]:
    if isinstance(exc, AnalysisPersistenceError):
        return (
            "Report persistence failed",
            exc.public_reason,
            "Analysis completed, but the report was not saved. Retry the analysis; if it repeats, review local application logs and persistence configuration.",
        )
    return (
        "Analysis failed",
        str(exc),
        "Analysis failed. Review the dashboard error card for details.",
    )


def persisted_report_reference(report: dict[str, Any]) -> tuple[str, str] | None:
    report_id = report.get("id") or (report.get("audit", {}).get("delivery") or {}).get(
        "report_id"
    )
    if report_id is None:
        return None
    try:
        normalized_report_id = int(report_id)
    except (TypeError, ValueError):
        return None
    return f"Saved report #{normalized_report_id}", f"/reports/{normalized_report_id}"


def resolve_initial_project_selection(*, has_saved_selection: bool, active_project):
    """Return the upload-panel project selection state."""
    if not has_saved_selection or active_project is None:
        return None, None
    return active_project.id, active_project.project_key


def uploads_allowed(active_project_key: str | None) -> bool:
    """Return whether manual uploads should be enabled."""
    return bool(active_project_key)


def should_clear_pending_uploads(
    *,
    current_file_count: int,
    previous_project_id: int | None,
    next_project_id: int | None,
) -> bool:
    """Return whether a project switch should clear staged uploads."""
    return (
        current_file_count > 0
        and previous_project_id is not None
        and next_project_id is not None
        and previous_project_id != next_project_id
    )


def build_feedback_rerender_handler(
    render_result_card: Callable[..., None],
    *,
    report: dict[str, Any],
    parse_batch: object,
    timer_state: dict[str, int],
) -> Callable[[], None]:
    """Return a feedback callback that preserves parse metadata on rerender."""

    def rerender() -> None:
        render_result_card(
            report,
            remaining_seconds=timer_state["remaining"],
            parse_batch=parse_batch,
        )

    return rerender


def build_upload_panel(
    on_analysis_complete: Callable[[], None] | None = None,
    *,
    on_project_change: Callable[[object], None] | None = None,
    embedded: bool = False,
    result_container=None,
) -> None:
    """Render the upload intake component for pending analyses."""
    saved_selection = has_active_project_selection()
    projects, project_authorization_error = load_authorized_ui_projects()
    active_project = get_active_project()
    saved_selection, active_project = resolve_authorized_active_project_selection(
        has_saved_selection=saved_selection,
        active_project=active_project,
        projects=projects,
        authorization_error=project_authorization_error,
    )
    initial_project_id, initial_project_key = resolve_initial_project_selection(
        has_saved_selection=saved_selection,
        active_project=active_project,
    )
    state: dict[str, object] = {
        "files": [],
        "summary": build_pending_analysis([]),
        "is_running": False,
        "progress_value": 0,
        "progress_message": "Waiting to analyze",
        "result_token": 0,
        "active_result": None,
        "projects": projects,
        "active_project_id": initial_project_id,
        "active_project_key": initial_project_key,
        "project_authorization_error": project_authorization_error,
    }

    card_classes = "w-full shadow-none"
    if embedded:
        card_classes += " bg-transparent p-0"
    else:
        card_classes += " dw-panel"
    with ui.column().classes("w-full gap-4"):
        upload_card = ui.card().classes(card_classes)
        if result_container is None:
            result_mount = ui.column().classes("w-full gap-4 mt-4")
        else:
            result_mount = result_container
        scheduler_mount = ui.column().classes("hidden")

    with upload_card:
        heading_spacing = "text-lg font-medium dw-text"
        body_spacing = "text-sm dw-muted"
        if embedded:
            heading_spacing += " mt-2"
            body_spacing += " mt-1"
        ui.label("Upload deployment artifacts").classes(heading_spacing)
        ui.label(
            "Drop Terraform (.tf/.tfvars/.hcl), Kubernetes YAML, Ansible YAML, Jenkinsfile, or CloudFormation YAML/JSON "
            "artifacts. DeployWhisper now recognizes CloudFormation by template signatures such as Resources, "
            "Parameters, Outputs, AWSTemplateFormatVersion, and intrinsic references."
        ).classes(body_spacing)
        project_controls = ui.row().classes("w-full items-end gap-3 flex-wrap")

        summary_row = ui.row().classes("w-full items-center gap-2 text-sm dw-muted")
        detail_column = ui.column().classes("w-full gap-2")
        upload_error = ui.label("").classes("text-xs dw-warning-text")
        action_column = ui.column().classes("w-full gap-2")

    progress_bar = None
    progress_label = None
    project_select = None

    def _project_options() -> dict[int, str]:
        return build_project_options(state["projects"])

    def refresh_saved_report() -> None:
        active_project_id = state["active_project_id"]
        if active_project_id is None:
            result_mount.clear()
            return
        active_report = fetch_active_dashboard_report(project_id=active_project_id)
        result_mount.clear()
        if active_report is not None:
            render_result_card(
                active_report,
                remaining_seconds=active_report["dashboard_remaining_seconds"],
            )

    def sync_upload_widget_state() -> None:
        if upload_widget is None:
            return
        if uploads_allowed(state["active_project_key"]):
            upload_widget.enable()
        else:
            upload_widget.disable()

    def refresh_projects(
        *,
        selected_project_id: int | None = None,
        notify_parent: bool = False,
    ) -> None:
        state["projects"], state["project_authorization_error"] = (
            load_authorized_ui_projects()
        )
        selected_project = None
        if selected_project_id is not None:
            try:
                selected_project = set_authorized_ui_project(
                    selected_project_id,
                    state["projects"],
                )
            except PermissionError as exc:
                state["active_project_id"] = None
                state["active_project_key"] = None
                upload_error.set_text(str(exc))
                if project_select is not None:
                    project_select.set_options(_project_options())
                    project_select.value = None
                    project_select.update()
                sync_upload_widget_state()
                refresh_saved_report()
                return
            state["active_project_id"] = selected_project.id
            state["active_project_key"] = selected_project.project_key
        if project_select is not None:
            project_select.set_options(_project_options())
            project_select.value = state["active_project_id"]
            project_select.update()
        sync_upload_widget_state()
        refresh_saved_report()
        if selected_project is not None and on_project_change is not None:
            on_project_change(selected_project)
        if notify_parent and on_analysis_complete:
            on_analysis_complete()

    with project_controls:
        project_select = ui.select(
            options=_project_options(),
            value=state["active_project_id"],
            label="Project workspace",
        ).classes("min-w-[280px] flex-1")

        def handle_project_change(event) -> None:
            selected_id = int(event.value) if event.value is not None else None
            if selected_id is None:
                return
            if should_clear_pending_uploads(
                current_file_count=len(state["files"]),
                previous_project_id=state["active_project_id"],
                next_project_id=selected_id,
            ):
                state["files"] = []
                state["summary"] = build_pending_analysis([])
                upload_error.set_text("Re-upload artifacts after switching projects.")
                if upload_widget is not None:
                    upload_widget.reset()
            refresh_projects(selected_project_id=selected_id, notify_parent=True)
            render_summary()
            render_actions()

        project_select.on_value_change(handle_project_change)

        def open_create_project_dialog() -> None:
            show_create_project_dialog(
                on_created=lambda created: (
                    refresh_projects(
                        selected_project_id=created.id,
                        notify_parent=True,
                    ),
                    render_actions(),
                    ui.notify(
                        f"Project workspace created: {created.display_name}.",
                        color="positive",
                    ),
                )
            )

        ui.button(
            "Create project",
            on_click=open_create_project_dialog,
            color="primary",
        ).props("flat no-caps")

    def clear_result_if_current(token: int) -> None:
        if token != state["result_token"]:
            return
        state["active_result"] = None
        result_mount.clear()

    def render_result_card(
        report: dict, *, remaining_seconds: int | None = None, parse_batch=None
    ) -> None:
        token = int(state["result_token"]) + 1
        state["result_token"] = token
        state["active_result"] = report
        result_mount.clear()
        countdown_label = None
        timer_state = {
            "remaining": max(
                int(
                    remaining_seconds
                    or report.get("dashboard_remaining_seconds")
                    or report.get("dashboard_display_duration_seconds")
                    or 0
                ),
                0,
            )
        }

        def update_countdown() -> None:
            if token != state["result_token"]:
                return
            if timer_state["remaining"] <= 0:
                clear_result_if_current(token)
                return
            if countdown_label is not None:
                countdown_label.set_text(
                    _format_countdown_label(timer_state["remaining"])
                )
            timer_state["remaining"] -= 1

        with result_mount:
            with ui.card().classes("w-full dw-panel shadow-none p-5"):
                with ui.row().classes(
                    "w-full items-start justify-between gap-4 flex-wrap"
                ):
                    with ui.row().classes("items-center gap-3 flex-wrap"):
                        render_risk_badge(report["severity"])
                        render_recommendation_label(
                            report["recommendation"], size="base"
                        )
                        confidence = coerce_confidence(report.get("confidence"))
                        if confidence is not None:
                            render_confidence_badge(confidence)
                    countdown_label = ui.label("").classes("text-xs dw-muted")
                ui.label(report["top_risk"]).classes(
                    "text-lg font-medium dw-text leading-6"
                )
                if report.get("narrative_available", True):
                    ui.label(report["narrative_opening"]).classes(
                        "text-sm dw-muted leading-6"
                    )
                else:
                    ui.label(
                        "Narrative unavailable. Review the deterministic findings and evidence below."
                    ).classes("text-sm dw-warning-text leading-6")
                ui.label(report["parse_summary"]).classes("text-xs dw-muted")
                report_reference = persisted_report_reference(report)
                if report_reference is not None:
                    reference_label, reference_target = report_reference
                    ui.link(reference_label, reference_target).classes(
                        "text-xs dw-link"
                    )
                manifest = report.get("submission_manifest") or {}
                if manifest.get("items"):
                    ui.label(format_submission_manifest_summary(manifest)).classes(
                        "text-xs dw-muted"
                    )
                    partial_notice = format_submission_manifest_partial_notice(manifest)
                    if partial_notice:
                        ui.label(partial_notice).classes(
                            "text-xs dw-warning-text leading-5"
                        )
                fallback_summary = format_submission_manifest_fallback_summary(
                    report.get("submission_manifest_fallback") or []
                )
                if fallback_summary and not manifest.get("items"):
                    ui.label(fallback_summary).classes(
                        "text-xs dw-warning-text leading-5 break-all"
                    )
                provenance_bits = [
                    f"Risk scoring: {report.get('assessment_source', 'unknown')}",
                    f"Narrative: {report.get('narrative_source', 'unknown')}",
                ]
                if report.get("narrative_provider") and report.get("narrative_model"):
                    provenance_bits.append(
                        f"Provider: {report['narrative_provider']} / {report['narrative_model']}"
                    )
                if report.get("skills_applied"):
                    provenance_bits.append(
                        "Skills: " + ", ".join(report["skills_applied"])
                    )
                ui.label(" · ".join(provenance_bits)).classes("text-xs dw-muted")
                llm_notice = extract_llm_notice(
                    report.get("warnings", []),
                    report.get("narrative_failure_notice"),
                )
                if llm_notice:
                    ui.label(llm_notice).classes("text-xs dw-warning-text leading-5")
                manifest_notice = extract_submission_manifest_notice(
                    report.get("warnings", [])
                )
                if manifest_notice:
                    ui.label(manifest_notice).classes(
                        "text-xs dw-warning-text leading-5"
                    )
                context = report.get("context_completeness") or {}
                render_topology_freshness_banner(context)
                if parse_batch is not None:
                    render_change_table(parse_batch)
                findings = report.get("findings", [])
                evidence_items = report.get("evidence_items", [])
                artifact_names = list(report.get("audit", {}).get("files_analyzed", []))
                if findings:
                    with ui.column().classes("mt-3 gap-2"):
                        render_findings_table(
                            findings,
                            evidence_items,
                            title="Findings table",
                            artifact_names=artifact_names,
                            report_id=int(report["id"]),
                            report_schema_version=str(
                                report.get("report_schema_version") or ""
                            ),
                        )
                        render_reviewer_feedback_panel(
                            report,
                            on_feedback_change=build_feedback_rerender_handler(
                                render_result_card,
                                report=report,
                                parse_batch=parse_batch,
                                timer_state=timer_state,
                            ),
                        )
                render_context_completeness_panel(context)
                blast_radius = report.get("blast_radius") or {}
                if (
                    blast_radius.get("affected")
                    or blast_radius.get("warning")
                    or blast_radius.get("direct_count", 0)
                    or blast_radius.get("transitive_count", 0)
                ):
                    render_blast_radius_panel(
                        BlastRadiusResult.model_validate(blast_radius),
                        severity=str(report["severity"]),
                    )
                rollback_plan = report.get("rollback_plan") or {}
                if rollback_plan.get("steps") or rollback_plan.get("warning"):
                    render_rollback_plan(RollbackPlan.model_validate(rollback_plan))
                contributors = report.get("contributors", [])
                if contributors:
                    with ui.column().classes("mt-3 gap-2"):
                        ui.label("Resource severity breakdown").classes(
                            "text-sm font-semibold dw-text"
                        )
                        for contributor in contributors[:5]:
                            with ui.row().classes(
                                "w-full items-start justify-between gap-3 flex-wrap"
                            ):
                                with ui.column().classes("min-w-0 flex-1 gap-1"):
                                    ui.label(contributor["resource_id"]).classes(
                                        "text-sm font-medium dw-text"
                                    )
                                    ui.label(contributor["reasoning"]).classes(
                                        "text-xs dw-muted leading-5"
                                    )
                                    for metadata_line in format_change_metadata_lines(
                                        contributor.get("metadata") or {}
                                    ):
                                        ui.label(metadata_line).classes(
                                            "text-xs dw-muted leading-5"
                                        )
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
                    ).classes("text-sm dw-text")
                progress_bar = ui.linear_progress(
                    value=float(state["progress_value"]) / 100
                ).classes("w-full")
                ui.label("Uploads are disabled while analysis is running.").classes(
                    "text-xs dw-muted"
                )
                return

            progress_bar = None
            progress_label = None
            analyze_button = ui.button(
                "Analyze", on_click=run_analysis, color="primary"
            ).props("unelevated")
            if not state["active_project_key"]:
                ui.label(
                    "Select an existing project or create one before running manual analysis."
                ).classes("text-xs dw-muted")
            if state["project_authorization_error"] is not None:
                ui.label(state["project_authorization_error"]).classes(
                    "text-xs dw-warning-text"
                )
            if summary.ready_count == 0 or not state["active_project_key"]:
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
            ui.label(f"{total_count} files").classes("text-sm dw-text")
            ui.label("·").classes("text-sm dw-muted")
            ui.label(f"{ready_count} accepted").classes("text-sm dw-muted")

        for item in summary.items:
            with detail_column:
                with ui.row().classes(
                    "w-full items-center justify-between dw-panel-soft px-3 py-2"
                ):
                    ui.label(item.name).classes("text-sm dw-text")
                    with ui.row().classes("items-center gap-3"):
                        ui.label(item.tool).classes("text-xs uppercase dw-muted")
                        ui.label(item.status).style(STATUS_STYLES[item.status]).classes(
                            "text-xs font-medium uppercase"
                        )
                ui.label(item.message).classes("text-xs dw-muted")

        render_actions()

    async def execute_analysis() -> None:
        summary = state["summary"]
        if state["is_running"] or summary.ready_count == 0:
            return

        files = _accepted_files(state["files"])
        if not files:
            ui.notify("No supported artifacts are ready for analysis.", color="warning")
            return
        if not state["active_project_key"]:
            ui.notify(
                "Select or create a project workspace before running analysis.",
                color="warning",
            )
            return

        state["is_running"] = True
        upload_widget.disable()
        render_actions()
        update_progress(5, "Preparing analysis")

        try:
            raw_files = list(state["files"])
            update_progress(25, "Running shared analysis pipeline")
            result = await run.io_bound(
                run_uploaded_analysis,
                raw_files,
                project_key=state["active_project_key"],
            )
            parse_batch = result.parse_batch
            assessment = result.assessment
            narrative = result.narrative
            persisted_report = result.persisted_report
            update_progress(
                90,
                f"Parsed {parse_batch.parsed_count} file(s), {parse_batch.failed_count} failed, {parse_batch.skipped_count} skipped",
            )
            update_progress(100, "Saved analysis report")
            display_report = dict(persisted_report)
            display_report["assessment_source"] = assessment.source
            display_report["narrative_source"] = narrative.source
            display_report["narrative_provider"] = narrative.provider
            display_report["narrative_model"] = narrative.model
            display_report["skills_applied"] = list(narrative.skills_applied)

            render_result_card(
                display_report,
                remaining_seconds=persisted_report.get(
                    "dashboard_display_duration_seconds"
                ),
                parse_batch=parse_batch,
            )
            state["files"] = []
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
            failure_title, failure_message, notification = format_analysis_failure(exc)
            result_mount.clear()
            with result_mount:
                with ui.card().classes("w-full dw-panel shadow-none p-5"):
                    ui.label(failure_title).classes(
                        "text-base font-semibold dw-danger-text"
                    )
                    ui.label(failure_message).classes("text-sm dw-muted")
            ui.notify(
                notification,
                color="negative",
            )
        finally:
            state["is_running"] = False
            sync_upload_widget_state()
            render_actions()

    def schedule_analysis_after_dialog_close() -> None:
        scheduler_mount.clear()
        with scheduler_mount:
            ui.timer(0.01, execute_analysis, once=True)

    async def run_analysis() -> None:
        readiness = await run.io_bound(check_provider_readiness)
        if readiness.ready:
            await execute_analysis()
            return

        dialog = ui.dialog()
        with (
            dialog,
            ui.card().classes(
                "w-[520px] dw-panel shadow-none p-6 gap-3"
            ) as dialog_card,
        ):
            decorate_modal_card(dialog_card, label="LLM provider not ready")
            ui.label("LLM provider not ready").classes("text-lg font-medium dw-text")
            ui.label(
                f"Provider: {readiness.provider} · Model: {readiness.model}"
            ).classes("text-sm dw-muted")
            ui.label(readiness.message).classes("text-sm dw-warning-text leading-6")
            ui.label(
                "If you continue, DeployWhisper will still parse files and produce heuristic-only analysis where LLM-assisted steps are unavailable."
            ).classes("text-sm dw-muted")
            with ui.row().classes("w-full justify-end gap-3 mt-4"):
                cancel_button = ui.button("Cancel", on_click=dialog.close).props(
                    "outline no-caps"
                )
                decorate_modal_close(cancel_button)

                def proceed_anyway() -> None:
                    dialog.close()
                    schedule_analysis_after_dialog_close()

                ui.button(
                    "Continue Anyway", on_click=proceed_anyway, color="primary"
                ).props("unelevated no-caps")
        dialog.open()

    async def handle_multi_upload(event: events.MultiUploadEventArguments) -> None:
        if not uploads_allowed(state["active_project_key"]):
            upload_error.set_text(
                "Select or create a project workspace before uploading deployment artifacts."
            )
            return
        if state["is_running"]:
            upload_error.set_text(
                "Wait for the current analysis to finish before uploading more artifacts."
            )
            return
        current_total = total_upload_bytes(list(state["files"]))
        uploads: list[tuple[str, bytes]] = []
        for uploaded_file in event.files:
            file_size = getattr(uploaded_file, "size", None)
            if (
                isinstance(file_size, int)
                and current_total + file_size > MAX_TOTAL_UPLOAD_BYTES
            ):
                upload_error.set_text(
                    "Total upload size exceeds the 50 MB analysis-session limit. Remove some artifacts and try again."
                )
                return
            content = await uploaded_file.read()
            current_total += len(content)
            if current_total > MAX_TOTAL_UPLOAD_BYTES:
                upload_error.set_text(
                    "Total upload size exceeds the 50 MB analysis-session limit. Remove some artifacts and try again."
                )
                return
            uploads.append((uploaded_file.name, content))
        state["summary"] = process_uploaded_files(state["files"], uploads)
        render_summary()

    def handle_rejected(_: events.UiEventArguments) -> None:
        upload_error.set_text(
            "One or more files were rejected by the uploader. Check file type or size."
        )

    upload_widget = None
    with upload_card:
        upload_widget = (
            ui.upload(
                on_multi_upload=handle_multi_upload,
                on_rejected=handle_rejected,
                auto_upload=True,
                multiple=True,
                label="Select deployment artifacts",
                max_file_size=50_000_000,
            )
            .props("accept=.json,.yaml,.yml,.tf,.tfvars,.hcl,Jenkinsfile")
            .classes("w-full")
        )

    refresh_projects()
    render_summary()
