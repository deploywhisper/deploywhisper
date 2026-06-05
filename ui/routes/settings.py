"""Settings route rendering."""

from __future__ import annotations

from typing import Any

from nicegui import events, ui

from llm.skill_context import get_custom_skill_statuses, save_custom_skill
from services.feedback_service import fetch_feedback_summary
from services.settings_service import (
    activate_local_mode,
    get_dashboard_result_display_duration_seconds,
    get_topology_drift_check_interval_hours,
    get_provider_settings,
    provider_defaults,
    provider_select_options,
    save_dashboard_result_display_duration_seconds,
    save_provider_settings,
    save_topology_drift_check_interval_hours,
    TOPOLOGY_DRIFT_CHECK_INTERVAL_OPTIONS,
    validate_provider_settings,
)
from services.topology_service import (
    TopologyStatus,
    get_topology_status,
    save_topology_definition,
    validate_topology_definition,
)
from ui.components.dashboard_shell import build_app_shell, workspace_content
from ui.project_authorization import resolve_authorized_ui_active_project
from ui.theme import build_page_header


def _empty_feedback_summary() -> dict[str, Any]:
    return {
        "current_state": {
            "useful_count": 0,
            "noisy_count": 0,
            "not_useful_count": 0,
            "false_positive_count": 0,
            "missed_finding_count": 0,
        },
        "totals": {"events_recorded": 0},
        "recent_notes": [],
    }


def process_topology_upload_content(
    raw_content: bytes,
    *,
    project_id: int | None = None,
) -> dict[str, Any]:
    """Decode topology upload content and return admin-facing feedback payload."""
    try:
        raw_text = raw_content.decode("utf-8")
        status = save_topology_definition(raw_text, project_id=project_id)
    except (UnicodeDecodeError, ValueError) as exc:
        return {
            "status": get_topology_status(project_id=project_id),
            "success_message": None,
            "error_message": f"Topology update failed: {exc}",
        }

    return {
        "status": status,
        "success_message": (
            f"Service topology updated — {status.service_count} services, "
            f"{status.dependency_count} dependencies — last updated just now."
        ),
        "error_message": None,
    }


def preview_topology_upload_content(
    raw_content: bytes,
    *,
    project_id: int | None = None,
) -> dict[str, Any]:
    """Decode topology upload content and validate it before persistence."""
    try:
        raw_text = raw_content.decode("utf-8")
        status = validate_topology_definition(raw_text, project_id=project_id)
    except (UnicodeDecodeError, ValueError) as exc:
        return {
            "status": TopologyStatus(path="selected://topology-upload", exists=False),
            "success_message": None,
            "error_message": f"Topology validation failed: {exc}",
        }

    if status.blocking_errors:
        return {
            "status": status,
            "success_message": None,
            "error_message": " ".join(status.blocking_errors),
        }

    return {
        "status": status,
        "success_message": (
            f"Topology JSON is valid — {status.service_count} services, "
            f"{status.dependency_count} dependencies — ready to save."
        ),
        "error_message": None,
    }


def process_custom_skill_upload_content(
    filename: str, raw_content: bytes
) -> dict[str, Any]:
    """Decode and persist a custom skill file with admin-facing feedback."""
    try:
        raw_text = raw_content.decode("utf-8")
        status = save_custom_skill(filename, raw_text)
    except (UnicodeDecodeError, ValueError) as exc:
        return {
            "statuses": get_custom_skill_statuses(),
            "success_message": None,
            "error_message": f"Custom skill update failed: {exc}",
        }

    mode_text = "override" if status.mode == "override" else "new skill"
    return {
        "statuses": get_custom_skill_statuses(),
        "success_message": f"Custom skill detected: {status.name} ({mode_text}).",
        "error_message": None,
    }


