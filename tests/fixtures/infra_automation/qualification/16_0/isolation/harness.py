"""Reproducible Docker qualification; uses only uniquely owned resources."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess  # nosec B404
import tempfile
import time
import uuid

DOCKER = "/usr/local/bin/docker"
ROOT = Path(__file__).resolve().parent
IMAGE = "dw16-qualification:1"


def command(args, timeout=60, env=None):
    result = subprocess.run(  # nosec B603
        args, capture_output=True, timeout=timeout, check=False, env=env
    )
    if result.returncode:
        # Private diagnostics stay private; no provider/raw-plan body is emitted.
        raise RuntimeError(
            f"catalog command failed: {args[0]} exit {result.returncode}"
        )
    if len(result.stdout) > 65536:
        raise RuntimeError("qualification output exceeded cap")
    return result.stdout


def admit(source_kind, relative_path, revision, argv):
    if source_kind != "protected_revision" or not re.fullmatch(
        "[0-9a-f]{40}", revision
    ):
        raise ValueError("unadmitted source")
    if relative_path != "source/main.tf" or argv != ["plan"]:
        raise ValueError("unadmitted path/catalog")
    return True


def source_admission(root, relative_path):
    candidate = root / relative_path
    if relative_path != "main.tf" or candidate.is_symlink() or not candidate.is_file():
        raise ValueError("inadmissible source path")
    if candidate.resolve().parent != root.resolve():
        raise ValueError("source escape")
    return hashlib.sha256(candidate.read_bytes()).hexdigest()


def admitted_source():
    with tempfile.TemporaryDirectory(prefix="dw16-source-") as temp:
        source = Path(temp)
        shutil.copyfile(ROOT / "source/main.tf", source / "main.tf")
        git = shutil.which("git")
        if not git:
            raise RuntimeError("Git missing")
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_AUTHOR_DATE": "2026-10-09T00:00:00Z",
            "GIT_COMMITTER_DATE": "2026-10-09T00:00:00Z",
        }
        command([git, "-C", temp, "init", "-q"], env=env)
        command([git, "-C", temp, "add", "main.tf"], env=env)
        command(
            [
                git,
                "-C",
                temp,
                "-c",
                "user.name=Qualification",
                "-c",
                "user.email=synthetic@example.invalid",
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "-qm",
                "Admit synthetic source",
            ],
            env=env,
        )
        revision = (
            command([git, "-C", temp, "rev-parse", "HEAD"], env=env).decode().strip()
        )
        admit("protected_revision", "source/main.tf", revision, ["plan"])
        return revision, source_admission(source, "main.tf")


class Qualification:
    def __init__(self):
        self.prefix = "dw16-" + uuid.uuid4().hex
        self.volumes = [self.prefix + "-staging", self.prefix + "-custody"]
        self.containers = []
        self.networks = []
        self.image = (
            command([DOCKER, "image", "inspect", IMAGE, "--format", "{{.Id}}"])
            .decode()
            .strip()
        )
        profile = json.loads((ROOT / "profile.json").read_text())
        if profile["schema_version"] != 1 or profile["image_id"] != self.image:
            raise ValueError("unqualified image/profile version")

    def setup(self):
        for volume, uid, mode in zip(self.volumes, (10001, 10002), ("0755", "0700")):
            command(
                [
                    DOCKER,
                    "volume",
                    "create",
                    "--driver=local",
                    "--opt=type=tmpfs",
                    "--opt=device=tmpfs",
                    f"--opt=o=size=8m,uid={uid},gid={uid},mode={mode}",
                    volume,
                ]
            )
        # Keep bounded stores mounted across independent receiver restarts.
        # This is process/container restart qualification, not host power-loss proof.
        anchor = self.prefix + "-lifecycle"
        self.containers.append(anchor)
        command(
            [
                DOCKER,
                "run",
                "-d",
                "--name",
                anchor,
                "--network=none",
                "--user=10002:10002",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--memory=32m",
                "--pids-limit=4",
                "--log-driver=none",
                "--entrypoint=python",
                "-v",
                self.volumes[0] + ":/staging",
                "-v",
                self.volumes[1] + ":/custody",
                self.image,
                "-c",
                "import time; time.sleep(300)",
            ]
        )

    def task(
        self,
        mode,
        receiver=False,
        memory="512m",
        disk="64m",
        pids="64",
        detached=False,
        network="none",
        deadline=60,
    ):
        name = self.prefix + "-" + str(len(self.containers))
        self.containers.append(name)
        uid = "10002" if receiver else "10001"
        # Private per-container mount, never shared host temporary storage.
        temporary_mount = (
            f"/tmp:rw,noexec,nosuid,nodev,size=8m,uid={uid},gid={uid},mode=0700"  # nosec B108
        )
        args = [
            DOCKER,
            "run",
            "--name",
            name,
            "--network=" + network,
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--user",
            uid + ":" + uid,
            "--memory",
            memory,
            "--memory-swap",
            memory,
            "--cpus=.5",
            "--pids-limit",
            pids,
            "--log-driver=none",
            "--tmpfs",
            f"/work:rw,noexec,nosuid,nodev,size={disk},uid={uid},gid={uid},mode=0700",
            "--tmpfs",
            temporary_mount,
            "-v",
            self.volumes[0] + ":/staging" + (":ro" if receiver else ""),
            "-v",
            self.volumes[1] + ":/custody" + ("" if receiver else ":ro"),
        ]
        if network != "none":
            args.extend(["-e", "LOCAL_PROBE=1"])
        if detached:
            args.append("-d")
        if mode == "store_disk":
            destination = "/custody" if receiver else "/staging"
            script = (
                "import os,json; from pathlib import Path\n"
                f"root=Path({destination!r}); target=root/'partial-upload'; denied=False\n"
                "try:\n"
                " with target.open('wb') as stream:\n"
                "  for _ in range(16): stream.write(bytes(1024*1024))\n"
                "except OSError: denied=True\n"
                "finally: target.unlink(missing_ok=True)\n"
                "info=os.statvfs(root); print(json.dumps({'disk_denied':denied,'partial_removed':not target.exists(),'capacity_bytes':info.f_blocks*info.f_frsize}))"
            )
            args.extend(["--entrypoint=python", self.image, "-c", script])
        elif receiver:
            args.extend(
                ["--entrypoint=python", self.image, "/opt/custody/probe.py", mode]
            )
        else:
            args.extend([self.image, mode])
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(args, stdout=stdout, stderr=stderr)  # nosec B603
            started = time.monotonic()
            capped = False
            while process.poll() is None:
                if (
                    os.fstat(stdout.fileno()).st_size
                    + os.fstat(stderr.fileno()).st_size
                    > 65536
                    or time.monotonic() - started > deadline
                ):
                    command([DOCKER, "kill", name])
                    capped = True
                    break
                time.sleep(0.02)
            process.wait(timeout=10)
            stdout.seek(0)
            stderr.seek(0)
            result = subprocess.CompletedProcess(
                args,
                124 if capped else process.returncode,
                stdout.read(65536),
                stderr.read(65536),
            )
        diagnostic = Path(tempfile.gettempdir()) / (name + ".private-stderr")
        descriptor = os.open(diagnostic, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(result.stderr)
        if len(result.stdout) > 65536:
            raise RuntimeError("output cap")
        return name, result.returncode, result.stdout

    def cleanup(self):
        for name in self.containers:
            subprocess.run([DOCKER, "rm", "-f", name], capture_output=True, check=False)  # nosec B603
        for volume in self.volumes:
            command([DOCKER, "volume", "rm", volume])
        for network in self.networks:
            command([DOCKER, "network", "rm", network])


def qualify():
    result = {"status": "running", "profile": "linux-arm64-docker-nonroot-offline-v1"}
    result["source_sha"], result["source_content_sha256"] = admitted_source()
    experiment = Qualification()
    try:
        experiment.setup()
        name, code, output = experiment.task("plan")
        if code:
            raise RuntimeError(f"real saved-plan probe failed ({code})")
        result["plan"] = json.loads(output)
        result["container_config"] = json.loads(command([DOCKER, "inspect", name]))[0]
        # Only sanitized boundaries, never environment bodies, are retained.
        cfg = result.pop("container_config")
        result["controls"] = {
            "uid": cfg["Config"]["User"],
            "read_only": cfg["HostConfig"]["ReadonlyRootfs"],
            "cap_drop": cfg["HostConfig"]["CapDrop"],
            "security_opt": cfg["HostConfig"]["SecurityOpt"],
            "network": cfg["HostConfig"]["NetworkMode"],
            "memory": cfg["HostConfig"]["Memory"],
            "nano_cpus": cfg["HostConfig"]["NanoCpus"],
            "pids_limit": cfg["HostConfig"]["PidsLimit"],
            "mount_destinations": [item["Destination"] for item in cfg["Mounts"]],
            "default_seccomp": True,
        }
        result["image_id"] = cfg["Image"]
        result["catalog_digests"] = json.loads(
            command(
                [
                    DOCKER,
                    "run",
                    "--rm",
                    "--network=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges:true",
                    "--entrypoint=python",
                    experiment.image,
                    "-c",
                    "import hashlib,json,pathlib; files=[pathlib.Path('/usr/local/bin/tofu'),pathlib.Path('/opt/qualification/source/main.tf'),*pathlib.Path('/opt/mirror').rglob('terraform-provider-external*')]; print(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}))",
                ]
            )
        )
        _, code, output = experiment.task("finalize", receiver=True)
        if code:
            raise RuntimeError(f"receiver finalize failed ({code})")
        result["custody"] = json.loads(output)
        _, code, output = experiment.task("restart", receiver=True)
        if code:
            raise RuntimeError(f"receiver restart failed ({code})")
        result["restart"] = json.loads(output)
        _, code, output = experiment.task("collector_denied")
        if code:
            raise RuntimeError("collector denial probe failed")
        result["collector"] = json.loads(output)
        result["store_disk"] = {}
        for receiver, label in ((False, "staging"), (True, "custody")):
            _, code, output = experiment.task("store_disk", receiver=receiver)
            if code:
                raise RuntimeError("bounded custody/staging disk probe failed")
            result["store_disk"][label] = json.loads(output)
        _, code, output = experiment.task("receiver_faults", receiver=True)
        if code:
            raise RuntimeError(f"real receiver faults failed ({code})")
        result["receiver_faults"] = json.loads(output)
        _, code, output = experiment.task("attacks", receiver=True)
        if code:
            raise RuntimeError(f"receiver attacks failed ({code})")
        result["custody_attacks"] = json.loads(output)
        _, code, output = experiment.task("disk", disk="16m")
        result["disk"] = {**json.loads(output), "exit_code": code}
        _, code, output = experiment.task("pids", pids="16")
        result["pids"] = {**json.loads(output), "exit_code": code}
        memory_name, code, _ = experiment.task("memory", memory="64m")
        metadata = json.loads(command([DOCKER, "inspect", memory_name]))[0]
        result["memory"] = {
            "exit_code": code,
            "oom_killed": metadata["State"]["OOMKilled"],
        }
        _, code, output = experiment.task("cpu")
        result["cpu"] = {**json.loads(output), "exit_code": code}
        for mode in ("output", "descendants"):
            name, code, _ = experiment.task(mode, deadline=1)
            state = json.loads(command([DOCKER, "inspect", name]))[0]["State"]
            result["output_cap" if mode == "output" else "time_cap"] = {
                "exit_code": code,
                "stopped": not state["Running"],
            }
        result["descendants"] = {}
        for cause in ("cancel", "timeout", "lease_loss"):
            name, code, _ = experiment.task("descendants", detached=True)
            if code:
                raise RuntimeError("descendant start failed")
            time.sleep(0.5)
            before = (
                command([DOCKER, "top", name, "-eo", "pid,comm"]).decode().splitlines()
            )
            command([DOCKER, "kill", name])
            state = json.loads(command([DOCKER, "inspect", name]))[0]["State"]
            result["descendants"][cause] = {
                "processes_before": len(before) - 1,
                "stopped": not state["Running"],
                "exit_code": state["ExitCode"],
            }
        network = experiment.prefix + "-local"
        experiment.networks.append(network)
        command([DOCKER, "network", "create", "--internal", network])
        sink = experiment.prefix + "-sink"
        experiment.containers.append(sink)
        command(
            [
                DOCKER,
                "run",
                "-d",
                "--name",
                sink,
                "--network",
                network,
                "--network-alias=probe-sink",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--log-driver=none",
                "--entrypoint=python",
                experiment.image,
                "-m",
                "http.server",
                "8000",
            ]
        )
        time.sleep(0.5)
        _, code, output = experiment.task("plan", network=network)
        if code:
            raise RuntimeError("approved local provider traffic probe failed")
        result["local_traffic"] = json.loads(output)["provider_probe"]
        _, code, output = experiment.task("replan", receiver=True)
        if code:
            raise RuntimeError("actual changed-plan grant probe failed")
        result["replan"] = json.loads(output)
        validate(result)
        result["status"] = "passed"
        return result
    finally:
        experiment.cleanup()


def validate(result):
    flags = [
        result["collector"]["custody_denied"],
        result["restart"]["restart_verified"],
        result["memory"]["oom_killed"],
        result["disk"]["disk_denied"],
        result["disk"]["partial_removed"],
        result["pids"]["pids_denied"],
        result["output_cap"]["stopped"],
        result["time_cap"]["stopped"],
        *result["custody_attacks"].values(),
    ]
    flags.extend(
        value == "True"
        for key, value in result["plan"]["provider_probe"].items()
        if key != "uid"
    )
    flags.extend(
        value == "True"
        for key, value in result["local_traffic"].items()
        if key != "uid"
    )
    flags.extend(
        item["stopped"] and item["processes_before"] >= 2
        for item in result["descendants"].values()
    )
    flags.extend(
        item["same_operation"]
        and item["repeat_action_denied"]
        and item["lock_retained"]
        and item["action_count"] <= 1
        and item["crash_exit"] == 73
        for item in result["receiver_faults"]["faults"].values()
    )
    flags.extend(
        [
            result["receiver_faults"]["tuple_mutations_denied"] == 30,
            result["plan"]["raw_digest"] == result["restart"]["raw_digest"],
            result["plan"]["raw_digest"] != result["plan"]["sanitized_digest"],
            result["plan"]["uid"] == 10001,
            result["custody"]["uid"] == 10002,
            result["cpu"]["cpu_max"] == "50000 100000",
            result["output_cap"]["exit_code"] == 124,
            result["time_cap"]["exit_code"] == 124,
        ]
    )
    if not all(flags):
        raise ValueError("mandatory qualification assertion failed")
    if not all(
        item["disk_denied"]
        and item["partial_removed"]
        and item["capacity_bytes"] == 8 * 1024 * 1024
        for item in result["store_disk"].values()
    ):
        raise ValueError("local store quota/cleanup failed")
    if (
        result["catalog_digests"]["/opt/qualification/source/main.tf"]
        != result["source_content_sha256"]
    ):
        raise ValueError("admitted source differs from executed image source")
    expected_catalog = {
        "/usr/local/bin/tofu": "d5c690023baebe8bf2cfb2062e292186f4797a173db22c973bd9de45cb68a62f",
        "/opt/mirror/registry.opentofu.org/hashicorp/external/2.3.5/linux_arm64/terraform-provider-external": "f9994ee228b86d34c289d858af46f758921f34393a27a1bb5677761c08228f50",
    }
    if any(
        result["catalog_digests"].get(path) != digest
        for path, digest in expected_catalog.items()
    ):
        raise ValueError("unsupported tool/provider catalog")
    if (
        not result["replan"]["replan_requires_new_tuple"]
        or not result["replan"]["actual_plan_changed"]
        or result["replan"]["action_count"] != 0
    ):
        raise ValueError("changed-plan old grant did not deny")
    controls = result["controls"]
    if (
        controls["network"] != "none"
        or not controls["read_only"]
        or controls["cap_drop"] != ["ALL"]
        or controls["security_opt"] != ["no-new-privileges:true"]
        or set(controls["mount_destinations"]) != {"/staging", "/custody"}
    ):
        raise ValueError("actual profile control mismatch")


if __name__ == "__main__":
    output = Path(os.environ["DW16_PRIVATE_RESULTS"])
    output.write_text(json.dumps(qualify(), indent=2) + "\n")
