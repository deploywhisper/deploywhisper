"""Confidence badge helpers."""

from __future__ import annotations

import math

from nicegui import ui


def coerce_confidence(value: object) -> float | None:
    if value is None:
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(confidence) or confidence < 0.0 or confidence > 1.0:
        return None
    return confidence


def confidence_bucket(confidence: float) -> str:
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.60:
        return "medium"
    return "low"


def _confidence_style(bucket: str) -> str:
    palette = {
        "high": ("rgba(83, 194, 107, 0.12)", "#53c26b"),
        "medium": ("rgba(216, 164, 50, 0.12)", "#d8a432"),
        "low": ("rgba(207, 63, 63, 0.12)", "#cf3f3f"),
    }
    bg, color = palette[bucket]
    return (
        f"background:{bg};"
        f"color:{color};"
        f"border:1px solid {bg.replace('0.12', '0.35')};"
        "border-radius:12px;"
        "padding:4px 12px;"
        "font-size:0.75rem;"
        "line-height:1.1;"
        "font-weight:600;"
        "letter-spacing:0.04em;"
        "text-transform:uppercase;"
    )


def render_confidence_badge(confidence: float):
    bucket = confidence_bucket(confidence)
    badge = ui.label(f"{bucket.upper()} CONFIDENCE").style(_confidence_style(bucket))
    badge.props(f'title="Confidence {confidence:.2f}"')
    return badge
