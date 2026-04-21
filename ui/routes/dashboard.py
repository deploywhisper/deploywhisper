"""Dashboard shell rendering."""

from __future__ import annotations

from nicegui import ui

from services.report_service import fetch_active_dashboard_report
from ui.components.upload_panel import build_upload_panel
from ui.components.verdict_card import render_verdict_card
from ui.routes.history import build_history_page
from ui.routes.settings import build_settings_page
from services.report_service import fetch_dashboard_briefing, fetch_dashboard_stats
from ui.theme import apply_theme, build_navigation_shell


def _briefing_summary_line(saved_briefings: int, high_focus: int) -> str:
    saved_label = "briefing" if saved_briefings == 1 else "briefings"
    saved_verb = "is" if saved_briefings == 1 else "are"
    focus_label = "report is" if high_focus == 1 else "reports are"
    if saved_briefings == 0:
        return "No saved briefings yet. Upload artifacts to start building operational history."
    return (
        f"{saved_briefings} saved {saved_label} {saved_verb} shaping the current advisory view. "
        f"{high_focus} {focus_label} currently high or critical."
    )


def build_dashboard() -> None:
    """Render the primary DeployWhisper workspace."""
    apply_theme()
    build_navigation_shell("dashboard")

    with ui.column().classes("dw-main-content dw-shell gap-5"):
        briefing_mount = None
        stats_mount = None
        result_mount = None
        deploy_review_card = None
        hero_mount = None

        def render_briefing() -> None:
            nonlocal briefing_mount
            briefing = fetch_dashboard_briefing()
            severity_counts = briefing["severity_counts"]
            total_reports = max(briefing["saved_briefings"], 1)
            segments = (
                ("Low", severity_counts["low"], "var(--dw-green)"),
                ("Medium", severity_counts["medium"], "var(--dw-amber)"),
                ("High", severity_counts["high"], "var(--dw-high)"),
                ("Critical", severity_counts["critical"], "var(--dw-red)"),
            )

            briefing_mount.clear()
            with briefing_mount:
                with ui.card().classes("dw-panel shadow-none w-full h-full p-0"):
                    with ui.column().classes("dw-preview gap-4 h-full justify-between"):
                        with ui.row().classes("items-start justify-between gap-4"):
                            with ui.column().classes("gap-2 min-w-0 flex-1"):
                                ui.label("Deployment briefing").classes(
                                    "dw-preview-kicker"
                                )
                                ui.label(
                                    "High-context risk analysis before infrastructure changes go live"
                                ).classes("dw-preview-title")
                            with ui.column().classes(
                                "dw-preview-score items-center justify-center text-center shrink-0"
                            ):
                                ui.label(str(briefing["weighted_focus_score"])).classes(
                                    "dw-preview-score-value"
                                )
                                ui.label("Risk focus").classes("dw-preview-score-label")
                        ui.label(
                            _briefing_summary_line(
                                briefing["saved_briefings"], briefing["high_focus"]
                            )
                        ).classes("dw-preview-body")
                        with ui.row().classes("w-full gap-3 flex-wrap"):
                            for value, label in (
                                (str(briefing["total_files_scanned"]), "Files scanned"),
                                (str(briefing["saved_briefings"]), "Saved briefings"),
                                (str(briefing["high_focus"]), "High focus"),
                            ):
                                with ui.column().classes(
                                    "dw-mini-stat flex-1 min-w-[92px]"
                                ):
                                    ui.label(value).classes(
                                        "font-semibold text-lg dw-text"
                                    )
                                    ui.label(label).classes(
                                        "text-xs dw-muted uppercase tracking-[0.1em]"
                                    )
                        with ui.column().classes("gap-2"):
                            ui.label(briefing["latest_summary"]).classes(
                                "text-sm dw-muted leading-6"
                            )
                            with ui.row().classes("w-full gap-1 items-center"):
                                for _, value, color in segments:
                                    width = (
                                        max(8, round((value / total_reports) * 100))
                                        if briefing["saved_briefings"]
                                        else 25
                                    )
                                    ui.element("span").style(
                                        f"height: 10px; width: {width}%; border-radius: 999px; background: {color}; display: inline-block;"
                                    )
                            with ui.row().classes("w-full gap-3 flex-wrap"):
                                for label, value, color_class in (
                                    ("Low", severity_counts["low"], "dw-success-text"),
                                    (
                                        "Medium",
                                        severity_counts["medium"],
                                        "dw-warning-text",
                                    ),
                                    ("High", severity_counts["high"], "dw-accent-text"),
                                    (
                                        "Critical",
                                        severity_counts["critical"],
                                        "dw-danger-text",
                                    ),
                                ):
                                    with ui.row().classes("items-center gap-2"):
                                        ui.label(label).classes(
                                            f"text-xs font-semibold uppercase tracking-[0.08em] {color_class}"
                                        )
                                        ui.label(str(value)).classes("text-xs dw-muted")

        def render_stats() -> None:
            stats = fetch_dashboard_stats()
            stats_mount.clear()
            with stats_mount:
                with ui.card().classes("w-full dw-panel shadow-none p-4"):
                    ui.label("Analysis snapshot").classes("dw-eyebrow")
                    with ui.row().classes("w-full items-stretch gap-2 flex-wrap mt-3"):
                        metrics = [
                            ("Files scanned", stats["total_files_scanned"], "dw-text"),
                            ("Low", stats["severity_counts"]["low"], "dw-success-text"),
                            (
                                "Medium",
                                stats["severity_counts"]["medium"],
                                "dw-warning-text",
                            ),
                            (
                                "High",
                                stats["severity_counts"]["high"],
                                "dw-accent-text",
                            ),
                            (
                                "Critical",
                                stats["severity_counts"]["critical"],
                                "dw-danger-text",
                            ),
                        ]
                        for label, value, color_class in metrics:
                            with ui.card().classes(
                                "dw-panel-soft shadow-none min-w-[120px] flex-1"
                            ):
                                with ui.column().classes("gap-1 p-3"):
                                    ui.label(str(value)).classes(
                                        f"text-2xl font-semibold {color_class}"
                                    )
                                    ui.label(label).classes(
                                        "text-[11px] font-semibold uppercase tracking-[0.08em] dw-muted"
                                    )

        def refresh_dashboard() -> None:
            render_hero()
            render_briefing()
            render_stats()

        def render_hero() -> None:
            active_report = fetch_active_dashboard_report()
            hero_mount.clear()
            with hero_mount:
                if active_report is not None:
                    render_verdict_card(active_report)
                    ui.label(
                        "Verdict, top risk, and trust signals stay above the detailed review sections so release decisions start with the summary."
                    ).classes("dw-body max-w-3xl")
                    return

                ui.label("Deploy review").classes("dw-eyebrow")
                ui.html(
                    '<div class="dw-dashboard-headline mt-3">'
                    '<span class="dw-gradient">Know the risk before</span><br>'
                    '<span class="dw-gradient">you hit</span> <span class="dw-accent-text">deploy</span>'
                    "</div>"
                )
                ui.label(
                    "Upload artifacts and generate one advisory briefing. One screen for verdict, blast radius, "
                    "rollback guidance, incident similarity, and a human-readable narrative before release."
                ).classes("dw-body mt-4 max-w-3xl")

        stats_mount = ui.column().classes("w-full")
        with ui.row().classes("w-full items-stretch gap-5 flex-wrap"):
            with ui.column().classes("flex-1 min-w-[320px] gap-4 self-stretch"):
                deploy_review_card = ui.card().classes(
                    "dw-panel dw-dashboard-hero shadow-none w-full p-6"
                )
                with deploy_review_card:
                    hero_mount = ui.column().classes("w-full gap-3")
            briefing_mount = ui.column().classes(
                "w-full max-w-[390px] min-w-[320px] self-stretch"
            )

        result_mount = ui.column().classes("w-full gap-4")

        with deploy_review_card:
            build_upload_panel(
                on_analysis_complete=refresh_dashboard,
                embedded=True,
                result_container=result_mount,
            )

        refresh_dashboard()


@ui.page("/history")
def history_page() -> None:
    build_history_page()


@ui.page("/settings")
def settings_page() -> None:
    build_settings_page()
