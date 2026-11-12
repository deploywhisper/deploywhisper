"""Join the real offline collector corpus to a disposable actual TLS application."""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import http.cookiejar
import json
import os
from pathlib import Path
import ssl
import sys
import time
from types import SimpleNamespace
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def require_terminal_collection(current, links):
    if current["state"] != "succeeded":
        raise RuntimeError("Actual collection run did not reach succeeded")
    if not links:
        raise RuntimeError("Shared analysis report unavailable")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--ca", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from scripts.runner_ui_fixture import read_private

    fixture = read_private(args.fixture)
    origin = fixture["origin"]
    if origin not in {"https://localhost:8443", "https://localhost:18443"}:
        raise ValueError("Exact disposable TLS origin required")
    # Production RunnerClient uses its normal verified TLS transport and this CA.
    os.environ["SSL_CERT_FILE"] = str(args.ca.resolve())
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        urllib.request.HTTPSHandler(
            context=ssl.create_default_context(cafile=str(args.ca))
        ),
    )
    csrf = None
    observed = []

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

    login = api(
        "/api/v1/auth/login",
        {"username": fixture["username"], "password": fixture["password"]},
    )
    csrf = login["csrf_token"]
    from scripts import qualify_collection as corpus
    from tests.test_infra_automation import test_collection_intake as old
    from infra_automation.runner.client import RunnerClient, TaskAssignment
    from infra_automation.runner.protocol import parse_message

    @contextmanager
    def actual_session(*, source_commit, profile_digest, repository_id):
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
                        "repository_id": repository_id,
                        "commit_sha": source_commit,
                        "profile_digest": profile_digest,
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
                "name": "Real TLS collector qualification",
                "definition": json.dumps(definition),
                "reason": "Synthetic real TLS qualification",
            },
        )
        revision = api(
            "/api/v1/infra-automation/workflows/" + workflow["id"] + "/revisions",
            {
                "expected_version": workflow["draft_version"],
                "idempotency_key": "tls-publish-" + workflow["id"],
                "reason": "Publish synthetic collection",
            },
        )
        issued = api(
            "/api/v1/infra-automation/runners/enrollments",
            {
                "project_id": p,
                "workspace_id": w,
                "tags": ["linux"],
                "tool": "opentofu",
                "profile_digest": profile_digest,
                "runner_version": "1.0",
                "reason": "Enroll actual local collector",
            },
        )
        client = RunnerClient(
            origin, issued["enrollment"]["runner_id"], issued["token"]
        )
        redeemed = client.redeem(issued["enrollment"])
        client = RunnerClient(origin, redeemed["runner_id"], redeemed["token"])
        if client.poll(max_polls=1) is not None:
            raise RuntimeError("Unexpected pre-admission assignment")
        run = api(
            "/api/v1/infra-automation/runs",
            {
                "workflow_id": workflow["id"],
                "revision_id": revision["id"],
                "workspace_id": w,
                "inputs": {},
                "idempotency_key": "tls-run-" + workflow["id"],
                "total_timeout_seconds": 600,
                "reason": "Execute synthetic isolated collection",
            },
        )
        task = client.poll(max_polls=20)
        if task is None:
            raise RuntimeError("No actual runner assignment")
        claimed = client.send(task.message, task.task_token)
        assignment = TaskAssignment(
            parse_message(
                task.message.model_dump(mode="json")
                | {
                    "scope": claimed["scope"],
                    "operation": "heartbeat",
                    "sequence": claimed["sequence"] + 1,
                }
            ),
            task.task_token,
        )
        upload = {}
        original = client._request

        def capture(method, suffix, payload=None, *, task_token=None):
            if suffix == "/uploads":
                upload.update(json.loads(base64.b64decode(payload["screened_content"])))
            return original(method, suffix, payload, task_token=task_token)

        client._request = capture

        def finish():
            deadline = time.monotonic() + 90
            links = []
            while time.monotonic() < deadline:
                current = api("/api/v1/infra-automation/runs/" + run["id"])
                value = api("/api/v1/infra-automation/runs/" + run["id"] + "/reports")
                links = value.get("items", []) if isinstance(value, dict) else value
                if current["state"] == "succeeded" and links:
                    break
                if current["state"] in ("failed", "timed_out", "cancelled"):
                    raise RuntimeError("Actual collection run failed")
                time.sleep(0.5)
            require_terminal_collection(current, links)
            report_id = links[0]["report_id"]
            report = api("/api/v1/analyses/" + str(report_id))
            result = {
                "authenticated_intake": True,
                "shared_analysis": True,
                "same_task_provenance": True,
                "report_id": report_id,
                "report_schema_version": report["report_schema_version"],
                "report_digest": corpus.digest(corpus.canonical(report)),
                "advisory": not report.get("should_block", False),
                "provenance": upload["provenance"],
            }
            observed.append(
                {
                    "run_id": run["id"],
                    "report_id": report_id,
                    "project_id": p,
                    "workspace_id": w,
                    "runner_id": client.runner_id,
                    "source_commit": source_commit,
                    "profile_digest": profile_digest,
                    "state": current["state"],
                    "actual_tls": True,
                    "default_runner_transport": True,
                }
            )
            return result

        yield SimpleNamespace(client=client, assignment=assignment, finish=finish)

    with patch.object(old, "real_collection_session", actual_session):
        corpus.run(SimpleNamespace(output=args.output, build=False))
    (args.output / "https-run.json").write_text(
        json.dumps({"origin": origin, "runs": observed}, indent=2) + "\n"
    )
    print("Actual TLS collector integration passed")


if __name__ == "__main__":
    main()
