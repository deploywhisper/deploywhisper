"""Recommendation label styling helpers."""

from __future__ import annotations

from nicegui import ui


def recommendation_text(value: str) -> str:
    """Normalize a stored recommendation value for UI display."""
    return value.upper()


def recommendation_classes(value: str, *, size: str = "sm") -> str:
    """Return semantic utility classes for deployment recommendation text."""
    palette = {
        "go": "text-green-600",
        "no-go": "text-red-600",
        "caution": "text-amber-600",
    }
    text_size = "text-sm" if size == "sm" else "text-base"
    color_class = palette.get(value.lower(), "text-[#1D2420]")
    return f"{text_size} font-bold uppercase tracking-[0.04em] {color_class}"


def render_recommendation_label(value: str, *, size: str = "sm"):
    """Render a consistent deployment recommendation label."""
    return ui.label(recommendation_text(value)).classes(recommendation_classes(value, size=size))
