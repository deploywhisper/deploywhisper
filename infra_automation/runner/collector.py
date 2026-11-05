"""Pinned in-image collector; its private frame is consumed only by the host broker."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import stat
import subprocess
import sys

MAX_FRAME = 131072


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def command_argv(tool):
    if tool not in ("opentofu", "terraform"):
        raise ValueError("Unsupported collector tool.")
    executable = "/usr/local/bin/" + ("tofu" if tool == "opentofu" else "terraform")
    return (
        (executable, "version", "-json"),
        (
            executable,
            "init",
            "-backend=false",
            "-input=false",
            "-no-color",
            "-lockfile=readonly",
        ),
        (
            executable,
            "plan",
            "-input=false",
            "-no-color",
            "-detailed-exitcode",
            "-out=/work/original.plan",
        ),
        (executable, "show", "-json", "/work/original.plan"),
    )


def command_digests(tool):
    argv = command_argv(tool)
    return tuple(
        "sha256:" + hashlib.sha256(canonical(value)).hexdigest()
        for value in ({"command": "collect_plan", "tool": tool}, argv)
    )


def classify_exit(code):
    if type(code) is not int:
        raise ValueError("Invalid tool exit.")
    return {0: "no_change", 2: "change"}.get(code, "failure")


def bounded_command(argv, environment):
    """Discard diagnostics; PID1 enforces the enclosing execution lifetime."""
    child = subprocess.Popen(
        argv,
        cwd="/work",
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True,
    )
    output = bytearray()
    total = 0
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
                    total += len(chunk)
                    if total > MAX_FRAME:
                        raise ValueError("Collector output limit.")
                    if key.fileobj is child.stdout:
                        output.extend(chunk)
        return child.wait(timeout=0.5), bytes(output)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=0.5)
        child.stdout.close()
        child.stderr.close()


def collect(tool, version):
    argv = command_argv(tool)
    environment = dict(os.environ)
    environment["TF_CLI_CONFIG_FILE"] = "/opt/deploywhisper/" + (
        "tofurc" if tool == "opentofu" else "terraformrc"
    )
    for source in Path("/source").iterdir():
        if source.is_dir():
            shutil.copytree(source, Path("/work") / source.name)
        else:
            shutil.copyfile(source, Path("/work") / source.name)
    code, raw = bounded_command(argv[0], environment)
    if code != 0 or json.loads(raw).get("terraform_version") != version:
        raise ValueError("Tool version mismatch.")
    code, _ = bounded_command(argv[1], environment)
    if code != 0:
        raise ValueError("Initialization failed.")
    code, _ = bounded_command(argv[2], environment)
    if classify_exit(code) == "failure":
        raise ValueError("Plan failed.")
    descriptor = os.open(
        "/work/original.plan", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    )
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 0 < before.st_size <= MAX_FRAME
        ):
            raise ValueError("Invalid saved plan.")
        plan = bytearray()
        while len(plan) <= MAX_FRAME:
            chunk = os.read(descriptor, min(8192, MAX_FRAME + 1 - len(plan)))
            if not chunk:
                break
            plan.extend(chunk)
        show_code, shown = bounded_command(argv[3], environment)
        after = os.fstat(descriptor)
        path_after = os.stat("/work/original.plan", follow_symlinks=False)
        if (
            show_code != 0
            or len(plan) != before.st_size
            or any(
                getattr(before, key) != getattr(after, key)
                for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            )
            or (path_after.st_dev, path_after.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise ValueError("Saved plan changed.")
    finally:
        os.close(descriptor)
    frame = canonical(
        {
            "version": 1,
            "tool": tool,
            "tool_version": version,
            "exit_code": code,
            "plan": base64.b64encode(plan).decode("ascii"),
            "json": shown.decode("utf-8"),
        }
    )
    if len(frame) > MAX_FRAME:
        raise ValueError("Collector frame limit.")
    return frame


def main():
    try:
        if len(sys.argv) != 3:
            return 1
        frame = collect(sys.argv[1], sys.argv[2])
        sys.stdout.buffer.write(frame)
        sys.stdout.buffer.flush()
        return 0
    except Exception:
        # Tool errors may contain credentials or state. Never echo diagnostics.
        return 1


if __name__ == "__main__":
    sys.exit(main())
