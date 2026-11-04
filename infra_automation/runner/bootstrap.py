"""Fixed in-image gate: prove controls and pins before accepting credentials."""

from __future__ import annotations

import hashlib
import errno
import fcntl
import struct
import ctypes
from datetime import datetime, timezone
import selectors
import signal
import subprocess
import threading
import time
import json
import math
import os
from pathlib import Path
import stat
import socket
import sys

READY = b"DW_RUNNER_READY_V1\n"
MAX_FRAME = 65536


def frame():
    raw = sys.stdin.buffer.readline(MAX_FRAME + 1)
    if len(raw) > MAX_FRAME or not raw.endswith(b"\n"):
        raise ValueError
    return json.loads(raw)


def file_hash(path, *, source=False):
    target = Path(path)
    if not target.is_absolute() or ".." in target.parts:
        raise ValueError
    if source:
        current = Path("/")
        for part in target.parts[1:]:
            current /= part
            if current.is_symlink():
                raise ValueError
    descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022:
            raise ValueError
        digest = hashlib.sha256()
        while block := os.read(descriptor, 65536):
            digest.update(block)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


class ControlFailure(ValueError):
    def __init__(self, code):
        self.code = code


def controls(profile):
    def require(condition, code):
        if not condition:
            raise ControlFailure(code)

    require(os.getuid() == 10001 and os.getgid() == 10001, 111)

    def read(path, code):
        try:
            return Path(path).read_text()
        except (OSError, ValueError):
            raise ControlFailure(code) from None

    status = dict(
        line.split(":", 1)
        for line in read("/proc/self/status", 112).splitlines()
        if ":" in line
    )
    require(
        status["NoNewPrivs"].strip() == "1"
        and status["Seccomp"].strip() == "2"
        and int(status["CapEff"].strip(), 16) == 0
        and int(status["CapPrm"].strip(), 16) == 0,
        112,
    )
    group = Path("/sys/fs/cgroup")
    require(int(read(group / "memory.max", 113)) == profile["memory_bytes"], 113)
    require(int(read(group / "memory.swap.max", 114)) == 0, 114)
    require(int(read(group / "pids.max", 115)) == profile["pids_limit"], 115)
    quota, period = read(group / "cpu.max", 116).split()
    require(int(quota) * 1_000_000_000 == profile["nano_cpus"] * int(period), 116)
    mounts = {
        line.split()[4]: line.split()[5].split(",")
        for line in read("/proc/self/mountinfo", 117).splitlines()
    }
    require("ro" in mounts["/"] and "ro" in mounts["/source"], 117)
    for path, size in (
        ("/work", profile["work_bytes"]),
        ("/tmp", profile["tmp_bytes"]),  # nosec B108 - verified private bounded task tmpfs
    ):  # nosec B108 - private bounded task tmpfs
        require({"rw", "nosuid", "nodev", "noexec"} <= set(mounts[path]), 118)
        fs = os.statvfs(path)
        require(fs.f_blocks * fs.f_frsize <= size, 119)
    require(
        not Path("/var/run/docker.sock").exists()
        and not Path("/run/docker.sock").exists(),
        120,
    )
    require(os.uname().release == profile["kernel_version"], 121)
    verify_offline_network()


DORMANT_TUNNELS = frozenset(
    {
        "erspan0",
        "gre0",
        "gretap0",
        "ip6_vti0",
        "ip6gre0",
        "ip6tnl0",
        "ip_vti0",
        "sit0",
        "tunl0",
    }
)


def verify_offline_network():
    """Qualify only loopback plus addressless, DOWN LinuxKit kernel tunnels."""
    interfaces = {name for _, name in socket.if_nameindex()}
    if "lo" not in interfaces or interfaces - ({"lo"} | DORMANT_TUNNELS):
        raise ControlFailure(121)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as query:
        for name in interfaces - {"lo"}:
            request = struct.pack("256s", name.encode("ascii"))
            flags = struct.unpack_from(
                "H", fcntl.ioctl(query.fileno(), 0x8913, request), 16
            )[0]
            if flags & (0x1 | 0x40):
                raise ControlFailure(121)
            try:
                fcntl.ioctl(query.fileno(), 0x8915, request)
            except OSError as error:
                if error.errno != errno.EADDRNOTAVAIL:
                    raise ControlFailure(121) from None
            else:
                raise ControlFailure(121)
    if Path("/proc/net/route").read_text().splitlines()[1:]:
        raise ControlFailure(121)
    for line in Path("/proc/net/if_inet6").read_text().splitlines():
        fields = line.split()
        if len(fields) != 6 or fields[-1] != "lo" or fields[0] != "0" * 31 + "1":
            raise ControlFailure(121)
    for line in Path("/proc/net/ipv6_route").read_text().splitlines():
        fields = line.split()
        if len(fields) != 10 or fields[-1] != "lo" or fields[4] != "0" * 32:
            raise ControlFailure(121)


# Linux v6.12 asm-generic syscall IDs used by AArch64, not portable numbers:
# https://github.com/torvalds/linux/blob/v6.12/include/uapi/asm-generic/unistd.h
# The inherited Docker builtin policy remains active; this filter only removes
# scheduling/inspection operations that could tamper with the same-UID watchdog.
WATCHDOG_DENIED_SYSCALLS = (30, 117, 118, 119, 122, 140, 270, 271, 274)


def watchdog_filter_program():
    # seccomp_data.arch at offset4; syscall number at offset0. Other ABIs die.
    program = [
        (0x20, 0, 0, 4),
        (0x15, 1, 0, 0xC00000B7),
        (0x06, 0, 0, 0x80000000),
        (0x20, 0, 0, 0),
    ]
    for number in WATCHDOG_DENIED_SYSCALLS:
        program.extend([(0x15, 0, 1, number), (0x06, 0, 0, 0x00050000 | errno.EPERM)])
    program.append((0x06, 0, 0, 0x7FFF0000))
    return tuple(program)


