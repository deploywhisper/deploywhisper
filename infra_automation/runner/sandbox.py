"""Operator-host Docker boundary; the application and task never receive a socket."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import tempfile
import threading
import time
import uuid

from infra_automation.runner.execution_profile import ExecutionProfile, IsolationError

BOOTSTRAP = "/opt/deploywhisper/bootstrap.py"
PYTHON = "/usr/local/bin/python"
SAFE_IMAGE_ENV = {"PATH", "LANG", "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256"}


def kill_process(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    return process.poll() is not None


def bounded_command(argv, *, env, timeout=15, maximum=1048576):
    """Bound control output before decoding; never echo Docker diagnostics."""
    process = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        start_new_session=True,
    )
    output = bytearray()
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        for stream in (process.stdout, process.stderr):
            selector.register(stream, selectors.EVENT_READ)
        try:
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise IsolationError()
                for key, _ in selector.select(
                    min(0.1, max(0, deadline - time.monotonic()))
                ):
                    chunk = os.read(key.fileobj.fileno(), 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if key.fileobj is process.stdout:
                        output.extend(chunk)
                    else:
                        # Count stderr too; discard its potentially sensitive text.
                        maximum -= len(chunk)
                    if len(output) > maximum:
                        raise IsolationError()
            if process.wait(timeout=max(0.01, deadline - time.monotonic())) != 0:
                raise IsolationError()
            return bytes(output)
        except (OSError, subprocess.SubprocessError, ValueError):
            raise IsolationError() from None
        finally:
            kill_process(process)
            process.stdout.close()
            process.stderr.close()


class DockerSandbox:
    """A separately configured privileged operator port, never an API credential."""

    def __init__(self, docker_binary, docker_host, profile: ExecutionProfile):
        try:
            self.profile = ExecutionProfile.model_validate(profile.model_dump())
            if type(docker_host) is not str or not docker_host.startswith("unix:///"):
                raise IsolationError()
            socket_path = Path(docker_host[7:])
            self.socket_path = socket_path.resolve(strict=True)
            info = self.socket_path.stat()
            if (
                not stat.S_ISSOCK(info.st_mode)
                or info.st_uid not in (0, os.getuid())
                or info.st_mode & 0o002
            ):
                raise IsolationError()
            self.binary = Path(docker_binary).resolve(strict=True)
            info = self.binary.stat()
            if (
                not self.binary.is_file()
                or not info.st_mode & 0o111
                or info.st_uid not in (0, os.getuid())
                or info.st_mode & 0o022
            ):
                raise IsolationError()
            self._binary_stat = (
                info.st_dev,
                info.st_ino,
                info.st_size,
                info.st_mtime_ns,
            )
            self._configuration = tempfile.TemporaryDirectory(
                prefix="dw-runner-docker-"
            )
            self.environment = {
                "PATH": "/usr/bin:/bin",
                "HOME": self._configuration.name,
                "LANG": "C.UTF-8",
            }
            self._owned: dict[str, str] = {}
            self._reservations: dict[str, str] = {}
            self._attempted: set[str] = set()
            self._control_deadlines = threading.local()
        except (OSError, ValueError, AttributeError):
            raise IsolationError() from None

    def close(self):
        self._configuration.cleanup()

    def _argv(self, *arguments):
        info = self.binary.stat()
        if (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
        ) != self._binary_stat:
            raise IsolationError()
        return [
            str(self.binary),
            "--host",
            "unix://" + str(self.socket_path),
            "--config",
            self._configuration.name,
            *arguments,
        ]

    @property
    def cleanup_deadline(self):
        return getattr(getattr(self, "_control_deadlines", None), "deadline", None)

    @cleanup_deadline.setter
    def cleanup_deadline(self, value):
        if not hasattr(self, "_control_deadlines"):
            self._control_deadlines = threading.local()
        self._control_deadlines.deadline = value

    def control(self, *arguments, timeout=15):
        deadline = self.cleanup_deadline
        if deadline is not None:
            timeout = min(timeout, deadline - time.monotonic())
            if timeout <= 0:
                raise IsolationError()
        try:
            return bounded_command(
                self._argv(*arguments), env=self.environment, timeout=timeout
            )
        except (OSError, ValueError):
            raise IsolationError() from None

    def preflight(self):
        try:
            info = json.loads(self.control("info", "--format", "{{json .}}"))
            if (
                info.get("OSType") != "linux"
                or info.get("Architecture") not in ("aarch64", "arm64")
                or info.get("ServerVersion") != self.profile.docker_version
                or info.get("KernelVersion") != self.profile.kernel_version
                or info.get("CgroupVersion") != "2"
                or any(
                    info.get(key) is not True
                    for key in (
                        "MemoryLimit",
                        "SwapLimit",
                        "CpuCfsPeriod",
                        "CpuCfsQuota",
                        "PidsLimit",
                    )
                )
                or "name=seccomp,profile=builtin" not in info.get("SecurityOptions", [])
            ):
                raise IsolationError()
            image = json.loads(self.control("image", "inspect", self.profile.image_id))[
                0
            ]
            if (
                image.get("Id") != self.profile.image_id
                or image.get("Os") != "linux"
                or image.get("Architecture") != "arm64"
                or image.get("Config", {}).get("Volumes")
            ):
                raise IsolationError()
            # The fixed bootstrap uses isolated Python and clears the child env.
            for entry in image.get("Config", {}).get("Env") or []:
                key, _, value = entry.partition("=")
                if key not in SAFE_IMAGE_ENV or len(value) > 1024:
                    raise IsolationError()
            return {
                key: info[key]
                for key in (
                    "OSType",
                    "Architecture",
                    "ServerVersion",
                    "CgroupVersion",
                    "KernelVersion",
                )
            }
        except (ValueError, KeyError, IndexError, TypeError):
            raise IsolationError() from None

    def reserve(self, name=None):
        name = name or "dw-isolated-" + uuid.uuid4().hex
        if (
            not re.fullmatch(r"dw-isolated-[a-f0-9]{32}", name)
            or name in self._reservations
        ):
            raise IsolationError()
        self._reservations[name] = uuid.uuid4().hex
        return name

    def reservation_nonce(self, name):
        return self._reservations[name]

    def _claim_created(self, name, nonce, task_digest, container_id=None):
        try:
            row = json.loads(self.control("inspect", container_id or name))[0]
        except (IsolationError, ValueError, IndexError):
            # Only an acknowledged immutable ID can be proven removed. An empty
            # name listing does not cancel an outstanding create on the daemon.
            if container_id is not None:
                try:
                    present = self.control(
                        "ps",
                        "--all",
                        "--no-trunc",
                        "--filter",
                        "id=" + container_id,
                        "--format",
                        "{{.ID}}",
                    )
                    if not present.strip():
                        self._attempted.discard(name)
                except IsolationError:
                    pass
            return False
        labels = row.get("Config", {}).get("Labels") or {}
        if (
            row.get("Image") != self.profile.image_id
            or row.get("Name", "").lstrip("/") != name
            or labels.get("deploywhisper.owner") != nonce
            or labels.get("deploywhisper.task") != task_digest
            or not re.fullmatch(r"[a-f0-9]{64}", row.get("Id", ""))
            or (container_id is not None and row["Id"] != container_id)
        ):
            return False
        self._owned[name] = row["Id"]
        return True

    def create(self, source_path, *, name=None, task_digest=None):
        self.preflight()
        source = Path(source_path)
        if (
            source.is_symlink()
            or not source.is_dir()
            or str(source.resolve()) != str(source)
            or any(c in str(source) for c in (",", "\n", "\r"))
        ):
            raise IsolationError()
        profile = self.profile
        if name is None or name not in self._reservations:
            name = self.reserve(name)
        nonce = self._reservations[name]
        if task_digest is not None and not re.fullmatch(r"[a-f0-9]{64}", task_digest):
            raise IsolationError()
        tmpfs = {
            path: f"rw,noexec,nosuid,nodev,size={size},uid=10001,gid=10001,mode=0700"
            for path, size in (
                ("/work", profile.work_bytes),
                ("/tmp", profile.tmp_bytes),  # nosec B108 - private bounded task tmpfs
            )
        }
        args = [
            "create",
            "--name",
            name,
            "--pull=never",
            "--platform=linux/arm64",
            "--user=10001:10001",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--cgroupns=private",
            "--network=none",
            "--ipc=none",
            "--memory",
            str(profile.memory_bytes),
            "--memory-swap",
            str(profile.memory_bytes),
            "--cpus",
            str(profile.nano_cpus / 1_000_000_000),
            "--pids-limit",
            str(profile.pids_limit),
            "--log-driver=none",
            "--ulimit",
            "core=0",
            "--ulimit",
            "nofile=256:256",
            "--ulimit",
            f"fsize={profile.work_bytes}:{profile.work_bytes}",
            "--mount",
            f"type=bind,src={source},dst=/source,readonly,bind-propagation=rprivate",
            "--workdir=/work",
            "--entrypoint",
            PYTHON,
            "--interactive",
        ]
        for path, options in tmpfs.items():
            args += ["--tmpfs", path + ":" + options]
        if task_digest is not None:
            args += ["--label", "deploywhisper.task=" + task_digest]
        args += ["--label", "deploywhisper.owner=" + nonce]
        args += [profile.image_id, "-I", BOOTSTRAP]
        # A collision observed before sending any create is a definite rejection.
        if self.control(
            "ps", "--all", "--filter", "name=^/" + name + "$", "--format", "{{.Names}}"
        ).strip():
            raise IsolationError()
        self._attempted.add(name)
        try:
            identifier = self.control(*args).decode("ascii").strip()
            if not re.fullmatch(r"[a-f0-9]{64}", identifier):
                raise IsolationError()
            if not self._claim_created(name, nonce, task_digest, identifier):
                raise IsolationError()
            self.verify(name, source, tmpfs)
            return name
        except BaseException:
            if name in self._owned or self._claim_created(name, nonce, task_digest):
                self.remove(name)
            raise

    def inspect(self, name):
        if name not in self._owned:
            raise IsolationError()
        try:
            row = json.loads(self.control("inspect", self._owned[name]))[0]
            if row.get("Id") != self._owned[name]:
                raise IsolationError()
            return row
        except (ValueError, IndexError, KeyError, TypeError):
            raise IsolationError() from None

    def verify(self, name, source, tmpfs):
        row = self.inspect(name)
        host = row["HostConfig"]
        configuration = row["Config"]
        profile = self.profile
        if (
            row.get("Image") != profile.image_id
            or row.get("State", {}).get("Running")
            or configuration.get("User") != "10001:10001"
            or configuration.get("Entrypoint") != [PYTHON]
            or configuration.get("Cmd") != ["-I", BOOTSTRAP]
            or configuration.get("WorkingDir") != "/work"
            or configuration.get("OpenStdin") is not True
            or host.get("ReadonlyRootfs") is not True
            or host.get("Privileged") is not False
            or host.get("CapDrop") != ["ALL"]
            or host.get("CapAdd")
            or host.get("NetworkMode") != "none"
            or set(row.get("NetworkSettings", {}).get("Networks", {})) != {"none"}
            or host.get("IpcMode") != "none"
            or host.get("PidMode")
            or host.get("CgroupnsMode") != "private"
            or host.get("Memory") != profile.memory_bytes
            or host.get("MemorySwap") != profile.memory_bytes
            or host.get("NanoCpus") != profile.nano_cpus
            or host.get("PidsLimit") != profile.pids_limit
            or host.get("Tmpfs") != tmpfs
            or host.get("LogConfig", {}).get("Type") != "none"
            or host.get("Devices")
            or host.get("Binds")
            or host.get("PortBindings")
            or host.get("SecurityOpt") != ["no-new-privileges:true"]
        ):
            raise IsolationError()
        mounts = row.get("Mounts", [])
        if len(mounts) != 1 or any(
            (
                m.get("Type"),
                m.get("Source"),
                m.get("Destination"),
                m.get("RW"),
                m.get("Propagation"),
            )
            != ("bind", str(source), "/source", False, "rprivate")
            for m in mounts
        ):
            raise IsolationError()
        if any(
            entry.partition("=")[0] not in SAFE_IMAGE_ENV
            for entry in configuration.get("Env", [])
        ):
            raise IsolationError()

    def start(self, name):
        if name not in self._owned:
            raise IsolationError()
        return subprocess.Popen(
            self._argv("start", "--attach", "--interactive", self._owned[name]),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.environment,
            start_new_session=True,
        )

    def terminate(self, name):
        if name not in self._owned:
            raise IsolationError()
        try:
            self.control(
                "kill",
                "--signal=KILL",
                self._owned[name],
                timeout=self.profile.cleanup_seconds,
            )
        except IsolationError:
            # Natural task exit may race the kill request. Only fresh proof for
            # this immutable owned ID permits cleanup to continue after failure.
            if not self.exists(name):
                return
            if self.inspect(name).get("State", {}).get("Running") is False:
                return
            raise
        if (
            self.exists(name)
            and self.inspect(name).get("State", {}).get("Running") is not False
        ):
            raise IsolationError()

    def owns(self, name):
        return name in self._owned

    def owned_id(self, name):
        if name not in self._owned:
            raise IsolationError()
        return self._owned[name]

    def pending_creation(self, name):
        return name in self._attempted

    def exists(self, name):
        if name not in self._owned:
            raise IsolationError()
        names = self.control(
            "ps",
            "--all",
            "--no-trunc",
            "--filter",
            "id=" + self._owned[name],
            "--format",
            "{{.ID}}",
        )
        identifiers = names.decode("ascii").splitlines()
        if not identifiers:
            return False
        if identifiers != [self._owned[name]]:
            raise IsolationError()
        return True

    def recover_owned(self, name, task_digest, nonce, *, container_id=None):
        if (
            not re.fullmatch(r"dw-isolated-[a-f0-9]{32}", name)
            or not re.fullmatch(r"[a-f0-9]{64}", task_digest)
            or not re.fullmatch(r"[a-f0-9]{32}", nonce)
        ):
            raise IsolationError()
        if container_id is not None and not re.fullmatch(r"[a-f0-9]{64}", container_id):
            raise IsolationError()
        self._attempted.add(name)
        if not self._claim_created(name, nonce, task_digest, container_id):
            if self.pending_creation(name):
                raise IsolationError()
            return False
        return True

    def remove(self, name):
        if name not in self._owned:
            raise IsolationError()
        if self.exists(name):
            self.control(
                "rm", "--force", self._owned[name], timeout=self.profile.cleanup_seconds
            )
        if self.exists(name):
            raise IsolationError()
        del self._owned[name]
        self._attempted.discard(name)
