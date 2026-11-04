"""Bounded trusted Git-object snapshots without checkout hooks or host config."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import selectors
import secrets
import signal
import stat
import sys
import subprocess  # nosec B404

# Subprocess execution below is restricted to the protected system Git binary.
import tempfile
import time
import weakref
from typing import Annotated, Literal

import hcl2
from pydantic import Field, PrivateAttr, StrictStr, field_validator
from infra_automation.contracts import ClosedModel, Digest
from infra_automation.runner.catalog import protected_directory, read_protected, _unique

MAX_FILES = 256
MAX_BYTES = 8 * 1024 * 1024
OBJECT_BYTES = 64 * 1024 * 1024
CONFIG_SUFFIXES = (".tf", ".tf.json", ".tofu", ".tofu.json")
_SNAPSHOTS: weakref.WeakValueDictionary[str, SourceSnapshot] = (
    weakref.WeakValueDictionary()
)


def _relative(value):
    path = PurePosixPath(value)
    if (
        type(value) is not str
        or not value
        or len(value) > 512
        or str(path) != value
        or path.is_absolute()
        or len(path.parts) > 16
        or any(p in ("", ".", "..", ".git") for p in path.parts)
        or "\\" in value
        or any(ord(c) < 33 or ord(c) > 126 for c in value)
    ):
        raise ValueError("Unsafe source path.")
    return value


class SourceRegistration(ClosedModel):
    _registration_path: Path | None = PrivateAttr(default=None)
    _registration_digest: str | None = PrivateAttr(default=None)
    repository_path: StrictStr
    commit: Annotated[StrictStr, Field(pattern=r"^[a-f0-9]{40}$")]
    trust: Literal["protected_revision"]
    tree_digest: Digest
    lock_digests: Annotated[dict[str, Digest], Field(min_length=1, max_length=128)]

    @field_validator("lock_digests")
    @classmethod
    def lock_paths(cls, value):
        for name in value:
            _relative(name)
        return value


def tree_digest(files: dict[str, str]) -> str:
    for name, checksum in files.items():
        _relative(name)
        if type(checksum) is not str or not re.fullmatch(
            r"sha256:[a-f0-9]{64}", checksum
        ):
            raise ValueError("Invalid source manifest.")
    raw = json.dumps(
        files, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def load_registration(path: str | Path, expected_digest: str) -> SourceRegistration:
    try:
        raw = read_protected(path)
        if "sha256:" + hashlib.sha256(raw).hexdigest() != expected_digest:
            raise ValueError
        registration = SourceRegistration.model_validate(
            json.loads(raw, object_pairs_hook=_unique)
        )
        registration._registration_path = Path(path)
        registration._registration_digest = expected_digest
        return registration
    except (ValueError, TypeError, RecursionError):
        raise ValueError("Protected source registration unavailable.") from None


def _verify_registration(registration):
    if (
        type(registration) is not SourceRegistration
        or registration._registration_path is None
        or registration._registration_digest is None
    ):
        raise ValueError("Protected source registration required.")
    current = load_registration(
        registration._registration_path, registration._registration_digest
    )
    if current.model_dump() != registration.model_dump():
        raise ValueError("Source registration changed.")
    return current


def _walk(fd, *, maximum, max_files, immutable=False):
    """Read a private tree through held directory descriptors; never follow links."""
    found = {}
    used = 0
    entries = 0
    deadline = time.monotonic() + 30

    def visit(directory, prefix=""):
        nonlocal used, entries
        for name in sorted(os.listdir(directory)):
            entries += 1
            if entries > max_files * 4 or time.monotonic() >= deadline:
                raise ValueError("Source traversal bound exceeded.")
            relative = _relative(prefix + name)
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (
                info.st_uid not in (0, os.getuid())
                or stat.S_IMODE(info.st_mode) & 0o022
            ):
                raise ValueError("Unsafe source permissions.")
            if stat.S_ISDIR(info.st_mode):
                child = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                )
                try:
                    opened = os.fstat(child)
                    if any(
                        getattr(opened, key) != getattr(info, key)
                        for key in ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid")
                    ):
                        raise ValueError
                    if immutable and stat.S_IMODE(info.st_mode) != 0o555:
                        raise ValueError
                    visit(child, relative + "/")
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                if len(found) >= max_files or info.st_size > maximum - used:
                    raise ValueError
                child = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
                )
                with os.fdopen(child, "rb") as stream:
                    before = os.fstat(stream.fileno())
                    if any(
                        getattr(before, key) != getattr(info, key)
                        for key in (
                            "st_dev",
                            "st_ino",
                            "st_mode",
                            "st_uid",
                            "st_gid",
                            "st_nlink",
                        )
                    ) or (immutable and stat.S_IMODE(before.st_mode) != 0o444):
                        raise ValueError
                    raw = stream.read(maximum - used + 1)
                    after = os.fstat(stream.fileno())
                    if len(raw) != before.st_size or any(
                        getattr(before, k) != getattr(after, k)
                        for k in (
                            "st_dev",
                            "st_ino",
                            "st_size",
                            "st_mtime_ns",
                            "st_ctime_ns",
                            "st_mode",
                            "st_uid",
                            "st_nlink",
                        )
                    ):
                        raise ValueError
                used += len(raw)
                if used > maximum:
                    raise ValueError
                found[relative] = raw
            else:
                raise ValueError("Source links and special files are forbidden.")

    visit(fd)
    return found


def _git(gitdir, *args, maximum=262144, operation_deadline=None):
    binary = Path("/usr/bin/git")
    info = binary.stat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid not in (0, os.getuid())
        or info.st_mode & 0o022
    ):
        raise ValueError
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(gitdir.parent),
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_LAZY_FETCH": "1",
    }
    argv = [
        str(binary),
        "--no-pager",
        "--no-replace-objects",
        "-c",
        "protocol.allow=never",
        "-c",
        "credential.helper=",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "--git-dir=" + str(gitdir),
        *args,
    ]
    limits = (
        "import os,resource,sys; "
        "resource.setrlimit(resource.RLIMIT_CORE,(0,0)); "
        "resource.setrlimit(resource.RLIMIT_CPU,(5,5)); "
        "resource.setrlimit(resource.RLIMIT_AS,(536870912,536870912)) if sys.platform=='linux' else None; "
        "os.execv(sys.argv[1],sys.argv[1:])"
    )
    process = subprocess.Popen(
        [sys.executable, "-I", "-c", limits, *argv],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=gitdir.parent,
        start_new_session=True,
    )  # nosec B603
    output = bytearray()
    errors = 0
    deadline = min(time.monotonic() + 10, operation_deadline or float("inf"))
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, True)
            selector.register(process.stderr, selectors.EVENT_READ, False)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fileobj.fileno(), min(65536, maximum + 1))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if key.data:
                        output.extend(chunk)
                    else:
                        errors += len(chunk)
                    if len(output) > maximum or errors > 4096:
                        raise ValueError
            if process.wait(timeout=max(0.001, deadline - time.monotonic())):
                raise ValueError
        return bytes(output)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
        process.stdout.close()
        process.stderr.close()


def _staging_identity(path, descriptor, expected):
    """Recheck privacy and pathname binding without releasing the held parent."""
    held = os.fstat(descriptor)
    if (
        (held.st_dev, held.st_ino) != expected
        or held.st_uid != os.getuid()
        or stat.S_IMODE(held.st_mode) != 0o700
    ):
        raise ValueError("Private source staging changed.")
    current = protected_directory(path, private=True)
    try:
        info = os.fstat(current)
        if (info.st_dev, info.st_ino) != expected:
            raise ValueError("Source staging was replaced.")
    finally:
        os.close(current)


@dataclass(frozen=True)
class SourceSnapshot:
    path: Path
    commit: str
    digest: str
    files: tuple[tuple[str, str], ...]
    _device: int = field(repr=False)
    _inode: int = field(repr=False)
    _registration: SourceRegistration = field(repr=False)
    _seal: str = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _parent_fd: int | None = field(default=None, repr=False)
    _parent_device: int | None = field(default=None, repr=False)
    _parent_inode: int | None = field(default=None, repr=False)
    _staging_fd: int | None = field(default=None, repr=False)
    _staging_device: int | None = field(default=None, repr=False)
    _staging_inode: int | None = field(default=None, repr=False)

    def verify(self) -> None:
        try:
            if self._closed or _SNAPSHOTS.get(self._seal) is not self:
                raise ValueError
            if self._parent_fd is None or self._staging_fd is None:
                raise ValueError
            staging_identity = (self._staging_device, self._staging_inode)
            _staging_identity(
                self.path.parent.parent, self._staging_fd, staging_identity
            )
            parent_identity = (self._parent_device, self._parent_inode)
            _staging_identity(self.path.parent, self._parent_fd, parent_identity)
            registration = _verify_registration(self._registration)
            if (registration.commit, registration.tree_digest) != (
                self.commit,
                self.digest,
            ):
                raise ValueError
            fd = os.open(
                self.path.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=self._parent_fd,
            )
            try:
                info = os.fstat(fd)
                if (info.st_dev, info.st_ino) != (
                    self._device,
                    self._inode,
                ) or stat.S_IMODE(info.st_mode) != 0o555:
                    raise ValueError
                actual = {
                    name: "sha256:" + hashlib.sha256(raw).hexdigest()
                    for name, raw in _walk(
                        fd, maximum=MAX_BYTES, max_files=MAX_FILES, immutable=True
                    ).items()
                }
                if (
                    tuple(sorted(actual.items())) != self.files
                    or tree_digest(actual) != self.digest
                ):
                    raise ValueError
            finally:
                os.close(fd)
            _staging_identity(self.path.parent, self._parent_fd, parent_identity)
            _staging_identity(
                self.path.parent.parent, self._staging_fd, staging_identity
            )
        except (ValueError, OSError, RuntimeError):
            raise ValueError("Immutable source snapshot unavailable.") from None

    def close(self) -> None:
        """Remove only this materialization, independent of revoked registration."""
        if self._closed:
            return
        if _SNAPSHOTS.get(self._seal) is not self:
            raise ValueError("Unknown source snapshot.")
        if self._parent_fd is None or self._staging_fd is None:
            raise ValueError("Source staging descriptor unavailable.")
        staging = self._staging_fd
        staging_info = os.fstat(staging)
        if (staging_info.st_dev, staging_info.st_ino) != (
            self._staging_device,
            self._staging_inode,
        ) or staging_info.st_uid != os.getuid():
            raise ValueError("Source staging descriptor changed.")
        parent = self._parent_fd
        held = os.fstat(parent)
        if (held.st_dev, held.st_ino) != (
            self._parent_device,
            self._parent_inode,
        ) or held.st_uid != os.getuid():
            raise ValueError("Source staging descriptor changed.")
        try:
            root = os.open(
                self.path.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent,
            )
            try:
                info = os.fstat(root)
                if (info.st_dev, info.st_ino) != (self._device, self._inode):
                    raise ValueError("Source snapshot was replaced.")
                count = 0
                deadline = time.monotonic() + 10

                def remove(directory):
                    nonlocal count
                    os.fchmod(directory, 0o700)
                    for name in os.listdir(directory):
                        count += 1
                        if count > MAX_FILES * 4 or time.monotonic() >= deadline:
                            raise ValueError("Source cleanup bound exceeded.")
                        entry = os.stat(name, dir_fd=directory, follow_symlinks=False)
                        if stat.S_ISDIR(entry.st_mode):
                            child = os.open(
                                name,
                                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=directory,
                            )
                            try:
                                current = os.fstat(child)
                                if (current.st_dev, current.st_ino) != (
                                    entry.st_dev,
                                    entry.st_ino,
                                ):
                                    raise ValueError("Source cleanup changed.")
                                remove(child)
                            finally:
                                os.close(child)
                            current = os.stat(
                                name, dir_fd=directory, follow_symlinks=False
                            )
                            if (current.st_dev, current.st_ino) != (
                                entry.st_dev,
                                entry.st_ino,
                            ):
                                raise ValueError("Source cleanup changed.")
                            os.rmdir(name, dir_fd=directory)
                        else:
                            # Unlink an introduced symlink itself, never its target.
                            os.unlink(name, dir_fd=directory)

                remove(root)
                current = os.stat(self.path.name, dir_fd=parent, follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (self._device, self._inode):
                    raise ValueError("Source snapshot was replaced.")
                os.rmdir(self.path.name, dir_fd=parent)
                envelope = os.stat(
                    self.path.parent.name, dir_fd=staging, follow_symlinks=False
                )
                if (envelope.st_dev, envelope.st_ino) != (
                    self._parent_device,
                    self._parent_inode,
                ):
                    raise ValueError("Source envelope was replaced.")
                os.rmdir(self.path.parent.name, dir_fd=staging)
                object.__setattr__(self, "_closed", True)
                _SNAPSHOTS.pop(self._seal, None)
            finally:
                os.close(root)
        finally:
            if self._closed:
                os.close(parent)
                object.__setattr__(self, "_parent_fd", None)
                os.close(staging)
                object.__setattr__(self, "_staging_fd", None)

    cleanup = close

    def __enter__(self):
        try:
            self.verify()
        except ValueError:
            self.close()
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def _validate_modules_inline(files):
    """Offline profile supports only vendored modules pinned by the source tree."""
    edges = {}
    for name, raw in files.items():
        if not name.endswith(CONFIG_SUFFIXES):
            continue
        try:
            document = (
                json.loads(raw, object_pairs_hook=_unique)
                if name.endswith(".json")
                else hcl2.loads(raw.decode("utf-8"))
            )
            blocks = document.get("module", {})
            if isinstance(blocks, dict):
                blocks = [blocks]
            if type(blocks) is not list:
                raise ValueError
            base = str(PurePosixPath(name).parent)
            for block in blocks:
                if type(block) is not dict:
                    raise ValueError
                for config in block.values():
                    if type(config) is not dict:
                        raise ValueError
                    source = config.get("source")
                    if type(source) is str and source.startswith('"'):
                        source = json.loads(source)
                    if (
                        type(source) is not str
                        or not source.startswith(("./", "../"))
                        or "\\" in source
                        or "${" in source
                        or "%{" in source
                        or "version" in config
                    ):
                        raise ValueError
                    target = posixpath.normpath(posixpath.join(base, source))
                    _relative(target)
                    if not any(
                        path.startswith(target + "/") and path.endswith(CONFIG_SUFFIXES)
                        for path in files
                    ):
                        raise ValueError
                    edges.setdefault(base, set()).add(target)
        except Exception:
            raise ValueError("Unpinned or invalid module source.") from None

    def visit(node, active, done):
        if node in active:
            raise ValueError("Cyclic module source.")
        if node in done:
            return
        for child in edges.get(node, ()):
            visit(child, active | {node}, done)
        done.add(node)

    done = set()
    for node in edges:
        visit(node, set(), done)


_MODULE_VALIDATOR = """
import json, resource, sys
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
if sys.platform == 'linux':
    resource.setrlimit(resource.RLIMIT_AS, (536870912, 536870912))
