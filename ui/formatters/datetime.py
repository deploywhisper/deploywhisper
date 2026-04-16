"""Datetime formatting helpers for UI surfaces."""

from __future__ import annotations

from datetime import datetime


def format_history_timestamp(value: str) -> str:
    """Convert an ISO timestamp into a compact human-readable label."""
    normalized = value.replace("Z", "+00:00")
    timestamp = datetime.fromisoformat(normalized)
    month = timestamp.strftime("%b")
    day = timestamp.strftime("%d").lstrip("0") or "0"
    year = timestamp.strftime("%Y")
    hour = timestamp.strftime("%I").lstrip("0") or "0"
    minute = timestamp.strftime("%M")
    meridiem = timestamp.strftime("%p")
    return f"{month} {day}, {year} · {hour}:{minute} {meridiem}"