def protect_watchdog(libc):
    class Instruction(ctypes.Structure):
        _fields_ = [
            ("code", ctypes.c_ushort),
            ("jt", ctypes.c_ubyte),
            ("jf", ctypes.c_ubyte),
            ("k", ctypes.c_uint32),
        ]

    class Program(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ushort),
            ("filter", ctypes.POINTER(Instruction)),
        ]

    instructions = watchdog_filter_program()
    array = (Instruction * len(instructions))(
        *(Instruction(*item) for item in instructions)
    )
    program = Program(len(instructions), array)
    before = int(
        dict(
            line.split(":", 1)
            for line in Path("/proc/self/status").read_text().splitlines()
            if ":" in line
        )["Seccomp_filters"]
    )
    if libc.prctl(22, 2, ctypes.byref(program), 0, 0) != 0:
        raise ValueError
    after = int(
        dict(
            line.split(":", 1)
            for line in Path("/proc/self/status").read_text().splitlines()
            if ":" in line
        )["Seccomp_filters"]
    )
    if after <= before:
        raise ValueError


def managed_command(argv, env, profile):
    child = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        close_fds=True,
        start_new_session=True,
    )
    output = bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            selector.register(child.stderr, selectors.EVENT_READ)
            while selector.get_map():
                for key, _ in selector.select(0.05):
                    chunk = os.read(key.fileobj.fileno(), 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    output.extend(chunk)
                    if len(output) > profile["output_bytes"]:
                        return 126
        code = child.wait(timeout=0.5)
        if code == 0:
            sys.stdout.buffer.write(output)
            sys.stdout.buffer.flush()
        return code if code >= 0 else 125
    finally:
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        child.stdout.close()
        child.stderr.close()


def watchdog_deadline(config, *, now_utc, monotonic_now, started_monotonic):
    """Map the original host cutoff once; setup and frame delay never renew it."""
    duration = config["profile"]["timeout_seconds"]
    budget = config["remaining_budget_seconds"]
    if type(duration) is not int or not 1 <= duration <= 600:
        raise ValueError
    if (
        type(budget) not in (int, float)
        or not math.isfinite(budget)
        or not 0 < budget <= duration
    ):
        raise ValueError
    lease = datetime.strptime(config["lease_deadline"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    original = datetime.strptime(
        config["execution_deadline"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    if original > lease:
        raise ValueError
    remaining = (original - now_utc).total_seconds()
    cutoff = min(started_monotonic + budget, monotonic_now + remaining)
    if remaining <= 0 or cutoff <= monotonic_now:
        raise ValueError
    return cutoff


def main():
    stage = 124
    started = time.monotonic()
    deadline = [started + 10]

    def watchdog():
        while time.monotonic() < deadline[0]:
            time.sleep(0.02)
        # Exiting namespace PID1 kills every descendant, including new sessions.
        os._exit(124)

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        config = frame()
        if set(config) != {
            "profile",
            "pins",
            "source_files",
            "argv",
            "lease_deadline",
            "execution_deadline",
            "remaining_budget_seconds",
        }:
            raise ValueError
        deadline[0] = watchdog_deadline(
            config,
            now_utc=datetime.now(timezone.utc),
            monotonic_now=time.monotonic(),
            started_monotonic=started,
        )
        stage = 110
        try:
            controls(config["profile"])
        except (KeyError, FileNotFoundError, PermissionError) as error:
            raise ControlFailure(
                {KeyError: 101, FileNotFoundError: 102, PermissionError: 103}[
                    type(error)
                ]
            ) from None
        stage = 122
        for pin in config["pins"]:
            if file_hash(pin["path"]) != pin["sha256"].removeprefix("sha256:"):
                raise ValueError
        stage = 123
        expected = {
            name: value.removeprefix("sha256:")
            for name, value in config["source_files"]
        }
        actual = {}
        for root, dirs, files in os.walk("/source", followlinks=False):
            for name in dirs:
                if (Path(root) / name).is_symlink():
                    raise ValueError
            for name in files:
                path = Path(root) / name
                actual[str(path.relative_to("/source"))] = file_hash(path, source=True)
        if actual != expected:
            raise ValueError
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(4, 0, 0, 0, 0) != 0 or libc.prctl(3, 0, 0, 0, 0) != 0:
            raise ValueError
        protect_watchdog(libc)
        sys.stdout.buffer.write(READY)
        sys.stdout.buffer.flush()
        stage = 125
        secrets = frame()
        names = config["profile"]["credential_names"]
        if type(secrets) is not dict or set(secrets) - set(names):
            raise ValueError
        if any(
            type(v) is not str or len(v) > 4096 or "\0" in v for v in secrets.values()
        ):
            raise ValueError
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/tmp",  # nosec B108 - task-only uid10001 tmpfs, not host /tmp
            "LANG": "C.UTF-8",
            "TF_IN_AUTOMATION": "1",
            "TF_INPUT": "0",
            "TF_CLI_CONFIG_FILE": "/opt/deploywhisper/tofurc",
        }
        env.update(secrets)
        argv = config["argv"]
        if type(argv) is not list or not argv or not Path(argv[0]).is_absolute():
            raise ValueError
        os.chdir("/work")
        sys.stdin.buffer.close()
        return managed_command(argv, env, config["profile"])
    except BaseException as error:
        # No parser/OS error may echo a secret, source body or credential frame.
        sys.stderr.write("Isolated runner operation unavailable.\n")
        return error.code if isinstance(error, ControlFailure) else stage


if __name__ == "__main__":
    raise SystemExit(main())
