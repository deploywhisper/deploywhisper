"""Read-only, bounded verification of an operator's offline tool cache.

Verification grants no runner admission and never downloads or executes files.
The qualified image/catalog remain independent execution requirements.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Annotated

from pydantic import Field, StrictInt, StrictStr, field_validator

from infra_automation.contracts import ClosedModel, Digest
from infra_automation.runner.catalog import protected_directory, read_protected, _unique

MAX_BYTES = 1073741824
MAX_FILE_BYTES = 134217728
MAX_ENTRIES = 512


class CacheEntry(ClosedModel):
    path: Annotated[StrictStr, Field(min_length=1, max_length=512)]
    size: Annotated[StrictInt, Field(ge=1, le=MAX_FILE_BYTES)]
    sha256: Digest

    @field_validator("path")
    @classmethod
    def relative_path(cls, value):
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or str(path) != value
            or any(part in {".", ".."} for part in path.parts)
            or len(path.parts) > 8
            or "\\" in value
            or any(ord(char) < 33 or ord(char) == 127 for char in value)
        ):
            raise ValueError("Invalid cache path.")
        return value


class CacheManifest(ClosedModel):
    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    files: Annotated[list[CacheEntry], Field(min_length=1, max_length=256)]


def _identity(info):
    return tuple(
        getattr(info, key)
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
    )


def _verify_file(parent, name, expected):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) not in {0o400, 0o500, 0o600, 0o700}
            or before.st_nlink != 1
            or before.st_size != expected.size
        ):
            raise ValueError
        digest = hashlib.sha256()
        count = 0
        while count <= expected.size:
            chunk = os.read(fd, min(65536, expected.size + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            digest.update(chunk)
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (
            count != expected.size
            or "sha256:" + digest.hexdigest() != expected.sha256
            or _identity(before) != _identity(os.fstat(fd))
            or _identity(before) != _identity(current)
        ):
            raise ValueError
    finally:
        os.close(fd)


def verify_cache(root, manifest, expected_digest, *, max_bytes=MAX_BYTES):
    """Check a private frozen cache against exact privately pinned manifest bytes.

    The operator must keep this cache quiesced throughout verification and image
    preparation. No validation result is a continuing lease on mutable files.
    """
    try:
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
            raise ValueError
        raw = read_protected(manifest)
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if type(expected_digest) is not str or digest != expected_digest:
            raise ValueError
        document = CacheManifest.model_validate(
            json.loads(raw, object_pairs_hook=_unique)
        )
        entries = {entry.path: entry for entry in document.files}
        total = sum(entry.size for entry in document.files)
        if len(entries) != len(document.files) or total > max_bytes:
            raise ValueError
        fd = protected_directory(Path(root), private=True)
        seen = set()
        count = 0

        def walk(parent, prefix="", depth=0):
            nonlocal count
            if depth > 8:
                raise ValueError
            before = os.fstat(parent)
            with os.scandir(parent) as children:
                for child in children:
                    count += 1
                    if count > MAX_ENTRIES:
                        raise ValueError
                    name = prefix + child.name
                    info = child.stat(follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        if (
                            info.st_uid != os.getuid()
                            or stat.S_IMODE(info.st_mode) != 0o700
                        ):
                            raise ValueError
                        nested = os.open(
                            child.name,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent,
                        )
                        try:
                            if _identity(info) != _identity(os.fstat(nested)):
                                raise ValueError
                            walk(nested, name + "/", depth + 1)
                            if _identity(info) != _identity(
                                os.stat(
                                    child.name, dir_fd=parent, follow_symlinks=False
                                )
                            ):
                                raise ValueError
                        finally:
                            os.close(nested)
                    elif name in entries:
                        _verify_file(parent, child.name, entries[name])
                        seen.add(name)
                    else:
                        raise ValueError
            if _identity(before) != _identity(os.fstat(parent)):
                raise ValueError

        try:
            walk(fd)
            if seen != entries.keys() or _identity(os.fstat(fd)) != _identity(
                os.stat(root, follow_symlinks=False)
            ):
                raise ValueError
        finally:
            os.close(fd)
        return {
            "version": 1,
            "files": len(seen),
            "bytes": total,
            "manifest_digest": digest,
        }
    except (OSError, ValueError, TypeError, RuntimeError, RecursionError):
        raise ValueError("Offline cache unavailable.") from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("Invalid cache command.")


def main(argv=None):
    parser = _Parser(
        description="Verify a private pinned offline cache; no downloads or execution."
    )
    parser.add_argument("--root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    try:
        args = parser.parse_args(argv)
        result = verify_cache(
            args.root, args.manifest, args.sha256, max_bytes=args.max_bytes
        )
    except (ValueError, OSError):
        print(
            "Offline cache unavailable; check private paths, pins and limits.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
