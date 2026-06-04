"""Shared project/workspace selector helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from html import escape
import re
from urllib.parse import urlparse

from nicegui import ui
from nicegui.events import KeyEventArguments

from services.project_service import ProjectRecord
from ui.components.review_accessibility import (
    decorate_modal_card,
    decorate_modal_close,
)
from ui.project_authorization import create_authorized_ui_project


def project_repository_context(project: ProjectRecord) -> str | None:
    """Return a compact repository context for project labels when available."""
    raw_value = str(project.repository_url or "").strip().rstrip("/")
    if not raw_value:
        return None
    trimmed = raw_value[:-4] if raw_value.endswith(".git") else raw_value
    if "://" in trimmed:
        parsed = urlparse(trimmed)
        path = parsed.path.strip("/")
        if path:
            return path
        return parsed.netloc or None
    return trimmed.lstrip("/")


def project_option_label(project: ProjectRecord) -> str:
    """Build a searchable label with project name plus repo/key context."""
    repository_context = project_repository_context(project)
    parts = [project.display_name]
    if repository_context:
        parts.append(repository_context)
    parts.append(project.project_key)
    return " · ".join(parts)


def split_project_option_label(label: str) -> tuple[str, str]:
    """Split a searchable label into primary and secondary lines."""
    parts = [part.strip() for part in str(label).split("·") if part.strip()]
    if not parts:
        return "", ""
    return parts[0], " · ".join(parts[1:])


def build_project_options(projects: Iterable[ProjectRecord]) -> dict[int, str]:
    """Return select-friendly project labels keyed by stable IDs."""
    return {int(project.id): project_option_label(project) for project in projects}


def filter_project_records(
    projects: Iterable[ProjectRecord],
    query: str | None,
) -> list[ProjectRecord]:
    """Filter projects by display name, repository context, or project key."""
    normalized = str(query or "").strip().lower()
    ordered = list(projects)
    if not normalized:
        return ordered
    matches: list[ProjectRecord] = []
    for project in ordered:
        search_text = " ".join(
            part
            for part in (
                project.display_name,
                project_repository_context(project) or "",
                project.project_key,
            )
            if part
        ).lower()
        if normalized in search_text:
            matches.append(project)
    return matches


def highlight_project_match(text: str, query: str | None) -> str:
    """Return safe HTML with matching query segments highlighted."""
    normalized = str(query or "").strip()
    safe_text = escape(text)
    if not normalized:
        return safe_text
    pattern = re.compile(re.escape(normalized), re.IGNORECASE)
    return pattern.sub(
        lambda match: f'<mark class="dw-project-match">{escape(match.group(0))}</mark>',
        safe_text,
    )


def project_context_heading() -> str:
    """Return the shared label for the global project filter."""
    return "Active Project"


def project_context_summary(active_project: ProjectRecord | None) -> str:
    """Return the current project display name for the shell."""
    if active_project is None:
        return "No project selected"
    return active_project.display_name


def project_context_meta(
    *,
    has_saved_selection: bool,
    active_project: ProjectRecord | None,
) -> str:
    """Describe repository/key context for the current project."""
    if active_project is None:
        return "Choose a workspace to scope reports, history, and settings."
    parts: list[str] = []
    if not has_saved_selection and active_project.is_default:
        parts.append("Default workspace")
    repository_context = project_repository_context(active_project)
    if repository_context:
        parts.append(repository_context)
    parts.append(f"Key {active_project.project_key}")
    return " · ".join(parts)


def build_project_combobox(
    *,
    projects: Iterable[ProjectRecord],
    current_project_id: int | None,
    on_select: Callable[[ProjectRecord], None],
) -> None:
    """Render a controlled, searchable project combobox."""
    ordered_projects = list(projects)
    state = {
        "query": "",
        "open": False,
        "highlighted_index": 0,
        "filtered": ordered_projects,
        "committing_selection": False,
    }

    def visible_projects() -> list[ProjectRecord]:
        return list(state["filtered"])

    with ui.element("div").classes("dw-project-combobox"):
        search_input = ui.input(
            placeholder="Search repo or project name",
            value="",
        ).classes("dw-project-search-input w-full")
        search_input.props("outlined clearable autocomplete=off")
        dropdown_mount = ui.element("div").classes("dw-project-dropdown-anchor")

    def render_dropdown() -> None:
        dropdown_mount.clear()
        if not state["open"]:
            return
        filtered = visible_projects()
        with dropdown_mount:
            with ui.card().classes("dw-project-dropdown-panel shadow-none"):
                if not filtered:
                    with ui.column().classes("dw-project-feedback-row gap-1"):
                        ui.label("No projects found").classes("dw-project-empty-title")
                        ui.label(
                            "Try another project name, repository slug, or workspace key."
                        ).classes("dw-project-empty-copy")
                    return

                with ui.column().classes("dw-project-dropdown-list gap-1"):
                    for index, project in enumerate(filtered):
                        is_active = project.id == current_project_id
                        is_highlighted = index == state["highlighted_index"]
                        primary = highlight_project_match(
                            project.display_name,
                            state["query"],
                        )
                        meta_parts = []
                        repository_context = project_repository_context(project)
                        if repository_context:
                            meta_parts.append(repository_context)
                        meta_parts.append(f"Key {project.project_key}")
                        secondary = highlight_project_match(
                            " · ".join(meta_parts),
                            state["query"],
                        )
                        option_classes = [
                            "dw-project-option-button",
                            "w-full",
                        ]
                        if is_highlighted:
                            option_classes.append("dw-project-option-active")
                        if is_active:
                            option_classes.append("dw-project-option-selected")
                        with (
                            ui.element("div")
                            .props(
                                "role=button tabindex=-1 "
                                f"aria-pressed={'true' if is_active else 'false'}"
                            )
                            .classes(" ".join(option_classes))
                            .on(
                                "pointerdown",
                                lambda project=project: select_project(project),
                                [],
                                js_handler="(event) => { event.preventDefault(); emit(); }",
                            )
                        ):
                            with ui.row().classes(
                                "w-full items-start justify-between gap-3"
                            ):
                                with ui.column().classes("min-w-0 flex-1 gap-[2px]"):
                                    ui.html(primary).classes(
                                        "dw-project-option-primary"
                                    )
                                ui.html(secondary).classes("dw-project-option-meta")
                                if is_active:
                                    ui.html(
                                        '<span aria-hidden="true" class="dw-project-option-check shrink-0">✓</span>'
                                    )

    def set_highlighted_index(index: int) -> None:
        filtered = visible_projects()
        if not filtered:
            state["highlighted_index"] = 0
            render_dropdown()
            return
        state["highlighted_index"] = max(0, min(index, len(filtered) - 1))
        render_dropdown()

    def apply_filter() -> None:
        filtered = filter_project_records(ordered_projects, str(state["query"]))
        state["filtered"] = filtered
        if not filtered:
            state["highlighted_index"] = 0
        else:
            state["highlighted_index"] = min(
                int(state["highlighted_index"]),
                len(filtered) - 1,
            )
        state["open"] = True
        render_dropdown()

    def handle_query_change() -> None:
        state["query"] = search_input.value or ""
        apply_filter()

    def select_project(project: ProjectRecord) -> None:
        if state["committing_selection"]:
            return
        state["committing_selection"] = True
        state["open"] = False
        render_dropdown()
        on_select(project)

    def close_dropdown() -> None:
        state["open"] = False
        state["committing_selection"] = False
        render_dropdown()

    def handle_keydown(event: KeyEventArguments) -> None:
        key = event.key
        filtered = visible_projects()
        if key.arrow_down:
            if not state["open"]:
                state["open"] = True
            if filtered:
                state["highlighted_index"] = min(
                    int(state["highlighted_index"]) + 1,
                    len(filtered) - 1,
                )
            render_dropdown()
            return
        if key.arrow_up:
            if not state["open"]:
                state["open"] = True
            if filtered:
                state["highlighted_index"] = max(
                    int(state["highlighted_index"]) - 1,
                    0,
                )
            render_dropdown()
            return
        if key.enter:
            if state["open"] and filtered:
                select_project(filtered[int(state["highlighted_index"])])
            return
        if key.escape:
            close_dropdown()

    def handle_focus() -> None:
        state["open"] = True
        state["filtered"] = filter_project_records(
            ordered_projects,
            str(state["query"]),
        )
        render_dropdown()

    def handle_blur() -> None:
        ui.timer(0.2, close_dropdown, once=True, immediate=False)

    search_input.on("focus", lambda _: handle_focus())
    search_input.on("blur", lambda _: handle_blur())
    search_input.on("keydown", handle_keydown)
    search_input.on(
        "update:model-value",
        lambda _: handle_query_change(),
    )


def open_create_project_dialog(
    *,
    on_created: Callable[[ProjectRecord], None],
) -> None:
    """Open the shared create-project dialog and invoke a callback on success."""
    dialog = ui.dialog()
    with (
        dialog,
        ui.card().classes("w-[520px] dw-panel shadow-none p-6 gap-3") as dialog_card,
    ):
        decorate_modal_card(dialog_card, label="Create project workspace")
        ui.label("Create project workspace").classes("text-lg font-medium dw-text")
        key_input = ui.input("Project key").classes("w-full")
        name_input = ui.input("Display name").classes("w-full")
        description_input = ui.textarea("Description").classes("w-full")
        repository_input = ui.input("Repository URL").classes("w-full")
        branch_input = ui.input("Default branch").classes("w-full")
        error_label = ui.label("").classes("text-xs dw-warning-text")

        def submit_project() -> None:
            try:
                created = create_authorized_ui_project(
                    project_key=key_input.value,
                    display_name=name_input.value,
                    description=description_input.value or None,
                    repository_url=repository_input.value or None,
                    default_branch=branch_input.value or None,
                )
            except (PermissionError, ValueError) as exc:
                error_label.set_text(str(exc))
                return
            dialog.close()
            on_created(created)

        with ui.row().classes("w-full justify-end gap-3 mt-4"):
            cancel_button = ui.button("Cancel", on_click=dialog.close).props(
                "outline no-caps"
            )
            decorate_modal_close(cancel_button)
            ui.button(
                "Create project",
                on_click=submit_project,
                color="primary",
            ).props("unelevated no-caps")
    dialog.open()
