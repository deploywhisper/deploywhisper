"""Shared risk label styling helpers."""

from __future__ import annotations

from nicegui import ui

RISK_TOKENS = {
    "low": {"color": "#53c26b", "bg": "rgba(83, 194, 107, 0.12)"},
    "medium": {"color": "#d8a432", "bg": "rgba(216, 164, 50, 0.12)"},
    "high": {"color": "#d87a30", "bg": "rgba(216, 122, 48, 0.12)"},
    "critical": {"color": "#cf3f3f", "bg": "rgba(207, 63, 63, 0.12)"},
    "uncertain": {"color": "#c3a04a", "bg": "rgba(195, 160, 74, 0.12)"},
}


def risk_token(level: str) -> dict[str, str]:
    return RISK_TOKENS.get(level.lower(), RISK_TOKENS["uncertain"])


def style_risk_badge(level: str) -> str:
    token = risk_token(level)
    border = f"1px solid {token['bg'].replace('0.12', '0.35')}" if level.lower() != "uncertain" else "1px dashed rgba(195, 160, 74, 0.45)"
    return (
        f"background:{token['bg']};"
        f"color:{token['color']};"
        f"border:{border};"
        "border-radius:12px;"
        "padding:4px 12px;"
        "font-size:0.75rem;"
        "line-height:1.1;"
        "font-weight:600;"
        "letter-spacing:0.04em;"
        "text-transform:uppercase;"
    )


def render_risk_badge(level: str, text: str | None = None):
    label = text or level.upper()
    return ui.label(label).style(style_risk_badge(level))
