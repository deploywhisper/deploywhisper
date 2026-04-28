"""Settings route rendering."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from llm.skill_context import get_custom_skill_statuses, save_custom_skill
from services.project_service import get_active_project
from services.settings_service import (
    activate_local_mode,
    get_dashboard_result_display_duration_seconds,
    provider_defaults,
    provider_select_options,
    get_provider_settings,
    save_dashboard_result_display_duration_seconds,
    save_provider_settings,
    validate_provider_settings,
)
from services.topology_service import get_topology_status, save_topology_definition
from ui.theme import apply_theme, build_navigation_shell, build_page_header


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
    apply_theme()
    build_navigation_shell("settings")
    active_project = get_active_project()
    settings = get_provider_settings()
    dashboard_duration_seconds = get_dashboard_result_display_duration_seconds()
    topology_status = get_topology_status(
        project_id=active_project.id if active_project is not None else None
    )
    custom_skill_statuses = get_custom_skill_statuses()
    provider_options = provider_select_options()

    with ui.column().classes("dw-main-content dw-shell gap-5"):
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
            with ui.column().classes("w-full gap-1 rounded-lg dw-panel-soft px-4 py-3"):
                ui.label("Secrets").classes("text-sm font-semibold dw-text")
                ui.label(
                    "Provider selection, model, and API base can be persisted. API keys are not stored in the app database and must come from environment variables or runtime secrets."
                ).classes("text-sm dw-muted")
            with ui.column().classes("w-full gap-1 rounded-lg dw-panel-soft px-4 py-3"):
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
            local_mode_toggle = ui.switch("Local-only mode", value=settings.local_mode)
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
                api_base_input.value = selected.api_base or str(defaults["api_base"])
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
                "Save AI settings", on_click=lambda: save_settings(), color="primary"
            ).props("unelevated")
            duration_feedback.text = f"Dashboard results currently remain visible for {duration_options[dashboard_duration_seconds]}."

        with ui.card().classes("w-full dw-panel shadow-none"):
            ui.label("Topology context").classes("text-lg font-medium dw-text")
            ui.label(
                "Upload or replace the service-topology JSON used by blast-radius analysis. "
                "DeployWhisper validates the structure immediately and shows any uncertainty."
            ).classes("text-sm dw-muted")
            if active_project is not None:
                ui.label(
                    f"Active project: {active_project.display_name} ({active_project.project_key})"
                ).classes("text-xs font-semibold uppercase tracking-[0.08em] dw-muted")
            topology_feedback = ui.column().classes("w-full gap-2")

            def render_topology_feedback(
                status,
                *,
                success_message: str | None = None,
                error_message: str | None = None,
            ) -> None:
                topology_feedback.clear()
                with topology_feedback:
                    if error_message:
                        ui.label(error_message).classes("text-sm dw-danger-text")

                    if success_message:
                        ui.label(success_message).classes("text-sm dw-success-text")

                    if status.exists:
                        ui.label(
                            f"{status.service_count} services · {status.dependency_count} dependencies · "
                            f"{status.resource_key_count} resource mappings"
                        ).classes("text-sm dw-text")
                        updated_at = status.updated_at or "timestamp unavailable"
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
                        ui.label(blocking_error).classes("text-xs dw-danger-text")
                    for warning in status.warnings:
                        ui.label(warning).classes("text-xs dw-warning-text")

            def handle_topology_upload(event) -> None:
                current_project = get_active_project()
                upload_result = process_topology_upload_content(
                    event.content.read(),
                    project_id=current_project.id
                    if current_project is not None
                    else None,
                )
                render_topology_feedback(
                    upload_result["status"],
                    success_message=upload_result["success_message"],
                    error_message=upload_result["error_message"],
                )

            ui.upload(
                on_upload=handle_topology_upload,
                auto_upload=True,
                multiple=False,
                max_file_size=5_000_000,
            ).props("accept=.json").classes("w-full")
            render_topology_feedback(topology_status)

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
