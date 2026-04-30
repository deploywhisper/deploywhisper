"""Helpers for report-facing topology freshness messaging."""

from __future__ import annotations

from typing import Literal

from services.topology_service import STALE_AFTER_DAYS

CRITICAL_TOPOLOGY_AGE_DAYS = 90
TOPOLOGY_MANAGEMENT_LINK = "/settings#topology-context"

TopologyFreshnessLevel = Literal["unknown", "current", "stale", "critical"]


def topology_freshness_days(context: dict | None) -> int | None:
    """Return normalized topology age in days when it is available."""
    freshness = (context or {}).get("topology_freshness_days")
    if freshness is None:
        return None
    try:
        value = int(freshness)
    except (TypeError, ValueError):
        return None
    return max(value, 0)


def topology_freshness_level(context: dict | None) -> TopologyFreshnessLevel:
    """Bucket topology freshness into user-facing review states."""
    freshness_days = topology_freshness_days(context)
    if freshness_days is None:
        return "unknown"
    if freshness_days >= CRITICAL_TOPOLOGY_AGE_DAYS:
        return "critical"
    if freshness_days >= STALE_AFTER_DAYS:
        return "stale"
    return "current"


def topology_freshness_age_text(context: dict | None) -> str:
    """Render the topology age copy used across report surfaces."""
    freshness_days = topology_freshness_days(context)
    if freshness_days is None:
        return "Unknown age"
    if freshness_days == 0:
        return "Imported today"
    if freshness_days == 1:
        return "1 day old"
    return f"{freshness_days} days old"


def topology_freshness_badge_text(context: dict | None) -> str:
    """Return the short alert label used for freshness badges."""
    return {
        "unknown": "UNKNOWN",
        "current": "CURRENT",
        "stale": f"STALE {STALE_AFTER_DAYS}+",
        "critical": f"CRITICAL {CRITICAL_TOPOLOGY_AGE_DAYS}+",
    }[topology_freshness_level(context)]


def topology_freshness_supporting_text(context: dict | None) -> str:
    """Explain how freshness should affect blast-radius trust."""
    return {
        "unknown": "Blast radius is missing a usable topology age signal.",
        "current": "Blast radius is backed by a recent topology snapshot.",
        "stale": "Blast radius should be discounted until topology is refreshed.",
        "critical": "Blast radius should be treated as high-uncertainty until topology is refreshed.",
    }[topology_freshness_level(context)]
