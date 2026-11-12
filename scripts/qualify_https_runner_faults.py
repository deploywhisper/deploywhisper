"""Actual TLS runner fault drills with real isolated collector processes."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def qualification_summary(case, origin, records, statuses):
    full_corpus = case is None and {item["case"] for item in records} == {
        "wire-lease-expiry",
        "running-revocation",
        "log-cap",
    }
    return {
        "qualified": full_corpus,
        "full_corpus": full_corpus,
        "origin": origin,
        "cases": records,
        "transport_observations": statuses,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--ca", type=Path, required=True)
    parser.add_argument("--catalog-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--case", choices=("wire-lease-expiry", "running-revocation", "log-cap")
    )
    args = parser.parse_args()
    from scripts.runner_ui_fixture import read_private
    from scripts import qualify_runner_isolation as isolation
    from infra_automation.receiver_custody import ProtectedCustody, canonical
    from infra_automation.runner.catalog import CatalogDocument
    from infra_automation.runner.client import (
        RunnerClient,
        RunnerClientError,
        TaskAssignment,
        _transport,
    )
    from infra_automation.runner.collection_client import CollectionHandler
    from infra_automation.runner.execution import ExecutionRunner, CollectorCredentials
    from infra_automation.runner.execution_profile import (
        ExecutionProfile,
        IsolationError,
    )
    from infra_automation.runner.protocol import parse_message
    from infra_automation.runner.sandbox import DockerSandbox
    from infra_automation.runner.source import (
        SourceRegistration,
        load_registration,
        materialize_source,
    )

    fixture = read_private(args.fixture)
    origin = fixture["origin"]
    if origin != "https://localhost:18443":
        raise ValueError("Exact owned TLS fault origin required")
    os.environ["SSL_CERT_FILE"] = str(args.ca.resolve())
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        urllib.request.HTTPSHandler(
            context=ssl.create_default_context(cafile=str(args.ca))
        ),
    )
    csrf = None
    statuses = []

    def api(path, payload=None):
        headers = {"Origin": origin, "Content-Type": "application/json"}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        request = urllib.request.Request(
            origin + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers=headers,
        )
        with opener.open(request, timeout=20) as response:
            return json.load(response)["data"]

    def transport(method, url, headers, body, timeout):
        status, raw = _transport(method, url, headers, body, timeout)
        statuses.append(
            {
                "method": method,
                "path": url.removeprefix(origin),
                "status": status,
                "monotonic": time.monotonic(),
            }
        )
        return status, raw

    login = api(
        "/api/v1/auth/login",
        {"username": fixture["username"], "password": fixture["password"]},
    )
    csrf = login["csrf_token"]
    catalog_record = json.loads(args.catalog_record.read_text())
    if catalog_record.get("qualified") is not True:
        raise ValueError("Executed qualified collector catalog required")
    document = CatalogDocument.model_validate(catalog_record["catalog"])
    profile = ExecutionProfile(
        image_id=document.image_id,
        memory_bytes=536870912,
        output_bytes=131072,
        credential_names=("COLLECTOR_TOKEN",),
    )
    docker = shutil.which("docker")
    context = json.loads(
        subprocess.check_output([docker, "context", "inspect"], text=True)
    )[0]
    docker_host = context["Endpoints"]["docker"]["Host"]
    records = []
    args.output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="dw1619-runner-faults-") as temporary:
        root = Path(temporary).resolve()
        root.chmod(0o700)
        catalog = root / "catalog.json"
        catalog.write_bytes(canonical(document.model_dump(mode="json")))
        catalog.chmod(0o600)
        cases = (
            (args.case,)
            if args.case
            else ("wire-lease-expiry", "running-revocation", "log-cap")
        )
        for case in cases:
            print("Executing fault case: " + case, flush=True)
            case_root = root / case
            case_root.mkdir(mode=0o700)
            count = 128 if case == "running-revocation" else 1
            contents = {
                "main.tf": (
                    'resource "terraform_data" "example" {\n count = '
                    + str(count)
                    + '\n input = "synthetic-safe-value"\n}\n'
                ).encode(),
                ".terraform.lock.hcl": b"# Builtin-only qualification.\n",
                "source.lock": b"builtin-opentofu-1.13.1\n",
            }
            repository, commit, files = isolation.make_repository(case_root, contents)
            registration = SourceRegistration(
                repository_path=str(repository),
                commit=commit,
                tree_digest=isolation.digest(canonical(files)),
                lock_digests={
                    name: files[name] for name in (".terraform.lock.hcl", "source.lock")
                },
                trust="protected_revision",
            )
            registered = case_root / "source-registration.json"
            registered.write_bytes(canonical(registration.model_dump(mode="json")))
            registered.chmod(0o600)
            staging = case_root / "snapshots"
            staging.mkdir(mode=0o700)
            sandbox = DockerSandbox(docker, docker_host, profile)
            created = []
            original_create = sandbox.create

            def observe_create(*values, **kwargs):
                result = original_create(*values, **kwargs)
                created.append(kwargs["name"])
                return result

            sandbox.create = observe_create
            runner = ExecutionRunner(
                sandbox,
                catalog,
                isolation.digest(catalog.read_bytes()),
                case_root / "journal",
            )
            p, w = fixture["project_id"], fixture["workspace_id"]
            definition = {
                "workflow_version": 2,
                "project_id": str(p),
                "workspace_id": str(w),
                "environment": "test",
                "inputs": {},
                "steps": [
                    {
                        "id": "collect",
                        "kind": "admitted_collection",
                        "depends_on": [],
                        "source": {
                            "kind": "collected",
                            "repository_id": "qualification-source",
                            "commit_sha": commit,
                            "profile_digest": runner.profile_digest,
                        },
                    },
                    {
                        "id": "analysis",
                        "kind": "shared_analysis",
                        "depends_on": ["collect"],
                        "artifact": {
                            "ref": "step",
                            "step_id": "collect",
                            "output": "screened_artifacts",
                        },
                    },
                ],
            }
            workflow = api(
                "/api/v1/infra-automation/workflows",
                {
                    "project_id": p,
                    "workspace_id": w,
                    "name": "Real fault " + case,
                    "definition": json.dumps(definition),
                    "reason": "Isolated TLS runner fault qualification",
                },
            )
            revision = api(
                "/api/v1/infra-automation/workflows/" + workflow["id"] + "/revisions",
                {
                    "expected_version": workflow["draft_version"],
                    "idempotency_key": "publish-" + case,
                    "reason": "Publish bounded fault case",
                },
            )
            issued = api(
                "/api/v1/infra-automation/runners/enrollments",
                {
                    "project_id": p,
                    "workspace_id": w,
                    "tags": ["linux"],
                    "tool": "opentofu",
                    "profile_digest": runner.profile_digest,
                    "runner_version": "1.0",
                    "reason": "Enroll isolated fault runner",
                },
            )
            bootstrap = RunnerClient(
                origin,
                issued["enrollment"]["runner_id"],
                issued["token"],
                transport=transport,
            )
            redeemed = bootstrap.redeem(issued["enrollment"])
            client = RunnerClient(
                origin, redeemed["runner_id"], redeemed["token"], transport=transport
            )
            require(
                client.poll(max_polls=1) is None,
                "Runner received an assignment before admission",
            )
            run = api(
                "/api/v1/infra-automation/runs",
                {
                    "workflow_id": workflow["id"],
                    "revision_id": revision["id"],
                    "workspace_id": w,
                    "inputs": {},
                    "idempotency_key": "run-" + case,
                    "total_timeout_seconds": 300,
                    "reason": "Execute bounded runner fault",
                },
            )
            assignment = client.poll(max_polls=20)
            if assignment is None:
                raise RuntimeError("Actual assignment missing")
            claim = client.send(assignment.message, assignment.task_token)
            message = parse_message(
                assignment.message.model_dump(mode="json")
                | {
                    "scope": claim["scope"],
                    "operation": "heartbeat",
                    "sequence": claim["sequence"] + 1,
                }
            )
            assignment = TaskAssignment(message, assignment.task_token)
            result = None
            facts = {
                "case": case,
                "run_id": run["id"],
                "project_id": p,
                "workspace_id": w,
                "attempt_id": message.scope.attempt_id
                if hasattr(message.scope, "attempt_id")
                else None,
                "runner_id": client.runner_id,
                "source_commit": commit,
                "published_wire_deadline": message.scope.lease_deadline,
            }
            with materialize_source(
                load_registration(
                    registered, isolation.digest(registered.read_bytes())
                ),
                staging,
            ) as snapshot:
                if case == "wire-lease-expiry":
                    expires = datetime.fromisoformat(
                        message.scope.lease_deadline.replace("Z", "+00:00")
                    )
                    cutoff = time.monotonic() + 40
                    expires += timedelta(seconds=1.1)
                    while datetime.now(timezone.utc) <= expires:
                        if time.monotonic() >= cutoff:
                            raise RuntimeError("Wire expiry wait exceeded its bound")
                        time.sleep(
                            min(
                                0.2,
                                max(
                                    0.01,
                                    (
                                        expires - datetime.now(timezone.utc)
                                    ).total_seconds(),
                                ),
                            )
                        )

                    def expired_callback(*_args, **_kwargs):
                        raise AssertionError(
                            "Expired scope reached an execution callback"
                        )

                    try:
                        runner.execute(
                            message.scope,
                            "collect_plan",
                            {"tool": "opentofu"},
                            snapshot,
                            expected_profile_digest=runner.profile_digest,
                            credential_resolver=expired_callback,
                            authority_check=expired_callback,
                            custody_finalizer=expired_callback,
                        )
                    except IsolationError:
                        facts["runner_result"] = {
                            "state": "expired_wire_admission_denied",
                            "finalizable": False,
                            "cleanup_complete": True,
                        }
                    else:
                        raise AssertionError("Expired scope started local execution")
                    require(
                        not created, "Expired task unexpectedly created a container"
                    )
                    try:
                        client.send(message, assignment.task_token)
                    except RunnerClientError:
                        facts["late_heartbeat_status"] = statuses[-1]["status"]
                    else:
                        raise AssertionError("Expired wire lease accepted")
                    require(
                        facts["late_heartbeat_status"] in (401, 409),
                        "Late heartbeat did not fail closed",
                    )
                else:
                    if case == "log-cap":
                        oversized = parse_message(
                            message.model_dump(mode="json")
                            | {"operation": "log", "log": "x" * 129}
                        )
                        try:
                            client.send(oversized, assignment.task_token)
                        except RunnerClientError:
                            require(
                                statuses[-1]["status"] == 429,
                                "Oversized log chunk did not return 429",
                            )
                        else:
                            raise AssertionError("Oversized log chunk admitted")
                        facts["oversized_chunk_status"] = 429
                        facts["oversized_chunk_bytes"] = 129
                        chunks = 0
                        while chunks < 100:
                            if chunks and chunks % 10 == 0:
                                beat = client.send(message, assignment.task_token)
                                message = parse_message(
                                    message.model_dump(mode="json")
                                    | {
                                        "scope": beat["scope"],
                                        "sequence": beat["sequence"] + 1,
                                    }
                                )
                            log_message = parse_message(
                                message.model_dump(mode="json")
                                | {
                                    "operation": "log",
                                    "log": (
                                        "safe synthetic diagnostic " + str(chunks) + " "
                                    )
                                    + "." * 70,
                                }
                            )
                            try:
                                receipt = client.send(
                                    log_message, assignment.task_token
                                )
                            except RunnerClientError:
                                require(
                                    statuses[-1]["status"] == 429,
                                    "Log-cap transport did not return 429",
                                )
                                break
                            chunks += 1
                            message = parse_message(
                                message.model_dump(mode="json")
                                | {
                                    "scope": receipt["scope"],
                                    "sequence": receipt["sequence"] + 1,
                                }
                            )
                        require(
                            25 < chunks < 100,
                            "Log-cap fixture did not exercise the bounded chunk range",
                        )
                        assignment = TaskAssignment(message, assignment.task_token)
                        facts.update(
                            accepted_log_chunks=chunks,
                            quota_status=429,
                            configured_attempt_log_bytes=8192,
                            configured_chunk_bytes=128,
                        )
                    custody = ProtectedCustody(case_root / "custody")
                    executed = []

                    class ObservedRunner:
                        profile_digest = runner.profile_digest

                        def execute(self, *values, **kwargs):
                            value = runner.execute(*values, **kwargs)
                            executed.append(value)
                            return value

                    revoked = threading.Event()
                    stop = threading.Event()

                    def observe_and_revoke():
                        until = time.monotonic() + 15
                        while not stop.is_set() and time.monotonic() < until:
                            for name in created:
                                completed = subprocess.run(
                                    [docker, "top", name, "-eo", "pid,ppid,comm"],
                                    capture_output=True,
                                    text=True,
                                )
                                rows = [
                                    line.split()
                                    for line in completed.stdout.splitlines()[1:]
                                ]
                                if any(row[-1] == "tofu" for row in rows if row):
                                    facts["observed_tool_processes"] = [
                                        row for row in rows if row and row[-1] == "tofu"
                                    ]
                                    api(
                                        "/api/v1/infra-automation/runners/"
                                        + client.runner_id
                                        + "/revoke",
                                        {
                                            "reason": "Revoke while actual isolated tool runs"
                                        },
                                    )
                                    facts["revoked_after_tool_started"] = True
                                    revoked.set()
                                    return
                            time.sleep(0.02)

                    monitor = (
                        threading.Thread(target=observe_and_revoke, daemon=True)
                        if case == "running-revocation"
                        else None
                    )
                    if monitor:
                        monitor.start()
                    handler = CollectionHandler(
                        scope=assignment.message.scope,
                        repository_id="qualification-source",
                        snapshot=snapshot,
                        runner=ObservedRunner(),
                        custody=custody,
                        tool="opentofu",
                        credential_resolver=lambda: CollectorCredentials(
                            "qualification-collector",
                            {"COLLECTOR_TOKEN": "synthetic-collector-sentinel"},
                        ),
                        evidence_ttl_seconds=600,
                        execution_timeout_seconds=60,
                    )
                    try:
                        handler(client, assignment)
                    except RunnerClientError:
                        if case != "running-revocation":
                            raise
                    finally:
                        stop.set()
                        if monitor:
                            monitor.join(timeout=20)
                    require(
                        len(executed) == 1,
                        "Fault fixture did not execute exactly once",
                    )
                    result = executed[0]
                    if case == "running-revocation":
                        require(
                            revoked.is_set()
                            and result.state == "authority_unavailable"
                            and not result.finalizable
                            and result.output == ""
                            and result.output_digest is None
                            and result.collection is None
                            and result.cleanup_complete,
                            "Running revocation did not fail closed after cleanup",
                        )
                    else:
                        if not result.finalizable or not result.cleanup_complete:
                            (args.output / "driver-failure.json").write_text(
                                json.dumps(
                                    {
                                        "case": case,
                                        "state": result.state,
                                        "cleanup_complete": result.cleanup_complete,
                                        "exit_code": result.exit_code,
                                        "statuses": statuses[-8:],
                                    },
                                    indent=2,
                                )
                                + "\n"
                            )
                        require(
                            result.finalizable and result.cleanup_complete,
                            "Log-cap execution did not finalize cleanly",
                        )
                if result is not None:
                    facts["runner_result"] = {
                        k: v
                        for k, v in asdict(result).items()
                        if k not in ("output", "collection")
                    }
                    facts["runner_result"]["finalizable"] = result.finalizable
                facts["containers_created"] = created
                facts["containers_removed"] = all(
                    subprocess.run(
                        [docker, "inspect", name], capture_output=True
                    ).returncode
                    != 0
                    for name in created
                )
                require(
                    facts["containers_removed"],
                    "Fault case left an owned container behind",
                )
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                current = api("/api/v1/infra-automation/runs/" + run["id"])
                if current["state"] in (
                    "failed",
                    "succeeded",
                    "cancelled",
                    "timed_out",
                ):
                    break
                time.sleep(0.25)
            facts["run_state"] = current["state"]
            steps = api("/api/v1/infra-automation/runs/" + run["id"] + "/steps")[
                "items"
            ]
            attempt = next(s for s in steps if s["step_id"] == "collect")
            facts["attempt_id"] = attempt["id"]
            logs = api(
                "/api/v1/infra-automation/runs/"
                + run["id"]
                + "/logs?attempt_id="
                + attempt["id"]
            )
            facts["log_page"] = {
                "items": len(logs["items"]),
                "cursor": {
                    k: v
                    for k, v in logs["cursor"].items()
                    if k not in ("snapshot_id", "next_cursor")
                },
            }
            links = api("/api/v1/infra-automation/runs/" + run["id"] + "/reports")[
                "items"
            ]
            facts["report_count"] = len(links)
            facts["custody_published"] = any(
                (case_root / "custody").rglob("metadata.json")
            )
            if case == "log-cap":
                retained = list(logs["items"])
                cursor = logs["cursor"]["next_cursor"]
                while cursor is not None:
                    page = api(
                        "/api/v1/infra-automation/runs/"
                        + run["id"]
                        + "/logs?attempt_id="
                        + attempt["id"]
                        + "&cursor="
                        + cursor
                    )
                    retained.extend(page["items"])
                    cursor = page["cursor"]["next_cursor"]
                retained.sort(key=lambda item: item["sequence"])
                facts["retained_log_bytes"] = len(canonical(retained))
                facts["retained_log_chunks"] = len(retained)
                require(
                    len(retained) == facts["accepted_log_chunks"]
                    and facts["retained_log_bytes"] <= 8192,
                    "Retained logs exceeded the accepted bounded result",
                )
                rejected = {
                    "sequence": len(retained) + 1,
                    "text": "safe synthetic diagnostic "
                    + str(len(retained))
                    + " "
                    + "." * 70,
                }
                require(
                    len(canonical(retained + [rejected])) > 8192,
                    "Rejected log chunk did not cross the configured cap",
                )
                require(
                    facts["custody_published"],
                    "Successful log-cap case did not publish custody",
                )
                require(
                    current["state"] == "succeeded"
                    and len(links) == 1
                    and logs["cursor"]["truncated"]
                    and not logs["cursor"]["gap"],
                    "Log-cap result did not retain one complete truncated history",
                )
            else:
                require(
                    current["state"] == "failed"
                    and not links
                    and not facts["custody_published"],
                    "Denied fault case advanced report or custody state",
                )
            if case != "running-revocation":
                api(
                    "/api/v1/infra-automation/runners/" + client.runner_id + "/revoke",
                    {"reason": "Close completed synthetic fault case"},
                )
            records.append(facts)
            (args.output / "runner-faults.json").write_text(
                json.dumps(
                    {"qualified": False, "origin": origin, "cases": records}, indent=2
                )
                + "\n"
            )
    summary = qualification_summary(args.case, origin, records, statuses)
    (args.output / "runner-faults.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(
        "Actual TLS runner faults passed"
        if summary["qualified"]
        else "Partial TLS runner fault case passed; full corpus unqualified",
        flush=True,
    )


if __name__ == "__main__":
    main()
