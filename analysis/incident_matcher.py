"""Incident matching access helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import re

from pydantic import BaseModel, Field

from parsers.base import UnifiedChange
from services.incident_service import get_incident_records


class IncidentMatch(BaseModel):
    incident_id: int = Field(..., description="Matched incident identifier")
    title: str = Field(..., description="Incident title")
    severity: str = Field(..., description="Incident severity")
    source_file: str = Field(..., description="Incident source file")
    incident_date: str | None = Field(default=None, description="Incident date if available")
    similarity: float = Field(..., description="Similarity score between 0 and 1")
    summary: str = Field(..., description="Short operational explanation")


def load_incident_candidates() -> list[dict]:
    """Return stored incident records for future similarity matching."""
    return get_incident_records()


TOKEN_PATTERN = re.compile(r"[a-z0-9_./-]+", re.IGNORECASE)
STOP_WORDS = {
    "terraform",
    "kubernetes",
    "deployment",
    "resource",
    "resources",
    "changed",
    "change",
    "included",
    "analysis",
    "set",
    "stage",
    "modify",
    "create",
    "delete",
    "destroy",
    "service",
}


def _tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if len(token) > 2 and token.lower() not in STOP_WORDS
    }


def _severity_bonus(severity: str) -> float:
    severity = severity.lower()
    if severity == "critical":
        return 0.08
    if severity == "high":
        return 0.05
    if severity == "medium":
        return 0.02
    return 0.0


def _recency_bonus(incident_date: str | None) -> float:
    if not incident_date:
        return 0.0
    try:
        parsed = datetime.fromisoformat(incident_date.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    age_days = max((datetime.now(UTC) - parsed).days, 0)
    if age_days <= 30:
        return 0.06
    if age_days <= 180:
        return 0.03
    if age_days <= 365:
        return 0.015
    return 0.0


def find_incident_matches(changes: list[UnifiedChange], min_similarity: float = 0.2) -> list[IncidentMatch]:
    """Return incident matches ranked by simple token overlap."""
    candidates = load_incident_candidates()
    if not candidates:
        return []

    change_text = " ".join(
        " ".join([change.source_file, change.tool, change.resource_id, change.summary]) for change in changes
    )
    change_tokens = _tokenize(change_text)
    if not change_tokens:
        return []

    matches: list[IncidentMatch] = []
    for candidate in candidates:
        incident_text = " ".join(
            [
                candidate.get("title", ""),
                candidate.get("severity", ""),
                candidate.get("source_file", ""),
                candidate.get("content", ""),
            ]
        )
        incident_tokens = _tokenize(incident_text)
        if not incident_tokens:
            continue
        overlap = change_tokens & incident_tokens
        union = change_tokens | incident_tokens
        similarity = len(overlap) / max(len(union), 1)
        similarity = min(
            1.0,
            similarity + _severity_bonus(candidate.get("severity", "unknown")) + _recency_bonus(candidate.get("incident_date")),
        )
        if similarity < min_similarity:
            continue
        matches.append(
            IncidentMatch(
                incident_id=candidate["id"],
                title=candidate["title"],
                severity=candidate["severity"],
                source_file=candidate["source_file"],
                incident_date=candidate.get("incident_date"),
                similarity=round(similarity, 2),
                summary=(
                    f"Similar to prior incident '{candidate['title']}' "
                    f"({candidate['severity']}) with {round(similarity * 100)}% token overlap."
                ),
            )
        )

    matches.sort(key=lambda match: match.similarity, reverse=True)
    return matches
