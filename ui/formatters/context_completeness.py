"""Context completeness badge helpers."""

from __future__ import annotations

import math

from nicegui import ui


def context_number(value: object, default: float = 0.0) -> float:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric_value):
        return default
    return max(0.0, min(numeric_value, 1.0))


def context_score(context: dict | None) -> float:
    if not context:
        return 0.0
    return round(context_number(context.get("context_score"), 0.0), 2)


def context_completeness_bucket(score: float) -> str:
    if score >= 0.85:
        return "strong"
    if score >= 0.60:
        return "partial"
    return "limited"


def _context_todo_items(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def context_completeness_bucket_for_context(context: dict | None) -> str:
    if context and (
        bool(context.get("insufficient_context"))
        or str(context.get("confidence_level", "")).lower() == "low"
        or bool(str(context.get("uncertainty") or "").strip())
        or bool(_context_todo_items(context.get("context_todos")))
    ):
        return "limited"
    return context_completeness_bucket(context_score(context))


def _context_style(bucket: str) -> str:
    palette = {
        "strong": ("rgba(83, 194, 107, 0.12)", "#53c26b"),
        "partial": ("rgba(216, 164, 50, 0.12)", "#d8a432"),
        "limited": ("rgba(207, 63, 63, 0.12)", "#cf3f3f"),
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


def render_context_completeness_badge(context: dict | None):
    score = context_score(context)
    bucket = context_completeness_bucket_for_context(context)
    bucket_label = {
        "strong": "Strong context",
        "partial": "Partial context",
        "limited": "Limited context",
    }[bucket]
    badge = ui.label(f"{bucket_label.upper()} · {score:.2f}").style(
        _context_style(bucket)
    )
    parser_success = context_number((context or {}).get("parser_success_rate"), 1.0)
    freshness = (context or {}).get("topology_freshness_days")
    freshness_text = "unknown" if freshness is None else str(freshness)
    badge.props(
        'title="'
        f"Context score {score:.2f}; parser success {parser_success:.2f}; topology freshness {freshness_text} day(s)"
        '"'
    )
    return badge
