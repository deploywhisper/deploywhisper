"""Shared skill manifest parsing and validation."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
import yaml
from yaml import YAMLError


_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def _is_deploywhisper_label(value: str | None) -> bool:
    return str(value or "").strip().lower() == "deploywhisper"


class SkillManifestValidationError(ValueError):
    """Raised when skill frontmatter or body validation fails."""

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("\n".join(issues))


class SkillManifestV1(BaseModel):
    """Versioned skill manifest contract."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., description="Stable lowercase skill identifier.")
    version: str = Field(..., description="Semantic version for the skill.")
    author: str = Field(..., description="Skill author or owner.")
    maintainer: str | None = Field(
        default=None,
        description="Optional current maintainer label when it differs from author.",
    )
    license: str = Field(..., description="Distribution license identifier.")
    triggers: list[str] = Field(
        ...,
        description="Filename and extension triggers for loading the skill.",
    )
    token_budget: int = Field(
        ..., ge=1, description="Suggested token budget for this skill."
    )
    tags: list[str] = Field(..., description="Search and categorization tags.")
    description: str = Field(..., description="Short summary of the skill.")
    test_suite_path: str = Field(
        ..., description="Repo-relative path to the skill validation suite."
    )
    always_load: bool = Field(
        default=False,
        description="Whether the runtime should always include this skill.",
    )
    tool: str | None = Field(
        default=None,
        description="Optional explicit tool family for registry filtering.",
    )
    trigger_content_patterns: list[str] = Field(
        default_factory=list,
        description="Optional content markers for trigger disambiguation.",
    )
    featured: bool = Field(
        default=False,
        description="Whether this is a curated featured community skill.",
    )

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _SKILL_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("must use lowercase letters, digits, and hyphens only")
        return normalized

    @field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        normalized = value.strip()
        if not _SEMVER_PATTERN.fullmatch(normalized):
            raise ValueError("must use semantic version format (for example 1.0.0)")
        return normalized

    @field_validator(
        "author", "license", "description", "test_suite_path", "maintainer"
    )
    @classmethod
    def _validate_non_empty_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized

    @field_validator("test_suite_path")
    @classmethod
    def _validate_test_suite_path(cls, value: str) -> str:
        normalized = value.strip()
        path = Path(normalized)
        if path.is_absolute():
            raise ValueError("must be a relative repository path")
        if ".." in path.parts:
            raise ValueError("must not traverse outside the repository")
        return normalized

    @field_validator("triggers", "tags", "trigger_content_patterns")
    @classmethod
    def _validate_string_list(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            candidate = str(item).strip()
            if not candidate:
                raise ValueError("must not contain empty values")
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(candidate)
        return normalized

    @field_validator("triggers")
    @classmethod
    def _validate_triggers_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("must include at least one trigger")
        return value

    @field_validator("tool")
    @classmethod
    def _validate_tool(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @model_validator(mode="after")
    def _validate_editorial_flags(self) -> "SkillManifestV1":
        effective_maintainer = self.maintainer or self.author
        if self.featured and (
            _is_deploywhisper_label(self.author)
            or _is_deploywhisper_label(effective_maintainer)
        ):
            raise ValueError(
                "featured skills must remain community-authored and community-maintained rather than DeployWhisper-owned"
            )
        return self


class SkillDocument(BaseModel):
    """Parsed skill document with normalized manifest metadata."""

    manifest: SkillManifestV1 | None = None
    body: str = Field(..., description="Markdown body without frontmatter.")
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    had_frontmatter: bool = Field(
        default=False, description="Whether the source file included YAML frontmatter."
    )


REPO_ROOT = Path(__file__).resolve().parents[1]


def build_skill_manifest_v1_schema() -> dict[str, Any]:
    """Return the published JSON Schema payload for skill manifest v1."""

    schema = SkillManifestV1.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "/schemas/skill-manifest-v1.json"
    return schema


def _validate_test_suite_path_exists(
    value: str,
    *,
    project_root: Path | None,
) -> None:
    if project_root is None:
        return
    candidate = (project_root / value).resolve()
    try:
        candidate.relative_to(project_root.resolve())
    except ValueError as exc:
        raise SkillManifestValidationError(
            ["test_suite_path: must resolve inside the repository root"]
        ) from exc
    if not candidate.exists():
        raise SkillManifestValidationError(
            [f"test_suite_path: path does not exist: {value}"]
        )


def split_frontmatter(raw_text: str) -> tuple[dict[str, Any], str, bool]:
    """Split YAML frontmatter from markdown content."""
    stripped = raw_text.strip()
    if stripped.startswith("---"):
        parts = stripped.split("---", 2)
        if len(parts) == 3:
            try:
                metadata = yaml.safe_load(parts[1]) or {}
            except YAMLError as exc:  # noqa: PERF203
                raise SkillManifestValidationError(
                    [f"Invalid YAML frontmatter: {exc}"]
                ) from exc
            if not isinstance(metadata, dict):
                raise SkillManifestValidationError(
                    ["Skill frontmatter must decode to a YAML object."]
                )
            return metadata, parts[2].strip(), True
    return {}, stripped, False


def _format_validation_errors(exc: ValidationError) -> list[str]:
    issues: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        issues.append(f"{location}: {error['msg']}")
    return issues


def parse_skill_document(
    raw_text: str,
    *,
    expected_name: str | None = None,
    strict_manifest: bool = False,
    allow_legacy_name: bool = False,
    project_root: Path | None = None,
) -> SkillDocument:
    """Parse a skill markdown document and optionally validate v1 frontmatter."""

    metadata, body, had_frontmatter = split_frontmatter(raw_text)
    if not body:
        raise SkillManifestValidationError(
            ["Skill markdown body must not be empty after frontmatter stripping."]
        )

    if not had_frontmatter:
        if strict_manifest:
            raise SkillManifestValidationError(
                ["Skill manifest frontmatter is required for manifest v1 validation."]
            )
        return SkillDocument(
            manifest=None,
            body=body,
            raw_metadata=metadata,
            had_frontmatter=False,
        )

    manifest_payload = dict(metadata)
    if (
        allow_legacy_name
        and "name" not in manifest_payload
        and "skill" in manifest_payload
    ):
        manifest_payload["name"] = manifest_payload["skill"]

    try:
        manifest = SkillManifestV1.model_validate(manifest_payload)
    except ValidationError as exc:
        if strict_manifest:
            raise SkillManifestValidationError(_format_validation_errors(exc)) from exc
        return SkillDocument(
            manifest=None,
            body=body,
            raw_metadata=metadata,
            had_frontmatter=True,
        )

    if expected_name is not None:
        normalized_expected = expected_name.strip().lower()
        if manifest.name != normalized_expected:
            raise SkillManifestValidationError(
                [
                    "name: must match the markdown filename stem "
                    f"('{normalized_expected}')"
                ]
            )
    if strict_manifest:
        _validate_test_suite_path_exists(
            manifest.test_suite_path,
            project_root=project_root,
        )

    return SkillDocument(
        manifest=manifest,
        body=body,
        raw_metadata=metadata,
        had_frontmatter=True,
    )


def load_skill_document(
    path: Path,
    *,
    strict_manifest: bool = False,
    allow_legacy_name: bool = False,
    project_root: Path | None = None,
) -> SkillDocument:
    """Load and parse a skill markdown file from disk."""

    return parse_skill_document(
        path.read_text(encoding="utf-8"),
        expected_name=path.stem.strip().lower(),
        strict_manifest=strict_manifest,
        allow_legacy_name=allow_legacy_name,
        project_root=project_root,
    )
