"""Offline participating-domain backup/restore; no external action is replayed.

The private control ledger is deliberately outside every backup/restored root.
Host administrators and nonparticipating legacy writers remain an operator trust
boundary. Do not claim a shared flock fences an unrelated remote receiver.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

try:
    import fcntl
except ImportError:  # Advisory-only platforms do not install the recovery profile.
    fcntl = None
import hashlib
from functools import wraps
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
from uuid import uuid4

from sqlalchemy import (
    table as sql_table,
    column as sql_column,
    select as sql_select,
    bindparam as sql_bind,
    update as sql_update,
    func as sql_func,
)
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect

REVISION = "042_add_receiver_recovery"
SAFE = 9007199254740991
MAX_FILES = 4096
MAX_BYTES = 1024 * 1024 * 1024
MAX_METADATA = 1024 * 1024
_exclusive_control = ContextVar("recovery_exclusive_control", default=None)


class RecoveryError(RuntimeError):
    def __init__(self):
        super().__init__(
            "Operator recovery unavailable; inspect protected local storage and stop participating writers."
        )


def _guarded(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (OSError, ValueError, sqlite3.Error, TypeError, KeyError):
            raise RecoveryError() from None

    return call


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RecoveryError()
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=pairs)


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def _digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _path(value):
    path = Path(os.path.abspath(value))
    for parent in reversed((path, *path.parents)):
        if parent.exists() or parent.is_symlink():
            if parent.is_symlink():
                raise RecoveryError()
    return path


@_guarded
def _private(path, *, directory=False):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    if directory:
        flags |= os.O_DIRECTORY
    from infra_automation.runner.catalog import protected_directory

    path = Path(path)
    if directory:
        fd = protected_directory(path, private=True)
    else:
        parent = protected_directory(path.parent)
        try:
            fd = os.open(path.name, flags, dir_fd=parent)
        finally:
            os.close(parent)
    try:
        info = os.fstat(fd)
        if (
            info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode)
            not in ((0o700,) if directory else (0o400, 0o600))
            or not (
                stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
            )
            or (not directory and info.st_nlink != 1)
        ):
            raise RecoveryError()
        return fd
    except BaseException:
        os.close(fd)
        raise


def _sync_dir(path):
    fd = _private(path, directory=True)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@_guarded
def _write(path, data, *, replace=False):
    from infra_automation.runner.catalog import protected_directory

    parent = protected_directory(path.parent, private=True)
    pending = ".pending-" + uuid4().hex
    descriptor = None
    created = False
    try:
        descriptor = os.open(
            pending,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent,
        )
        created = True
        remaining = memoryview(data)
        while remaining:
            count = os.write(descriptor, remaining)
            if count <= 0:
                raise RecoveryError()
            remaining = remaining[count:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        if replace:
            os.replace(pending, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        else:
            os.link(
                pending,
                path.name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
            os.unlink(pending, dir_fd=parent)
        created = False
        os.fsync(parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            try:
                os.unlink(pending, dir_fd=parent)
            except FileNotFoundError:
                pass
        os.close(parent)


def _read(path, maximum=MAX_METADATA):
    fd = _private(path)
    try:
        before = os.fstat(fd)
        if before.st_size > maximum:
            raise RecoveryError()
        raw = bytearray()
        while len(raw) <= maximum:
            chunk = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not chunk:
                after = os.fstat(fd)
                if len(raw) != before.st_size or any(
                    getattr(before, k) != getattr(after, k)
                    for k in (
                        "st_dev",
                        "st_ino",
                        "st_size",
                        "st_mtime_ns",
                        "st_ctime_ns",
                    )
                ):
                    raise RecoveryError()
                return bytes(raw)
            raw.extend(chunk)
        raise RecoveryError()
    finally:
        os.close(fd)


def _walk(root):
    """Hold every directory identity while opening bounded regular private files."""
    results = {}
    total = 0
    entries = 0

    def visit(fd, prefix, depth):
        nonlocal total, entries
        if depth > 32:
            raise RecoveryError()
        for entry in os.scandir(fd):
            entries += 1
            if entries > MAX_FILES:
                raise RecoveryError()
            name = entry.name
            if name in {".", ".."} or any(ord(c) < 32 for c in name):
                raise RecoveryError()
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            relative = prefix + name
            if stat.S_ISDIR(info.st_mode):
                child = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
                try:
                    current = os.fstat(child)
                    if (
                        current.st_uid != os.getuid()
                        or stat.S_IMODE(current.st_mode) != 0o700
                    ):
                        raise RecoveryError()
                    results[relative] = (None, 0o700)
                    visit(child, relative + "/", depth + 1)
                finally:
                    os.close(child)
            else:
                child = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
                )
                try:
                    before = os.fstat(child)
                    if (
                        not stat.S_ISREG(before.st_mode)
                        or before.st_uid != os.getuid()
                        or before.st_nlink != 1
                        or stat.S_IMODE(before.st_mode) not in (0o400, 0o600)
                        or total + before.st_size > MAX_BYTES
                        or len(results) >= MAX_FILES
                    ):
                        raise RecoveryError()
                    chunks = []
                    count = 0
                    while chunk := os.read(child, min(65536, MAX_BYTES - total + 1)):
                        count += len(chunk)
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise RecoveryError()
                        chunks.append(chunk)
                    after = os.fstat(child)
                    if (
                        before.st_dev,
                        before.st_ino,
                        before.st_size,
                        before.st_mtime_ns,
                    ) != (
                        after.st_dev,
                        after.st_ino,
                        after.st_size,
                        after.st_mtime_ns,
                    ) or count != before.st_size:
                        raise RecoveryError()
                    results[relative] = (b"".join(chunks), stat.S_IMODE(before.st_mode))
                finally:
                    os.close(child)

    fd = _private(root, directory=True)
    try:
        visit(fd, "", 0)
    finally:
        os.close(fd)
    return results


def _records(files):
    return {
        name: (
            {"kind": "directory", "mode": mode}
            if raw is None
            else {
                "kind": "file",
                "size": len(raw),
                "digest": _digest(raw),
                "mode": mode,
            }
        )
        for name, (raw, mode) in files.items()
    }


def _copy_tree(source, destination):
    files = _walk(source)
    destination.mkdir(mode=0o700)
    for relative, (raw, mode) in files.items():
        target = destination / relative
        if raw is None:
            target.mkdir(mode=0o700, parents=True, exist_ok=True)
        else:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _write(target, raw)
            target.chmod(mode)
    for directory, _, _ in os.walk(destination, topdown=False):
        _sync_dir(Path(directory))
    return _records(files)


@contextmanager
def _connect(path):
    """Let SQLite exclusively own database descriptors and POSIX file locks.

    A raw open/close of a live database would release this process's SQLite
    locks, including locks on other pooled connections. See SQLite's corruption
    guide section 2.2. Validate through a held directory and lstat instead.
    """
    from infra_automation.runner.catalog import protected_directory

    path = _path(path)
    parent = protected_directory(path.parent, private=True)
    connection = None

    def checked_info():
        info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) not in (0o400, 0o600)
            or info.st_nlink != 1
        ):
            raise RecoveryError()
        return info

    try:
        before = checked_info()
        connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=0)
        after = checked_info()
        actual = connection.execute("PRAGMA database_list").fetchone()[2]
        if (
            any(
                getattr(before, key) != getattr(after, key)
                for key in ("st_dev", "st_ino", "st_uid", "st_mode", "st_nlink")
            )
            or _path(actual) != path
        ):
            raise RecoveryError()
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    finally:
        if connection is not None:
            connection.close()
        os.close(parent)


def _tables(connection):
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _ceiling(connection):
    maximum = 1
    tables = _tables(connection)
    for table, columns in (
        ("identity_accounts", ("authentication_version",)),
        (
            "infra_automation_policies",
            ("version", "authorization_epoch", "restore_epoch"),
        ),
        (
            "infra_automation_runners",
            (
                "generation",
                "issuer_authentication_version",
                "issuer_membership_version",
            ),
        ),
        ("infra_automation_coordinator_lease", ("generation", "version")),
        ("infra_automation_recovery_state", ("generation",)),
    ):
        if table not in tables:
            continue
        for column in columns:
            for (value,) in connection.execute(
                str(
                    sql_select(sql_column(column))
                    .select_from(sql_table(table))
                    .compile(dialect=sqlite_dialect())
                )
            ):
                if type(value) is not int or not 1 <= value < SAFE:
                    raise RecoveryError()
                maximum = max(maximum, value)
    return maximum


def _timestamp(connection):
    value = datetime.now(timezone.utc)
    for table in _tables(connection):
        if not re.fullmatch(r"[a-z_]+", table):
            continue
        columns = {
            row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
        }
        for column in columns & {"last_observed_at", "updated_at"}:
            candidate = connection.execute(
                str(
                    sql_select(sql_func.max(sql_column(column)))
                    .select_from(sql_table(table))
                    .compile(dialect=sqlite_dialect())
                )
            ).fetchone()[0]
            if candidate:
                parsed = datetime.fromisoformat(candidate)
                parsed = (
                    parsed.replace(tzinfo=timezone.utc)
                    if parsed.tzinfo is None
                    else parsed.astimezone(timezone.utc)
                )
                value = max(value, parsed)
    return value.replace(tzinfo=None).isoformat(" ")


class RecoveryStore:
    def __init__(self, control):
        self.control = _path(control)

    @contextmanager
    def _lock(self, exclusive=False):
        if fcntl is None:
            raise RecoveryError()
        fd = _private(self.control, directory=True)
        os.close(fd)
        descriptor = os.open(
            self.control / "lifecycle.lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
        )
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise RecoveryError()
            try:
                fcntl.flock(
                    descriptor,
                    (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB,
                )
            except OSError:
                raise RecoveryError() from None
            token = _exclusive_control.set(self.control) if exclusive else None
            try:
                yield
            finally:
                if token is not None:
                    _exclusive_control.reset(token)
        finally:
            os.close(descriptor)

    def _ledger(self):
        value = _json(_read(self.control / "ledger.json"))
        if (
            type(value) is not dict
            or set(value)
            != {
                "version",
                "installation_id",
                "generation",
                "phase",
                "database",
                "roots",
                "operation_id",
                "backup",
                "manifest_digest",
                "publication",
            }
            or (type(value["version"]) is not int or value["version"] != 1)
            or type(value["generation"]) is not int
            or not 1 <= value["generation"] <= SAFE
            or value["phase"]
            not in {
                "ready",
                "restore_reserved",
                "publishing",
                "reconciliation_required",
                "completing",
            }
            or re.fullmatch(r"[a-f0-9]{32}", value["installation_id"]) is None
        ):
            raise RecoveryError()
        self._layout(value["database"], value["roots"])
        return value

    def _save(self, value):
        _write(self.control / "ledger.json", _canonical(value), replace=True)

    def _layout(self, database, roots):
        if (
            type(roots) is not dict
            or not {"artifacts", "custody"} <= set(roots)
            or len(roots) > 8
            or any(re.fullmatch(r"[a-z][a-z_]{0,31}", role) is None for role in roots)
        ):
            raise RecoveryError()
        paths = [
            self.control,
            _path(database),
            *(_path(path) for path in roots.values()),
        ]
        for index, path in enumerate(paths):
            for other in paths[index + 1 :]:
                if path == other or path in other.parents or other in path.parents:
                    raise RecoveryError()
        return paths

    @_guarded
    def initialize(self, database, roots):
        database = _path(database)
        roots = {role: str(_path(root)) for role, root in roots.items()}
        self._layout(database, roots)
        for root in roots.values():
            fd = _private(root, directory=True)
            os.close(fd)
        self.control.mkdir(mode=0o700)
        _write(self.control / "lifecycle.lock", b"")
        with self._lock(exclusive=True), _connect(database) as connection:
            self._schema(connection)
            if connection.execute(
                "SELECT 1 FROM infra_automation_recovery_state"
            ).fetchone():
                raise RecoveryError()
            generation = _ceiling(connection)
            installation_id = uuid4().hex
            now = _timestamp(connection)
            connection.execute(
                "INSERT INTO infra_automation_recovery_state VALUES(1,?,?, 'ready',NULL,?)",
                (installation_id, generation, now),
            )
            connection.commit()
            self._save(
                dict(
                    version=1,
                    installation_id=installation_id,
                    generation=generation,
                    phase="ready",
                    database=str(database),
                    roots=roots,
                    operation_id=None,
                    backup=None,
                    manifest_digest=None,
                    publication={},
                )
            )
        return self.status()

    @_guarded
    def status(self):
        with self._lock():
            return self._ledger()

    @contextmanager
    def participate(self):
        if _exclusive_control.get() == self.control:
            yield
            return
        with self._lock():
            self.assert_ready(effects=False)
            yield

    @_guarded
    def assert_ready(self, *, effects=False, session=None):
        value = self._ledger()
        if value["phase"] not in (
            {"ready"} if effects else {"ready", "reconciliation_required"}
        ):
            raise RecoveryError()
        query = "SELECT installation_id,generation,phase FROM infra_automation_recovery_state WHERE id=1"
        if session is None:
            with _connect(value["database"]) as connection:
                row = connection.execute(query).fetchone()
        else:
            actual = _path(session.get_bind().url.database)
            if actual != Path(value["database"]):
                raise RecoveryError()
            row = session.connection().exec_driver_sql(query).fetchone()
        if row is None or tuple(row) != (
            value["installation_id"],
            value["generation"],
            value["phase"],
        ):
            raise RecoveryError()
        for root in value["roots"].values():
            fd = _private(root, directory=True)
            os.close(fd)
        return value

    @_guarded
    def backup(self, output):
        with self._lock(exclusive=True):
            value = self.assert_ready()
            if value["phase"] != "ready":
                raise RecoveryError()
            output = _path(output)
            for source in [
                self.control,
                Path(value["database"]),
                *(Path(p) for p in value["roots"].values()),
            ]:
                if (
                    output == source
                    or source in output.parents
                    or output in source.parents
                ):
                    raise RecoveryError()
            if output.exists():
                raise RecoveryError()
            staging = output.with_name(".backup-" + uuid4().hex)
            staging.mkdir(mode=0o700)
            database_copy = staging / "database.sqlite"
            _write(database_copy, b"")
            with (
                _connect(value["database"]) as source,
                _connect(database_copy) as destination,
            ):
                source.execute("BEGIN IMMEDIATE")
                source.rollback()
                source.backup(destination)
                self._integrity(destination)
                self._schema(destination)
            raw = _read(database_copy, MAX_BYTES)
            files = {
                "database.sqlite": {
                    "kind": "file",
                    "size": len(raw),
                    "digest": _digest(raw),
                    "mode": 0o600,
                }
            }
            for role, root in value["roots"].items():
                files[role] = {"kind": "directory", "mode": 0o700}
                for relative, record in _copy_tree(Path(root), staging / role).items():
                    files[role + "/" + relative] = record
            if (
                len(files) > MAX_FILES
                or sum(record.get("size", 0) for record in files.values()) > MAX_BYTES
            ):
                raise RecoveryError()
            manifest = dict(
                version=1,
                schema_revision=REVISION,
                installation_id=value["installation_id"],
                generation=value["generation"],
                files=files,
                roles=sorted(value["roots"]),
            )
            _write(staging / "manifest.json", _canonical(manifest))
            _sync_dir(staging)
            from infra_automation.receiver_custody import _publish_directory

            parent_fd = os.open(
                output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            try:
                _publish_directory(parent_fd, staging.name, output.name)
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            return {
                "manifest_digest": _digest(_canonical(manifest)),
                "files": len(files),
            }

    @staticmethod
    def _integrity(connection):
        if (
            connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
            or connection.execute("PRAGMA foreign_key_check").fetchone()
        ):
            raise RecoveryError()

    @staticmethod
    def _schema(connection):
        """Use the same complete effective-guard checks as application startup."""
        from sqlalchemy import create_engine, inspect
        from sqlalchemy.exc import SQLAlchemyError
        from models import database
        import models.tables  # noqa: F401

        if connection.execute("SELECT version_num FROM alembic_version").fetchall() != [
            (REVISION,)
        ]:
            raise RecoveryError()
        path = connection.execute("PRAGMA database_list").fetchone()[2]
        engine = create_engine("sqlite:///" + str(path))
        try:
            with engine.connect() as db:
                tables = set(inspect(db).get_table_names())
                if not database._identity_schema_complete(
                    db, tables
                ) or not database._project_authorization_schema_complete(db, tables):
                    raise RecoveryError()
                for revision in sorted(database._KNOWN_ALEMBIC_REVISIONS):
                    if (
                        revision[:3].isdigit()
                        and 31 <= int(revision[:3]) <= 42
                        and not database._infra_automation_schema_complete(
                            db, tables, revision
                        )
                    ):
                        raise RecoveryError()
        except (RuntimeError, SQLAlchemyError, ValueError):
            raise RecoveryError() from None
        finally:
            engine.dispose()

    def _verify_backup(self, backup, value):
        backup = _path(backup)
        for source in [
            self.control,
            Path(value["database"]),
            *(Path(path) for path in value["roots"].values()),
        ]:
            if backup == source or source in backup.parents or backup in source.parents:
                raise RecoveryError()
        files = _walk(backup)
        if "manifest.json" not in files:
            raise RecoveryError()
        raw = files.pop("manifest.json")[0]
        if len(raw) > MAX_METADATA:
            raise RecoveryError()
        manifest = _json(raw)
        if (
            set(manifest)
            != {
                "version",
                "schema_revision",
                "installation_id",
                "generation",
                "files",
                "roles",
            }
            or type(manifest["version"]) is not int
            or manifest["version"] != 1
            or manifest["schema_revision"] != REVISION
            or type(manifest["generation"]) is not int
            or not 1 <= manifest["generation"] <= SAFE
            or manifest["installation_id"] != value["installation_id"]
            or manifest["roles"] != sorted(value["roots"])
        ):
            raise RecoveryError()
        actual = _records(files)
        if actual != manifest["files"] or "database.sqlite" not in actual:
            raise RecoveryError()
        return backup, _digest(raw)

    @staticmethod
    def _preserve_external_history(current, incoming):
        """An older snapshot cannot erase current known external work.

        Conservatively require current handoff/grant/lock/fact rows in the input
        with identical bytes. Reconciliation or a break is never synthesized by
        restoring an older snapshot; operator must use a sufficiently new backup
        or a separately reviewed manual recovery if current storage is corrupt.
        """
        for table in (
            "infra_automation_handoffs",
            "infra_automation_grants",
            "infra_automation_target_locks",
            "infra_automation_external_facts",
        ):
            columns = [
                row[1] for row in current.execute(f'PRAGMA table_info("{table}")')
            ]
            if not columns:
                raise RecoveryError()
            relation = sql_table(table, *(sql_column(name) for name in columns))
            current_sql = str(sql_select(*relation.c).compile(dialect=sqlite_dialect()))
            predicate = [
                column.is_(sql_bind("p" + str(index)))
                for index, column in enumerate(relation.c)
            ]
            match_sql = str(
                sql_select(relation.c[0])
                .where(*predicate)
                .compile(dialect=sqlite_dialect())
            )
            for record in current.execute(current_sql):
                if incoming.execute(match_sql, record).fetchone() is None:
                    raise RecoveryError()
        for record in current.execute(
            "SELECT id,version,state,external_possible FROM infra_automation_runs WHERE external_possible=1"
        ):
            if (
                incoming.execute(
                    "SELECT 1 FROM infra_automation_runs WHERE id=? AND version=? AND state=? AND external_possible=?",
                    record,
                ).fetchone()
                is None
            ):
                raise RecoveryError()

    @_guarded
    def restore(self, backup):
        with self._lock(exclusive=True):
            value = self.assert_ready()
            backup, digest = self._verify_backup(backup, value)
            with (
                _connect(value["database"]) as current,
                _connect(backup / "database.sqlite") as incoming,
            ):
                self._integrity(incoming)
                self._schema(incoming)
                self._schema(current)
                self._preserve_external_history(current, incoming)
                generation = (
                    max(value["generation"], _ceiling(current), _ceiling(incoming)) + 1
                )
                if generation >= SAFE:
                    raise RecoveryError()
                # Detect active nonparticipating SQLite writers; domain locking is
                # still necessary for files/remote receiver processes.
                current.execute("BEGIN EXCLUSIVE")
                current.rollback()
            value.update(
                generation=generation,
                phase="restore_reserved",
                operation_id=uuid4().hex,
                backup=str(backup),
                manifest_digest=digest,
                publication={},
            )
            self._save(value)
            return self._finish_restore(value)

    @_guarded
    def resume(self):
        with self._lock(exclusive=True):
            value = self._ledger()
            if value["phase"] == "completing":
                # Resume only publication of an already recorded completion, or
                # reopen read-only recovery after its business transaction rolled
                # back. Requiring the old session here would make an interrupted
                # completion unrecoverable after that session expires.
                operation_id = value["operation_id"]
                manifest = value["manifest_digest"]
                if (
                    type(operation_id) is not str
                    or re.fullmatch(r"[a-f0-9]{32}", operation_id) is None
                    or type(manifest) is not str
                    or re.fullmatch(r"sha256:[a-f0-9]{64}", manifest) is None
                ):
                    raise RecoveryError()
                with _connect(value["database"]) as connection:
                    self._integrity(connection)
                    self._schema(connection)
                    state = connection.execute(
                        "SELECT installation_id,generation,phase,manifest_digest FROM infra_automation_recovery_state WHERE id=1"
                    ).fetchone()
                    restored = connection.execute(
                        "SELECT generation,backup_digest,event,actor_id FROM infra_automation_restore_events WHERE id=?",
                        (operation_id,),
                    ).fetchone()
                    if (
                        state is None
                        or tuple(state[:2])
                        != (value["installation_id"], value["generation"])
                        or state[3] != manifest
                        or restored
                        != (value["generation"], manifest, "restored", "local-operator")
                    ):
                        raise RecoveryError()
                    completed = connection.execute(
                        "SELECT id,backup_digest,actor_id FROM infra_automation_restore_events WHERE generation=? AND event='completed'",
                        (value["generation"],),
                    ).fetchall()
                    if state[2] == "reconciliation_required" and not completed:
                        phase = "reconciliation_required"
                    elif state[2] == "ready" and len(completed) == 1:
                        identifier, digest, actor = completed[0]
                        expected = hashlib.sha256(
                            (operation_id + ":completed").encode()
                        ).hexdigest()[:32]
                        if (
                            identifier != expected
                            or digest != manifest
                            or not connection.execute(
                                "SELECT 1 FROM identity_accounts WHERE id=? AND principal_type='human'",
                                (actor,),
                            ).fetchone()
                        ):
                            raise RecoveryError()
                        phase = "ready"
                    else:
                        raise RecoveryError()
                # No database mutation, new credential, policy enablement or
                # replacement approval occurs while completing this journal.
                value["phase"] = phase
                self._save(value)
                return self.assert_ready(effects=False)
            if value["phase"] not in {"restore_reserved", "publishing"}:
                raise RecoveryError()
            return self._finish_restore(value)

    @staticmethod
    def _fingerprint(path, *, database=False):
        if database:
            return _digest(_read(path, MAX_BYTES))
        files = _walk(path)
        return _digest(_canonical(_records(files)))

    def _stage(self, value):
        backup, digest = self._verify_backup(value["backup"], value)
        if digest != value["manifest_digest"]:
            raise RecoveryError()
        staged = {}
        sources = {
            "database": backup / "database.sqlite",
            **{role: backup / role for role in value["roots"]},
        }
        targets = {
            "database": Path(value["database"]),
            **{role: Path(path) for role, path in value["roots"].items()},
        }
        for role, target in targets.items():
            stage = target.with_name(
                ".restore-new-" + value["operation_id"] + "-" + role
            )
            old = target.with_name(".restore-old-" + value["operation_id"] + "-" + role)
            staged[role] = (stage, target, old)
            record = value["publication"].get(role)
            is_db = role == "database"
            if old.exists():
                if (
                    record is None
                    or self._fingerprint(old, database=is_db) != record["old"]
                ):
                    raise RecoveryError()
                installed = target if target.exists() else stage
                if self._fingerprint(installed, database=is_db) != record["new"]:
                    raise RecoveryError()
                continue
            if record is not None:
                if (
                    self._fingerprint(target, database=is_db) != record["old"]
                    or self._fingerprint(stage, database=is_db) != record["new"]
                ):
                    raise RecoveryError()
                continue
            if stage.exists():
                if is_db:
                    _read(stage, MAX_BYTES)
                    stage.unlink()
                else:
                    _walk(stage)
                    shutil.rmtree(stage)
            if is_db:
                with _connect(target) as current:
                    checkpoint = current.execute(
                        "PRAGMA wal_checkpoint(TRUNCATE)"
                    ).fetchone()
                    if checkpoint and checkpoint[0]:
                        raise RecoveryError()
                _write(stage, _read(sources[role], MAX_BYTES))
                with _connect(stage) as connection:
                    self._invalidate(connection, value)
                    self._integrity(connection)
                descriptor = _private(stage)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            else:
                _copy_tree(sources[role], stage)
            value["publication"][role] = dict(
                old=self._fingerprint(target, database=is_db),
                new=self._fingerprint(stage, database=is_db),
            )
            self._save(value)
        return staged

    def _finish_restore(self, value):
        staged = self._stage(value)
        value["phase"] = "publishing"
        self._save(value)
        for role, (stage, target, old) in staged.items():
            if not old.exists():
                if (
                    self._fingerprint(target, database=role == "database")
                    != value["publication"][role]["old"]
                ):
                    raise RecoveryError()
                os.rename(target, old)
                _sync_dir(target.parent)
            if stage.exists():
                if (
                    target.exists()
                    or self._fingerprint(stage, database=role == "database")
                    != value["publication"][role]["new"]
                ):
                    raise RecoveryError()
                os.rename(stage, target)
                _sync_dir(target.parent)
            if (
                self._fingerprint(target, database=role == "database")
                != value["publication"][role]["new"]
            ):
                raise RecoveryError()
        with _connect(value["database"]) as connection:
            self._integrity(connection)
            row = connection.execute(
                "SELECT installation_id,generation,phase FROM infra_automation_recovery_state WHERE id=1"
            ).fetchone()
            if row != (
                value["installation_id"],
                value["generation"],
                "reconciliation_required",
            ):
                raise RecoveryError()
        value["phase"] = "reconciliation_required"
        self._save(value)
        return self.assert_ready()

    def _invalidate(self, connection, value):
        tables = _tables(connection)
        now = _timestamp(connection)
        generation = value["generation"]
        connection.execute("BEGIN IMMEDIATE")
        for table, column in (
            ("identity_sessions", "revoked_at"),
            ("identity_credentials", "consumed_at"),
            ("infra_automation_runner_enrollments", "consumed_at"),
        ):
            if table in tables:
                relation = sql_table(table, sql_column(column))
                statement = (
                    sql_update(relation)
                    .where(relation.c[column].is_(None))
                    .values({column: sql_bind("now")})
                )
                connection.execute(
                    str(statement.compile(dialect=sqlite_dialect())), (now,)
                )
        if "identity_accounts" in tables:
            connection.execute(
                "UPDATE identity_accounts SET authentication_version=?", (generation,)
            )
        if "infra_automation_policies" in tables:
            for project_id, settings_json in connection.execute(
                "SELECT project_id,settings_json FROM infra_automation_policies"
            ).fetchall():
                settings = _json(settings_json)
                settings["enabled"] = False
                connection.execute(
                    "UPDATE infra_automation_policies SET settings_json=?,version=?,authorization_epoch=?,restore_epoch=?,updated_at=? WHERE project_id=?",
                    (
                        _canonical(settings).decode(),
                        generation,
                        generation,
                        generation,
                        now,
                        project_id,
                    ),
                )
        if "infra_automation_runners" in tables:
            connection.execute(
                "UPDATE infra_automation_runners SET generation=?,status='revoked',credential_hash=NULL,credential_expires_at=NULL,last_observed_at=?",
                (generation, now),
            )
        if "infra_automation_runner_tasks" in tables:
            connection.execute(
                "UPDATE infra_automation_runner_tasks SET upload_id=NULL,upload_digest=NULL,upload_bytes=NULL"
            )
        if "infra_automation_coordinator_lease" in tables:
            connection.execute(
                "UPDATE infra_automation_coordinator_lease SET generation=?,version=?,owner_id=NULL,owner_hash=NULL,lease_until=NULL,last_observed_at=?",
                (generation, generation, now),
            )
        if "infra_automation_grants" in tables:
            connection.execute(
                "UPDATE infra_automation_grants SET status='invalidated',version=version+1 WHERE status='available'"
            )
        existing = connection.execute(
            "SELECT installation_id FROM infra_automation_recovery_state WHERE id=1"
        ).fetchone()
        if existing is None or existing[0] != value["installation_id"]:
            raise RecoveryError()
        connection.execute(
            "UPDATE infra_automation_recovery_state SET generation=?,phase='reconciliation_required',manifest_digest=?,updated_at=? WHERE id=1",
            (generation, value["manifest_digest"], now),
        )
        connection.execute(
            "INSERT INTO infra_automation_restore_events(id,generation,backup_digest,event,actor_id,reason,created_at) VALUES(?,?,?,'restored','local-operator','Coordinated offline restore; imported authority invalidated.',?)",
            (value["operation_id"], generation, value["manifest_digest"], now),
        )
        connection.commit()

    def complete(self, reason):
        """Explicit fresh human administration; never a grant or remote action."""
        from services import project_service as authorization
        from services import infra_automation_support as support
        from infra_automation import reconciliation
        from sqlalchemy import select, text
        from models.tables import InfraAutomationHandoff, InfraAutomationPolicy

        with self._lock(exclusive=True):
            value = self._ledger()
            if value["phase"] not in {"reconciliation_required", "completing"}:
                raise RecoveryError()
            with authorization.authorized_session() as session:
                actual = _path(session.get_bind().url.database)
                if actual != Path(value["database"]):
                    raise RecoveryError()
                principal = authorization._verified_principal(session, mutation=True)
                if (
                    not principal.is_admin
                    or principal.principal_type != "human"
                    or principal.credential_audience != "human"
                ):
                    raise authorization.TrustedAuthorizationError()
                if (
                    type(reason) is not str
                    or not 1 <= len(reason) <= 256
                    or not reason.strip()
                    or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in reason)
                ):
                    raise RecoveryError()
                support.screened_label(reason)
                for project_id in session.scalars(
                    select(InfraAutomationPolicy.project_id)
                ):
                    support.scope(
                        session, project_id, None, "automation.admin", mutation=True
                    )
                row = (
                    session.connection()
                    .exec_driver_sql(
                        "SELECT installation_id,generation,phase FROM infra_automation_recovery_state WHERE id=1"
                    )
                    .fetchone()
                )
                if row is None or tuple(row[:2]) != (
                    value["installation_id"],
                    value["generation"],
                ):
                    raise RecoveryError()
                completed_id = hashlib.sha256(
                    (value["operation_id"] + ":completed").encode()
                ).hexdigest()[:32]
                if row[2] == "ready":
                    if (
                        value["phase"] != "completing"
                        or not session.connection()
                        .exec_driver_sql(
                            "SELECT 1 FROM infra_automation_restore_events WHERE id=? AND event='completed' AND generation=?",
                            (completed_id, value["generation"]),
                        )
                        .fetchone()
                    ):
                        raise RecoveryError()
                else:
                    if row[2] != "reconciliation_required":
                        raise RecoveryError()
                    operations = list(session.scalars(select(InfraAutomationHandoff)))
                    for operation in operations:
                        if operation.broken:
                            continue
                        callback = reconciliation.latest(
                            session, operation.id, "callback"
                        )
                        if (
                            operation.state not in {"succeeded", "failed"}
                            or callback is None
                            or callback["message"]["state"] != operation.state
                        ):
                            raise RecoveryError()
                    if (
                        session.connection()
                        .exec_driver_sql(
                            "SELECT 1 FROM infra_automation_target_locks WHERE status='held' LIMIT 1"
                        )
                        .fetchone()
                    ):
                        raise RecoveryError()
                    if (
                        session.connection()
                        .exec_driver_sql(
                            "SELECT 1 FROM infra_automation_runs r WHERE r.external_possible=1 AND r.state IN ('handing_off','external_running','delivery_unknown') AND NOT EXISTS(SELECT 1 FROM infra_automation_handoffs h WHERE h.run_id=r.id) LIMIT 1"
                        )
                        .fetchone()
                    ):
                        raise RecoveryError()
                    # Journal first: crash after this point never clears the barrier.
                    value["phase"] = "completing"
                    self._save(value)
                    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(" ")
                    session.execute(
                        text(
                            "UPDATE infra_automation_recovery_state SET phase='ready',updated_at=CASE WHEN updated_at>:now THEN updated_at ELSE :now END WHERE id=1"
                        ),
                        {"now": now},
                    )
                    session.execute(
                        text(
                            "INSERT INTO infra_automation_restore_events(id,generation,backup_digest,event,actor_id,reason,created_at) VALUES(:id,:generation,:digest,'completed',:actor,:reason,:now)"
                        ),
                        dict(
                            id=completed_id,
                            generation=value["generation"],
                            digest=value["manifest_digest"],
                            actor=principal.principal_id,
                            reason=reason,
                            now=now,
                        ),
                    )
            value["phase"] = "ready"
            self._save(value)
            return self.assert_ready()


def configured_store():
    import config

    path = getattr(config.settings, "recovery_control_path", "")
    return RecoveryStore(path) if path else None


@contextmanager
def participating_operation():
    from infra_automation.lifecycle import LifecycleError

    try:
        store = configured_store()
        if store is None:
            yield
        else:
            with store.participate():
                yield
    except RecoveryError:
        raise LifecycleError(503) from None


def assert_effects_allowed(session):
    """Deny-only hook; never substitutes for operation audience/permission checks."""
    from infra_automation.lifecycle import LifecycleError

    try:
        store = configured_store()
        if store is None:
            row = (
                session.connection()
                .exec_driver_sql(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='infra_automation_recovery_state'"
                )
                .fetchone()
            )
            if (
                row
                and session.connection()
                .exec_driver_sql(
                    "SELECT 1 FROM infra_automation_recovery_state LIMIT 1"
                )
                .fetchone()
            ):
                raise RecoveryError()
        else:
            store.assert_ready(effects=True, session=session)
    except (RecoveryError, OSError, ValueError, sqlite3.Error):
        raise LifecycleError(503) from None


def assert_startup_allowed():
    """Run before migrations/background workers; removing config never unfences DB."""
    import config
    from sqlalchemy.engine import make_url

    store = configured_store()
    if store is not None:
        value = store.assert_ready(effects=False)
        url = make_url(config.settings.database_url)
        if url.get_backend_name() != "sqlite" or _path(url.database) != Path(
            value["database"]
        ):
            raise RecoveryError()
        return value
    url = make_url(config.settings.database_url)
    if (
        url.get_backend_name() != "sqlite"
        or not url.database
        or url.database == ":memory:"
    ):
        return
    path = Path(url.database)
    if not path.exists():
        return
    # Unconfigured legacy installs remain unchanged; a bound database does not.
    connection = (
        sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        if path.is_absolute()
        else sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    )
    try:
        if (
            "infra_automation_recovery_state" in _tables(connection)
            and connection.execute(
                "SELECT 1 FROM infra_automation_recovery_state LIMIT 1"
            ).fetchone()
        ):
            raise RecoveryError()
    finally:
        connection.close()


@_guarded
def upgrade_database_copy(source, output):
    """Upgrade a private immutable v1.4.0 copy, never the operator's live DB."""
    from alembic import command
    from alembic.config import Config

    source, output = _path(source), _path(output)
    source_fd = _private(source)
    try:
        if (
            stat.S_IMODE(os.fstat(source_fd).st_mode) != 0o400
            or output.exists()
            or source == output
        ):
            raise RecoveryError()
    finally:
        os.close(source_fd)
    input_connection = sqlite3.connect(
        source.as_uri() + "?mode=ro", uri=True, timeout=0
    )
    try:
        if input_connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchall() != [("028_add_narrative_guidance_payload",)]:
            raise RecoveryError()
        RecoveryStore._integrity(input_connection)
        staging = output.with_name(".upgrade-" + uuid4().hex)
        _write(staging, b"")
        with _connect(staging) as destination:
            input_connection.backup(destination)
    finally:
        input_connection.close()
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    previous = os.environ.get("DATABASE_URL")
    try:
        # Alembic's existing env.py takes DATABASE_URL over Config. This helper
        # is an offline single-process operator command, never an HTTP handler.
        os.environ["DATABASE_URL"] = "sqlite:///" + str(staging)
        cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    with _connect(staging) as connection:
        RecoveryStore._integrity(connection)
        RecoveryStore._schema(connection)
    fd = _private(staging)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    os.link(staging, output, follow_symlinks=False)
    staging.unlink()
    _sync_dir(output.parent)
    return {"schema_revision": REVISION}
