"""Dashboard shell rendering."""

from __future__ import annotations

from nicegui import ui

from ui.components.upload_panel import build_upload_panel
from ui.routes.history import build_history_page
from ui.routes.settings import build_settings_page
from services.report_service import fetch_dashboard_stats
from ui.theme import apply_theme, build_navigation_shell, build_page_header


def build_dashboard() -> None:
    """Render the primary DeployWhisper workspace."""
    apply_theme()
    build_navigation_shell("dashboard")

    with ui.column().classes("dw-main-content dw-shell gap-5"):
        stats_card = ui.card().classes("w-full dw-panel shadow-none p-4")

        def render_stats() -> None:
            stats = fetch_dashboard_stats()
            stats_card.clear()
            with stats_card:
                ui.label("Analysis snapshot").classes("dw-eyebrow")
                with ui.row().classes("w-full items-stretch gap-3 flex-wrap mt-2"):
                    metrics = [
                        ("Files scanned", stats["total_files_scanned"], "text-[#1D2420]"),
                        ("Low", stats["severity_counts"]["low"], "text-[#2E9E62]"),
                        ("Medium", stats["severity_counts"]["medium"], "text-[#C58A18]"),
                        ("High", stats["severity_counts"]["high"], "text-[#D97706]"),
                        ("Critical", stats["severity_counts"]["critical"], "text-[#C24141]"),
                    ]
                    for label, value, color_class in metrics:
                        with ui.card().classes("min-w-[120px] flex-1 border border-[#D8DDD4] shadow-none bg-[#FAFBF8]"):
                            with ui.column().classes("items-center gap-1 p-4"):
                                ui.label(str(value)).classes(f"text-2xl font-semibold {color_class}")
                                ui.label(label).classes("text-xs uppercase tracking-[0.08em] dw-muted")

        render_stats()
        with ui.card().classes("w-full dw-panel shadow-none"):
            build_page_header(
                eyebrow="Deploy review",
                title="Upload artifacts and generate one advisory briefing",
                subtitle=(
                    "One screen for verdict, blast radius, rollback guidance, incident similarity, "
                    "and human-readable narrative before release."
                ),
            )
            with ui.row().classes("items-center gap-4 mt-4 flex-wrap"):
                for label, color in (
                    ("Low", "#2e9e62"),
                    ("Medium", "#c58a18"),
                    ("High", "#d97706"),
                    ("Critical", "#c24141"),
                ):
                    with ui.row().classes("items-center gap-2"):
                        ui.element("span").style(
                            f"width: 8px; height: 8px; border-radius: 999px; background: {color}; display: inline-block;"
                        )
                        ui.label(label).classes("text-xs dw-muted")
        build_upload_panel(on_analysis_complete=render_stats)


@ui.page("/history")
def history_page() -> None:
    build_history_page()


@ui.page("/settings")
def settings_page() -> None:
    build_settings_page()
