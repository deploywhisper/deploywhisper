"""Registry-backed installer operations for custom skills."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Literal
from urllib import error, parse, request

from pydantic import BaseModel, Field

from config import settings
from services.skill_manifest_service import (
    SkillManifestValidationError,
    load_skill_document,
    parse_skill_document,
)

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
CUSTOM_DIR = SKILLS_DIR / "custom"
SkillInstallMode = Literal["override", "new"]
_SKILL_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SkillInstallerError(ValueError):
    """Raised when installer actions fail."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class InstalledSkillEntry(BaseModel):
    """Normalized installed-skill summary for CLI output."""

    id: str = Field(..., description="Stable skill identifier.")
    version: str | None = Field(
        default=None, description="Installed manifest version when available."
    )
    mode: SkillInstallMode = Field(
        ..., description="Whether the local install overrides a bundled skill."
    )
    active: bool = Field(..., description="Whether the installed file parses cleanly.")
    path: str = Field(..., description="Filesystem location of the installed skill.")
    description: str | None = Field(
        default=None, description="Installed manifest description when available."
    )
    warning: str | None = Field(
        default=None, description="Parsing warning for invalid installed files."
    )


class SkillRemoteContent(BaseModel):
    """Registry-delivered markdown payload for an installable skill."""

    id: str = Field(..., description="Stable skill identifier.")
    version: str = Field(..., description="Registry version for the returned skill.")
    content: str = Field(..., description="Raw markdown content including frontmatter.")
    sha256: str = Field(..., description="SHA-256 checksum of the registry payload.")
    source_url: str = Field(..., description="Registry endpoint used for retrieval.")


class SkillInstallResult(BaseModel):
    """Outcome details for install/update/remove operations."""

    action: Literal["installed", "updated", "removed", "unchanged"] = Field(
        ..., description="Lifecycle action that completed."
    )
    skill_id: str = Field(..., description="Stable skill identifier.")
    version: str | None = Field(
        default=None, description="Version after the action completes."
    )
    previous_version: str | None = Field(
        default=None, description="Version before the action completes."
    )
    destination: str = Field(..., description="Local skill file path.")
    mode: SkillInstallMode = Field(
        ..., description="Whether the installed skill is a new file or override."
    )
    sha256: str | None = Field(
        default=None, description="Checksum for the written registry payload."
    )
    source_url: str | None = Field(
        default=None, description="Registry URL used for install or update."
    )


def _normalize_skill_id(skill_id: str) -> str:
    normalized = skill_id.strip().lower()
    if not normalized:
        raise SkillInstallerError(
            "invalid_skill_id",
            "Skill id must not be empty.",
        )
    if not _SKILL_ID_PATTERN.fullmatch(normalized):
        raise SkillInstallerError(
            "invalid_skill_id",
            "Skill id must use lowercase letters, digits, and hyphens only.",
            {"skill_id": normalized},
        )
    return normalized


def _skill_destination(skill_id: str) -> Path:
    return CUSTOM_DIR / f"{skill_id}.md"


def _install_mode(skill_id: str) -> SkillInstallMode:
    return "override" if (SKILLS_DIR / f"{skill_id}.md").exists() else "new"


def _current_version(path: Path) -> str | None:
    try:
        document = load_skill_document(
            path,
            strict_manifest=False,
            allow_legacy_name=True,
        )
    except (FileNotFoundError, SkillManifestValidationError):
        return None
    return document.manifest.version if document.manifest else None


def _current_checksum(path: Path) -> str | None:
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _registry_base_url() -> str:
    configured = (settings.skills_registry_base_url or "").strip()
    if configured:
        return configured.rstrip("/")
    raise SkillInstallerError(
        "skills_registry_unconfigured",
        "Skill registry URL is not configured. Set DEPLOYWHISPER_SKILLS_REGISTRY_URL or APP_BASE_URL.",
    )


def _load_json(url: str) -> dict:
    req = request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "DeployWhisper/skill-installer",
        },
    )
    try:
        with request.urlopen(req, timeout=15) as response:
            payload = response.read().decode("utf-8")
    except error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        error_payload = dict(payload.get("error") or {})
        raise SkillInstallerError(
            str(error_payload.get("code") or "skills_registry_request_failed"),
            str(
                error_payload.get("message") or f"Skill registry request failed: {exc}"
            ),
            {
                key: str(value)
                for key, value in dict(error_payload.get("details") or {}).items()
            },
        ) from exc
    except error.URLError as exc:
        raise SkillInstallerError(
            "skills_registry_unreachable",
            "Skill registry could not be reached.",
            {"reason": str(exc.reason)},
        ) from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SkillInstallerError(
            "skills_registry_invalid_response",
            "Skill registry returned invalid JSON.",
            {"url": url},
        ) from exc


