"""Shared skill registry retrieval and normalization."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from services.skill_analytics_service import fetch_skill_analytics
from services.skill_manifest_service import load_skill_document
from services.skill_test_harness_service import (
    SkillTestSummary,
    summarize_skill_test_suite,
)

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
CUSTOM_DIR = SKILLS_DIR / "custom"
SkillSource = Literal["built-in", "custom-override", "custom-new"]
SkillRegistrySort = Literal["popularity", "recency"]

_SKILL_BROWSER_METADATA: dict[str, dict[str, object]] = {}


class SkillRegistryEntry(BaseModel):
    """Normalized current skill metadata for external surfaces."""

    id: str = Field(..., description="Stable skill identifier")
    name: str = Field(..., description="Human-readable skill name")
    version: str = Field(..., description="Current effective version")
    source: SkillSource = Field(..., description="Where the skill was resolved from")
    author: str = Field(..., description="Skill author or owner label")
    maintainer: str = Field(..., description="Current maintainer label")
    is_official: bool = Field(
        default=False,
        description="Whether the skill is officially maintained by DeployWhisper.",
    )
    is_featured: bool = Field(
        default=False,
        description="Whether the skill is a curated featured community entry.",
    )
    license: str | None = Field(default=None, description="Declared skill license")
    description: str = Field(..., description="Skill summary")
    tool: str = Field(..., description="Primary tool family for the skill")
    tags: list[str] = Field(default_factory=list, description="Searchable skill tags")
    token_budget: int | None = Field(
        default=None, description="Suggested token budget for the skill"
    )
    test_suite_path: str | None = Field(
        default=None, description="Repository path to the skill validation suite"
    )
    test_results: SkillTestSummary | None = Field(
        default=None, description="Latest deterministic harness summary for the skill."
    )
    triggers: list[str] = Field(
        default_factory=list, description="Filename or extension triggers"
    )
    trigger_content_patterns: list[str] = Field(
        default_factory=list, description="Content markers used for matching"
    )
    contributors: list[str] = Field(
        default_factory=list, description="Visible contributor names for browser UI."
    )
    install_count: int = Field(
        default=0,
        description="Current install count from the shared analytics snapshot.",
    )
    active_issue_count: int = Field(
        default=0,
        description="Open issue count from the shared analytics snapshot.",
    )
    analytics_updated_at: str = Field(
        ...,
        description="When the analytics snapshot used for this record was last refreshed.",
    )
    download_count: int = Field(
        default=0, description="Current catalog download count or seeded preview value."
    )
    star_count: int = Field(
        default=0, description="Current catalog star count or seeded preview value."
    )
    install_command: str = Field(
        ..., description="Copy-pasteable installer command for this skill."
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


class SkillRegistryContent(BaseModel):
    """Raw markdown payload for an installable registry skill."""

    id: str = Field(..., description="Stable skill identifier")
    version: str = Field(..., description="Registry version for this skill")
    content: str = Field(..., description="Raw markdown content with frontmatter")
    sha256: str = Field(..., description="SHA-256 checksum of the content")


class _SkillRecord(BaseModel):
    id: str
    name: str
    version: str
    source: SkillSource
    author: str
    maintainer: str
    is_official: bool = False
    is_featured: bool = False
    license: str | None = None
    description: str
    tool: str
    tags: list[str] = Field(default_factory=list)
    token_budget: int | None = None
    test_suite_path: str | None = None
    test_results: SkillTestSummary | None = None
    triggers: list[str] = Field(default_factory=list)
    trigger_content_patterns: list[str] = Field(default_factory=list)
    contributors: list[str] = Field(default_factory=list)
    install_count: int = 0
    active_issue_count: int = 0
    analytics_updated_at: str
    download_count: int = 0
    star_count: int = 0
    updated_at: str
    updated_at_epoch: float
    path: Path


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


def _default_author(source: SkillSource) -> str:
    if source == "built-in":
        return "DeployWhisper"
    return "Local custom skill"


def _is_official_maintainer(value: str) -> bool:
    return value.strip().lower() == "deploywhisper"


def _default_tool(tool: str | None, skill_id: str) -> str:
    if tool:
        return tool
    return skill_id


def _display_name(skill_id: str) -> str:
    return skill_id.replace("-", " ").title()


def _contributors_for(skill_id: str, author: str) -> list[str]:
    seeded = _SKILL_BROWSER_METADATA.get(skill_id, {}).get("contributors")
    if isinstance(seeded, list):
        contributors = [str(item).strip() for item in seeded if str(item).strip()]
        if contributors:
            return contributors
    return [author]


def _download_count_for(skill_id: str) -> int:
    seeded = _SKILL_BROWSER_METADATA.get(skill_id, {}).get("download_count")
    return int(seeded) if isinstance(seeded, int) else 0


def _star_count_for(skill_id: str) -> int:
    seeded = _SKILL_BROWSER_METADATA.get(skill_id, {}).get("star_count")
    return int(seeded) if isinstance(seeded, int) else 0


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
        "maintainer": record.maintainer,
        "is_official": record.is_official,
        "is_featured": record.is_featured,
        "license": record.license,
        "description": record.description,
        "tool": record.tool,
        "tags": list(record.tags),
        "token_budget": record.token_budget,
        "test_suite_path": record.test_suite_path,
        "test_results": record.test_results,
        "triggers": list(record.triggers),
        "trigger_content_patterns": list(record.trigger_content_patterns),
        "contributors": list(record.contributors),
        "install_count": record.install_count,
        "active_issue_count": record.active_issue_count,
        "analytics_updated_at": record.analytics_updated_at,
        "download_count": record.download_count,
        "star_count": record.star_count,
        "install_command": f"deploywhisper skill install {record.id}",
        "updated_at": record.updated_at,
        "available_versions": available_versions,
    }
    if is_current is None:
        return SkillRegistryEntry(**payload)
    return SkillRegistryVersionEntry(**payload, is_current=is_current)


def _load_skill_record(path: Path, *, source: SkillSource) -> _SkillRecord | None:
    try:
        parsed = load_skill_document(
            path,
            strict_manifest=True,
            allow_legacy_name=False,
            project_root=None,
        )
    except ValueError:
        return None
    if parsed.manifest is None:
        return None

    skill_id = _normalize_skill_id(
        parsed.manifest.name,
        path,
    )
    analytics, analytics_updated_at = fetch_skill_analytics(skill_id)
    updated_at, updated_epoch = _updated_at(path)
    return _SkillRecord(
        id=skill_id,
        name=_display_name(skill_id),
        version=parsed.manifest.version,
        source=source,
        author=parsed.manifest.author or _default_author(source),
        maintainer=(
            parsed.manifest.maintainer
            or parsed.manifest.author
            or _default_author(source)
        ),
        is_official=_is_official_maintainer(
            parsed.manifest.maintainer
            or parsed.manifest.author
            or _default_author(source)
        ),
        is_featured=parsed.manifest.featured,
        license=parsed.manifest.license or None,
        description=parsed.manifest.description,
        tool=_default_tool(parsed.manifest.tool, skill_id),
        tags=list(parsed.manifest.tags),
        token_budget=parsed.manifest.token_budget,
        test_suite_path=parsed.manifest.test_suite_path,
        test_results=summarize_skill_test_suite(skill_id),
        triggers=list(parsed.manifest.triggers),
        trigger_content_patterns=list(parsed.manifest.trigger_content_patterns),
        contributors=_contributors_for(
            skill_id,
            parsed.manifest.author or _default_author(source),
        ),
        install_count=analytics.install_count,
        active_issue_count=analytics.active_issue_count,
        analytics_updated_at=analytics_updated_at,
        download_count=analytics.install_count or _download_count_for(skill_id),
        star_count=analytics.star_count or _star_count_for(skill_id),
        updated_at=updated_at,
        updated_at_epoch=updated_epoch,
        path=path,
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
                record.maintainer,
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
    sort: SkillRegistrySort = "popularity",
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
        for item in sorted(
            current_items,
            key=lambda current: (
                (
                    -current.install_count,
                    -current.star_count,
                    current.id,
                )
                if sort == "popularity"
                else (current.updated_at, current.id)
            ),
            reverse=(sort == "recency"),
        )
        if _matches_query(
            _SkillRecord(**item.model_dump(), updated_at_epoch=0, path=Path(".")),
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


def fetch_skill_registry_content(
    skill_id: str,
    *,
    version: str | None = None,
) -> SkillRegistryContent | None:
    """Return raw markdown content for a registry skill version."""

    versions_by_skill = _load_versions_by_skill(include_custom=False)
    records = versions_by_skill.get(skill_id.strip().lower())
    if not records:
        return None

    selected = _current_record(records)
    if version is not None:
        normalized_version = version.strip()
        matching = [
            record for record in records if record.version == normalized_version
        ]
        if not matching:
            return None
        selected = _sorted_versions(matching)[0]

    content = selected.path.read_text(encoding="utf-8")
    return SkillRegistryContent(
        id=selected.id,
        version=selected.version,
        content=content,
        sha256=sha256(content.encode("utf-8")).hexdigest(),
    )
