"""Deterministic vs inferred badge helpers."""

from __future__ import annotations

from nicegui import ui


def render_determinism_badge(deterministic: bool):
    if deterministic:
        label = "Deterministic"
        bg = "rgba(83, 194, 107, 0.12)"
        color = "#53c26b"
    else:
        label = "Inferred"
        bg = "rgba(216, 164, 50, 0.12)"
        color = "#d8a432"
    return ui.label(label.upper()).style(
        f"background:{bg};"
        f"color:{color};"
        f"border:1px solid {bg.replace('0.12', '0.35')};"
        "border-radius:12px;"
        "padding:4px 10px;"
        "font-size:0.72rem;"
        "line-height:1.1;"
        "font-weight:600;"
        "letter-spacing:0.04em;"
        "text-transform:uppercase;"
    )
