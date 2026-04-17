"""Rollback plan rendering."""

from __future__ import annotations

from analysis.rollback_planner import RollbackPlan
from nicegui import ui


def render_rollback_plan(plan: RollbackPlan) -> None:
    """Render an ordered rollback timeline."""
    with ui.card().classes("w-full dw-panel shadow-none"):
        ui.label("Rollback plan").classes("text-lg font-medium dw-text")
        ui.label(f"Complexity: {plan.complexity}").classes("text-sm dw-muted")
        if plan.warning:
            ui.label(plan.warning).classes("text-xs dw-warning-text")
        with ui.column().classes("w-full gap-3"):
            for step in plan.steps:
                with ui.row().classes("w-full items-start gap-3 dw-panel-soft px-3 py-3"):
                    ui.label(str(step.order)).classes("text-sm font-medium dw-accent-text")
                    with ui.column().classes("gap-1"):
                        title = step.title + (" · critical" if step.critical else "")
                        ui.label(title).classes("text-sm font-medium dw-text")
                        ui.label(step.detail).classes("text-sm dw-muted")