def fetch_registry_skill_content(
    skill_id: str,
    *,
    version: str | None = None,
) -> SkillRemoteContent:
    """Fetch a registry skill markdown payload and validate it locally."""

    normalized_id = _normalize_skill_id(skill_id)
    query = ""
    if version:
        query = "?" + parse.urlencode({"version": version.strip()})
    url = (
        f"{_registry_base_url()}/api/v1/skills/"
        f"{parse.quote(normalized_id)}/content{query}"
    )
    payload = _load_json(url)
    data = dict(payload.get("data") or {})
    content = str(data.get("content") or "")
    if not content:
        raise SkillInstallerError(
            "skills_registry_invalid_response",
            "Skill registry response did not include skill content.",
            {"url": url},
        )

    try:
        document = parse_skill_document(
            content,
            expected_name=normalized_id,
            strict_manifest=True,
            project_root=None,
        )
    except SkillManifestValidationError as exc:
        raise SkillInstallerError(
            "invalid_skill_manifest",
            "Fetched skill manifest failed validation.",
            {"issues": "; ".join(exc.issues)},
        ) from exc

    assert document.manifest is not None
    checksum = sha256(content.encode("utf-8")).hexdigest()
    advertised_checksum = str(data.get("sha256") or "").strip()
    if advertised_checksum and advertised_checksum != checksum:
        raise SkillInstallerError(
            "skill_checksum_mismatch",
            "Fetched skill checksum did not match the registry metadata.",
            {"skill_id": normalized_id},
        )

    return SkillRemoteContent(
        id=normalized_id,
        version=document.manifest.version,
        content=content,
        sha256=checksum,
        source_url=url,
    )


def list_installed_skills() -> list[InstalledSkillEntry]:
    """Return installed custom skills from the local cache directory."""

    if not CUSTOM_DIR.exists():
        return []

    built_in_ids = {
        path.stem.strip().lower()
        for path in SKILLS_DIR.glob("*.md")
        if path.is_file() and path.name.lower() != "readme.md"
    }
    entries: list[InstalledSkillEntry] = []
    for path in sorted(
        item
        for item in CUSTOM_DIR.glob("*.md")
        if item.is_file() and item.name.lower() != "readme.md"
    ):
        skill_id = path.stem.strip().lower()
        mode: SkillInstallMode = "override" if skill_id in built_in_ids else "new"
        try:
            document = load_skill_document(
                path,
                strict_manifest=False,
                allow_legacy_name=True,
            )
            manifest = document.manifest
            entries.append(
                InstalledSkillEntry(
                    id=skill_id,
                    version=manifest.version if manifest else None,
                    mode=mode,
                    active=True,
                    path=str(path),
                    description=manifest.description if manifest else None,
                )
            )
        except SkillManifestValidationError as exc:
            entries.append(
                InstalledSkillEntry(
                    id=skill_id,
                    version=None,
                    mode=mode,
                    active=False,
                    path=str(path),
                    warning=exc.issues[0]
                    if exc.issues
                    else "Skill manifest is invalid.",
                )
            )
    return entries


def install_skill(skill_id: str) -> SkillInstallResult:
    """Install a skill from the configured registry into skills/custom."""

    normalized_id = _normalize_skill_id(skill_id)
    destination = _skill_destination(normalized_id)
    if destination.exists():
        raise SkillInstallerError(
            "skill_already_installed",
            "Skill is already installed. Use `deploywhisper skill update` to refresh it.",
            {"skill_id": normalized_id, "path": str(destination)},
        )

    remote = fetch_registry_skill_content(normalized_id)
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    destination.write_text(remote.content, encoding="utf-8")
    return SkillInstallResult(
        action="installed",
        skill_id=normalized_id,
        version=remote.version,
        destination=str(destination),
        mode=_install_mode(normalized_id),
        sha256=remote.sha256,
        source_url=remote.source_url,
    )


def update_skill(skill_id: str) -> SkillInstallResult:
    """Refresh an installed skill to the latest registry version."""

    normalized_id = _normalize_skill_id(skill_id)
    destination = _skill_destination(normalized_id)
    if not destination.exists():
        raise SkillInstallerError(
            "skill_not_installed",
            "Skill is not installed. Use `deploywhisper skill install` first.",
            {"skill_id": normalized_id, "path": str(destination)},
        )

    previous_version = _current_version(destination)
    previous_checksum = _current_checksum(destination)
    remote = fetch_registry_skill_content(normalized_id)
    if previous_version == remote.version and previous_checksum == remote.sha256:
        return SkillInstallResult(
            action="unchanged",
            skill_id=normalized_id,
            version=remote.version,
            previous_version=previous_version,
            destination=str(destination),
            mode=_install_mode(normalized_id),
            sha256=remote.sha256,
            source_url=remote.source_url,
        )

    destination.write_text(remote.content, encoding="utf-8")
    return SkillInstallResult(
        action="updated",
        skill_id=normalized_id,
        version=remote.version,
        previous_version=previous_version,
        destination=str(destination),
        mode=_install_mode(normalized_id),
        sha256=remote.sha256,
        source_url=remote.source_url,
    )


def remove_skill(skill_id: str) -> SkillInstallResult:
    """Remove an installed custom skill from the local cache."""

    normalized_id = _normalize_skill_id(skill_id)
    destination = _skill_destination(normalized_id)
    if not destination.exists():
        raise SkillInstallerError(
            "skill_not_installed",
            "Skill is not installed.",
            {"skill_id": normalized_id, "path": str(destination)},
        )

    previous_version = _current_version(destination)
    destination.unlink()
    return SkillInstallResult(
        action="removed",
        skill_id=normalized_id,
        version=None,
        previous_version=previous_version,
        destination=str(destination),
        mode=_install_mode(normalized_id),
    )
