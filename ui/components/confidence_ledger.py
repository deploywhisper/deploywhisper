"""Confidence-ledger rendering for report reasoning details."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from services.confidence_ledger import (
    build_confidence_ledger,
    normalize_confidence_ledger_payload,
)
from ui.components.review_accessibility import decorate_review_section


def _render_list(title: str, items: list[str]) -> None:
    with ui.card().classes("dw-panel-soft shadow-none min-w-[240px] flex-1"):
        with ui.column().classes("gap-2 p-4"):
            ui.label(title).classes(
                "text-[11px] font-semibold uppercase tracking-[0.08em] dw-muted"
            )
            for item in items:
                ui.label(item).classes("text-sm dw-text leading-6")


def _ledger_payload(report: dict[str, Any]) -> dict[str, list[str]]:
    payload = report.get("confidence_ledger")
    if isinstance(payload, dict):
        return normalize_confidence_ledger_payload(
            payload,
            fallback_ledger=build_confidence_ledger(report),
        )
    return build_confidence_ledger(report)


def render_confidence_ledger(report: dict[str, Any]) -> None:
    """Render confidence factors and why-not-lower/higher reasoning."""
    ledger = _ledger_payload(report)
    with ui.card().classes("w-full dw-panel shadow-none p-5") as ledger_card:
        decorate_review_section(
            ledger_card,
            section="confidence-ledger",
            label="Confidence ledger",
        )
        with ui.column().classes("gap-4"):
            with ui.column().classes("gap-1"):
                ui.label("Confidence ledger").classes(
                    "text-lg font-medium dw-text"
                ).props("role=heading aria-level=2")
                ui.label(
                    "Reasoning details that explain the verdict using persisted evidence, contributors, confidence, and context quality."
                ).classes("text-sm dw-muted leading-6")
            with ui.row().classes("w-full gap-3 flex-wrap"):
                _render_list(
                    "Contributors",
                    ledger["contributors"]
                    or ["No resource-level contributors were recorded."],
                )
                _render_list(
                    "Confidence factors",
                    ledger["confidence_factors"]
                    or ["No confidence factors were recorded."],
                )
            with ui.row().classes("w-full gap-3 flex-wrap"):
                _render_list(
                    "Why not lower",
                    ledger["why_not_lower"]
                    or ["No why-not-lower reasoning was recorded."],
                )
                _render_list(
                    "Why not higher",
                    ledger["why_not_higher"]
                    or ["No why-not-higher reasoning was recorded."],
                )
                _render_list(
                    "Uncertainty drivers",
                    ledger["uncertainty_drivers"]
                    or ["No uncertainty drivers were recorded."],
                )
