"""Disposable singleton SQLite experiment, deliberately separate from app DB."""

from __future__ import annotations

from contextlib import closing
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time


class Busy(RuntimeError):
    """Bounded lock budget exhausted; caller may retry only safe local work."""


class Store:
    def __init__(self, path, initialize=True):
        self.path = str(path)
        self.busy_count = 0
        if not initialize:
            return
        with closing(self.connection()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS control (
                    id INTEGER PRIMARY KEY CHECK(id=1), generation INTEGER,
                    auth_epoch INTEGER, restore_epoch INTEGER);
                INSERT OR IGNORE INTO control VALUES(1,1,1,1);
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY CHECK(id=1), state TEXT, version INTEGER,
                    generation INTEGER, attempt INTEGER, fence INTEGER, lease INTEGER,
                    auth_epoch INTEGER, restore_epoch INTEGER, owner TEXT,
                    kind TEXT, target_lock INTEGER);
                INSERT OR IGNORE INTO jobs VALUES(1,'queued',0,1,0,0,0,1,1,'','local',0);
                CREATE TABLE IF NOT EXISTS attempts (
                    job INTEGER, attempt INTEGER, fence INTEGER,
                    UNIQUE(job,attempt), UNIQUE(job,fence));
                CREATE TABLE IF NOT EXISTS outputs (
                    job INTEGER, attempt INTEGER, fence INTEGER, content TEXT,
                    UNIQUE(job,attempt,fence));
                CREATE TABLE IF NOT EXISTS audit (
                    sequence INTEGER PRIMARY KEY, event TEXT);
            """)

    def connection(self):
        # Opening the first WAL reader can briefly contend during WAL recovery.
        # Bound connection configuration separately; claims still use timeout=0.
        db = sqlite3.connect(self.path, timeout=0.03)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA busy_timeout=0")
        except sqlite3.Error:
            db.close()
            raise
        return db

    def transaction(self, action):
        for retry in range(4):
            db = self.connection()
            try:
                db.execute("BEGIN IMMEDIATE")
                result = action(db)
                db.commit()
                return result
            except sqlite3.OperationalError as error:
                db.rollback()
                if getattr(error, "sqlite_errorcode", None) != sqlite3.SQLITE_BUSY:
                    raise
                self.busy_count += 1
                if retry == 3:
                    raise Busy(
                        "four SQLITE_BUSY observations; no effect committed"
                    ) from error
                time.sleep(0.01)
            finally:
                db.close()

    def row(self):
        with closing(self.connection()) as db:
            return dict(db.execute("SELECT * FROM jobs").fetchone())

    def attempts(self):
        with closing(self.connection()) as db:
            return [dict(row) for row in db.execute("SELECT * FROM attempts")]

    def outputs(self):
        with closing(self.connection()) as db:
            return [dict(row) for row in db.execute("SELECT * FROM outputs")]

    def claim(self, owner, version, generation, now, crash=False):
        def action(db):
            row = dict(db.execute("SELECT * FROM jobs").fetchone())
            control = dict(db.execute("SELECT * FROM control").fetchone())
            eligible = row["state"] == "queued" or (
                row["state"] == "running"
                and row["kind"] == "local"
                and row["lease"] <= now
            )
            if (
                not eligible
                or row["version"] != version
                or control["generation"] != generation
            ):
                return None
            changed = db.execute(
                "UPDATE jobs SET state='running',version=version+1,generation=?,"
                "attempt=attempt+1,fence=fence+1,lease=?,auth_epoch=?,restore_epoch=?,"
                "owner=?,target_lock=1 WHERE id=1 AND version=?",
                (
                    generation,
                    now + 10,
                    control["auth_epoch"],
                    control["restore_epoch"],
                    owner,
                    version,
                ),
            ).rowcount
            if changed != 1:
                return None
            token = dict(db.execute("SELECT * FROM jobs").fetchone())
            db.execute(
                "INSERT INTO attempts VALUES(1,?,?)", (token["attempt"], token["fence"])
            )
            db.execute("INSERT INTO audit(event) VALUES('claim')")
            if crash:
                os._exit(73)
            return token

        return self.transaction(action)

    def mutate(self, token, kind, now):
        def action(db):
            row = dict(db.execute("SELECT * FROM jobs").fetchone())
            control = dict(db.execute("SELECT * FROM control").fetchone())
            fields = (
                "id",
                "owner",
                "attempt",
                "fence",
                "generation",
                "auth_epoch",
                "restore_epoch",
            )
            if (
                row["state"] != "running"
                or row["lease"] <= now
                or any(row[field] != token[field] for field in fields)
                or any(
                    row[field] != control[field]
                    for field in ("generation", "auth_epoch", "restore_epoch")
                )
            ):
                return False
            if kind == "complete":
                if not db.execute(
                    "SELECT 1 FROM outputs WHERE job=1 AND attempt=? AND fence=?",
                    (row["attempt"], row["fence"]),
                ).fetchone():
                    return False
                db.execute(
                    "UPDATE jobs SET state='succeeded',version=version+1,target_lock=0 WHERE id=1"
                )
            elif kind == "upload":
                db.execute(
                    "INSERT OR IGNORE INTO outputs VALUES(1,?,?,?)",
                    (row["attempt"], row["fence"], "screened synthetic output"),
                )
            elif kind == "heartbeat":
                db.execute("UPDATE jobs SET lease=? WHERE id=1", (now + 10,))
            elif kind != "log":
                return False
            db.execute("INSERT INTO audit(event) VALUES(?)", (kind,))
            return True

        return self.transaction(action)

    def new_generation(self):
        return self.transaction(
            lambda db: db.execute("UPDATE control SET generation=generation+1")
        )

    def revoke(self, field):
        if field not in ("auth_epoch", "restore_epoch"):
            raise ValueError("unsupported epoch")
        statements = {
            "auth_epoch": "UPDATE control SET auth_epoch=auth_epoch+1",
            "restore_epoch": "UPDATE control SET restore_epoch=restore_epoch+1",
        }
        return self.transaction(lambda db: db.execute(statements[field]))

    def set_kind(self, kind):
        if kind not in ("local", "external"):
            raise ValueError("unsupported kind")
        self.transaction(lambda db: db.execute("UPDATE jobs SET kind=?", (kind,)))

    def recover(self, now):
        def action(db):
            changed = db.execute(
                "UPDATE jobs SET state='delivery_unknown',version=version+1 WHERE state='running' AND kind='external' AND lease<=?",
                (now,),
            ).rowcount
            if changed:
                db.execute("INSERT INTO audit(event) VALUES('reconcile_only')")
            return changed == 1

        return self.transaction(action)


def contender(path, barrier, queue, owner):
    store = Store(path, initialize=False)
    store.row()
    barrier.wait(timeout=10)
    queue.put(store.claim(owner, 0, 1, 10) is not None)


def race(path):
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    queue = context.Queue()
    children = [
        context.Process(target=contender, args=(str(path), barrier, queue, owner))
        for owner in ("a", "b")
    ]
    try:
        for child in children:
            child.start()
        result = [queue.get(timeout=15) for _ in children]
        for child in children:
            child.join(timeout=15)
            if child.exitcode != 0:
                raise RuntimeError("race child failed")
        return result
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join()
        queue.close()


def crash(path, point):
    store = Store(path)
    token = store.claim("crash-child", 0, 1, 10, crash=point == "precommit")
    if point == "output-before-success":
        store.mutate(token, "upload", 11)
    os._exit(73)


def evidence():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "corpus.sqlite"
        store = Store(path)
        winners = race(path)

        def snapshot(current):
            with closing(current.connection()) as db:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                events = [
                    row[0]
                    for row in db.execute("SELECT event FROM audit ORDER BY sequence")
                ]
            return {
                "state": current.row()["state"],
                "attempt": current.row()["attempt"],
                "fence": current.row()["fence"],
                "target_lock": current.row()["target_lock"],
                "output_count": len(current.outputs()),
                "screened_timeline": events,
                "database_sha256": hashlib.sha256(
                    Path(current.path).read_bytes()
                ).hexdigest(),
            }

        cases = [
            {
                "case": "synchronized-independent-process-race",
                "winners": sum(winners),
                **snapshot(store),
            }
        ]
        for point in ("precommit", "postcommit", "output-before-success"):
            crash_path = Path(directory) / f"{point}.sqlite"
            crashed = Store(crash_path)
            child = multiprocessing.get_context("spawn").Process(
                target=crash, args=(str(crash_path), point)
            )
            child.start()
            child.join(timeout=15)
            if child.is_alive():
                child.terminate()
                child.join()
                raise RuntimeError("crash child exceeded deadline")
            cases.append(
                {
                    "case": point,
                    "abrupt_exit_code": child.exitcode,
                    **snapshot(crashed),
                }
            )
        old = store.row()
        store.new_generation()
        new = store.claim("replacement", 1, 2, 21)
        denied = {
            kind: not store.mutate(old, kind, 22)
            for kind in ("heartbeat", "log", "upload", "complete")
        }
        cases.append(
            {
                "case": "generation-overlap-lease-reclaim",
                "stale_mutations_denied": denied,
                **snapshot(store),
            }
        )
        store.revoke("restore_epoch")
        cases.append(
            {
                "case": "restore-invalidation",
                "stale_mutation_denied": not store.mutate(new, "upload", 22),
                **snapshot(store),
            }
        )
        external = Store(Path(directory) / "external.sqlite")
        external.set_kind("external")
        external.claim("receiver", 0, 1, 10)
        external.recover(21)
        cases.append(
            {
                "case": "external-uncertainty",
                "retry_denied": external.claim("retry", 2, 1, 22) is None,
                **snapshot(external),
            }
        )
        with closing(store.connection()) as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            pragmas = {
                name: db.execute(f"PRAGMA {name}").fetchone()[0]
                for name in ("journal_mode", "synchronous", "busy_timeout")
            }
        return {
            "sqlite_version": sqlite3.sqlite_version,
            "pragmas": pragmas,
            "cases": cases,
            "limits": [
                "single local host; disposable synthetic rows only",
                "not a capacity, power-loss or HA qualification",
                "host/root/DB administrators can bypass the model",
                "logical injected lease clock; production monotonic clock policy remains downstream",
                "external reconciliation uses a separate receiver contract; no exactly-once effect claim",
            ],
        }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "crash":
        crash(sys.argv[2], sys.argv[3])
    else:
        print(json.dumps(evidence(), indent=2))
