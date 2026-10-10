"""Disposable real-tool containment probe. Never emits plan contents."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess  # nosec B404
import sys


def run_tool(args):
    result = subprocess.run(  # nosec B603
        ["/usr/local/bin/tofu", *args],
        cwd="/work",
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "TF_IN_AUTOMATION": "1",
            "TF_INPUT": "0",
            "TF_CLI_CONFIG_FILE": "/opt/qualification/tofurc",
            "HOME": "/work",
            **({"LOCAL_PROBE": "1"} if os.environ.get("LOCAL_PROBE") == "1" else {}),
        },
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        sys.stderr.buffer.write(result.stderr)
        raise ValueError("real tool failed; diagnostics remain private")
    return result.stdout


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if mode == "descendants":
        child = subprocess.Popen(  # nosec B603
            [sys.executable, "-c", "import time; time.sleep(300)"]
        )
        print(json.dumps({"child": child.pid}), flush=True)
        child.wait()
        return
    if mode == "memory":
        bytearray(256 * 1024 * 1024)
        return
    if mode == "output":
        while True:
            print("x" * 4096, flush=True)
    if mode == "cpu":
        import time

        stop = time.monotonic() + 2
        while time.monotonic() < stop:
            pass
        print(
            json.dumps(
                {
                    "cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
                    "cpu_stat": Path("/sys/fs/cgroup/cpu.stat").read_text(),
                }
            )
        )
        return
    if mode == "pids":
        children = []
        try:
            for _ in range(64):
                children.append(os.fork())
                if children[-1] == 0:
                    os._exit(0)
            print(json.dumps({"pids_denied": False}))
        except OSError:
            print(json.dumps({"pids_denied": True}))
        finally:
            for pid in children:
                os.waitpid(pid, 0)
        return
    if mode == "disk":
        target = Path("/work/partial")
        denied = False
        try:
            with target.open("wb") as output:
                for _ in range(64):
                    output.write(bytes(1024 * 1024))
        except OSError:
            denied = True
        finally:
            target.unlink(missing_ok=True)
        print(
            json.dumps({"disk_denied": denied, "partial_removed": not target.exists()})
        )
        return
    if mode == "collector_denied":
        try:
            list(Path("/custody").iterdir())
            print(json.dumps({"custody_denied": False}))
        except PermissionError:
            print(json.dumps({"custody_denied": True}))
        return
    for source in Path("/opt/qualification/source").iterdir():
        shutil.copyfile(source, Path("/work") / source.name)
    run_tool(["init", "-backend=false", "-input=false", "-no-color"])
    run_tool(["plan", "-out=/staging/original.plan", "-input=false", "-no-color"])
    plan = Path("/staging/original.plan").read_bytes()
    raw = hashlib.sha256(plan).hexdigest()
    shown = json.loads(run_tool(["show", "-json", "/staging/original.plan"]))
    screened = json.dumps(
        shown["planned_values"]["outputs"]["probe"]["value"], sort_keys=True
    ).encode()
    Path("/staging/screened.json").write_bytes(screened)
    print(
        json.dumps(
            {
                "raw_digest": raw,
                "sanitized_digest": hashlib.sha256(screened).hexdigest(),
                "provider_probe": json.loads(screened),
                "uid": os.getuid(),
            }
        )
    )


if __name__ == "__main__":
    main()
