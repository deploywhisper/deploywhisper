"""Fail-closed global slots and parent-death supervision for trusted local work.

Slot files are never unlinked: their flock inode is the coordination boundary.
An interrupted supervisor leaves a durable dirty record, requiring operator
recovery rather than guessing whether an old process group is safe to signal.
"""

from __future__ import annotations

import importlib
from types import ModuleType

try:
    fcntl: ModuleType | None = importlib.import_module("fcntl")
except ImportError:  # Optional engine remains inert on unsupported platforms.
    fcntl = None
import json
import math
import struct
import multiprocessing
from multiprocessing.connection import wait
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from sqlalchemy.engine import make_url

OWNER_PULSE_SECONDS = 3.0


class _Slot:
    def __init__(self, descriptor):
        self.descriptor = descriptor

    def write(self, record):
        payload = json.dumps(record, sort_keys=True).encode("ascii")
        os.lseek(self.descriptor, 0, os.SEEK_SET)
        os.write(self.descriptor, payload)
        os.ftruncate(self.descriptor, len(payload))
        os.fsync(self.descriptor)

    def close(self):
        os.close(self.descriptor)


def _slot_directory(database_url):
    url = make_url(database_url)
    if url.drivername != "sqlite" or not url.database or url.database == ":memory:":
        raise ValueError("Supervision requires a file SQLite database.")
    database = Path(url.database).resolve()
    directory = database.parent / ("." + database.name + ".engine-worker-slots")
    directory.mkdir(mode=0o700, exist_ok=True)
    return directory


def _open_slot(path):
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    except FileExistsError:
        descriptor = os.open(path, os.O_RDWR)
    else:
        # Interrupted initialization is invalid metadata and therefore denies.
        os.write(descriptor, b'{"state":"clean"}')
        os.fsync(descriptor)
    return _Slot(descriptor)


