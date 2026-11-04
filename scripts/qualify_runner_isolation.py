"""Run real hostile Linux ARM64 probes through the production isolation boundary.

Build-time pinned downloads are permitted. Task execution always uses
ExecutionRunner; no Docker run/exec path bypasses its admission or lifetime.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import get_args
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURE = ROOT / "tests/fixtures/infra_automation/qualification/16_13"
IMAGE = "dw16-13-qualification:1"


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def command(argv, *, environment=None, timeout=60):
    result = subprocess.run(
        argv,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if result.returncode or len(result.stdout) > 1048576:
        raise RuntimeError("Qualification control command failed.")
    return result.stdout


def prepare_image(docker, build, output):
    if build:
        with (output / "image-build.log").open("wb") as log:
            result = subprocess.run(
                [
                    docker,
                    "build",
                    "--platform",
                    "linux/arm64",
                    "-f",
                    str(FIXTURE / "Dockerfile"),
                    "-t",
                    IMAGE,
                    str(ROOT),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=600,
                check=False,
            )
        if result.returncode:
            raise RuntimeError("Pinned qualification image build failed.")
    info = json.loads(command([docker, "image", "inspect", IMAGE]))[0]
    container = (
        command([docker, "create", "--entrypoint", "/bin/false", info["Id"]])
        .decode()
        .strip()
    )
    try:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "pins.json"
            command(
                [docker, "cp", container + ":/opt/deploywhisper/pins.json", str(target)]
            )
            pins = json.loads(target.read_bytes())
    finally:
        command([docker, "rm", container])
    return info, pins


def make_repository(root, contents=None):
    source = root / "repository"
    source.mkdir(mode=0o700)
    contents = (
        contents
        if contents is not None
        else {
            name: (FIXTURE / "source" / name).read_bytes()
            for name in ("main.tf", ".terraform.lock.hcl", "source.lock")
        }
    )
    for name, raw in contents.items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(raw)
    environment = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(root),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_AUTHOR_DATE": "2026-11-04T00:00:00Z",
        "GIT_COMMITTER_DATE": "2026-11-04T00:00:00Z",
    }
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git unavailable.")
    for args in (
        ("init", "-q"),
        ("add", "--all"),
        (
            "-c",
            "user.name=Qualification",
            "-c",
            "user.email=synthetic@example.invalid",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-qm",
            "Synthetic trusted source",
        ),
    ):
        command([git, "-C", str(source), *args], environment=environment)
    commit = (
        command([git, "-C", str(source), "rev-parse", "HEAD"], environment=environment)
        .decode()
        .strip()
    )
    files = {name: digest(raw) for name, raw in contents.items()}
    return source, commit, files


def assess(cases, admission, stable):
    expected = {
        "invalid-image-pin": "unsupported_profile",
        "unsupported-host-profile": "preflight_denied",
        "receiver-identity-denied": "credential_denied",
        "receiver-environment-denied": "credential_denied",
        "real-provider": "succeeded",
        "vendored-tofu-provider": "succeeded",
        "tool-version": "succeeded",
        "environment": "succeeded",
        "watchdog-defenses": "succeeded",
        "cancel-at-finalization": "cancelled",
        "cpu-cap": "succeeded",
        "memory-cap": "memory_limit",
        "pid-cap": "succeeded",
        "disk-cap": "succeeded",
        "output-cap": "output_limit",
        "partial-evidence": "failed",
        "cancel-descendants": "cancelled",
        "lease-descendants": "lease_lost",
        "timeout-descendants": "timed_out",
    }
    by_name = {item["case"]: item for item in cases}
    checks = {
        "complete_corpus": set(by_name) == set(expected),
        "stable_sources": stable,
        "hostile_admission": len(admission) >= 9
        and all(item["denied"] for item in admission),
    }
    for name, state in expected.items():
        item = by_name.get(name, {})
        result = item.get("result", {})
        checks[name + ":state"] = result.get("state") == state
        if name == "unsupported-host-profile":
            checks[name + ":precredential"] = (
                item.get("resolver_calls") == 0
                and item.get("container_created") is False
            )
            continue
        checks[name + ":cleanup"] = (
            result.get("cleanup_complete") is True
            and item.get("container_removed") is True
        )
        checks[name + ":metadata"] = item.get("metadata_secret_free") is True
        if state != "succeeded":
            checks[name + ":no_partial_publication"] = (
                result.get("finalizable") is False
                and result.get("output_digest") is None
                and item.get("output_size") == 0
            )
        if name == "invalid-image-pin":
            checks[name + ":precredential"] = item.get("resolver_calls") == 0
        if name.endswith("descendants"):
            lines = (item.get("process_tree") or "").strip().splitlines()[1:]
            rows = [line.split() for line in lines]
            checks[name + ":escaped_descendants_observed"] = (
                len(rows) >= 3 and len({row[2] for row in rows if len(row) >= 4}) >= 2
            )
            before_host_kill = item.get("cancel_persisted_before_kill") is True
            watchdog_expired_first = (
                name == "timeout-descendants"
                and item.get("cancel_persisted_before_kill") is None
                and (item.get("last_state") or {}).get("ExitCode") == 124
                and (item.get("last_state") or {}).get("Running") is False
            )
            checks[name + ":durable_cancellation"] = item.get(
                "cancel_persisted_before_removal"
            ) is True and (before_host_kill or watchdog_expired_first)
    for name in ("environment", "real-provider", "vendored-tofu-provider"):
        evidence = by_name.get(name, {}).get("evidence") or {}
        if name in ("real-provider", "vendored-tofu-provider"):
            checks[name + ":actual_plan"] = (
                evidence.get("plan_created") is True
                and len(evidence.get("raw_digest", "")) == 64
            )
            evidence = evidence.get("provider_probe") or {}
        count = str(evidence.get("seccomp_filter_count", ""))
        checks[name + ":stacked_seccomp"] = count.isdigit() and int(count) >= 2
        checks[name + ":nonroot"] = (
            str(evidence.get("uid")) == "10001" and str(evidence.get("gid")) == "10001"
        )
        for key in (
            "seccomp_enforced",
            "no_new_privileges",
            "capabilities_dropped",
            "host_secret_absent",
            "receiver_secret_absent",
            "git_config_absent",
            "collector_present",
            "socket_absent",
            "metadata_denied",
            "egress_denied",
            "root_readonly",
            "source_readonly",
            "catalog_readonly",
            "dormant_interfaces_down",
            "activation_denied",
            "no_nonloopback_ipv4_address",
            "no_nonloopback_ipv6_address",
            "no_nonloopback_ipv4_route",
            "no_nonloopback_ipv6_route",
        ):
            checks[name + ":" + key] = str(evidence.get(key)) == "True"
    cpu = by_name.get("cpu-cap", {}).get("evidence") or {}
    statistics = dict(
        line.split()
        for line in cpu.get("cpu_stat", "").splitlines()
        if len(line.split()) == 2
    )
    checks["cpu:quota_and_throttle"] = (
        cpu.get("cpu_max") == "50000 100000"
        and int(statistics.get("nr_throttled", "0")) > 0
    )
    checks["memory:actual_oom"] = (
        by_name.get("memory-cap", {}).get("last_state") or {}
    ).get("OOMKilled") is True
    pids = by_name.get("pid-cap", {}).get("evidence") or {}
    checks["pids:actual_limit"] = (
        pids.get("pids_denied") is True
        and 0 < pids.get("children_created", 0) < 16
        and pids.get("pids_max") == "16"
    )
    disk = by_name.get("disk-cap", {}).get("evidence") or {}
    checks["disk:actual_enospc_cleanup"] = (
        disk.get("disk_denied") is True
        and disk.get("failure_errno") == 28
        and disk.get("partial_removed") is True
    )
    version = by_name.get("tool-version", {}).get("evidence") or {}
    checks["catalog:tool_version_executed"] = (
        version.get("terraform_version") == "1.13.1"
    )
    vendor = by_name.get("vendored-tofu-provider", {}).get("evidence") or {}
    checks["source:vendored_tofu_module_executed"] = (
        "module.local.terraform_data.vendored" in vendor.get("module_resources", [])
    )
    required_admission = {
        "tofu-outside",
        "tofu-remote",
        "tofu-oversize",
        "tofu-json-outside",
        "tofu-json-remote",
        "tofu-json-oversize",
        "public-staging-parent",
        "removed-provider-command",
    }
    checks["review:required_admission_cases"] = required_admission <= {
        item["case"] for item in admission
    }
    for item in admission:
        if item["case"] in required_admission:
            checks[item["case"] + ":precredential"] = (
                item.get("credential_resolver_calls") == 0
            )
    public = next(
        (item for item in admission if item["case"] == "public-staging-parent"), {}
    )
    checks["public_staging_no_partial_source"] = (
        public.get("staging_empty_after_denial") is True
    )
    defenses = by_name.get("watchdog-defenses", {}).get("evidence") or {}
    for key in (
        "separate_pid1",
        "watchdog_not_stopped",
        "ptrace_denied",
        "proc_memory_denied",
        "signal_stop_and_kill_attempted",
        "priority_denied",
        "scheduler_denied",
        "affinity_denied",
    ):
        checks["watchdog:" + key] = defenses.get(key) is True
    return checks


def orphan_controller(path):
    """Separate trusted host process; the task still uses the production runner."""
    from infra_automation.runner.catalog import read_protected
    from infra_automation.runner.execution import ExecutionRunner, CollectorCredentials
    from infra_automation.runner.execution_profile import ExecutionProfile
    from infra_automation.runner.protocol import TaskScope
    from infra_automation.runner.sandbox import DockerSandbox
    from infra_automation.runner.source import load_registration, materialize_source

    value = json.loads(read_protected(path))
    source = materialize_source(
        load_registration(value["registration_path"], value["registration_digest"]),
        value["source_parent"],
    )
    timings = {}

    class TimedSandbox(DockerSandbox):
        def create(self, source_path, *, name=None, task_digest=None):
            timings["create_entered_monotonic"] = time.monotonic()
            Path(value["timings_path"]).write_bytes(canonical(timings))
            time.sleep(value["create_delay_seconds"])
            return super().create(source_path, name=name, task_digest=task_digest)

    sandbox = TimedSandbox(
        value["docker"],
        value["docker_host"],
        ExecutionProfile.model_validate_json(canonical(value["profile"])),
    )
    try:
        runner = ExecutionRunner(
            sandbox, value["catalog"], value["catalog_digest"], value["journal"]
        )

        def resolve_credentials():
            timings["credential_resolver_calls"] = (
                timings.get("credential_resolver_calls", 0) + 1
            )
            Path(value["timings_path"]).write_bytes(canonical(timings))
            return CollectorCredentials(
                "qualification-collector",
                {"COLLECTOR_TOKEN": "synthetic-collector-sentinel"},
            )

        timings["execute_entered_monotonic"] = time.monotonic()
        Path(value["timings_path"]).write_bytes(canonical(timings))
        result = runner.execute(
            TaskScope.model_validate(value["scope"]),
            "qualification_probe",
            {"mode": value["mode"]},
            source,
            expected_profile_digest=runner.profile_digest,
            credential_resolver=resolve_credentials,
            authority_check=lambda: True,
        )
        return 0 if result.finalizable else 1
    finally:
        source.close()
        sandbox.close()


def controller_death(
    root,
    docker,
    docker_host,
    image_id,
    registration_path,
    catalog,
    catalog_digest,
    mode="descendants",
    create_delay_seconds=0,
    lease_seconds=25,
):
    """Kill the host supervisor; observe namespace watchdog, then durable recovery."""
    from infra_automation.runner.execution import ExecutionRunner
    from infra_automation.runner.execution_profile import ExecutionProfile
    from infra_automation.runner.protocol import TaskScope
    from infra_automation.runner.sandbox import DockerSandbox

    (root / "controller-error.json").unlink(missing_ok=True)
    case_key = mode + (f"-delay-{create_delay_seconds}" if create_delay_seconds else "")
    journal = root / ("orphan-journal-" + case_key)
    journal.mkdir(mode=0o700)
    source_parent = root / ("orphan-snapshots-" + case_key)
    source_parent.mkdir(mode=0o700)
    profile = ExecutionProfile(
        image_id=image_id, timeout_seconds=6, credential_names=("COLLECTOR_TOKEN",)
    )
    scope = TaskScope(
        runner_id="qualification-runner",
        project_id="1",
        workspace_id="1",
        run_id="qualification-run",
        step_id="operator-death-" + case_key,
        attempt=1,
        fence=1,
        coordinator_generation=1,
        authorization_epoch=1,
        restore_epoch=1,
        lease_deadline=(
            datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        audience="runner-task-v1",
    )
    timings_path = root / ("orphan-timings-" + case_key + ".json")
    timings_path.write_bytes(b"{}")
    timings_path.chmod(0o600)
    configuration = root / ("orphan-controller-" + case_key + ".json")
    configuration.write_bytes(
        canonical(
            {
                "mode": mode,
                "create_delay_seconds": create_delay_seconds,
                "timings_path": str(timings_path),
                "registration_path": str(registration_path),
                "registration_digest": digest(registration_path.read_bytes()),
                "source_parent": str(source_parent),
                "docker": docker,
                "docker_host": docker_host,
                "profile": profile.model_dump(mode="json"),
                "scope": scope.model_dump(mode="json"),
                "catalog": str(catalog),
                "catalog_digest": catalog_digest,
                "journal": str(journal),
            }
        )
    )
    configuration.chmod(0o600)
    process = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--orphan-controller",
            str(configuration),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    name = None
    tree = None
    state = None
    expired_without_host = False
    killed_at = None
    stopped_observed_at = None
    original_deadline = None
    observation_tolerance = 0.75
    running_beyond_original_bound = False
    started = time.monotonic()
    sandbox = DockerSandbox(docker, docker_host, profile)
    recovery = []
    try:
        until = time.monotonic() + 15
        while time.monotonic() < until and process.poll() is None:
            database = journal / "executions.sqlite3"
            if database.exists():
                with closing(sqlite3.connect(database)) as db:
                    try:
                        row = db.execute(
                            "SELECT container_id,state FROM executions"
                        ).fetchone()
                    except sqlite3.OperationalError:
                        row = None
                if row and row[1] == "running":
                    name = row[0]
                    try:
                        tree = command(
                            [docker, "top", name, "-eo", "pid,ppid,sid,comm"]
                        ).decode()
                    except RuntimeError:
                        tree = None
                    if tree and len(tree.strip().splitlines()) >= 5:
                        break
            time.sleep(0.05)
        if process.poll() is None and tree and len(tree.strip().splitlines()) >= 5:
            process.kill()
            process.wait(timeout=2)
            killed_at = time.monotonic()
            timings = json.loads(timings_path.read_bytes())
            original_deadline = (
                timings["execute_entered_monotonic"] + profile.timeout_seconds
            )
            until = original_deadline + observation_tolerance + 3
            while time.monotonic() < until:
                state = json.loads(command([docker, "inspect", name]))[0]["State"]
                observed_at = time.monotonic()
                if not state["Running"]:
                    stopped_observed_at = observed_at
                    expired_without_host = state["ExitCode"] == 124
                    break
                if observed_at > original_deadline + observation_tolerance:
                    running_beyond_original_bound = True
                time.sleep(0.05)
        runner = ExecutionRunner(sandbox, catalog, catalog_digest, journal)
        recovery = runner.recover_pending()
        removed = not name or not command(
            [
                docker,
                "ps",
                "-a",
                "--filter",
                "name=^/" + name + "$",
                "--format",
                "{{.ID}}",
            ]
        )
        with closing(sqlite3.connect(journal / "executions.sqlite3")) as db:
            rows = db.execute(
                "SELECT state,cancel_requested,cleanup_complete FROM executions"
            ).fetchall()
        qualified = bool(
            process.returncode == -9
            and expired_without_host
            and json.loads(timings_path.read_bytes()).get("credential_resolver_calls")
            == 1
            and stopped_observed_at is not None
            and original_deadline is not None
            and stopped_observed_at <= original_deadline + observation_tolerance
            and not running_beyond_original_bound
            and removed
            and len(recovery) == 1
            and recovery[0]["cleanup_complete"]
            and rows == [("interrupted", 1, 1)]
        )
        return {
            "qualified": qualified,
            "create_delay_seconds": create_delay_seconds,
            "lease_seconds": lease_seconds,
            "timings": json.loads(timings_path.read_bytes()),
            "original_deadline_anchor": "Host execute call entry, conservatively before runtime preflight and setup",
            "original_deadline_monotonic": original_deadline,
            "observation_tolerance_seconds": observation_tolerance,
            "stop_observed_monotonic": stopped_observed_at,
            "stopped_within_original_deadline": stopped_observed_at is not None
            and original_deadline is not None
            and stopped_observed_at <= original_deadline + observation_tolerance,
            "running_beyond_original_bound": running_beyond_original_bound,
            "credential_resolver_calls": json.loads(timings_path.read_bytes()).get(
                "credential_resolver_calls", 0
            ),
            "controller_killed_seconds_after_original_start": killed_at
            - json.loads(timings_path.read_bytes())["execute_entered_monotonic"]
            if killed_at
            else None,
            "controller_exit": process.returncode,
            "controller_error": json.loads((root / "controller-error.json").read_text())
            if (root / "controller-error.json").exists()
            else None,
            "container_state_before_recovery": state,
            "process_tree_before_controller_kill": tree,
            "expired_without_host": expired_without_host,
            "elapsed_seconds": time.monotonic() - started,
            "seconds_after_controller_death": time.monotonic() - killed_at
            if killed_at
            else None,
            "recovery": recovery,
            "container_removed": removed,
            "journal_states": rows,
            "profile": profile.model_dump(mode="json"),
        }
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        if name:
            try:
                ExecutionRunner(
                    sandbox, catalog, catalog_digest, journal
                ).recover_pending()
            except ValueError:
                pass
        sandbox.close()


def run(args):
    witness_paths = [
        *(ROOT / "infra_automation/runner").glob("*.py"),
        Path(__file__).resolve(),
        *(
            path
            for path in FIXTURE.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        ),
    ]
    before_hashes = {
        str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in witness_paths
    }
    from infra_automation.runner.catalog import (
        CatalogDocument,
        CommandRequest,
        build_argv,
        load_catalog,
    )
    from infra_automation.runner.execution_profile import ExecutionProfile
    from infra_automation.runner.sandbox import DockerSandbox
    from infra_automation.runner.execution import ExecutionRunner, CollectorCredentials
    from infra_automation.runner.source import (
        SourceRegistration,
        materialize_source,
        load_registration,
    )
    from infra_automation.runner.protocol import TaskScope

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker unavailable.")
    image, pins = prepare_image(docker, args.build, output)
    image_sources = {
        "/opt/deploywhisper/bootstrap.py": ROOT
        / "infra_automation/runner/bootstrap.py",
        **{
            "/opt/deploywhisper/" + name: FIXTURE / name
            for name in ("probe.py", "provider_probe.py", "tofurc")
        },
        **{
            "/opt/deploywhisper/source/" + name: FIXTURE / "source" / name
            for name in ("main.tf", ".terraform.lock.hcl", "source.lock")
        },
    }
    image_source_checks = {
        name: pins.get(name) == digest(path.read_bytes())
        for name, path in image_sources.items()
    }
    context = json.loads(command([docker, "context", "inspect"]))[0]
    docker_host = context["Endpoints"]["docker"]["Host"]
    results = []
    with tempfile.TemporaryDirectory(prefix="dw16-13-qualified-") as temporary:
        root = Path(temporary).resolve()
        root.chmod(0o700)
        repository, commit, files = make_repository(root)
        registration = SourceRegistration(
            repository_path=str(repository),
            commit=commit,
            tree_digest=digest(canonical(files)),
            lock_digests={
                name: files[name] for name in (".terraform.lock.hcl", "source.lock")
            },
            trust="protected_revision",
        )
        registration_path = root / "source-registration.json"
        registration_path.write_bytes(canonical(registration.model_dump(mode="json")))
        registration_path.chmod(0o600)
        registration = load_registration(
            registration_path, digest(registration_path.read_bytes())
        )
        source_parent = root / "snapshots"
        source_parent.mkdir(mode=0o700)
        snapshot = materialize_source(registration, source_parent)
        file_pins = []
        for path, checksum in pins.items():
            kind = (
                "provider"
                if "terraform-provider-external" in path
                else "lock"
                if path.endswith((".terraform.lock.hcl", "/tofurc", "/source.lock"))
                else "probe"
                if path.endswith(".py")
                else "tool"
                if path.startswith("/usr/local/")
                else "module"
            )
            file_pins.append({"path": path, "sha256": checksum, "kind": kind})
        document = CatalogDocument(version=1, image_id=image["Id"], files=file_pins)
        catalog = root / "catalog.json"
        catalog.write_bytes(canonical(document.model_dump(mode="json")))
        catalog.chmod(0o600)
        catalog_digest = digest(catalog.read_bytes())
        journal = root / "journal"
        journal.mkdir(mode=0o700)

        class ObservedSandbox(DockerSandbox):
            def __init__(self, profile):
                super().__init__(docker, docker_host, profile)
                self.created = None
                self.launched_at = None
                self.controls = None
                self.last_state = None
                self.process_tree = None
                self.cancel_persisted_before_kill = None
                self.cancel_persisted_before_removal = None
                self.metadata_secret_free = None
                self.cancel_action = None

            def create(self, source_path, name=None, task_digest=None):
                name = super().create(source_path, name=name, task_digest=task_digest)
                self.created = name
                row = self.inspect(name)
                host = row["HostConfig"]
                self.controls = {
                    key: host.get(key)
                    for key in (
                        "ReadonlyRootfs",
                        "Privileged",
                        "CapDrop",
                        "CapAdd",
                        "SecurityOpt",
                        "NetworkMode",
                        "IpcMode",
                        "PidMode",
                        "CgroupnsMode",
                        "Memory",
                        "MemorySwap",
                        "NanoCpus",
                        "PidsLimit",
                        "Tmpfs",
                        "LogConfig",
                        "Devices",
                        "Binds",
                    )
                }
                self.controls["user"] = row["Config"]["User"]
                self.controls["mounts"] = [
                    {
                        key: mount.get(key)
                        for key in ("Type", "Destination", "RW", "Propagation")
                    }
                    for mount in row["Mounts"]
                ]
                return name

            def start(self, name):
                process = super().start(name)
                self.launched_at = time.monotonic()
                return process

            def observe_tree(self):
                if (
                    self.created
                    and self.launched_at
                    and time.monotonic() - self.launched_at > 0.8
                ):
                    try:
                        self.process_tree = self.control(
                            "top", self.created, "-eo", "pid,ppid,sid,comm"
                        ).decode()
                    except ValueError:
                        pass

            def terminate(self, name):
                with closing(sqlite3.connect(journal / "executions.sqlite3")) as db:
                    row = db.execute(
                        "SELECT state,cancel_requested FROM executions WHERE container_id=?",
                        (name,),
                    ).fetchone()
                    self.cancel_persisted_before_kill = bool(row and row[1] == 1)
                return super().terminate(name)

            def remove(self, name):
                if self.cancel_action is not None:
                    self.cancel_action()
                    self.cancel_action = None
                with closing(sqlite3.connect(journal / "executions.sqlite3")) as db:
                    row = db.execute(
                        "SELECT cancel_requested FROM executions WHERE container_id=?",
                        (name,),
                    ).fetchone()
                    self.cancel_persisted_before_removal = bool(row and row[0] == 1)
                try:
                    inspection = self.inspect(name)
                    self.last_state = inspection["State"]
                    metadata = json.dumps(inspection)
                    self.metadata_secret_free = all(
                        value not in metadata
                        for value in (
                            "synthetic-collector-sentinel",
                            "synthetic-host-sentinel",
                            "synthetic-receiver-sentinel",
                        )
                    )
                except ValueError:
                    pass
                return super().remove(name)

        def execute(
            label,
            mode,
            *,
            profile_changes=None,
            cancel=False,
            lease_loss=False,
            credentials=True,
            resolver_identity="qualification-collector",
            credential_environment=None,
            catalog_override=None,
            cancel_during_cleanup=False,
            command_id="qualification_probe",
            source_override=None,
        ):
            if args.case and args.case != label:
                return None
            values = {
                "image_id": image["Id"],
                "memory_bytes": 536870912,
                "credential_names": ("COLLECTOR_TOKEN",),
            }
            values.update(profile_changes or {})
            try:
                profile = ExecutionProfile(**values)
            except ValueError as exc:
                record = {
                    "case": label,
                    "mode": mode,
                    "result": {"state": "preflight_denied", "finalizable": False},
                    "exception_type": type(exc).__name__,
                    "resolver_calls": 0,
                    "container_created": False,
                }
                results.append(record)
                return record
            sandbox = ObservedSandbox(profile)
            resolver_calls = []

            def resolve():
                resolver_calls.append(True)
                return CollectorCredentials(
                    identity=resolver_identity,
                    environment=credential_environment
                    if credential_environment is not None
                    else (
                        {"COLLECTOR_TOKEN": "synthetic-collector-sentinel"}
                        if credentials
                        else {}
                    ),
                )

            def observing():
                if mode == "descendants":
                    sandbox.observe_tree()
                return False

            def stopping():
                observing()
                return bool(
                    sandbox.launched_at and time.monotonic() - sandbox.launched_at >= 2
                )

            started = time.monotonic()
            try:
                selected_catalog, selected_digest = catalog_override or (
                    catalog,
                    catalog_digest,
                )
                runner = ExecutionRunner(
                    sandbox, selected_catalog, selected_digest, journal
                )
                scope = TaskScope(
                    runner_id="qualification-runner",
                    project_id="1",
                    workspace_id="1",
                    run_id="qualification-run",
                    step_id=label,
                    attempt=1,
                    fence=1,
                    coordinator_generation=1,
                    authorization_epoch=1,
                    restore_epoch=1,
                    lease_deadline=(
                        datetime.now(timezone.utc)
                        + timedelta(seconds=profile.timeout_seconds + 20)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    audience="runner-task-v1",
                )
                if cancel_during_cleanup:
                    sandbox.cancel_action = lambda: runner.cancel(scope)
                with patch.dict(
                    os.environ,
                    {
                        "QUALIFICATION_HOST_SECRET": "synthetic-host-sentinel",
                        "RECEIVER_API_TOKEN": "synthetic-receiver-sentinel",
                        "GIT_CONFIG_GLOBAL": "/nonexistent-hostile-config",
                    },
                ):
                    result = runner.execute(
                        scope=scope,
                        command_id=command_id,
                        parameters={"mode": mode} if mode is not None else {},
                        source_snapshot=source_override or snapshot,
                        expected_profile_digest=runner.profile_digest,
                        credential_resolver=resolve,
                        authority_check=(lambda: not stopping())
                        if lease_loss
                        else lambda: True,
                        cancellation_check=stopping if cancel else observing,
                    )
                value = asdict(result) if is_dataclass(result) else result.model_dump()
                value["finalizable"] = result.finalizable
                raw = value.pop("output", b"")
                if type(raw) is str:
                    raw = raw.encode()
                try:
                    evidence = json.loads(raw) if raw else None
                except ValueError:
                    evidence = None
                absent = True
                if sandbox.created:
                    absent = not command(
                        [
                            docker,
                            "ps",
                            "-a",
                            "--filter",
                            "name=^/" + sandbox.created + "$",
                            "--format",
                            "{{.ID}}",
                        ]
                    )
                record = {
                    "case": label,
                    "mode": mode,
                    "command": command_id,
                    "source_digest": (source_override or snapshot).digest,
                    "result": value,
                    "evidence": evidence,
                    "output_size": len(raw),
                    "elapsed_seconds": time.monotonic() - started,
                    "resolver_calls": len(resolver_calls),
                    "controls": sandbox.controls,
                    "last_state": sandbox.last_state,
                    "process_tree": sandbox.process_tree,
                    "cancel_persisted_before_kill": sandbox.cancel_persisted_before_kill,
                    "cancel_persisted_before_removal": sandbox.cancel_persisted_before_removal,
                    "metadata_secret_free": sandbox.metadata_secret_free,
                    "container_removed": absent,
                    "profile": profile.model_dump(mode="json"),
                }
                results.append(record)
                return record
            except Exception as exc:
                record = {
                    "case": label,
                    "mode": mode,
                    "result": {"state": "preflight_denied", "finalizable": False},
                    "exception_type": type(exc).__name__,
                    "resolver_calls": len(resolver_calls),
                    "container_created": sandbox.created is not None,
                }
                results.append(record)
                return record
            finally:
                sandbox.close()

        admission = []

        def denial(name, operation, credential_counter=None):
            try:
                operation()
            except (ValueError, TypeError, OSError):
                denied = True
            else:
                denied = False
            admission.append(
                {
                    "case": name,
                    "denied": denied,
                    "credential_resolver_calls": len(credential_counter or []),
                }
            )

        for payload in (
            {"command": "sh"},
            {"command": "tool_version", "argv": ["-destroy"]},
            {"command": "qualification_probe", "mode": "--help"},
        ):
            denial(
                "catalog-option-" + str(len(admission)),
                lambda payload=payload: CommandRequest.model_validate(payload),
            )
        denial(
            "untrusted-pr",
            lambda: SourceRegistration.model_validate(
                {**registration.model_dump(), "trust": "pull_request"}
            ),
        )
        denial(
            "commit-option",
            lambda: SourceRegistration.model_validate(
                {**registration.model_dump(), "commit": "--help"}
            ),
        )
        original_catalog = catalog.read_bytes()
        catalog.write_bytes(b"{}")
        denial("catalog-mutated", lambda: load_catalog(catalog, catalog_digest))
        catalog.write_bytes(original_catalog)
        alias = root / "catalog-alias"
        alias.symlink_to(catalog)
        denial("catalog-symlink", lambda: load_catalog(alias, catalog_digest))
        build_argv(
            load_catalog(catalog, catalog_digest),
            CommandRequest(command="qualification_probe", mode="success"),
        )
        marker = root / "forbidden-hook-marker"
        hook = repository / ".git/hooks/post-checkout"
        hook.write_text("#!/bin/sh\nprintf forbidden > " + str(marker) + "\n")
        hook.chmod(0o700)
        with (repository / ".git/config").open("a") as config:
            config.write(
                "\n[core]\n fsmonitor = "
                + str(hook)
                + "\n hooksPath = "
                + str(hook.parent)
                + "\n[credential]\n helper = !"
                + str(hook)
                + "\n"
            )
        hostile_environment = {
            "GIT_CONFIG_GLOBAL": str(repository / ".git/config"),
            "GIT_CONFIG_SYSTEM": str(repository / ".git/config"),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.fsmonitor",
            "GIT_CONFIG_VALUE_0": str(hook),
        }
        with patch.dict(os.environ, hostile_environment):
            clean = materialize_source(registration, source_parent)
        admission.append(
            {
                "case": "hostile-hooks-config-helpers",
                "denied": not marker.exists(),
                "snapshot_verified": clean.verify() is None,
            }
        )
        snapshot.path.chmod(0o755)
        escape = snapshot.path / "escape"
        escape.symlink_to(root / "catalog.json")
        snapshot.path.chmod(0o555)
        denial("snapshot-symlink-escape", snapshot.verify)
        snapshot.path.chmod(0o755)
        escape.unlink()
        snapshot.path.chmod(0o555)
        snapshot.verify()

        source_case_inputs = []
        base_contents = {
            name: (FIXTURE / "source" / name).read_bytes()
            for name in ("main.tf", ".terraform.lock.hcl", "source.lock")
        }

        def registered_variant(name, changed):
            variant_root = root / ("variant-" + name)
            variant_root.mkdir(mode=0o700)
            location, revision, hashes = make_repository(
                variant_root, {**base_contents, **changed}
            )
            value = SourceRegistration(
                repository_path=str(location),
                commit=revision,
                tree_digest=digest(canonical(hashes)),
                lock_digests={
                    key: hashes[key] for key in ("source.lock", ".terraform.lock.hcl")
                },
                trust="protected_revision",
            )
            registration_file = variant_root / "registration.json"
            registration_file.write_bytes(canonical(value.model_dump(mode="json")))
            registration_file.chmod(0o600)
            value = load_registration(
                registration_file, digest(registration_file.read_bytes())
            )
            destination = variant_root / "staging"
            destination.mkdir(mode=0o700)
            source_case_inputs.append(
                {
                    "case": name,
                    "commit": revision,
                    "tree_digest": value.tree_digest,
                    "configuration_bytes": {
                        key: len(raw) for key, raw in changed.items()
                    },
                    "files": hashes,
                }
            )
            return value, destination

        variants = {
            "tofu-outside": {
                "main.tofu": b'module "outside" { source = "/opt/deploywhisper/source" }'
            },
            "tofu-remote": {
                "main.tofu": b'module "remote" { source = "git::https://example.invalid/module.git" }'
            },
            "tofu-oversize": {"main.tofu": b"#" + b"x" * 131073 + b"\n"},
            "tofu-json-outside": {
                "main.tofu.json": canonical(
                    {"module": {"outside": {"source": "/opt/deploywhisper/source"}}}
                )
            },
            "tofu-json-remote": {
                "main.tofu.json": canonical(
                    {
                        "module": {
                            "remote": {
                                "source": "git::https://example.invalid/module.git"
                            }
                        }
                    }
                )
            },
            "tofu-json-oversize": {
                "main.tofu.json": canonical({"locals": {"padding": "x" * 131073}})
            },
        }
        for name, changed in variants.items():
            value, destination = registered_variant(name, changed)
            calls = []

            def materialize_before_credentials(
                value=value, destination=destination, calls=calls
            ):
                admitted = materialize_source(value, destination)
                try:
                    calls.append(True)
                finally:
                    admitted.close()

            denial(name, materialize_before_credentials, calls)
        public_parent = root / "public-staging"
        public_parent.mkdir(mode=0o755)
        public_calls = []

        def public_stage_before_credentials():
            admitted = materialize_source(registration, public_parent)
            try:
                public_calls.append(True)
            finally:
                admitted.close()

        denial("public-staging-parent", public_stage_before_credentials, public_calls)
        admission[-1]["staging_empty_after_denial"] = not any(public_parent.iterdir())
        admission[-1]["staging_mode"] = "0755"
        denial(
            "removed-provider-command", lambda: CommandRequest(command="provider_probe")
        )
        child_module = canonical(
            {
                "resource": {
                    "terraform_data": {"vendored": {"input": "pinned-local-fixture"}}
                }
            }
        )
        vendor_lock = json.loads(base_contents["source.lock"])
        vendor_lock["modules"] = [
            {"path": "modules/child", "sha256": digest(child_module)}
        ]
        vendor_registration, vendor_parent = registered_variant(
            "vendored-tofu",
            {
                "modules.tofu": b'module "local" { source = "./modules/child" }',
                "modules/child/main.tofu.json": child_module,
                "source.lock": canonical(vendor_lock),
            },
        )
        vendor_snapshot = materialize_source(vendor_registration, vendor_parent)

        denied_catalog = root / "catalog-invalid-pin.json"
        invalid_pins = document.model_dump(mode="json")
        invalid_pins["files"][0]["sha256"] = "sha256:" + "0" * 64
        denied_catalog.write_bytes(canonical(invalid_pins))
        denied_catalog.chmod(0o600)
        execute(
            "invalid-image-pin",
            "environment",
            catalog_override=(denied_catalog, digest(denied_catalog.read_bytes())),
        )
        execute(
            "unsupported-host-profile",
            "environment",
            profile_changes={"docker_version": "0.0.0"},
        )
        execute(
            "receiver-identity-denied",
            "environment",
            resolver_identity="receiver-identity",
        )
        execute(
            "receiver-environment-denied",
            "environment",
            credential_environment={
                "RECEIVER_API_TOKEN": "synthetic-receiver-sentinel"
            },
        )
        execute("real-provider", "plan")
        execute("vendored-tofu-provider", "plan", source_override=vendor_snapshot)
        execute("tool-version", None, command_id="tool_version")
        execute("environment", "environment")
        execute("watchdog-defenses", "watchdog")
        execute("cancel-at-finalization", "success", cancel_during_cleanup=True)
        execute("cpu-cap", "cpu")
        execute("memory-cap", "memory", profile_changes={"memory_bytes": 67108864})
        execute("pid-cap", "pids", profile_changes={"pids_limit": 16})
        execute("disk-cap", "disk", profile_changes={"work_bytes": 8388608})
        execute("output-cap", "output", profile_changes={"output_bytes": 4096})
        execute("partial-evidence", "partial")
        execute("cancel-descendants", "descendants", cancel=True)
        execute("lease-descendants", "descendants", lease_loss=True)
        execute(
            "timeout-descendants", "descendants", profile_changes={"timeout_seconds": 3}
        )
        death = (
            controller_death(
                root,
                docker,
                docker_host,
                image["Id"],
                registration_path,
                catalog,
                catalog_digest,
            )
            if args.case is None or args.case == "operator-death"
            else {"qualified": False, "not_run": True}
        )
        loaded_death = (
            controller_death(
                root,
                docker,
                docker_host,
                image["Id"],
                registration_path,
                catalog,
                catalog_digest,
                mode="watchdog_load",
            )
            if args.case is None or args.case == "operator-death-load"
            else {"qualified": False, "not_run": True}
        )
        delayed_death = (
            controller_death(
                root,
                docker,
                docker_host,
                image["Id"],
                registration_path,
                catalog,
                catalog_digest,
                create_delay_seconds=3,
                lease_seconds=60,
            )
            if args.case is None or args.case == "operator-death-delayed"
            else {"qualified": False, "not_run": True}
        )
        snapshot.verify()
        snapshot.close()
        clean.close()
        vendor_snapshot.close()
        source_cleanup_complete = (
            not snapshot.path.exists()
            and not clean.path.exists()
            and not vendor_snapshot.path.exists()
        )
        journal_summary = []
        journal_bytes = b""
        if (journal / "executions.sqlite3").exists():
            with closing(sqlite3.connect(journal / "executions.sqlite3")) as db:
                journal_summary = [
                    dict(
                        state=row[0],
                        cancel_requested=bool(row[1]),
                        cleanup_complete=bool(row[2]),
                        count=row[3],
                    )
                    for row in db.execute(
                        "SELECT state,cancel_requested,cleanup_complete,count(*) FROM executions GROUP BY state,cancel_requested,cleanup_complete"
                    )
                ]
            journal_bytes = (journal / "executions.sqlite3").read_bytes()
        journal_secret_free = all(
            value not in journal_bytes
            for value in (
                b"synthetic-collector-sentinel",
                b"synthetic-host-sentinel",
                b"synthetic-receiver-sentinel",
            )
        )
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "image_id": image["Id"],
            "image_architecture": image["Architecture"],
            "image_source_pin_checks": image_source_checks,
            "image_python_version": next(
                entry.partition("=")[2]
                for entry in image["Config"]["Env"]
                if entry.startswith("PYTHON_VERSION=")
            ),
            "operator_python_version": sys.version.split()[0],
            "docker_version": json.loads(
                command([docker, "version", "--format", "{{json .Server}}"])
            ),
            "source_commit": commit,
            "source_files": files,
            "catalog": document.model_dump(mode="json"),
            "catalog_digest": catalog_digest,
            "source_hashes": before_hashes,
            "source_hashes_unchanged": before_hashes
            == {name: digest((ROOT / name).read_bytes()) for name in before_hashes},
            "cases": results,
            "admission": admission,
            "source_case_inputs": source_case_inputs,
            "advertised_commands": list(
                get_args(CommandRequest.model_fields["command"].annotation)
            ),
            "r4_ambiguous_creation": {
                "evidence_level": "controlled transport/fault-double regression tests",
                "real_late_daemon_commit_reproduced": False,
                "qualification_claim": "No live Docker late-commit timing qualification is claimed.",
            },
            "source_cleanup_complete": source_cleanup_complete,
            "operator_death": death,
            "operator_death_under_load": loaded_death,
            "operator_death_delayed_setup": delayed_death,
            "journal_summary": journal_summary,
            "journal_secret_free": journal_secret_free,
            "qualified": False,
            "limitations": [
                "Only declared Linux ARM64 Docker daemon profile; Darwin host is an operator control host, not a sandbox.",
                "No production collector/provider credentials or custody admission; Story16.14 owns integration.",
                "No internet or additional local network allowed; only offline profile exercised.",
            ],
        }
        report["checks"] = assess(results, admission, report["source_hashes_unchanged"])
        report["checks"]["operator_death_watchdog_and_recovery"] = death["qualified"]
        report["checks"]["operator_death_under_cpu_load"] = loaded_death["qualified"]
        report["checks"]["delayed_setup_original_deadline"] = delayed_death["qualified"]
        report["checks"]["catalog_all_advertised_commands_executed"] = set(
            report["advertised_commands"]
        ) <= {
            item.get("command")
            for item in results
            if item["result"]["state"] == "succeeded"
        }
        report["checks"]["image_source_pins"] = all(image_source_checks.values())
        report["checks"]["source_cleanup"] = source_cleanup_complete
        report["checks"]["journal_secret_free"] = journal_secret_free
        report["qualified"] = all(report["checks"].values())
        report["failed_checks"] = [
            name for name, passed in report["checks"].items() if not passed
        ]
        (output / "results.json").write_text(
            json.dumps(report, indent=2, default=str) + "\n"
        )
        print(
            json.dumps(
                {
                    "image_id": image["Id"],
                    "cases": len(results),
                    "qualified": report["qualified"],
                    "failed_checks": report["failed_checks"],
                    "source_hashes_unchanged": report["source_hashes_unchanged"],
                }
            )
        )
    return 0 if report["qualified"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--orphan-controller", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--case", help="Run one named fixed corpus case for diagnosis.")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/verification/infra-automation/16-13"
    )
    arguments = parser.parse_args()
    if arguments.orphan_controller:
        try:
            status = orphan_controller(arguments.orphan_controller)
        except Exception as error:
            import traceback

            facts = {
                "exception_type": type(error).__name__,
                "frames": [
                    f"{Path(frame.filename).name}:{frame.lineno}"
                    for frame in traceback.extract_tb(error.__traceback__)
                ],
            }
            (arguments.orphan_controller.parent / "controller-error.json").write_bytes(
                canonical(facts)
            )
            status = 1
    else:
        status = run(arguments)
    raise SystemExit(status)
