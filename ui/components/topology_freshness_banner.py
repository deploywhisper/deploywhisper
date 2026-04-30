"""Prominent topology freshness callout for report surfaces."""

from __future__ import annotations

from nicegui import ui

from ui.formatters.topology_freshness import (
    TOPOLOGY_MANAGEMENT_LINK,
    topology_freshness_age_text,
    topology_freshness_badge_text,
    topology_freshness_level,
    topology_freshness_supporting_text,
)


def _banner_style(level: str) -> str:
    palette = {
        "unknown": ("rgba(69, 81, 99, 0.06)", "rgba(69, 81, 99, 0.18)"),
        "current": ("rgba(83, 194, 107, 0.1)", "rgba(83, 194, 107, 0.28)"),
        "stale": ("rgba(216, 164, 50, 0.12)", "rgba(216, 164, 50, 0.32)"),
        "critical": ("rgba(207, 63, 63, 0.12)", "rgba(207, 63, 63, 0.32)"),
    }
    background, border = palette[level]
    return f"background:{background};border:1px solid {border};border-radius:18px;"


def _badge_style(level: str) -> str:
    palette = {
        "unknown": ("rgba(69, 81, 99, 0.1)", "#455163", "rgba(69, 81, 99, 0.25)"),
        "current": ("rgba(83, 194, 107, 0.12)", "#53c26b", "rgba(83, 194, 107, 0.35)"),
        "stale": ("rgba(216, 164, 50, 0.12)", "#d8a432", "rgba(216, 164, 50, 0.35)"),
        "critical": ("rgba(207, 63, 63, 0.12)", "#cf3f3f", "rgba(207, 63, 63, 0.35)"),
    }
    background, color, border = palette[level]
    return (
        f"background:{background};"
        f"color:{color};"
        f"border:1px solid {border};"
        "border-radius:999px;"
        "padding:4px 10px;"
        "font-size:0.72rem;"
        "line-height:1.1;"
        "font-weight:700;"
        "letter-spacing:0.04em;"
        "text-transform:uppercase;"
    )


def render_topology_freshness_banner(
    context: dict | None,
    *,
    link_target: str = TOPOLOGY_MANAGEMENT_LINK,
    show_link: bool = True,
    link_label: str = "Manage topology",
) -> None:
    """Render the report-native topology freshness callout."""
    level = topology_freshness_level(context)
    with ui.card().classes("w-full shadow-none").style(_banner_style(level)):
        with ui.column().classes("gap-2 p-4"):
            with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
                with ui.column().classes("gap-1 min-w-0 flex-1"):
                    ui.label("Topology freshness").classes(
                        "text-[11px] font-semibold uppercase tracking-[0.08em] dw-muted"
                    )
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        ui.label(topology_freshness_age_text(context)).classes(
                            "text-base font-semibold dw-text"
                        )
                        ui.label(topology_freshness_badge_text(context)).style(
                            _badge_style(level)
                        )
                if show_link:
                    ui.link(link_label, link_target).classes(
                        "text-sm font-semibold dw-accent-text"
                    )
            ui.label(topology_freshness_supporting_text(context)).classes(
                "text-sm dw-muted leading-6"
            )
