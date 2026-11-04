"""Operator-protected immutable command catalog; never a server command language."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Annotated, Literal

from pydantic import Field, StrictInt, field_validator, model_validator
from infra_automation.contracts import ClosedModel, Digest


class ArtifactPin(ClosedModel):
    path: str
    sha256: Digest
    kind: Literal["tool", "provider", "module", "lock", "probe"]

    @field_validator("path")
    @classmethod
    def contained_path(cls, value):
        path = PurePosixPath(value)
        if (
            not value.startswith(("/usr/local/", "/opt/"))
            or str(path) != value
            or ".." in path.parts
            or "\\" in value
            or any(ord(c) < 33 for c in value)
            or len(value) > 512
            or value.endswith(".sock")
        ):
            raise ValueError("Invalid catalog path.")
        return value


class CatalogDocument(ClosedModel):
    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    image_id: Digest
    files: Annotated[tuple[ArtifactPin, ...], Field(min_length=1, max_length=256)]

    @field_validator("files", mode="before")
    @classmethod
    def json_array(cls, value):
        return tuple(value) if type(value) is list else value

    @model_validator(mode="after")
    def unique_paths(self):
        if len({item.path for item in self.files}) != len(self.files):
            raise ValueError("Duplicate catalog path.")
        return self


ProbeMode = Literal[
    "plan",
    "environment",
    "cpu",
    "memory",
    "pids",
    "disk",
    "output",
    "descendants",
    "containment",
    "network",
    "success",
    "partial",
    "watchdog",
    "watchdog_load",
]


class CommandRequest(ClosedModel):
    command: Literal["qualification_probe", "tool_version"]
    mode: ProbeMode | None = None

    @model_validator(mode="after")
    def closed_modes(self):
        if (self.command == "qualification_probe") != (self.mode is not None):
            raise ValueError("Invalid catalog parameters.")
        return self


def protected_directory(path: str | Path, *, private: bool = False) -> int:
    """Open a canonical directory through no-follow descriptor-relative traversal."""
    path = Path(path)
    if not path.is_absolute() or str(path) != str(path.resolve(strict=True)):
        raise ValueError("Operator path must be canonical.")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if info.st_uid not in (0, os.getuid()) or stat.S_IMODE(info.st_mode) & 0o022:
            raise ValueError("Unsafe operator directory.")
        if private and (
            info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise ValueError("Private operator directory required.")
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_protected(path: str | Path, maximum: int = 131072) -> bytes:
    """Read exact private regular-file bytes, rejecting substitutions and hardlinks."""
    try:
        path = Path(path)
        parent = protected_directory(path.parent)
        try:
            fd = os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
        finally:
            os.close(parent)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid not in (0, os.getuid())
                or stat.S_IMODE(before.st_mode) not in (0o400, 0o600)
                or before.st_nlink != 1
                or not 0 < before.st_size <= maximum
            ):
                raise ValueError
            raw = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
            if len(raw) != before.st_size or any(
                getattr(before, key) != getattr(after, key)
                for key in (
                    "st_dev",
                    "st_ino",
                    "st_mode",
                    "st_uid",
                    "st_gid",
                    "st_nlink",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                )
            ):
                raise ValueError
            return raw
    except (OSError, ValueError, RuntimeError):
        raise ValueError("Protected operator configuration unavailable.") from None


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate operator field.")
        result[key] = value
    return result


def load_catalog(path: str | Path, expected_digest: str) -> CatalogDocument:
    try:
        raw = read_protected(path)
        if "sha256:" + hashlib.sha256(raw).hexdigest() != expected_digest:
            raise ValueError
        return CatalogDocument.model_validate(
            json.loads(raw, object_pairs_hook=_unique)
        )
    except (ValueError, TypeError, RecursionError):
        raise ValueError("Protected command catalog unavailable.") from None


def build_argv(catalog: CatalogDocument, request: CommandRequest) -> tuple[str, ...]:
    """Generate fixed argv only; parameters never select executables or flags."""
    catalog = CatalogDocument.model_validate(catalog.model_dump())
    request = CommandRequest.model_validate(request.model_dump())
    argv: tuple[str, ...]
    if request.command == "qualification_probe":
        if request.mode is None:
            raise ValueError("Probe mode required.")
        argv = (
            "/usr/local/bin/python",
            "-I",
            "/opt/deploywhisper/probe.py",
            request.mode,
        )
    else:
        argv = ("/usr/local/bin/tofu", "version", "-json")
    required = {"/opt/deploywhisper/bootstrap.py", argv[0]}
    if request.command != "tool_version":
        required.add(argv[2])
    if request.mode == "plan":
        required.add("/usr/local/bin/tofu")
        required.add("/opt/deploywhisper/tofurc")
        if not {"provider", "lock"}.issubset({pin.kind for pin in catalog.files}):
            raise ValueError("Provider or dependency lock identity unavailable.")
    if not required.issubset({pin.path for pin in catalog.files}):
        raise ValueError("Required command identity unavailable.")
    return tuple(argv)
