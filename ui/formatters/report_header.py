"""Verdict-first report header signal helpers."""

from __future__ import annotations

from typing import Any

from services.confidence_ledger import (
    evidence_law_status as evidence_law_status,
    severe_findings as severe_findings,
)
from ui.formatters.confidence import coerce_confidence, confidence_bucket


def report_verdict_text(report: dict[str, Any]) -> str:
    recommendation = str(report.get("recommendation") or "review").upper()
    severity = str(report.get("severity") or "unknown").upper()
    return f"{recommendation} · {severity} RISK"


def report_confidence_text(report: dict[str, Any]) -> str:
    confidence = coerce_confidence(report.get("confidence"))
    if confidence is None:
        return "Unavailable"
    return f"{confidence_bucket(confidence).title()} ({confidence:.2f})"


def next_action_text(report: dict[str, Any], evidence_status: str) -> str:
    if evidence_status == "Needs review":
        return "Review linked evidence before treating severe claims as release risk."
    recommendation = str(report.get("recommendation") or "").lower()
    if recommendation == "no-go":
        return "Review linked evidence and rollback readiness before release."
    if recommendation == "caution":
        return "Review linked evidence and resolve open context before release."
    return "Continue normal release review; this advisory is not an approval."