sys.path.insert(0, sys.argv[1])
from infra_automation.runner.source import _validate_modules_inline
try:
    value = json.loads(sys.stdin.buffer.read(67108865))
    _validate_modules_inline({name: text.encode('utf-8') for name, text in value.items()})
except BaseException:
    sys.exit(1)
"""


def _validate_modules(files, *, deadline=None):
    """Parse bounded HCL in a disposable host child before credential resolution."""
    configs = {
        name: raw for name, raw in files.items() if name.endswith(CONFIG_SUFFIXES)
    }
    if any(len(raw) > 131072 for raw in configs.values()):
        raise ValueError("Terraform configuration exceeds profile bound.")
    # Include all file names so vendored module roots remain resolvable, but no
    # non-configuration content is sent to the parser.
    value = {
        name: raw.decode("utf-8") if name in configs else ""
        for name, raw in files.items()
    }
    raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
    if len(raw) > 67108864:
        raise ValueError("Source parser input exceeds bound.")
    remaining = min(10.0, deadline - time.monotonic()) if deadline is not None else 10.0
    if remaining <= 0:
        raise ValueError("Source deadline expired.")
    root = Path(__file__).resolve().parents[2]
    process = subprocess.Popen(  # nosec B603
        [sys.executable, "-I", "-c", _MODULE_VALIDATOR, str(root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        cwd=root,
        start_new_session=True,
    )
    try:
        process.communicate(input=raw, timeout=remaining)
        if process.returncode != 0:
            raise ValueError("Invalid or unpinned module source.")
    except subprocess.TimeoutExpired:
        raise ValueError("Source parser deadline expired.") from None
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
        if process.stdin is not None:
            process.stdin.close()


def materialize_source(
    registration: SourceRegistration, destination_parent: str | Path
) -> SourceSnapshot:
    destination = None
    snapshot = None
    parent_fd = None
    envelope_fd = None
    envelope_name = None
    envelope_info = None
    try:
        registration = _verify_registration(registration)
        operation_deadline = time.monotonic() + 30
        destination_parent = Path(destination_parent)
        parent_fd = protected_directory(destination_parent, private=True)
        parent_info = os.fstat(parent_fd)
        parent_identity = (parent_info.st_dev, parent_info.st_ino)
        repository = Path(registration.repository_path)
        repo_fd = protected_directory(repository)
        os.close(repo_fd)
        gitdir = repository / ".git" if (repository / ".git").exists() else repository
        git_fd = protected_directory(gitdir)
        try:
            for forbidden in ("commondir", "shallow", "info/grafts"):
                if (gitdir / forbidden).exists():
                    raise ValueError
            objects_fd = os.open(
                "objects", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=git_fd
            )
            try:
                objects = _walk(objects_fd, maximum=OBJECT_BYTES, max_files=4096)
            finally:
                os.close(objects_fd)
        finally:
            os.close(git_fd)
        if any(
            name == "info/alternates" or name.endswith(".promisor") for name in objects
        ):
            raise ValueError
        # Git's private scratch is independent of the caller's staging pathname;
        # replacing that pathname cannot redirect scratch copies or cleanup.
        with tempfile.TemporaryDirectory(prefix="dw-git-objects-") as temporary:
            clean = Path(temporary) / "repo.git"
            clean.mkdir(mode=0o700)
            (clean / "objects").mkdir()
            (clean / "refs").mkdir()
            (clean / "HEAD").write_text("ref: refs/heads/unborn\n")
            (clean / "config").write_text(
                "[core]\n repositoryformatversion = 0\n bare = true\n"
            )
            for name, raw in objects.items():
                path = clean / "objects" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                path.chmod(0o400)
            body = _git(
                clean,
                "cat-file",
                "commit",
                registration.commit,
                maximum=65536,
                operation_deadline=operation_deadline,
            )
            git_hash = hashlib.sha1(
                b"commit " + str(len(body)).encode() + b"\0" + body,
                usedforsecurity=False,
            ).hexdigest()
            if git_hash != registration.commit:
                raise ValueError
            listing = _git(
                clean,
                "ls-tree",
                "-r",
                "-z",
                "--full-tree",
                registration.commit,
                operation_deadline=operation_deadline,
            )
            files: dict[str, bytes] = {}
            total = 0
            for entry in listing.split(b"\0"):
                if not entry:
                    continue
                metadata, name = entry.split(b"\t", 1)
                mode, kind, oid = metadata.split(b" ")
                name = _relative(name.decode("utf-8"))
                if (
                    mode not in (b"100644", b"100755")
                    or kind != b"blob"
                    or not re.fullmatch(b"[a-f0-9]{40}", oid)
                    or name in files
                    or len(files) >= MAX_FILES
                ):
                    raise ValueError
                raw = _git(
                    clean,
                    "cat-file",
                    "blob",
                    oid.decode(),
                    maximum=MAX_BYTES - total,
                    operation_deadline=operation_deadline,
                )
                if (
                    hashlib.sha1(
                        b"blob " + str(len(raw)).encode() + b"\0" + raw,
                        usedforsecurity=False,
                    ).hexdigest()
                    != oid.decode()
                ):
                    raise ValueError
                total += len(raw)
                files[name] = raw
            manifest = {
                name: "sha256:" + hashlib.sha256(raw).hexdigest()
                for name, raw in files.items()
            }
            if (
                not files
                or tree_digest(manifest) != registration.tree_digest
                or any(
                    manifest.get(name) != checksum
                    for name, checksum in registration.lock_digests.items()
                )
            ):
                raise ValueError
            _validate_modules(files, deadline=operation_deadline)
            directories = {
                str(parent)
                for name in files
                for parent in PurePosixPath(name).parents
                if str(parent) != "."
            }
            if len(directories) + len(files) > MAX_FILES * 4:
                raise ValueError("Source entry bound exceeded.")
            _staging_identity(destination_parent, parent_fd, parent_identity)
            envelope_name = "dw-source-" + secrets.token_hex(16)
            os.mkdir(envelope_name, 0o700, dir_fd=parent_fd)
            envelope_fd = os.open(
                envelope_name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            envelope_info = os.fstat(envelope_fd)
            # This private envelope never becomes container-readable. It still
            # protects the published tree if the caller relaxes staging modes.
            os.mkdir("tree", 0o700, dir_fd=envelope_fd)
            destination = destination_parent / envelope_name / "tree"
            root_fd = os.open(
                "tree", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=envelope_fd
            )
            try:
                info = os.fstat(root_fd)
                snapshot = SourceSnapshot(
                    destination,
                    registration.commit,
                    registration.tree_digest,
                    tuple(sorted(manifest.items())),
                    info.st_dev,
                    info.st_ino,
                    registration,
                    secrets.token_hex(24),
                    _parent_fd=envelope_fd,
                    _parent_device=envelope_info.st_dev,
                    _parent_inode=envelope_info.st_ino,
                    _staging_fd=parent_fd,
                    _staging_device=parent_info.st_dev,
                    _staging_inode=parent_info.st_ino,
                )
                _SNAPSHOTS[snapshot._seal] = snapshot
                for filename, raw in files.items():
                    _staging_identity(destination_parent, parent_fd, parent_identity)
                    components = PurePosixPath(filename).parts
                    directory = os.dup(root_fd)
                    try:
                        for component in components[:-1]:
                            try:
                                os.mkdir(component, 0o700, dir_fd=directory)
                            except FileExistsError:
                                pass
                            child = os.open(
                                component,
                                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=directory,
                            )
                            os.close(directory)
                            directory = child
                        fd = os.open(
                            components[-1],
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o600,
                            dir_fd=directory,
                        )
                        with os.fdopen(fd, "wb") as stream:
                            stream.write(raw)
                    finally:
                        os.close(directory)

                def publish(directory):
                    for child_name in os.listdir(directory):
                        _staging_identity(
                            destination_parent, parent_fd, parent_identity
                        )
                        child_info = os.stat(
                            child_name, dir_fd=directory, follow_symlinks=False
                        )
                        if stat.S_ISDIR(child_info.st_mode):
                            fd = os.open(
                                child_name,
                                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=directory,
                            )
                            try:
                                publish(fd)
                            finally:
                                os.close(fd)
                        elif stat.S_ISREG(child_info.st_mode):
                            fd = os.open(
                                child_name,
                                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                dir_fd=directory,
                            )
                            try:
                                _staging_identity(
                                    destination_parent, parent_fd, parent_identity
                                )
                                os.fchmod(fd, 0o444)
                            finally:
                                os.close(fd)
                        else:
                            raise ValueError("Source publication changed.")
                    _staging_identity(destination_parent, parent_fd, parent_identity)
                    # Distinct container UID needs read/traverse access to this
                    # read-only tree; its enclosing 0700 envelope stays private.
                    os.fchmod(directory, 0o555)  # nosec B103

                publish(root_fd)
            finally:
                os.close(root_fd)
            snapshot.verify()
        snapshot.verify()
        return snapshot
    except (ValueError, TypeError, OSError, RuntimeError, subprocess.SubprocessError):
        if snapshot is not None:
            try:
                snapshot.close()
            except (OSError, ValueError):
                # Leave private evidence for operator recovery rather than deleting
                # any substituted or foreign tree.
                if snapshot._parent_fd is not None:
                    os.close(snapshot._parent_fd)
                    object.__setattr__(snapshot, "_parent_fd", None)
                if snapshot._staging_fd is not None:
                    os.close(snapshot._staging_fd)
                    object.__setattr__(snapshot, "_staging_fd", None)
                _SNAPSHOTS.pop(snapshot._seal, None)
                raise ValueError("Trusted source cleanup unavailable.") from None
        raise ValueError("Trusted immutable source unavailable.") from None
    finally:
        if snapshot is None:
            if envelope_fd is not None:
                os.close(envelope_fd)
            if parent_fd is not None:
                try:
                    if envelope_name is not None and envelope_info is not None:
                        remaining = os.stat(
                            envelope_name, dir_fd=parent_fd, follow_symlinks=False
                        )
                        if (remaining.st_dev, remaining.st_ino) == (
                            envelope_info.st_dev,
                            envelope_info.st_ino,
                        ):
                            os.rmdir(envelope_name, dir_fd=parent_fd)
                finally:
                    os.close(parent_fd)
