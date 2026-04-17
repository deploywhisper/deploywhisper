"""Blast radius panel rendering."""

from __future__ import annotations

from analysis.blast_radius import BlastRadiusResult
from nicegui import ui


def render_blast_radius_panel(result: BlastRadiusResult) -> None:
    """Render a legibility-first blast radius panel."""
    with ui.card().classes("w-full dw-panel shadow-none"):
        ui.label("Blast radius").classes("text-lg font-medium dw-text")
        ui.label(
            f"{result.direct_count} direct · {result.transitive_count} transitive affected services"
        ).classes("text-sm dw-muted")
        ui.label("Legend: depth 0 = directly affected, depth 1+ = transitively affected.").classes(
            "text-xs dw-muted"
        )
        if result.warning:
            ui.label(result.warning).classes("text-xs dw-warning-text")

        if not result.affected:
            ui.label("No downstream dependencies found.").classes("text-sm dw-muted")
            return

        with ui.column().classes("w-full gap-2"):
            for node in result.affected:
                ui.label(f"{node.label} · depth {node.depth}").classes("text-sm dw-text")
