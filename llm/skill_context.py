"""Skill context loading for narrative generation."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, Field

from analysis.risk_scorer import RiskAssessment


SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
CUSTOM_DIR = SKILLS_DIR / "custom"


class ActiveSkill(BaseModel):
    """Resolved skill definition after built-in/custom precedence is applied."""

    name: str = Field(..., description="Stable skill name")
    source: Literal["built-in", "custom-override", "custom-new"] = Field(..., description="Resolved skill source")
    path: str = Field(..., description="Resolved markdown path")
    content: str = Field(..., description="Skill markdown without frontmatter")


class CustomSkillStatus(BaseModel):
    """Admin-facing summary of detected custom skill files."""

    name: str = Field(..., description="Stable skill name")
    mode: Literal["override", "new"] = Field(..., description="Whether this custom skill overrides a built-in skill")
    active: bool = Field(..., description="Whether the custom skill is active")
    path: str = Field(..., description="Filesystem location")
    warning: str | None = Field(default=None, description="Why the custom skill was ignored")


def _strip_frontmatter(content: str) -> str:
    content = content.strip()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) == 3:
            content = parts[2].strip()
    return content.strip()


def _skill_name_from_path(path: Path) -> str | None:
    if path.suffix.lower() != ".md":
        return None
    name = path.stem.strip().lower()
    return name or None


def _read_skill_file(path: Path) -> str | None:
    if not path.exists():
        return None
    content = _strip_frontmatter(path.read_text(encoding="utf-8"))
    return content or None


def _iter_skill_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob("*.md") if path.is_file())


def get_active_skills() -> dict[str, ActiveSkill]:
    """Return the effective skill registry after custom precedence is applied."""
    active: dict[str, ActiveSkill] = {}

    for path in _iter_skill_files(SKILLS_DIR):
        name = _skill_name_from_path(path)
        content = _read_skill_file(path)
        if not name or not content:
            continue
        active[name] = ActiveSkill(name=name, source="built-in", path=str(path), content=content)

    for path in _iter_skill_files(CUSTOM_DIR):
        name = _skill_name_from_path(path)
        content = _read_skill_file(path)
        if not name or not content:
            continue
        source = "custom-override" if name in active else "custom-new"
        active[name] = ActiveSkill(name=name, source=source, path=str(path), content=content)

    return active


def get_custom_skill_statuses() -> list[CustomSkillStatus]:
    """Return admin-facing summaries for custom skill discovery."""
    built_in_names = {
        name
        for path in _iter_skill_files(SKILLS_DIR)
        if path.parent == SKILLS_DIR
        for name in [_skill_name_from_path(path)]
        if name
    }
    statuses: list[CustomSkillStatus] = []
    for path in _iter_skill_files(CUSTOM_DIR):
        name = _skill_name_from_path(path)
        if not name:
            continue
        content = _read_skill_file(path)
        statuses.append(
            CustomSkillStatus(
                name=name,
                mode="override" if name in built_in_names else "new",
                active=content is not None,
                path=str(path),
                warning=None if content else "Custom skill file is empty after frontmatter stripping.",
            )
        )
    return statuses


def save_custom_skill(filename: str, raw_text: str) -> CustomSkillStatus:
    """Persist a custom markdown skill file and return its resolved admin status."""
    candidate_name = Path(filename).name
    if not candidate_name.lower().endswith(".md"):
        raise ValueError("Custom skill files must use the .md extension.")

    skill_name = Path(candidate_name).stem.strip().lower()
    if not skill_name:
        raise ValueError("Custom skill filename must include a skill name.")

    stripped = _strip_frontmatter(raw_text)
    if not stripped:
        raise ValueError("Custom skill content cannot be empty.")

    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    destination = CUSTOM_DIR / f"{skill_name}.md"
    destination.write_text(raw_text, encoding="utf-8")

    for status in get_custom_skill_statuses():
        if status.name == skill_name:
            return status
    raise ValueError("Custom skill could not be resolved after saving.")


def _assessment_search_blob(assessment: RiskAssessment) -> str:
    parts = [assessment.top_risk, *assessment.warnings]
    for contributor in assessment.contributors:
        parts.extend(
            [
                contributor.tool,
                contributor.resource_id,
                contributor.source_file,
                contributor.action,
                contributor.summary,
            ]
        )
    return " ".join(part.lower() for part in parts if part)


def _custom_skill_applies(skill_name: str, search_blob: str) -> bool:
    normalized_name = skill_name.lower().strip()
    if not normalized_name:
        return False
    if re.search(rf"\b{re.escape(normalized_name)}\b", search_blob):
        return True

    tokens = [token for token in re.split(r"[^a-z0-9]+", normalized_name) if token]
    if len(tokens) > 1 and all(re.search(rf"\b{re.escape(token)}\b", search_blob) for token in tokens):
        return True
    return False


def build_skill_context(assessment: RiskAssessment) -> str:
    active_skills = get_active_skills()
    seen: set[str] = set()
    sections: list[str] = []
    search_blob = _assessment_search_blob(assessment)
    for contributor in assessment.contributors:
        tool_name = contributor.tool.lower()
        if tool_name in seen:
            continue
        seen.add(tool_name)
        skill = active_skills.get(tool_name)
        if skill:
            sections.append(f"## {tool_name.upper()} SKILL ({skill.source})\n{skill.content}")

    for skill_name, skill in active_skills.items():
        if skill.source != "custom-new":
            continue
        if skill_name in seen:
            continue
        if _custom_skill_applies(skill_name, search_blob):
            sections.append(f"## {skill_name.upper()} SKILL ({skill.source})\n{skill.content}")
            seen.add(skill_name)
    return "\n\n".join(sections)
