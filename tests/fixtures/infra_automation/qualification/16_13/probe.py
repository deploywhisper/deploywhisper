"""Hostile fixture commands; executable only inside the qualified sandbox."""

from __future__ import annotations

import hashlib
import ctypes
import errno
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


def emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)


def run_tool(arguments):
    result = subprocess.run(
        ["/usr/local/bin/tofu", *arguments],
        cwd="/work",
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/work",
            "TF_IN_AUTOMATION": "1",
            "TF_INPUT": "0",
            "TF_CLI_CONFIG_FILE": "/opt/deploywhisper/tofurc",
            **{
                key: value
                for key, value in os.environ.items()
                if key in ("COLLECTOR_TOKEN",)
            },
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Pinned tool command failed.")
    return result.stdout


def watchdog_attacks():
    if os.getpid() == 1:
        return {"separate_pid1": False}
    for signum in (signal.SIGSTOP, signal.SIGKILL):
        try:
            os.kill(1, signum)
        except PermissionError:
            pass
    time.sleep(0.1)
    state = Path("/proc/1/stat").read_text().split(")", 1)[1].split()[0]
    libc = ctypes.CDLL(None, use_errno=True)
    attached = libc.ptrace(16, 1, 0, 0)
    ptrace_denied = attached == -1 and ctypes.get_errno() in (
        errno.EPERM,
        errno.EACCES,
    )
    if attached == 0:
        libc.ptrace(17, 1, 0, 0)
    try:
        descriptor = os.open("/proc/1/mem", os.O_RDONLY)
    except PermissionError:
        memory_denied = True
    else:
        os.close(descriptor)
        memory_denied = False
    scheduling = {}
    operations = {
        "priority": lambda: os.setpriority(os.PRIO_PROCESS, 1, 19),
        "scheduler": lambda: os.sched_setscheduler(1, os.SCHED_IDLE, os.sched_param(0)),
        "affinity": lambda: os.sched_setaffinity(1, {min(os.sched_getaffinity(0))}),
    }
    for name, operation in operations.items():
        try:
            operation()
        except OSError as exc:
            scheduling[name + "_denied"] = exc.errno == errno.EPERM
            scheduling[name + "_errno"] = exc.errno
        else:
            scheduling[name + "_denied"] = False
            scheduling[name + "_errno"] = None
    return {
        **scheduling,
        "separate_pid1": True,
        "watchdog_not_stopped": state not in ("T", "t", "Z"),
        "ptrace_denied": ptrace_denied,
        "proc_memory_denied": memory_denied,
        "signal_stop_and_kill_attempted": True,
    }


def main(mode):
    if mode in ("environment", "containment", "network"):
        # -I excludes sibling imports; load only the pinned operator-owned file.
        import runpy

        emit(runpy.run_path("/opt/deploywhisper/provider_probe.py")["evidence"]())
    elif mode == "plan":
        for source in Path("/source").iterdir():
            if source.is_file():
                shutil.copyfile(source, Path("/work") / source.name)
            elif source.is_dir():
                shutil.copytree(source, Path("/work") / source.name)
        run_tool(["init", "-backend=false", "-input=false", "-no-color"])
        run_tool(["plan", "-out=/work/original.plan", "-input=false", "-no-color"])
        plan = json.loads(run_tool(["show", "-json", "/work/original.plan"]))
        emit(
            {
                "provider_probe": plan["planned_values"]["outputs"]["probe"]["value"],
                "plan_created": Path("/work/original.plan").is_file(),
                "tool_version": plan["terraform_version"],
                "python_version": sys.version.split()[0],
                "module_resources": sorted(
                    resource["address"]
                    for module in plan["planned_values"]["root_module"].get(
                        "child_modules", []
                    )
                    for resource in module.get("resources", [])
                ),
                "raw_digest": hashlib.sha256(
                    Path("/work/original.plan").read_bytes()
                ).hexdigest(),
            }
        )
    elif mode == "cpu":
        stop = time.monotonic() + 3
        while time.monotonic() < stop:
            pass
        emit(
            {
                "cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
                "cpu_stat": Path("/sys/fs/cgroup/cpu.stat").read_text(),
            }
        )
    elif mode == "memory":
        memory = []
        while True:
            memory.append(bytearray(8 * 1024 * 1024))
    elif mode == "pids":
        children = []
        denied = False
        try:
            for _ in range(256):
                pid = os.fork()
                if pid == 0:
                    time.sleep(300)
                    os._exit(0)
                children.append(pid)
        except OSError:
            denied = True
        finally:
            for pid in children:
                os.kill(pid, signal.SIGKILL)
            for pid in children:
                os.waitpid(pid, 0)
        emit(
            {
                "pids_denied": denied,
                "children_created": len(children),
                "pids_max": Path("/sys/fs/cgroup/pids.max").read_text().strip(),
            }
        )
    elif mode == "disk":
        paths = []
        failure_errno = None
        try:
            for index in range(256):
                path = Path("/work") / f"partial-evidence-{index}"
                paths.append(path)
                path.write_bytes(bytes(1024 * 1024))
        except OSError as exc:
            failure_errno = exc.errno
        finally:
            for path in paths:
                path.unlink(missing_ok=True)
        emit(
            {
                "disk_denied": failure_errno == 28,
                "failure_errno": failure_errno,
                "partial_removed": not any(path.exists() for path in paths),
            }
        )
    elif mode == "output":
        for _ in range(256):
            print("x" * 4096, flush=True)
    elif mode == "descendants":
        pid = os.fork()
        if pid == 0:
            os.setsid()
            grandchild = os.fork()
            emit(
                {
                    "role": "grandchild" if grandchild == 0 else "child",
                    "pid": os.getpid(),
                    "sid": os.getsid(0),
                }
            )
            while True:
                time.sleep(1)
        emit({"role": "parent", "pid": os.getpid(), "child": pid})
        while True:
            time.sleep(1)
    elif mode == "watchdog":
        emit(watchdog_attacks())
    elif mode == "watchdog_load":
        emit(watchdog_attacks())
        target = min(os.sched_getaffinity(0))
        for _ in range(6):
            if os.fork() == 0:
                os.setsid()
                try:
                    os.sched_setaffinity(0, {target})
                except PermissionError:
                    pass
                while True:
                    pass
        while True:
            time.sleep(1)
    elif mode == "partial":
        Path("/work/partial-evidence").write_bytes(b'{"unfinished":')
        print('{"unfinished":', flush=True)
        raise SystemExit(2)
    elif mode == "success":
        emit({"qualified_fixture": True})
    else:
        raise SystemExit(2)


if __name__ == "__main__":
    main(sys.argv[1])