def build_settings_page() -> None:
    """Render the provider settings form."""
    content_refresh = {"fn": lambda *_: None}

    def handle_project_change(*_) -> None:
        content_refresh["fn"]()

    build_app_shell("settings", on_project_change=handle_project_change)

    @ui.refreshable
    def render_settings_content() -> None:
        _, active_project, authorization_error = resolve_authorized_ui_active_project()

        def current_authorized_project():
            _, project, _ = resolve_authorized_ui_active_project()
            return project

        settings = get_provider_settings()
        dashboard_duration_seconds = get_dashboard_result_display_duration_seconds()
        drift_interval_hours = get_topology_drift_check_interval_hours()
        topology_status = (
            None
            if authorization_error is not None
            else get_topology_status(
                project_id=active_project.id if active_project is not None else None
            )
        )
        feedback_summary = (
            _empty_feedback_summary()
            if authorization_error is not None
            else fetch_feedback_summary(
                project_id=active_project.id if active_project is not None else None
            )
        )
        custom_skill_statuses = get_custom_skill_statuses()
        provider_options = provider_select_options()
        staged_topology: dict[str, Any] = {"name": None, "content": None}

        with workspace_content(aria_label="Operational settings workspace"):
            with ui.card().classes("w-full dw-panel dw-page-header shadow-none"):
                build_page_header(
                    eyebrow="Settings",
                    title="Operational settings",
                    subtitle="Manage provider access, topology context, and custom AI skills.",
                    back_href="/",
                    back_label="Back to dashboard",
                )
            with ui.card().classes("w-full dw-panel shadow-none"):
                ui.label("AI provider").classes("text-lg font-medium dw-text")
                ui.label(
                    "Configure one active provider at a time. Saved provider profiles stay in the database so you can switch between them later."
                ).classes("text-sm dw-muted")
                with ui.column().classes(
                    "w-full gap-1 rounded-lg dw-panel-soft px-4 py-3"
                ):
                    ui.label("Secrets").classes("text-sm font-semibold dw-text")
                    ui.label(
                        "Provider selection, model, and API base can be persisted. API keys are not stored in the app database and must come from environment variables or runtime secrets."
                    ).classes("text-sm dw-muted")
                with ui.column().classes(
                    "w-full gap-1 rounded-lg dw-panel-soft px-4 py-3"
                ):
                    ui.label("Provider capabilities").classes(
                        "text-sm font-semibold dw-text"
                    )
                    ui.label(
                        "MCP readiness remains optional and future-facing. Current narrative flows still use structured summaries only."
                    ).classes("text-sm dw-muted")
                    capability_summary = ui.label("").classes("text-sm dw-muted")
                provider_select = ui.select(
                    options=provider_options,
                    value=settings.provider,
                    label="Active Provider",
                ).classes("w-full")
                model_input = ui.input("Model", value=settings.model).classes("w-full")
                api_base_input = ui.input("API base", value=settings.api_base).classes(
                    "w-full"
                )
                api_key_input = ui.input(
                    "API key",
                    value=settings.api_key or "",
                    password=True,
                    password_toggle_button=True,
                ).classes("w-full")
                local_mode_toggle = ui.switch(
                    "Local-only mode", value=settings.local_mode
                )
                feedback = ui.label(
                    f"Current source: {settings.source} · active provider: {settings.provider}"
                ).classes("text-sm dw-muted")
                duration_feedback = ui.label("").classes("text-sm dw-muted")
                duration_options = {
                    60: "1 minute",
                    300: "5 minutes",
                    600: "10 minutes",
                    900: "15 minutes",
                    1800: "30 minutes",
                }
                duration_select = ui.select(
                    options=duration_options,
                    value=dashboard_duration_seconds,
                    label="Dashboard Result Display Duration",
                ).classes("w-full")

                def sync_provider_fields(provider_name: str) -> None:
                    selected = get_provider_settings(provider_name)
                    defaults = provider_defaults(provider_name)
                    model_input.value = selected.model or str(defaults["model"])
                    api_base_input.value = selected.api_base or str(
                        defaults["api_base"]
                    )
                    api_key_input.value = selected.api_key or ""
                    local_mode_toggle.value = selected.local_mode
                    capabilities = selected.capabilities
                    capability_summary.text = (
                        "Structured output: "
                        f"{'yes' if capabilities.supports_structured_output else 'no'} · "
                        "Local-only: "
                        f"{'yes' if capabilities.supports_local_only_mode else 'no'} · "
                        "Remote MCP: "
                        f"{'yes' if capabilities.supports_remote_mcp else 'no'} · "
                        "Local MCP: "
                        f"{'yes' if capabilities.supports_local_mcp else 'no'} · "
                        "Tool approval: "
                        f"{'yes' if capabilities.supports_tool_approval else 'no'}"
                    )
                    if capabilities.supports_local_only_mode:
                        local_mode_toggle.enable()
                    else:
                        local_mode_toggle.disable()
                    if not capabilities.supports_local_only_mode:
                        local_mode_toggle.value = False

                provider_select.on_value_change(
                    lambda event: sync_provider_fields(str(event.value))
                )
                sync_provider_fields(settings.provider)

                def save_settings() -> None:
                    selected_provider = str(provider_select.value)
                    local_mode = (
                        bool(local_mode_toggle.value)
                        if selected_provider == "ollama"
                        else False
                    )
                    if local_mode:
                        saved = activate_local_mode(
                            model=model_input.value.strip(),
                            api_base=api_base_input.value.strip(),
                        )
                    else:
                        saved = save_provider_settings(
                            provider=selected_provider,
                            model=model_input.value.strip(),
                            api_base=api_base_input.value.strip(),
                            api_key=api_key_input.value.strip() or None,
                            local_mode=local_mode,
                            activate=True,
                        )
                    validation = validate_provider_settings(saved)
                    if validation["valid"]:
                        feedback.text = (
                            f"Saved provider settings: {saved.provider} · {saved.model} · "
                            f"local_mode={saved.local_mode} · source={saved.source} · validation=ok"
                        )
                    else:
                        feedback.text = (
                            f"Saved provider settings: {saved.provider} · {saved.model} · "
                            f"local_mode={saved.local_mode} · source={saved.source} · validation failed: {validation['message']}"
                        )
                    saved_duration = save_dashboard_result_display_duration_seconds(
                        int(duration_select.value)
                    )
                    duration_feedback.text = f"Dashboard results will remain visible for {duration_options[saved_duration]}."

                ui.button(
                    "Save AI settings",
                    on_click=lambda: save_settings(),
                    color="primary",
                ).props("unelevated")
                duration_feedback.text = f"Dashboard results currently remain visible for {duration_options[dashboard_duration_seconds]}."

            with ui.element("section").props("id=topology-context").classes("w-full"):
                with ui.card().classes("w-full dw-panel shadow-none"):
                    ui.label("Topology context").classes("text-lg font-medium dw-text")
                    ui.label(
                        "Upload or replace the service-topology JSON used by blast-radius analysis. "
                        "DeployWhisper validates the structure when you select a file, "
                        "then saves it to the active project when you confirm."
                    ).classes("text-sm dw-muted")
                    if active_project is not None:
                        ui.label(
                            f"Active project: {active_project.display_name} ({active_project.project_key})"
                        ).classes(
                            "text-xs font-semibold uppercase tracking-[0.08em] dw-muted"
                        )
                    topology_feedback = ui.column().classes("w-full gap-2")
                    topology_validation_feedback = ui.column().classes("w-full gap-2")
                    topology_upload_feedback = ui.label("").classes(
                        "text-xs font-medium dw-accent-text"
                    )
                    drift_interval_options = {
                        hours: (
                            "Every 6 hours"
                            if hours == 6
                            else "Every 12 hours"
                            if hours == 12
                            else "Daily"
                            if hours == 24
                            else "Weekly"
                        )
                        for hours in TOPOLOGY_DRIFT_CHECK_INTERVAL_OPTIONS
                    }

                    def render_topology_validation_feedback(
                        status,
                        *,
                        file_name: str | None = None,
                        success_message: str | None = None,
                        error_message: str | None = None,
                    ) -> None:
                        topology_validation_feedback.clear()
                        if status is None:
                            return
                        with topology_validation_feedback:
                            ui.label("Selected topology file").classes(
                                "text-xs font-semibold uppercase tracking-[0.08em] dw-muted"
                            )
                            if file_name:
                                ui.label(file_name).classes("text-sm dw-text")
                            if error_message:
                                ui.label(error_message).classes(
                                    "text-sm dw-danger-text"
                                )
                            if success_message:
                                ui.label(success_message).classes(
                                    "text-sm dw-success-text"
                                )
                            if status.service_count or status.dependency_count:
                                ui.label(
                                    f"{status.service_count} services · "
                                    f"{status.dependency_count} dependencies · "
                                    f"{status.resource_key_count} resource mappings"
                                ).classes("text-xs dw-text")
                            if status.preview_services:
                                ui.label(
                                    "Preview: " + ", ".join(status.preview_services)
                                ).classes("text-xs dw-muted")
                            for warning in status.warnings:
                                ui.label(warning).classes("text-xs dw-warning-text")
                            for blocking_error in status.blocking_errors:
                                if error_message and blocking_error in error_message:
                                    continue
                                ui.label(blocking_error).classes(
                                    "text-xs dw-danger-text"
                                )

                    def render_topology_feedback(
                        status,
                        *,
                        success_message: str | None = None,
                        error_message: str | None = None,
                    ) -> None:
                        topology_feedback.clear()
                        with topology_feedback:
                            if error_message:
                                ui.label(error_message).classes(
                                    "text-sm dw-danger-text"
                                )

                            if success_message:
                                ui.label(success_message).classes(
                                    "text-sm dw-success-text"
                                )

                            if status.exists:
                                ui.label(
                                    f"{status.service_count} services · {status.dependency_count} dependencies · "
                                    f"{status.resource_key_count} resource mappings"
                                ).classes("text-sm dw-text")
                                updated_at = (
                                    status.updated_at or "timestamp unavailable"
                                )
                                ui.label(f"Active file: {status.path}").classes(
                                    "text-xs dw-muted"
                                )
                                ui.label(f"Last updated: {updated_at}").classes(
                                    "text-xs dw-muted"
                                )
                                if status.preview_services:
                                    ui.label(
                                        "Preview: " + ", ".join(status.preview_services)
                                    ).classes("text-xs dw-muted")
                            else:
                                ui.label(f"Active file: {status.path}").classes(
                                    "text-xs dw-muted"
                                )
                                ui.label("No topology is active yet.").classes(
                                    "text-sm dw-muted"
                                )

                            for blocking_error in status.blocking_errors:
                                ui.label(blocking_error).classes(
                                    "text-xs dw-danger-text"
                                )
                            for warning in status.warnings:
                                ui.label(warning).classes("text-xs dw-warning-text")
                            ui.separator()
                            ui.label("Topology drift").classes(
                                "text-sm font-semibold dw-text"
                            )
                            if status.drift is None:
                                ui.label("No drift check has run yet.").classes(
                                    "text-xs dw-muted"
                                )
                            else:
                                drift = status.drift
                                ui.label(
                                    f"Status: {drift.status.replace('_', ' ')}"
                                ).classes("text-xs dw-text")
                                ui.label(
                                    f"Drift check cadence: {drift.interval_hours} hour(s)"
                                ).classes("text-xs dw-muted")
                                if drift.checked_at:
                                    ui.label(
                                        f"Last checked: {drift.checked_at}"
                                    ).classes("text-xs dw-muted")
                                if drift.next_check_at:
                                    ui.label(
                                        f"Next check: {drift.next_check_at}"
                                    ).classes("text-xs dw-muted")
                                if (
                                    drift.added_resources
                                    or drift.removed_resources
                                    or drift.modified_resources
                                ):
                                    ui.label(
                                        "Changed resources: "
                                        f"+{len(drift.added_resources)} / "
                                        f"-{len(drift.removed_resources)} / "
                                        f"~{len(drift.modified_resources)}"
                                    ).classes("text-xs dw-text")
                                    if drift.added_resources:
                                        ui.label(
                                            "Added: " + ", ".join(drift.added_resources)
                                        ).classes("text-xs dw-muted")
                                    if drift.removed_resources:
                                        ui.label(
                                            "Removed: "
                                            + ", ".join(drift.removed_resources)
                                        ).classes("text-xs dw-muted")
                                    if drift.modified_resources:
                                        ui.label(
                                            "Modified: "
                                            + ", ".join(drift.modified_resources)
                                        ).classes("text-xs dw-muted")
                                for warning in drift.warnings:
                                    ui.label(warning).classes("text-xs dw-warning-text")

                    def save_drift_interval(event) -> None:
                        try:
                            saved_interval = save_topology_drift_check_interval_hours(
                                int(event.value)
                            )
                        except ValueError as exc:
                            ui.notify(str(exc), type="negative")
                            return
                        ui.notify(
                            "Topology drift cadence updated to "
                            f"{drift_interval_options.get(saved_interval, saved_interval)}.",
                            type="positive",
                        )
                        render_settings_content.refresh()

                    async def handle_topology_upload(
                        event: events.UploadEventArguments,
                    ) -> None:
                        current_project = current_authorized_project()
                        uploaded_content = await event.file.read()
                        if current_project is None:
                            staged_topology["name"] = None
                            staged_topology["content"] = None
                            topology_upload_feedback.text = ""
                            render_topology_validation_feedback(
                                TopologyStatus(
                                    path="selected://topology-upload",
                                    exists=False,
                                ),
                                file_name=event.file.name,
                                error_message=authorization_error
                                or "Select an active project before previewing topology context.",
                            )
                            return
                        preview_result = preview_topology_upload_content(
                            uploaded_content,
                            project_id=current_project.id,
                        )
                        if preview_result["error_message"] is None:
                            staged_topology["name"] = event.file.name
                            staged_topology["content"] = uploaded_content
                            topology_upload_feedback.text = f"Selected topology JSON ready to save: {event.file.name}"
                        else:
                            staged_topology["name"] = None
                            staged_topology["content"] = None
                            topology_upload_feedback.text = ""
                        render_topology_validation_feedback(
                            preview_result["status"],
                            file_name=event.file.name,
                            success_message=preview_result["success_message"],
                            error_message=preview_result["error_message"],
                        )

                    with ui.column().classes(
                        "w-full gap-3 rounded-[20px] border border-[color:var(--dw-line)] bg-[color:var(--dw-surface-soft)] p-4 mt-3"
                    ):
                        topology_upload = (
                            ui.upload(
                                on_upload=handle_topology_upload,
                                auto_upload=True,
                                multiple=False,
                                max_file_size=5_000_000,
                            )
                            .props("accept=.json")
                            .classes("w-full dw-topology-uploader")
                        )
                        ui.label(
                            "Choose a topology JSON, review the validation result, then click save to apply it to the active project shown above."
                        ).classes("text-xs dw-muted leading-5")

                        def submit_topology_upload() -> None:
                            current_project = current_authorized_project()
                            if current_project is None:
                                ui.notify(
                                    "Select an active project before saving topology context.",
                                    type="warning",
                                )
                                return
                            content = staged_topology.get("content")
                            if not isinstance(content, (bytes, bytearray)):
                                ui.notify(
                                    "Choose a topology JSON before saving it to the active project.",
                                    type="warning",
                                )
                                return
                            upload_result = process_topology_upload_content(
                                bytes(content),
                                project_id=current_project.id,
                            )
                            render_topology_feedback(
                                upload_result["status"],
                                success_message=upload_result["success_message"],
                                error_message=upload_result["error_message"],
                            )
                            if upload_result["error_message"] is None:
                                staged_topology["name"] = None
                                staged_topology["content"] = None
                                topology_upload_feedback.text = ""
                                render_topology_validation_feedback(None)
                                topology_upload.reset()

                        ui.button(
                            "Save topology to active project",
                            on_click=submit_topology_upload,
                            color="primary",
                        ).props("unelevated no-caps").classes("self-start")
                    drift_interval_select = ui.select(
                        options=drift_interval_options,
                        value=drift_interval_hours,
                        label="Drift check cadence",
                    ).classes("w-full")
                    drift_interval_select.on_value_change(
                        lambda event: save_drift_interval(event)
                    )
                    if authorization_error is None and topology_status is not None:
                        render_topology_feedback(topology_status)
                    else:
                        with topology_feedback:
                            ui.label(authorization_error or "").classes(
                                "text-sm dw-warning-text"
                            )

            with ui.card().classes("w-full dw-panel shadow-none"):
                ui.label("Reviewer feedback summary").classes(
                    "text-lg font-medium dw-text"
                )
                ui.label(
                    "Admin-facing all-workspaces summary of the latest reviewer feedback state for the active project."
                ).classes("text-sm dw-muted")
                with ui.row().classes("w-full items-stretch gap-2 flex-wrap mt-3"):
                    metrics = [
                        ("Useful", feedback_summary["current_state"]["useful_count"]),
                        (
                            "Noisy",
                            feedback_summary["current_state"].get(
                                "noisy_count",
                                feedback_summary["current_state"]["not_useful_count"],
                            ),
                        ),
                        (
                            "False positives",
                            feedback_summary["current_state"]["false_positive_count"],
                        ),
                        (
                            "Missed findings",
                            feedback_summary["current_state"]["missed_finding_count"],
                        ),
                    ]
                    for label, value in metrics:
                        with ui.card().classes(
                            "dw-panel-soft shadow-none min-w-[120px] flex-1"
                        ):
                            with ui.column().classes("gap-1 p-3"):
                                ui.label(str(value)).classes(
                                    "text-2xl font-semibold dw-text"
                                )
                                ui.label(label).classes(
                                    "text-[11px] font-semibold uppercase tracking-[0.08em] dw-muted"
                                )
                ui.label(
                    f"Recorded feedback events: {feedback_summary['totals']['events_recorded']}"
                ).classes("text-sm dw-muted mt-3")
                with ui.column().classes("w-full gap-2 mt-2"):
                    ui.label("Recent notes").classes("text-sm font-semibold dw-text")
                    if not feedback_summary["recent_notes"]:
                        ui.label(
                            "No reviewer notes have been captured for the active project yet."
                        ).classes("text-sm dw-muted")
                    for item in feedback_summary["recent_notes"]:
                        ui.label(
                            f"{item['type'].replace('_', ' ').title()}: {item['text']}"
                        ).classes("text-sm dw-muted leading-6")

            with ui.card().classes("w-full dw-panel shadow-none"):
                ui.label("Custom AI Skills").classes("text-lg font-medium dw-text")
                ui.label(
                    "Add markdown skills under skills/custom to override built-ins or introduce team-specific guidance."
                ).classes("text-sm dw-muted")
                skill_feedback = ui.column().classes("w-full gap-2")

                def render_skill_feedback(
                    statuses,
                    *,
                    success_message: str | None = None,
                    error_message: str | None = None,
                ) -> None:
                    skill_feedback.clear()
                    with skill_feedback:
                        if error_message:
                            ui.label(error_message).classes("text-sm dw-danger-text")

                        if success_message:
                            ui.label(success_message).classes("text-sm dw-success-text")

                        if statuses:
                            for status in statuses:
                                mode_text = (
                                    "override" if status.mode == "override" else "new"
                                )
                                state_text = "detected" if status.active else "ignored"
                                ui.label(
                                    f"{status.name} · {mode_text} · {state_text}"
                                ).classes("text-sm dw-text")
                                ui.label(status.path).classes("text-xs dw-muted")
                                if status.warning:
                                    ui.label(status.warning).classes(
                                        "text-xs dw-warning-text"
                                    )
                        else:
                            ui.label("No custom skills detected.").classes(
                                "text-sm dw-muted"
                            )

                def handle_custom_skill_upload(event) -> None:
                    upload_result = process_custom_skill_upload_content(
                        event.name, event.content.read()
                    )
                    render_skill_feedback(
                        upload_result["statuses"],
                        success_message=upload_result["success_message"],
                        error_message=upload_result["error_message"],
                    )

                ui.upload(
                    on_upload=handle_custom_skill_upload,
                    auto_upload=True,
                    multiple=False,
                    max_file_size=1_000_000,
                ).props("accept=.md").classes("w-full")
                render_skill_feedback(custom_skill_statuses)

    content_refresh["fn"] = lambda *_: render_settings_content.refresh()
    render_settings_content()
