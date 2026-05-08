"""Normalized change table rendering."""

from __future__ import annotations

from nicegui import ui

from parsers.base import ParseBatchResult, is_non_mutating_action


def _compact_list(value: object, *, limit: int | None = 4) -> str | None:
    if not isinstance(value, list) or not value:
        return None
    items = [str(item) for item in value if str(item)]
    if not items:
        return None
    if limit is None:
        return ", ".join(items)
    visible = items[:limit]
    suffix = f" (+{len(items) - limit} more)" if len(items) > limit else ""
    return ", ".join(visible) + suffix


def format_change_metadata_lines(metadata: dict | None) -> list[str]:
    """Return compact UI lines for parser-normalized Terraform metadata."""
    if not isinstance(metadata, dict) or not metadata:
        return []

    lines: list[str] = []
    module_address = metadata.get("module_address")
    if module_address:
        lines.append(f"Module: {module_address}")
    provider_name = metadata.get("provider_name")
    if provider_name:
        lines.append(f"Provider: {provider_name}")
    versions = [
        str(value)
        for value in (
            metadata.get("plan_format_version"),
            metadata.get("terraform_version"),
        )
        if value
    ]
    if versions:
        lines.append("Terraform metadata: " + " / ".join(versions))

    for label, key in (
        ("Actions", "actions"),
        ("Replace paths", "replace_paths"),
        ("Unknown after apply", "unknown_after_apply"),
        ("Redacted fields", "redacted_fields"),
        ("Unsupported fields", "unsupported_fields"),
        ("Unsupported plan fields", "plan_unsupported_fields"),
    ):
        rendered = _compact_list(
            metadata.get(key),
            limit=None
            if key
            in {"redacted_fields", "unsupported_fields", "plan_unsupported_fields"}
            else 4,
        )
        if rendered:
            lines.append(f"{label}: {rendered}")
    return lines


def _hidden_change_metadata_lines(
    parse_batch: ParseBatchResult,
    *,
    visible_change_keys: set[tuple[str, str]],
) -> list[str]:
    lines: list[str] = []
    seen_lines: set[str] = set()

    for file_result in parse_batch.files:
        if file_result.status != "parsed":
            continue
        for change in file_result.changes:
            if change.tool != "terraform":
                continue
            if (change.source_file, change.change_id) in visible_change_keys:
                continue
            for metadata_line in format_change_metadata_lines(change.metadata):
                rendered = f"{file_result.file_name}: {metadata_line}"
                if rendered in seen_lines:
                    continue
                seen_lines.add(rendered)
                lines.append(rendered)

    return lines


def render_change_table(parse_batch: ParseBatchResult) -> None:
    """Render a compact normalized change table for review."""
    with ui.card().classes("w-full dw-panel shadow-none"):
        ui.label("Normalized changes").classes("text-lg font-medium dw-text")

        changes = [
            change
            for file_result in parse_batch.files
            if file_result.status == "parsed"
            for change in file_result.changes
            if not (
                change.tool == "terraform" and is_non_mutating_action(change.action)
            )
        ]
        visible_change_keys = {
            (change.source_file, change.change_id) for change in changes
        }
        for metadata_line in _hidden_change_metadata_lines(
            parse_batch,
            visible_change_keys=visible_change_keys,
        ):
            ui.label(metadata_line).classes("text-xs dw-muted leading-5")

        if not changes:
            ui.label("No mutating normalized changes available.").classes(
                "text-sm dw-muted"
            )
            return

        with ui.column().classes("w-full gap-2"):
            for change in changes:
                with ui.row().classes(
                    "w-full items-start justify-between gap-4 dw-panel-soft px-3 py-3"
                ):
                    with ui.column().classes("gap-1"):
                        ui.label(change.summary).classes("text-sm font-medium dw-text")
                        ui.label(
                            f"{change.source_file} · {change.resource_id}"
                        ).classes("text-xs dw-muted")
                        for metadata_line in format_change_metadata_lines(
                            change.metadata
                        ):
                            ui.label(metadata_line).classes(
                                "text-xs dw-muted leading-5"
                            )
                    ui.label(f"{change.tool} · {change.action}").classes(
                        "text-xs uppercase dw-muted"
                    )