def _reserve(database_url, max_slots):
    if fcntl is None or os.name != "posix":
        raise ValueError("Worker supervision requires POSIX file locking.")
    if type(max_slots) is not int or not 1 <= max_slots <= 2:
        raise ValueError("One or two global slots are required.")
    directory = _slot_directory(database_url)
    admission = os.open(directory / "admission", os.O_CREAT | os.O_RDWR, 0o600)
    available = []
    selected = None
    try:
        try:
            fcntl.flock(admission, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        occupied = 0
        # Always inspect both physical slots, including after a bound reduction.
        for index in range(2):
            slot = _open_slot(directory / str(index))
            try:
                fcntl.flock(slot.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                os.lseek(slot.descriptor, 0, os.SEEK_SET)
                record = json.loads(os.read(slot.descriptor, 4096))
                if record == {"state": "clean"}:
                    available.append(slot)
                    continue
            except (BlockingIOError, ValueError, OSError):
                pass
            occupied += 1
            slot.close()
        if occupied < max_slots and available:
            selected = available.pop(0)
        return selected
    finally:
        for slot in available:
            slot.close()
        os.close(admission)


def global_slot_available(database_url, max_slots=2):
    """Optimistic read-only probe; only the supervisor reserves admission."""
    if (
        fcntl is None
        or os.name != "posix"
        or type(max_slots) is not int
        or not 1 <= max_slots <= 2
    ):
        return False
    try:
        directory = _slot_directory(database_url)
        occupied = 0
        available = False
        for index in range(2):
            slot = _open_slot(directory / str(index))
            try:
                fcntl.flock(slot.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                os.lseek(slot.descriptor, 0, os.SEEK_SET)
                clean = json.loads(os.read(slot.descriptor, 4096)) == {"state": "clean"}
            except (BlockingIOError, ValueError, OSError):
                clean = False
            finally:
                slot.close()
            occupied += not clean
            available = available or clean
        return available and occupied < max_slots
    except (OSError, ValueError):
        return False


class _OwnerLifetime:
    def __init__(self, channel):
        self.channel = channel
        self.deadline = time.monotonic() + OWNER_PULSE_SECONDS

    def stopped(self):
        now = time.monotonic()
        # A late pulse cannot resurrect an already expired execution lifetime.
        if now >= self.deadline:
            return True
        try:
            while self.channel.poll():
                payload = self.channel.recv_bytes(8)
                if len(payload) != 8:
                    return True
                proposed = struct.unpack("!d", payload)[0]
                if (
                    not math.isfinite(proposed)
                    or proposed > now + OWNER_PULSE_SECONDS + 0.1
                ):
                    return True
                self.deadline = proposed
        except (EOFError, OSError, ValueError):
            return True
        return time.monotonic() >= self.deadline


def _start_time(pid):
    if sys.platform != "linux":
        return None
    return (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()[19]


def _group_executing(pgid):
    """Exclude exited zombies, retaining the unreaped leader as a PID guard."""
    if sys.platform == "linux":
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            except (FileNotFoundError, ProcessLookupError):
                continue
            if int(fields[2]) == pgid and fields[0] != "Z":
                return True
        return False
    # macOS lacks /proc. ps exposes both process-group identity and zombie state.
    result = subprocess.run(
        ["ps", "-axo", "pgid=,stat="],
        capture_output=True,
        text=True,
        check=True,
        timeout=0.5,
    )
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2:
            raise RuntimeError("Process-group inspection unavailable.")
        if int(fields[0]) == pgid and not fields[1].startswith("Z"):
            return True
    return False


def _stop_worker(process, grouped):
    """Do not poll/join/reap the leader until all group execution has stopped."""
    pid = process.pid
    try:
        grouped = grouped or os.getpgid(pid) == pid
    except ProcessLookupError:
        pass

    def confirmed_dead():
        exited = bool(wait([process.sentinel], timeout=0))
        if exited and (not grouped or not _group_executing(pid)):
            process.join(timeout=0.2)
            if process.exitcode is None:
                raise RuntimeError("Worker exit unconfirmed.")
            return True
        return False

    def send(signum):
        try:
            if grouped:
                os.killpg(pid, signum)
            else:
                os.kill(pid, signum)
        except ProcessLookupError:
            pass
        except PermissionError:
            # A group may exit between the confirmation and signal on macOS.
            # Permission errors for any still-executing group remain fatal.
            if confirmed_dead():
                return True
            raise
        return False

    if confirmed_dead() or send(signal.SIGTERM):
        return
    deadline = time.monotonic() + 1.5
    grace = time.monotonic() + 0.1
    while True:
        if confirmed_dead():
            return
        if time.monotonic() >= grace and send(signal.SIGKILL):
            return
        if time.monotonic() >= deadline:
            raise RuntimeError("Owned process-group termination unconfirmed.")
        time.sleep(0.02)


def supervisor_main(
    database_url,
    attempt_id,
    worker_target,
    worker_args,
    parent_liveness_rx,
    result_channel,
    max_slots=2,
):
    """Spawn one gated worker; parent EOF owns its complete group lifetime.

    worker_target receives two appended arguments: ready_tx and execution_gate_rx.
    It must setsid(), send b'ready', then await b'start' before doing any work.
    result_channel is also in worker_args and carries worker results to the parent.
    """
    lifetime = _OwnerLifetime(parent_liveness_rx)
    slot = None
    reservation_deadline = time.monotonic() + 0.25
    while not lifetime.stopped():
        slot = _reserve(database_url, max_slots)
        if slot is not None or time.monotonic() >= reservation_deadline:
            break
        # A second supervisor may be fsyncing its short reservation. This is a
        # finite startup handshake, never an executor queue or handler execution.
        time.sleep(0.01)
    if slot is None:
        try:
            result_channel.send_bytes(b'{"outcome":"retryable_local_failure"}')
        finally:
            result_channel.close()
            parent_liveness_rx.close()
        return
    process = None
    ready_rx = ready_tx = gate_rx = gate_tx = None
    clean = False
    grouped = False
    try:
        slot.write({"state": "reserved", "attempt_id": attempt_id})
        if lifetime.stopped():
            clean = True
            return
        context = multiprocessing.get_context("spawn")
        ready_rx, ready_tx = context.Pipe(duplex=False)
        gate_rx, gate_tx = context.Pipe(duplex=False)
        process = context.Process(
            target=worker_target, args=(*worker_args, ready_tx, gate_rx)
        )
        process.start()
        ready_tx.close()
        gate_rx.close()
        result_channel.close()
        slot.write(
            {
                "state": "active",
                "attempt_id": attempt_id,
                "pid": process.pid,
                "pgid": process.pid,
                "start_time": _start_time(process.pid),
            }
        )
        startup_deadline = time.monotonic() + 3
        while not grouped:
            events = wait(
                [ready_rx, parent_liveness_rx, process.sentinel], timeout=0.05
            )
            if lifetime.stopped() or process.sentinel in events:
                break
            if ready_rx in events:
                try:
                    grouped = ready_rx.recv_bytes(16) == b"ready"
                except EOFError:
                    break
                if not grouped or os.getpgid(process.pid) != process.pid:
                    raise RuntimeError("Worker process-group handshake invalid.")
                if not lifetime.stopped():
                    gate_tx.send_bytes(b"start")
                break
            if time.monotonic() >= startup_deadline:
                break
        gate_tx.close()
        if grouped:
            while True:
                events = wait([parent_liveness_rx, process.sentinel], timeout=0.05)
                if lifetime.stopped() or process.sentinel in events:
                    break
        _stop_worker(process, grouped)
        process.close()
        process = None
        clean = True
    finally:
        # On an exception, attempt cleanup but retain dirty metadata unless proven.
        if process is not None:
            try:
                _stop_worker(process, grouped)
                process.close()
                clean = True
            except Exception:
                pass
        if clean:
            slot.write({"state": "clean"})
        slot.close()
        for channel in (
            ready_rx,
            ready_tx,
            gate_rx,
            gate_tx,
            parent_liveness_rx,
            result_channel,
        ):
            if channel is not None:
                channel.close()
        if not clean:
            # Avoid multiprocessing's implicit join of an unconfirmed live child.
            os._exit(71)
