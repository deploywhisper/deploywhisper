"""Measure real runner service claims using twenty synthetic client processes.

This diagnostic never certifies the PRD reference host or HTTPS latency. Results
explicitly fail reference qualification while preserving measured service samples.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import platform
import sqlite3
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def utc_now():
    return datetime.now(timezone.utc)


def client(connection):
    """Separate compatible runner process parses each assigned frozen envelope."""
    from infra_automation.runner.protocol import RunnerMessage

    connection.send({"pid": os.getpid(), "ready": True})
    while True:
        assignment = connection.recv()
        if assignment is None:
            break
        try:
            message = RunnerMessage(
                operation="claim",
                scope=assignment["scope"],
                profile_digest=assignment["profile_digest"],
                capabilities=assignment["capabilities"],
                sequence=1,
            )
            connection.send(message.model_dump())
        except Exception:
            connection.send(None)
    connection.close()


def percentile(values, percent):
    return (
        sorted(values)[max(0, math.ceil(len(values) * percent / 100) - 1)]
        if values
        else None
    )


def source_hashes():
    paths = [
        "scripts/benchmark_runner_protocol.py",
        "infra_automation/runner/claims.py",
        "infra_automation/runner/protocol.py",
        "services/infra_automation_runners.py",
        "services/infra_automation_runner_tasks.py",
        "infra_automation/claims.py",
        "models/tables.py",
    ]
    return {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths
    }


def environment_limits():
    values = {}
    for name in ("cpu.max", "memory.max"):
        path = Path("/sys/fs/cgroup") / name
        values[name] = path.read_text().strip() if path.is_file() else None
    return values


def reference_failures(report):
    reasons = []
    limits = report["cgroup_limits"]
    if platform.system() != "Linux":
        reasons.append("Reference qualification requires Linux.")
    if limits.get("cpu.max") != "400000 100000":
        reasons.append("Reference qualification requires a four-CPU cgroup quota.")
    if limits.get("memory.max") != str(8 * 1024**3):
        reasons.append("Reference qualification requires an eight-GiB memory ceiling.")
    if (report["requested_warmups"], report["requested_samples"]) != (100, 1000):
        reasons.append("Qualification requires exactly 100 warmups and 1000 samples.")
    if report["runner_processes"] != 20:
        reasons.append("Qualification requires twenty runner processes.")
    if report["measured_samples"] != report["requested_samples"]:
        reasons.append("The complete measured sample set is required.")
    if report["failures"] or report["harness_failure"]:
        reasons.append("Runner claim failures are not permitted.")
    if report["p95_ms"] is None or report["p95_ms"] >= 2000:
        reasons.append("The p95 enqueue-to-claim latency must be below 2000 ms.")
    if not report["source_hashes_unchanged"]:
        reasons.append("Benchmark source changed during measurement.")
    return reasons


def run(warmup, samples, output):
    from importlib import import_module
    from infra_automation import claims as engine
    from infra_automation.contracts import ProfileContract, RegistryContract
    from infra_automation.runner.claims import RunnerRequirements
    from infra_automation.runner.protocol import RunnerMessage
    from infra_automation.state import AuditActor
    from models.repositories import infra_automation_runs as repo
    from services import infra_automation_engine_support as engine_support
    from services import infra_automation_runner_tasks as tasks
    from services import infra_automation_runners as runners
    from services import infra_automation_support as support
    from services import project_service as auth
    from tests.test_infra_automation.test_workflow_snapshots import (
        WorkflowSnapshotTests,
    )

    profile = "sha256:" + "a" * 64
    definition = {
        "workflow_version": 2,
        "project_id": "100",
        "workspace_id": "100",
        "environment": "dev",
        "inputs": {},
        "steps": [
            {
                "id": f"collect{i}",
                "kind": "admitted_collection",
                "depends_on": [],
                "source": {
                    "kind": "collected",
                    "repository_id": "synthetic-repository",
                    "commit_sha": "b" * 40,
                    "profile_digest": profile,
                },
            }
            for i in range(50)
        ],
    }
    context = multiprocessing.get_context("spawn")
    clients = []
    processes = []
    pids = []
    case = WorkflowSnapshotTests(methodName="runTest")
    source_before = source_hashes()
    started = utc_now()
    records = []
    failure = None
    settings_patch = None
    try:
        case.setUp()
        case.enable()
        import config

        profile_manifest = support.canonical(
            [
                {
                    "profile_digest": profile,
                    "tool": "opentofu",
                    "tool_version": "1.13.1",
                    "runner_version": "1.0",
                    "tags": ["isolated", *[f"slot{i}" for i in range(20)]],
                }
            ]
        )
        profile_path = Path(case.temp.name) / "benchmark-profiles.json"
        profile_path.write_bytes(profile_manifest)
        profile_path.chmod(0o600)
        settings_patch = patch.object(
            config,
            "settings",
            replace(
                config.settings,
                collection_profiles_path=str(profile_path),
                collection_profiles_sha256=support.digest(profile_manifest),
            ),
        )
        settings_patch.start()
        with case.engine.begin() as db:
            for name, body in import_module(
                "migrations.versions.032_add_infra_automation_engine"
            ).GUARDS.items():
                db.exec_driver_sql(f"CREATE TRIGGER {name} {body}")
        registry = RegistryContract(
            profiles=(
                ProfileContract(
                    digest=profile, tool="opentofu", authorization_kinds=("exact_plan",)
                ),
            )
        )
        snapshot = case.export(
            case.publish_fixture(definition), inputs={}, registry_contract=registry
        )
        credentials = []
        for i in range(20):
            with case.credentials():
                issued = runners.create_enrollment(
                    runners.EnrollmentRequest(
                        project_id=100,
                        workspace_id=100,
                        tags=["isolated", f"slot{i}"],
                        tool="opentofu",
                        profile_digest=profile,
                        runner_version="1.0",
                        reason="Synthetic benchmark enrollment.",
                    ),
                    now=utc_now(),
                )
            credential = runners.redeem(
                issued.enrollment.enrollment_id,
                issued.token.get_secret_value(),
                now=utc_now(),
            )
            credentials.append(
                runners.RunnerCredential(
                    credential.runner_id, credential.token.get_secret_value()
                )
            )
            parent, child = context.Pipe()
            process = context.Process(target=client, args=(child,))
            process.start()
            child.close()
            if not parent.poll(30):
                raise RuntimeError("Runner startup timeout.")
            pids.append(parent.recv()["pid"])
            clients.append(parent)
            processes.append(process)
        with case.credentials(), auth.authorized_session() as db:
            engine_support.ensure_engine_actor(
                db, support.scope(db, 100, 100, "automation.request", mutation=True)
            )
            owner = engine.acquire_coordinator(
                db, project_id=100, workspace_id=100, now=utc_now()
            )
        actor = AuditActor("human-a", "human", "admin")
        runs = []
        for i in range(warmup + samples):
            case.now = utc_now()
            if i % 500 == 0:
                runs = []
                for j in range(10):
                    now = utc_now()
                    with auth.authorized_session() as db:
                        row = repo.create_run(
                            db,
                            snapshot=snapshot,
                            request_digest=support.digest(f"request-{i}-{j}".encode()),
                            key_digest=support.digest(f"key-{i}-{j}".encode()),
                            requested_by="human-a",
                            deadline_at=now + timedelta(minutes=10),
                            audit_actor=actor,
                            reason="Synthetic benchmark run.",
                            now=now,
                        )
                        engine.start_run(
                            db,
                            owner,
                            run_id=row.id,
                            expected_version=row.version,
                            now=now,
                        )
                        runs.append(row.id)
            index = i % 20
            now = utc_now()
            tasks.poll(credentials[index], now=now)
            with auth.authorized_session() as db:
                engine.renew_coordinator(
                    db, owner, project_id=100, workspace_id=100, now=now
                )
                attempt = engine.prepare_attempt(
                    db,
                    owner,
                    run_id=runs[(i % 500) % 10],
                    step_id=f"collect{(i % 500) // 10}",
                    handler_id="synthetic-collection",
                    handler_version="1",
                    retry_safe=True,
                    now=now,
                )
            enqueued = utc_now()
            start = time.perf_counter_ns()
            row = {
                "index": i,
                "warmup": i < warmup,
                "runner_pid": pids[index],
                "enqueued_at": enqueued.isoformat(),
                "stage": "queue",
            }
            try:
                requirement = RunnerRequirements(
                    tags=["isolated", f"slot{index}"],
                    tool="opentofu",
                    profile_digest=profile,
                    runner_version="1.0",
                )
                tasks.queue_assignment(owner, attempt.id, requirement, now=utc_now())
                row["stage"] = "poll"
                assignment = tasks.poll(credentials[index], now=utc_now())
                if assignment is None:
                    raise RuntimeError("Assignment unavailable.")
                clients[index].send(assignment)
                if not clients[index].poll(10):
                    raise RuntimeError("Runner response timeout.")
                message = RunnerMessage.model_validate(clients[index].recv())
                row["stage"] = "claim"
                result = tasks.operate(
                    message, credentials[index], assignment["task_token"], now=utc_now()
                )
                row.update(
                    claimed_at=utc_now().isoformat(),
                    elapsed_ms=(time.perf_counter_ns() - start) / 1_000_000,
                    state=result["state"],
                    success=result["state"] == "running",
                )
                # Use the production collected-output envelope. The bytes remain
                # synthetic and establish no real collector or custody trust.
                from infra_automation.runner.collector import command_digests

                text = '{"format_version":"1.2","terraform_version":"1.13.1","resource_changes":[]}'
                command_digest, argv_digest = command_digests("opentofu")
                source_deadline = (now + timedelta(minutes=5)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                raw_local_digest = support.digest(b"synthetic protected plan")
                raw = support.canonical(
                    {
                        "version": 1,
                        "artifacts": [{"name": "plan.json", "content": text}],
                        "provenance": {
                            "version": 1,
                            "kind": "collected",
                            "scope": result["scope"],
                            "repository_id": "synthetic-repository",
                            "commit_sha": "b" * 40,
                            "profile_digest": profile,
                            "tool": "opentofu",
                            "tool_version": "1.13.1",
                            "command_digest": command_digest,
                            "argv_digest": argv_digest,
                            "raw_local_digest": raw_local_digest,
                            "sanitized_digest": support.digest(
                                support.canonical([["plan.json", text]])
                            ),
                            "redaction_version": 1,
                            "exit_code": 0,
                            "collected_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "source_deadline": source_deadline,
                            "custody": {
                                "version": 1,
                                "handle": f"synthetic-{attempt.id}",
                                "raw_local_digest": raw_local_digest,
                                "expires_at": source_deadline,
                            },
                        },
                    }
                )
                upload = RunnerMessage(
                    operation="upload",
                    scope=result["scope"],
                    capabilities=["screened-collection-v1"],
                    profile_digest=profile,
                    sequence=2,
                    upload_digest=support.digest(raw),
                    atomic_upload_id=attempt.id,
                )
                row["stage"] = "upload"
                uploaded = tasks.operate(
                    upload,
                    credentials[index],
                    assignment["task_token"],
                    upload_bytes=raw,
                    now=utc_now(),
                )
                complete = RunnerMessage(
                    operation="complete",
                    scope=uploaded["scope"],
                    capabilities=["screened-collection-v1"],
                    profile_digest=profile,
                    sequence=3,
                    state="succeeded",
                    atomic_upload_id=attempt.id,
                )
                row["stage"] = "complete"
                tasks.operate(
                    complete,
                    credentials[index],
                    assignment["task_token"],
                    now=utc_now(),
                )
                if (i % 500) // 10 == 49:
                    row["stage"] = "finish-run"
                    with auth.authorized_session() as db:
                        current = repo.get_run(db, runs[(i % 500) % 10])
                        repo.transition_run(
                            db,
                            run_id=current.id,
                            expected_version=current.version,
                            state="succeeded",
                            audit_actor=actor,
                            reason="Synthetic benchmark complete.",
                            now=utc_now(),
                        )
            except Exception as exc:
                row.update(
                    success=False,
                    failure_type=type(exc).__name__,
                    failure_code=getattr(exc, "status_code", None),
                )
            records.append(row)
            if not row["success"]:
                break
    except Exception as exc:
        failure = type(exc).__name__
    finally:
        for connection in clients:
            try:
                connection.send(None)
            except (BrokenPipeError, EOFError, OSError):
                pass
        for process in processes:
            process.join(5)
            if process.is_alive():
                process.terminate()
                process.join(5)
        if settings_patch is not None:
            settings_patch.stop()
        case.doCleanups()
    measured = [row for row in records if not row["warmup"]]
    latencies = [row["elapsed_ms"] for row in measured if row["success"]]
    report = {
        "started_at": started.isoformat(),
        "finished_at": utc_now().isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "cpu_count": os.cpu_count(),
        "runner_processes": len(pids),
        "runner_pids": pids,
        "dataset_digest": hashlib.sha256(
            json.dumps(definition, sort_keys=True).encode()
        ).hexdigest(),
        "requested_warmups": warmup,
        "requested_samples": samples,
        "measured_samples": len(measured),
        "failures": sum(not row["success"] for row in measured),
        "harness_failure": failure,
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "p99_ms": percentile(latencies, 99),
        "source_hashes": source_before,
        "source_hashes_unchanged": source_before == source_hashes(),
        "cgroup_limits": environment_limits(),
        "limitations": [
            "Process IPC represents the runner boundary; the separate Story16.19 actual-TLS qualification proves transport behavior, not these latency samples.",
            "Claims are serially dispatched round-robin to20 processes; no concurrent queue saturation claim.",
            "Synthetic 50-step definitions and durable engine/service paths; no real collection.",
            "Metadata-created fixture plus engine migration guards; no full upgrade qualification.",
            "The separate 30-minute capacity harness owns saturation qualification.",
        ],
        "samples": records,
    }
    report["qualification_failures"] = reference_failures(report)
    report["runner_service_latency_qualified"] = not report["qualification_failures"]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, indent=2))
    return 0 if report["runner_service_latency_qualified"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.warmup <= 1000 or not 1 <= args.samples <= 10000:
        parser.error("Use 0–1000 warmups and 1–10000 samples.")
    raise SystemExit(run(args.warmup, args.samples, args.output))
