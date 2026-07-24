"""Configured-source installer operations for custom skills."""

from __future__ import annotations

import errno
from hashlib import sha256
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
from typing import Literal
from urllib import error, parse, request

from pydantic import BaseModel, Field

from config import settings
from services.skill_manifest_service import (
    SkillManifestValidationError,
    is_missing_manifest_frontmatter_error,
    load_skill_document,
    parse_skill_document,
)

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
CUSTOM_DIR = SKILLS_DIR / "custom"
SkillInstallMode = Literal["override", "new"]
_SKILL_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MISSING_MANIFEST_WARNING = "Skill manifest frontmatter is required."


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
    """Validated markdown payload from a configured Skill source."""

    id: str = Field(..., description="Stable skill identifier.")
    version: str = Field(..., description="Manifest version for the returned skill.")
    content: str = Field(..., description="Raw markdown content including frontmatter.")
    sha256: str = Field(..., description="SHA-256 checksum of the source payload.")
    source_url: str = Field(..., description="Source URI used for retrieval.")


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
        default=None, description="Checksum for the written source payload."
    )
    source_url: str | None = Field(
        default=None, description="Source URI used for install or update."
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
        _validate_registry_url(
            configured,
            invalid_code="skills_registry_invalid_url",
            insecure_code="skills_registry_insecure_url",
            allow_query=False,
        )
        return configured.rstrip("/")
    raise SkillInstallerError(
        "skills_source_unconfigured",
        "Skill source is not configured. Set DEPLOYWHISPER_SKILLS_SOURCE_DIR, "
        "DEPLOYWHISPER_SKILLS_REGISTRY_URL, APP_BASE_URL, or PUBLIC_APP_URL.",
    )


def _is_local_registry_host(hostname: str | None) -> bool:
    normalized = (hostname or "").strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _redact_registry_url(url: str) -> str:
    try:
        parsed = parse.urlparse(url)
        if not parsed.username and not parsed.password:
            return url
        hostname = parsed.hostname or ""
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        try:
            port = parsed.port
        except ValueError:
            port = None
        netloc = f"{hostname}:{port}" if port else hostname
        return parse.urlunparse(
            (
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
    except ValueError:
        return url


def _validate_registry_url(
    url: str,
    *,
    invalid_code: str,
    insecure_code: str,
    allow_query: bool = True,
    allow_fragment: bool = False,
) -> parse.ParseResult:
    parsed = parse.urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise SkillInstallerError(
            invalid_code,
            "Skill registry URL must be an HTTP(S) URL with a host.",
            {"url": _redact_registry_url(url)},
        )
    if parsed.username or parsed.password:
        raise SkillInstallerError(
            invalid_code,
            "Skill registry URL must not include embedded credentials.",
            {"url": _redact_registry_url(url)},
        )
    try:
        parsed.port
    except ValueError as exc:
        raise SkillInstallerError(
            invalid_code,
            "Skill registry URL must include a valid port when a port is specified.",
            {"url": _redact_registry_url(url)},
        ) from exc
    if parsed.query and not allow_query:
        raise SkillInstallerError(
            invalid_code,
            "Skill registry URL must not include query parameters.",
            {"url": _redact_registry_url(url)},
        )
    if parsed.fragment and not allow_fragment:
        raise SkillInstallerError(
            invalid_code,
            "Skill registry URL must not include a fragment.",
            {"url": _redact_registry_url(url)},
        )
    if parsed.scheme.lower() == "http" and not _is_local_registry_host(parsed.hostname):
        raise SkillInstallerError(
            insecure_code,
            "Skill registry URL must use HTTPS unless it targets a local development host.",
            {"url": _redact_registry_url(url)},
        )
    return parsed


def _registry_authority(parsed: parse.ParseResult) -> tuple[str, int | None]:
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    return (parsed.hostname or "").lower(), parsed.port or default_port


class _RegistryRedirectHandler(request.HTTPRedirectHandler):
    """Validate registry redirects before urllib follows them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        requested = _validate_registry_url(
            req.full_url,
            invalid_code="skills_registry_invalid_url",
            insecure_code="skills_registry_insecure_url",
        )
        target_url = parse.urljoin(req.full_url, newurl)
        target = _validate_registry_url(
            target_url,
            invalid_code="skills_registry_invalid_redirect",
            insecure_code="skills_registry_insecure_redirect",
        )
        if _registry_authority(target) != _registry_authority(requested):
            raise SkillInstallerError(
                "skills_registry_redirect_host_mismatch",
                "Skill registry redirects must stay on the configured registry host.",
                {
                    "url": _redact_registry_url(req.full_url),
                    "redirect_url": _redact_registry_url(target_url),
                },
            )
        return super().redirect_request(req, fp, code, msg, headers, target_url)


def _open_registry_request(req: request.Request):
    opener = request.build_opener(_RegistryRedirectHandler)
    return opener.open(req, timeout=15)


def _load_json(url: str) -> dict:
    requested = _validate_registry_url(
        url,
        invalid_code="skills_registry_invalid_url",
        insecure_code="skills_registry_insecure_url",
    )
    req = request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "DeployWhisper/skill-installer",
        },
    )
    try:
        with _open_registry_request(req) as response:
            try:
                final_url = response.geturl()
            except AttributeError:
                final_url = req.full_url
            final = _validate_registry_url(
                final_url,
                invalid_code="skills_registry_invalid_redirect",
                insecure_code="skills_registry_insecure_redirect",
            )
            if _registry_authority(final) != _registry_authority(requested):
                raise SkillInstallerError(
                    "skills_registry_redirect_host_mismatch",
                    "Skill registry redirects must stay on the configured registry host.",
                    {
                        "url": _redact_registry_url(url),
                        "redirect_url": _redact_registry_url(final_url),
                    },
                )
            try:
                payload = response.read().decode("utf-8")
            except UnicodeDecodeError as exc:
                raise SkillInstallerError(
                    "skills_registry_invalid_response",
                    "Skill registry returned invalid JSON.",
                    {"url": url},
                ) from exc
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
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SkillInstallerError(
            "skills_registry_invalid_response",
            "Skill registry returned invalid JSON.",
            {"url": url},
        ) from exc
    if not isinstance(data, dict):
        raise SkillInstallerError(
            "skills_registry_invalid_response",
            "Skill registry returned invalid JSON.",
            {"url": url},
        )
    return data


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

    return _validate_source_content(
        normalized_id,
        content,
        source_url=url,
        advertised_checksum=str(data.get("sha256") or "").strip(),
    )


def _validate_source_content(
    skill_id: str,
    content: str,
    *,
    source_url: str,
    advertised_checksum: str = "",
) -> SkillRemoteContent:
    """Validate source markdown without evaluating or executing its body."""

    try:
        document = parse_skill_document(
            content,
            expected_name=skill_id,
            strict_manifest=True,
            project_root=None,
        )
    except SkillManifestValidationError as exc:
        raise SkillInstallerError(
            "invalid_skill_manifest",
            "Fetched skill manifest failed validation.",
            {"issues": "; ".join(exc.issues)},
        ) from exc

    if document.manifest is None:
        raise SkillInstallerError(
            "invalid_skill_manifest",
            "Fetched skill manifest failed validation.",
            {"issues": "Skill manifest frontmatter is required."},
        )
    checksum = sha256(content.encode("utf-8")).hexdigest()
    if advertised_checksum and advertised_checksum != checksum:
        raise SkillInstallerError(
            "skill_checksum_mismatch",
            "Fetched skill checksum did not match the registry metadata.",
            {"skill_id": skill_id},
        )

    return SkillRemoteContent(
        id=skill_id,
        version=document.manifest.version,
        content=content,
        sha256=checksum,
        source_url=source_url,
    )


def _configured_local_source_dir() -> Path | None:
    configured = str(getattr(settings, "skills_local_source_dir", "") or "").strip()
    if not configured:
        return None
    source_dir = Path(configured).expanduser()
    try:
        resolved = source_dir.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SkillInstallerError(
            "skills_local_source_unavailable",
            "Configured local Skill source directory is unavailable.",
            {"path": str(source_dir)},
        ) from exc
    if not resolved.is_dir():
        raise SkillInstallerError(
            "skills_local_source_invalid",
            "Configured local Skill source must be a directory.",
            {"path": str(resolved)},
        )
    return resolved


def fetch_local_skill_content(
    skill_id: str,
    source_dir: Path,
) -> SkillRemoteContent:
    """Read and validate one Skill from a local self-hosted source directory."""

    normalized_id = _normalize_skill_id(skill_id)
    filename = f"{normalized_id}.md"
    candidate = source_dir / filename
    directory_fd: int | None = None
    file_fd: int | None = None
    try:
        directory_fd = os.open(
            source_dir,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            initial_stat = os.stat(
                filename,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError as exc:
            raise SkillInstallerError(
                "skill_source_not_found",
                "Skill was not found in the configured local source.",
                {"skill_id": normalized_id, "path": str(candidate)},
            ) from exc
        except OSError as exc:
            raise SkillInstallerError(
                "skill_source_unreadable",
                "Local Skill source could not be inspected.",
                {"skill_id": normalized_id, "path": str(candidate)},
            ) from exc

        if not stat.S_ISREG(initial_stat.st_mode):
            raise SkillInstallerError(
                "skills_local_source_invalid",
                "Local Skill source must be a regular file, not a symlink or special file.",
                {"skill_id": normalized_id, "path": str(candidate)},
            )

        open_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        open_flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            file_fd = os.open(
                filename,
                open_flags,
                dir_fd=directory_fd,
            )
        except FileNotFoundError as exc:
            raise SkillInstallerError(
                "skill_source_not_found",
                "Skill was not found in the configured local source.",
                {"skill_id": normalized_id, "path": str(candidate)},
            ) from exc
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise SkillInstallerError(
                    "skills_local_source_invalid",
                    "Local Skill source must not be a symlink.",
                    {"skill_id": normalized_id, "path": str(candidate)},
                ) from exc
            raise SkillInstallerError(
                "skill_source_unreadable",
                "Local Skill source could not be opened.",
                {"skill_id": normalized_id, "path": str(candidate)},
            ) from exc

        opened_stat = os.fstat(file_fd)
        try:
            current_stat = os.stat(
                filename,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise SkillInstallerError(
                "skills_local_source_invalid",
                "Local Skill source changed while it was being opened.",
                {"skill_id": normalized_id, "path": str(candidate)},
            ) from exc
        expected_identity = (initial_stat.st_dev, initial_stat.st_ino)
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or not stat.S_ISREG(current_stat.st_mode)
            or (opened_stat.st_dev, opened_stat.st_ino) != expected_identity
            or (current_stat.st_dev, current_stat.st_ino) != expected_identity
        ):
            raise SkillInstallerError(
                "skills_local_source_invalid",
                "Local Skill source changed while it was being opened.",
                {"skill_id": normalized_id, "path": str(candidate)},
            )

        try:
            with os.fdopen(file_fd, encoding="utf-8") as source_file:
                file_fd = None
                content = source_file.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise SkillInstallerError(
                "skill_source_unreadable",
                "Local Skill source could not be read as UTF-8.",
                {"skill_id": normalized_id, "path": str(candidate)},
            ) from exc
    except SkillInstallerError:
        raise
    except OSError as exc:
        raise SkillInstallerError(
            "skills_local_source_unavailable",
            "Configured local Skill source directory became unavailable.",
            {"path": str(source_dir)},
        ) from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)

    return _validate_source_content(
        normalized_id,
        content,
        source_url=candidate.as_uri(),
    )


def fetch_configured_skill_content(skill_id: str) -> SkillRemoteContent:
    """Fetch from the configured local source, falling back to the registry."""

    local_source_dir = _configured_local_source_dir()
    if local_source_dir is not None:
        return fetch_local_skill_content(skill_id, local_source_dir)
    return fetch_registry_skill_content(skill_id)


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
                strict_manifest=True,
                allow_legacy_name=False,
                project_root=None,
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
            if is_missing_manifest_frontmatter_error(exc):
                entries.append(
                    InstalledSkillEntry(
                        id=skill_id,
                        version=None,
                        mode=mode,
                        active=False,
                        path=str(path),
                        description=None,
                        warning=MISSING_MANIFEST_WARNING,
                    )
                )
                continue
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
        except (OSError, UnicodeDecodeError):
            entries.append(
                InstalledSkillEntry(
                    id=skill_id,
                    version=None,
                    mode=mode,
                    active=False,
                    path=str(path),
                    warning="Skill file could not be read as UTF-8.",
                )
            )
    return entries


def install_skill(skill_id: str) -> SkillInstallResult:
    """Install a skill from the configured source into skills/custom."""

    normalized_id = _normalize_skill_id(skill_id)
    destination = _skill_destination(normalized_id)
    if destination.exists():
        raise SkillInstallerError(
            "skill_already_installed",
            "Skill is already installed. Use `deploywhisper skill update` to refresh it.",
            {"skill_id": normalized_id, "path": str(destination)},
        )

    source = fetch_configured_skill_content(normalized_id)
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    destination.write_text(source.content, encoding="utf-8")
    return SkillInstallResult(
        action="installed",
        skill_id=normalized_id,
        version=source.version,
        destination=str(destination),
        mode=_install_mode(normalized_id),
        sha256=source.sha256,
        source_url=source.source_url,
    )


def update_skill(skill_id: str) -> SkillInstallResult:
    """Refresh an installed skill from the configured source."""

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
    source = fetch_configured_skill_content(normalized_id)
    if previous_version == source.version and previous_checksum == source.sha256:
        return SkillInstallResult(
            action="unchanged",
            skill_id=normalized_id,
            version=source.version,
            previous_version=previous_version,
            destination=str(destination),
            mode=_install_mode(normalized_id),
            sha256=source.sha256,
            source_url=source.source_url,
        )

    destination.write_text(source.content, encoding="utf-8")
    return SkillInstallResult(
        action="updated",
        skill_id=normalized_id,
        version=source.version,
        previous_version=previous_version,
        destination=str(destination),
        mode=_install_mode(normalized_id),
        sha256=source.sha256,
        source_url=source.source_url,
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
