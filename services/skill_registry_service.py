"""Shared skill registry retrieval and normalization."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any, Literal

from pydantic import BaseModel, Field
import yaml
from yaml import YAMLError


SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
CUSTOM_DIR = SKILLS_DIR / "custom"
SkillSource = Literal["built-in", "custom-override", "custom-new"]


class SkillRegistryEntry(BaseModel):
    """Normalized current skill metadata for external surfaces."""

    id: str = Field(..., description="Stable skill identifier")
    name: str = Field(..., description="Human-readable skill name")
    version: str = Field(..., description="Current effective version")
    source: SkillSource = Field(..., description="Where the skill was resolved from")
    author: str = Field(..., description="Skill author or owner label")
    license: str | None = Field(default=None, description="Declared skill license")
    description: str = Field(..., description="Skill summary")
    tool: str = Field(..., description="Primary tool family for the skill")
    tags: list[str] = Field(default_factory=list, description="Searchable skill tags")
    token_budget: int | None = Field(
        default=None, description="Suggested token budget for the skill"
    )
    triggers: list[str] = Field(
        default_factory=list, description="Filename or extension triggers"
    )
    trigger_content_patterns: list[str] = Field(
        default_factory=list, description="Content markers used for matching"
    )
    updated_at: str = Field(..., description="Last local update timestamp")
    available_versions: int = Field(
        ..., description="Number of versions discoverable for this skill id"
    )


class SkillRegistryVersionEntry(SkillRegistryEntry):
    """Version history entry for a skill."""

    is_current: bool = Field(
        ..., description="Whether this version is the effective current version"
    )


class SkillRegistryPage(BaseModel):
    """Paginated page of current registry entries."""

    items: list[SkillRegistryEntry] = Field(default_factory=list)
    total_count: int = Field(..., description="Total number of matching skills")
    page: int = Field(..., description="Current result page")
    page_size: int = Field(..., description="Current result page size")


class _SkillRecord(BaseModel):
    id: str
    name: str
    version: str
    source: SkillSource
    author: str
    license: str | None = None
    description: str
    tool: str
    tags: list[str] = Field(default_factory=list)
    token_budget: int | None = None
    triggers: list[str] = Field(default_factory=list)
    trigger_content_patterns: list[str] = Field(default_factory=list)
    updated_at: str
    updated_at_epoch: float


class _ParsedSkillFile(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)
    content: str = Field(..., description="Markdown body without frontmatter")


def _split_frontmatter(content: str) -> _ParsedSkillFile | None:
    stripped = content.strip()
    if stripped.startswith("---"):
        parts = stripped.split("---", 2)
        if len(parts) == 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except YAMLError:
                return None
            if not isinstance(frontmatter, dict):
                frontmatter = {}
            return _ParsedSkillFile(metadata=frontmatter, content=parts[2].strip())
    return _ParsedSkillFile(metadata={}, content=stripped)


def _iter_skill_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        path
        for path in directory.glob("*.md")
        if path.is_file() and path.name.lower() != "readme.md"
    )


def _normalize_skill_id(raw_value: str | None, path: Path) -> str:
    candidate = str(raw_value or path.stem).strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", candidate).strip("-")
    return normalized or path.stem.strip().lower()


def _normalize_string_list(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    items = raw_value if isinstance(raw_value, list) else [raw_value]
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def _normalize_token_budget(raw_value: Any) -> int | None:
    if raw_value in {None, ""}:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _extract_description(metadata: dict[str, Any], content: str) -> str:
    description = str(metadata.get("description") or "").strip()
    if description:
        return description
    for line in content.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        return candidate
    return "No description provided."


def _default_author(source: SkillSource) -> str:
    if source == "built-in":
        return "DeployWhisper"
    return "Local custom skill"


def _default_tool(metadata: dict[str, Any], skill_id: str) -> str:
    for key in ("tool_type", "tool"):
        value = str(metadata.get(key) or "").strip().lower()
        if value:
            return value
    return skill_id


def _display_name(metadata: dict[str, Any], skill_id: str) -> str:
    explicit = str(metadata.get("name") or "").strip()
    if explicit:
        return explicit
    return skill_id.replace("-", " ").title()


def _updated_at(path: Path) -> tuple[str, float]:
    updated_epoch = path.stat().st_mtime
    updated_at = datetime.fromtimestamp(updated_epoch, tz=UTC).isoformat()
    return updated_at.replace("+00:00", "Z"), updated_epoch


def _version_key(version: str) -> tuple[Any, ...]:
    parts = re.split(r"[^0-9A-Za-z]+", version)
    key: list[Any] = []
    for part in parts:
        if not part:
            continue
        key.append(int(part) if part.isdigit() else part.lower())
    return tuple(key)


def _source_priority(source: SkillSource) -> int:
    return {
        "built-in": 1,
        "custom-override": 2,
        "custom-new": 3,
    }[source]


def _record_to_entry(
    record: _SkillRecord,
    *,
    available_versions: int,
    is_current: bool | None = None,
) -> SkillRegistryEntry | SkillRegistryVersionEntry:
    payload = {
        "id": record.id,
        "name": record.name,
        "version": record.version,
        "source": record.source,
        "author": record.author,
        "license": record.license,
        "description": record.description,
        "tool": record.tool,
        "tags": list(record.tags),
        "token_budget": record.token_budget,
        "triggers": list(record.triggers),
        "trigger_content_patterns": list(record.trigger_content_patterns),
        "updated_at": record.updated_at,
        "available_versions": available_versions,
    }
    if is_current is None:
        return SkillRegistryEntry(**payload)
    return SkillRegistryVersionEntry(**payload, is_current=is_current)


def _load_skill_record(path: Path, *, source: SkillSource) -> _SkillRecord | None:
    raw_content = path.read_text(encoding="utf-8")
    parsed = _split_frontmatter(raw_content)
    if parsed is None or not parsed.content:
        return None

    skill_id = _normalize_skill_id(
        parsed.metadata.get("skill") or parsed.metadata.get("name"),
        path,
    )
    updated_at, updated_epoch = _updated_at(path)
    return _SkillRecord(
        id=skill_id,
        name=_display_name(parsed.metadata, skill_id),
        version=str(parsed.metadata.get("version") or "1.0"),
        source=source,
        author=str(parsed.metadata.get("author") or _default_author(source)),
        license=str(parsed.metadata.get("license")).strip() or None
        if parsed.metadata.get("license") is not None
        else None,
        description=_extract_description(parsed.metadata, parsed.content),
        tool=_default_tool(parsed.metadata, skill_id),
        tags=_normalize_string_list(parsed.metadata.get("tags")),
        token_budget=_normalize_token_budget(parsed.metadata.get("token_budget")),
        triggers=_normalize_string_list(parsed.metadata.get("triggers")),
        trigger_content_patterns=_normalize_string_list(
            parsed.metadata.get("trigger_content_patterns")
        ),
        updated_at=updated_at,
        updated_at_epoch=updated_epoch,
    )


def _load_versions_by_skill(*, include_custom: bool) -> dict[str, list[_SkillRecord]]:
    versions_by_skill: dict[str, list[_SkillRecord]] = {}

    for path in _iter_skill_files(SKILLS_DIR):
        if path.parent != SKILLS_DIR:
            continue
        record = _load_skill_record(path, source="built-in")
        if record is None:
            continue
        versions_by_skill.setdefault(record.id, []).append(record)

    if include_custom:
        built_in_ids = {
            _normalize_skill_id(None, path)
            for path in _iter_skill_files(SKILLS_DIR)
            if path.parent == SKILLS_DIR
        }

        for path in _iter_skill_files(CUSTOM_DIR):
            inferred_id = _normalize_skill_id(None, path)
            source: SkillSource = (
                "custom-override" if inferred_id in built_in_ids else "custom-new"
            )
            record = _load_skill_record(path, source=source)
            if record is None:
                continue
            versions_by_skill.setdefault(record.id, []).append(record)

    return versions_by_skill


def _current_record(records: list[_SkillRecord]) -> _SkillRecord:
    return max(
        records,
        key=lambda record: (
            _source_priority(record.source),
            _version_key(record.version),
            record.updated_at_epoch,
        ),
    )


def _sorted_versions(records: list[_SkillRecord]) -> list[_SkillRecord]:
    return sorted(
        records,
        key=lambda record: (
            _source_priority(record.source),
            _version_key(record.version),
            record.updated_at_epoch,
        ),
        reverse=True,
    )


def _matches_query(
    record: _SkillRecord,
    *,
    tool: str | None,
    tag: str | None,
    author: str | None,
    search: str | None,
) -> bool:
    if tool and record.tool.lower() != tool.strip().lower():
        return False
    if tag and tag.strip().lower() not in {item.lower() for item in record.tags}:
        return False
    if author and record.author.lower() != author.strip().lower():
        return False
    if search:
        needle = search.strip().lower()
        haystack = " ".join(
            [
                record.id,
                record.name,
                record.version,
                record.author,
                record.tool,
                record.description,
                *record.tags,
                *record.triggers,
                *record.trigger_content_patterns,
            ]
        ).lower()
        if needle not in haystack:
            return False
    return True


def fetch_skill_registry_page(
    *,
    tool: str | None = None,
    tag: str | None = None,
    author: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> SkillRegistryPage:
    versions_by_skill = _load_versions_by_skill(include_custom=False)
    current_items = [
        _record_to_entry(
            _current_record(records),
            available_versions=len(records),
        )
        for records in versions_by_skill.values()
    ]
    filtered = [
        item
        for item in sorted(current_items, key=lambda current: current.id)
        if _matches_query(
            _SkillRecord(**item.model_dump(), updated_at_epoch=0),
            tool=tool,
            tag=tag,
            author=author,
            search=search,
        )
    ]
    total_count = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    return SkillRegistryPage(
        items=filtered[start:end],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


def fetch_skill_registry_entry(skill_id: str) -> SkillRegistryEntry | None:
    versions_by_skill = _load_versions_by_skill(include_custom=False)
    records = versions_by_skill.get(skill_id.strip().lower())
    if not records:
        return None
    return _record_to_entry(_current_record(records), available_versions=len(records))


def fetch_skill_registry_versions(skill_id: str) -> list[SkillRegistryVersionEntry]:
    versions_by_skill = _load_versions_by_skill(include_custom=False)
    records = versions_by_skill.get(skill_id.strip().lower())
    if not records:
        return []
    current = _current_record(records)
    available_versions = len(records)
    return [
        _record_to_entry(
            record,
            available_versions=available_versions,
            is_current=(
                record.source == current.source and record.version == current.version
            ),
        )
        for record in _sorted_versions(records)
    ]
