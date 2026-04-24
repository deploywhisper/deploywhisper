"""Shared skill analytics snapshot loading."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ANALYTICS_PATH = REPO_ROOT / "data" / "skill-analytics.json"


class SkillAnalyticsEntry(BaseModel):
    """Snapshot-backed analytics for one skill."""

    install_count: int = Field(default=0, ge=0)
    star_count: int = Field(default=0, ge=0)
    active_issue_count: int = Field(default=0, ge=0)


class SkillAnalyticsSnapshot(BaseModel):
    """Analytics snapshot shared by API, UI, and CLI surfaces."""

    generated_at: str = Field(..., description="When the snapshot was last refreshed.")
    skills: dict[str, SkillAnalyticsEntry] = Field(default_factory=dict)


def load_skill_analytics_snapshot(
    path: Path = SKILL_ANALYTICS_PATH,
) -> SkillAnalyticsSnapshot:
    """Load the committed analytics snapshot or return an empty default."""

    if not path.exists():
        return SkillAnalyticsSnapshot(generated_at="1970-01-01T00:00:00Z")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return SkillAnalyticsSnapshot.model_validate(payload)


def fetch_skill_analytics(
    skill_id: str,
    *,
    snapshot: SkillAnalyticsSnapshot | None = None,
) -> tuple[SkillAnalyticsEntry, str]:
    """Return analytics plus the snapshot refresh timestamp for one skill."""

    loaded_snapshot = snapshot or load_skill_analytics_snapshot()
    analytics = loaded_snapshot.skills.get(skill_id.strip().lower())
    return (
        analytics or SkillAnalyticsEntry(),
        loaded_snapshot.generated_at,
    )
