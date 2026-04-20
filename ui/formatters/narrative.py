"""Narrative formatting helpers."""

from __future__ import annotations


def extract_llm_notice(
    warnings: list[str], failure_notice: str | None = None
) -> str | None:
    """Return the highest-signal LLM fallback/connectivity notice from warning strings."""
    if failure_notice:
        return failure_notice
    for warning in warnings:
        lowered = warning.lower()
        if "narrative provider unavailable" in lowered:
            return warning
    for warning in warnings:
        lowered = warning.lower()
        if "llm severity assessment unavailable" in lowered:
            return warning
    return None
