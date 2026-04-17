"""Normalized change table rendering."""

from __future__ import annotations

from nicegui import ui

from parsers.base import ParseBatchResult


def render_change_table(parse_batch: ParseBatchResult) -> None:
    """Render a compact normalized change table for review."""
    with ui.card().classes("w-full dw-panel shadow-none"):
        ui.label("Normalized changes").classes("text-lg font-medium dw-text")

        changes = [
            change
            for file_result in parse_batch.files
            if file_result.status == "parsed"
            for change in file_result.changes
        ]
        if not changes:
            ui.label("No normalized changes available.").classes("text-sm dw-muted")
            return

        with ui.column().classes("w-full gap-2"):
            for change in changes:
                with ui.row().classes("w-full items-start justify-between gap-4 dw-panel-soft px-3 py-3"):
                    with ui.column().classes("gap-1"):
                        ui.label(change.summary).classes("text-sm font-medium dw-text")
                        ui.label(f"{change.source_file} · {change.resource_id}").classes("text-xs dw-muted")
                    ui.label(f"{change.tool} · {change.action}").classes("text-xs uppercase dw-muted")
