"""Rollback plan rendering."""

from __future__ import annotations

import json

from analysis.rollback_planner import RollbackPlan, build_rollback_copy_text
from nicegui import ui


async def copy_rollback_plan_to_clipboard(plan: RollbackPlan) -> None:
    """Copy the rollback plan and surface the real browser outcome."""
    result = await ui.run_javascript(
        """
        (async () => {
            try {
                if (!navigator.clipboard || !window.isSecureContext) {
                    return {
                        ok: false,
                        message: 'Clipboard copy requires a secure browser context.',
                    };
                }
                await navigator.clipboard.writeText(%s);
                return {ok: true};
            } catch (error) {
                return {
                    ok: false,
                    message: String(error && error.message ? error.message : error),
                };
            }
        })()
        """
        % json.dumps(build_rollback_copy_text(plan)),
        timeout=2.0,
    )
    if result and result.get("ok"):
        ui.notify("Rollback plan copied.", color="positive")
        return
    ui.notify(
        "Unable to copy rollback plan."
        + (
            f" {result.get('message')}"
            if isinstance(result, dict) and result.get("message")
            else ""
        ),
        color="warning",
    )


def render_rollback_plan(plan: RollbackPlan) -> None:
    """Render an ordered rollback timeline."""

    with ui.card().classes("w-full dw-panel shadow-none"):
        with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
            with ui.column().classes("gap-1 min-w-0 flex-1"):
                ui.label("Rollback plan").classes("text-lg font-medium dw-text")
                ui.label(
                    f"Complexity: {plan.complexity_score}/5 ({plan.complexity})"
                ).classes("text-sm dw-muted")
                ui.label(plan.complexity_explanation).classes(
                    "text-sm dw-muted leading-6"
                )
            ui.button(
                "Copy full plan", on_click=lambda: copy_rollback_plan_to_clipboard(plan)
            ).props("outline no-caps icon=content_copy")
        if plan.warning:
            ui.label(plan.warning).classes("text-xs dw-warning-text")
        with ui.column().classes("w-full gap-3"):
            for step in plan.steps:
                with ui.row().classes(
                    "w-full items-start gap-3 dw-panel-soft px-3 py-3"
                ):
                    with ui.column().classes("items-center gap-1 pt-1"):
                        ui.label(str(step.order)).classes(
                            "text-sm font-medium dw-accent-text"
                        )
                        ui.label(f"~{step.estimated_minutes} min").classes(
                            "text-[11px] dw-muted"
                        )
                    with ui.column().classes("gap-2 min-w-0 flex-1"):
                        with ui.row().classes("items-center gap-2 flex-wrap"):
                            ui.label(step.title).classes("text-sm font-medium dw-text")
                            if step.critical:
                                ui.label("Critical path").classes(
                                    "text-[11px] font-semibold uppercase tracking-[0.08em] dw-accent-text"
                                )
                        ui.label(step.detail).classes("text-sm dw-muted")
