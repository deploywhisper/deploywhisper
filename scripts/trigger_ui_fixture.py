"""Disposable signed-trigger origin proof with real API and CLI admission.

This harness seeds only synthetic identities in an explicitly opted-in nonroot
container with a tmpfs database. Browser tests create and publish actual workflow
and inventory revisions through authenticated APIs. A structural collection profile admits pending source-pinned requests only;
no runner, authority provider, receiver or live collection proof is installed.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
from http.cookies import SimpleCookie
import secrets
import subprocess
import time
import json
import os
from pathlib import Path
import runpy
import stat
import sys

ORIGIN = "http://localhost:8080"
DATABASE = "sqlite:////app/data/deploywhisper.db"
# Guarded disposable container; both credential files use exclusive mode0600 creation.
SEED_OUTPUT = Path("/tmp/trigger-ui-account-fixture.json")  # nosec B108
BROWSER_OUTPUT = Path("/tmp/trigger-ui-browser-fixture.json")  # nosec B108


def required_environment():
    return {
        "TRIGGER_UI_DISPOSABLE": "1",
        "AUTOMATION_UI_DISPOSABLE": "1",
        "DEPLOYWHISPER_IDENTITY_PROFILE": "local-development",
        "DEPLOYWHISPER_IDENTITY_ORIGIN": ORIGIN,
        "DEPLOYWHISPER_AUTHORIZATION_PROFILE": "verified",
        "DEPLOYWHISPER_IDENTITY_DECISION_MODE": "shared",
        "DATABASE_URL": DATABASE,
        "APP_BASE_URL": ORIGIN,
    }


def guard():
    if (
        not Path("/.dockerenv").is_file()
        or os.geteuid() == 0
        or any(
            os.environ.get(key) != value
            for key, value in required_environment().items()
        )
        or Path.cwd() != Path("/app")
        or Path("/app/data").is_symlink()
    ):
        raise RuntimeError("Requires the exact nonroot disposable HTTP Compose lane.")
    mounts = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        before, after = line.split(" - ", 1)
        if before.split()[4] == "/app/data":
            mounts.append(after.split()[0])
    if mounts != ["tmpfs"]:
        raise RuntimeError("The application database must be disposable tmpfs.")
    database = Path("/app/data/deploywhisper.db")
    if database.is_symlink() or database.resolve().parent != Path("/app/data"):
        raise RuntimeError("Unexpected disposable database path.")
    os.umask(0o077)
    sys.path.insert(0, "/app")
    import config

    if (
        config.settings.database_url != DATABASE
        or config.settings.identity_profile != "local-development"
        or config.settings.identity_origin != ORIGIN
        or config.settings.identity_decision_mode != "shared"
    ):
        raise RuntimeError("Loaded configuration differs from the disposable lane.")


def read_private(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or not 0 < metadata.st_size <= 262144
        ):
            raise RuntimeError("Fixture must be a bounded private regular file.")
        with os.fdopen(descriptor, "r") as stream:
            descriptor = -1
            value = json.load(stream)
        if type(value) is not dict:
            raise RuntimeError("Invalid private fixture.")
        return value
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def browser_fixture(state):
    return {
        "version": 1,
        "origin": ORIGIN,
        "lane": "signed-trigger-origins",
        "accounts": state["accounts"],
        "operatorPool": state["operatorPool"],
        "projects": state["projects"],
    }


def seed_identities():
    if SEED_OUTPUT.exists() or BROWSER_OUTPUT.exists():
        raise RuntimeError(
            "Refusing an existing browser fixture; restart the disposable lane."
        )
    previous = sys.argv
    try:
        sys.argv = ["seed_infra_automation_ui.py", "--output", str(SEED_OUTPUT)]
        # The operator-owned seeder is a read-only Compose mount.
        runpy.run_path("/tmp/seed_infra_automation_ui.py", run_name="__main__")  # nosec B108
    finally:
        sys.argv = previous
    state = read_private(SEED_OUTPUT)
    state = seed_origins(state)
    value = browser_fixture(state)
    value["workflows"] = state["workflows"]
    value["principals"] = state["principals"]
    value["source"] = state["source"]
    descriptor = os.open(
        BROWSER_OUTPUT, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream, separators=(",", ":"), allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


PRIVATE = Path("/tmp/trigger-ui-private")  # nosec B108
STATE = PRIVATE / "state.json"
RESULTS = PRIVATE / "runs.json"
PROFILE = "sha256:" + "d" * 64
SOURCE = {"repository_id": "synthetic-origin-repository", "commit_sha": "a" * 40}


def write_private(path, value):
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream, separators=(",", ":"), allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def seed_origins(state):
    import config
    from infra_automation.lifecycle import CreateWorkflowRequest, PublishWorkflowRequest
    from services.identity_service import IdentityService
    from services import project_service as auth
    from services import infra_automation_service as workflows
    from services.infra_automation_triggers import (
        provision_principal,
        ProvisionPrincipalRequest,
    )

    PRIVATE.mkdir(mode=0o700)
    profiles = [
        {
            "profile_digest": PROFILE,
            "tool": "opentofu",
            "tool_version": "1.13.1",
            "runner_version": "synthetic-origin-proof",
            "tags": [],
        }
    ]
    profile_path = PRIVATE / "profiles.json"
    write_private(profile_path, profiles)
    profile_sha = "sha256:" + hashlib.sha256(profile_path.read_bytes()).hexdigest()
    os.environ["DEPLOYWHISPER_COLLECTION_PROFILES_PATH"] = str(profile_path)
    os.environ["DEPLOYWHISPER_COLLECTION_PROFILES_SHA256"] = profile_sha
    config.settings = replace(
        config.settings,
        collection_profiles_path=str(profile_path),
        collection_profiles_sha256=profile_sha,
    )
    identity = IdentityService(
        security_profile="local-development", trusted_origin=ORIGIN
    )
    operator = state["accounts"]["operator"]
    issued = identity.login(operator["username"], operator["password"])
    token, csrf = issued.token.get_secret_value(), issued.csrf_token.get_secret_value()
    scope = state["projects"]["enabled"]
    workflow_values = {}
    principals = {}
    keys, secrets_by_env = [], {}
    with auth.credential_context(identity, token, csrf_token=csrf, mutation=True):
        for kind in ("uploaded", "collected"):
            intake = {
                "id": "intake",
                "kind": "uploaded_intake"
                if kind == "uploaded"
                else "admitted_collection",
                "depends_on": [],
                "source": {"kind": "uploaded"}
                if kind == "uploaded"
                else {"kind": "collected", **SOURCE, "profile_digest": PROFILE},
            }
            definition = {
                "workflow_version": 2,
                "project_id": str(scope["projectId"]),
                "workspace_id": str(scope["workspaceId"]),
                "environment": "test",
                "inputs": {},
                "steps": [
                    intake,
                    {
                        "id": "analysis",
                        "kind": "shared_analysis",
                        "depends_on": ["intake"],
                        "artifact": {
                            "ref": "step",
                            "step_id": "intake",
                            "output": "screened_artifacts",
                        },
                    },
                ],
            }
            created = workflows.create_workflow(
                CreateWorkflowRequest(
                    project_id=scope["projectId"],
                    workspace_id=scope["workspaceId"],
                    name=f"Synthetic {kind} origin proof",
                    definition=json.dumps(definition),
                    reason="Disposable origin browser setup",
                )
            )
            revision = workflows.publish_workflow(
                created["id"],
                PublishWorkflowRequest(
                    expected_version=created["draft_version"],
                    idempotency_key=f"origin-publish-{kind}",
                    reason="Publish synthetic origin workflow",
                ),
            )
            workflow_values[kind] = {
                "workflowId": created["id"],
                "revisionId": revision["id"],
            }
        for kind in ("service", "agent"):
            principal = provision_principal(
                ProvisionPrincipalRequest(
                    project_id=scope["projectId"],
                    workspace_id=scope["workspaceId"],
                    username=f"ui-proof-{kind}-{secrets.token_hex(5)}",
                    principal_type=kind,
                    role="contributor",
                    reason="Disposable signed-origin principal",
                )
            )
            key_id = f"origin-{kind}-key"
            reference = f"SYNTHETIC_TRIGGER_UI_{kind.upper()}"
            secret = secrets.token_hex(32)
            secrets_by_env[reference] = secret
            os.environ[reference] = secret
            key = {
                "key_id": key_id,
                "principal_id": principal["principal_id"],
                "principal_type": kind,
                "project_id": scope["projectId"],
                "workspace_id": scope["workspaceId"],
                "allowed_revision_ids": [workflow_values["collected"]["revisionId"]],
                "allowed_sources": [SOURCE],
                "allowed_origins": ["webhook", "cli", "pull_request"],
                "authentication_version": principal["authentication_version"],
                "membership_version": principal["membership_version"],
                "restore_epoch": principal["restore_epoch"],
                "expires_at": (
                    datetime.now(timezone.utc) + timedelta(hours=2)
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "secret_env_ref": reference,
            }
            keys.append(key)
            principals[kind] = {
                "principalId": principal["principal_id"],
                "keyId": key_id,
                "secretEnvRef": reference,
            }
            write_private(
                PRIVATE / f"{kind}.json",
                {
                    "kind": "signed",
                    "origin": ORIGIN,
                    "key_id": key_id,
                    "secret_env_ref": reference,
                },
            )
    identity.logout(token, csrf_token=csrf)
    manifest_path = PRIVATE / "manifest.json"
    write_private(manifest_path, {"version": 1, "keys": keys})
    manifest_sha = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    os.environ["DEPLOYWHISPER_TRIGGER_KEYS_PATH"] = str(manifest_path)
    os.environ["DEPLOYWHISPER_TRIGGER_KEYS_SHA256"] = manifest_sha
    config.settings = replace(
        config.settings,
        trigger_keys_path=str(manifest_path),
        trigger_keys_sha256=manifest_sha,
    )
    state.update(
        workflows=workflow_values,
        principals=principals,
        source={**SOURCE, "profile_digest": PROFILE},
    )
    write_private(STATE, {**state, "secrets": secrets_by_env})
    return state


def http_json(path, body, headers=None):
    connection = http.client.HTTPConnection("localhost", 8080, timeout=20)
    try:
        connection.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Origin": ORIGIN,
                **(headers or {}),
            },
        )
        response = connection.getresponse()
        raw = response.read(131073)
        if response.status != 200 or len(raw) > 131072:
            raise RuntimeError("Synthetic API operation denied.")
        value = json.loads(raw)
        return value["data"], response.getheader("Set-Cookie")
    finally:
        connection.close()


def cli_call(credential, command, body, name):
    request_path = PRIVATE / f"{name}.json"
    write_private(request_path, body)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.analyze",
            "automation",
            "--credential-file",
            str(credential),
            *command,
            "--request",
            str(request_path),
        ],
        capture_output=True,
        timeout=45,
        check=False,
    )
    if result.returncode != 0:
        code = "unavailable"
        try:
            candidate = (
                json.loads(result.stderr or result.stdout).get("error", {}).get("code")
            )
            if candidate in {
                "authentication_required",
                "permission_denied",
                "binding_conflict",
                "request_validation_failed",
                "quota_exceeded",
                "authority_unavailable",
            }:
                code = candidate
        except (ValueError, AttributeError):
            pass
        print(
            f"Synthetic CLI {name} failed: exit={result.returncode}, code={code}.",
            file=sys.stderr,
        )
        raise RuntimeError("Synthetic CLI operation failed.")
    value = json.loads(result.stdout)
    return value["data"]


def exercise():
    if RESULTS.exists():
        return
    state = read_private(STATE)
    os.environ.update(state["secrets"])
    scope = state["projects"]["enabled"]
    account = state["accounts"]["operator"]
    login, cookie_header = http_json(
        "/api/v1/auth/login",
        json.dumps(
            {"username": account["username"], "password": account["password"]}
        ).encode(),
    )
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    human_file = PRIVATE / "human.json"
    write_private(
        human_file,
        {
            "kind": "human",
            "origin": ORIGIN,
            "session_token": cookie["dw-local-session"].value,
            "csrf_token": login["csrf_token"],
        },
    )
    workflow = state["workflows"]["uploaded"]
    run_request = {
        "workflow_id": workflow["workflowId"],
        "revision_id": workflow["revisionId"],
        "workspace_id": scope["workspaceId"],
        "inputs": {},
        "idempotency_key": "origin-human-cli",
        "total_timeout_seconds": 3600,
        "reason": "Synthetic human CLI origin proof",
    }
    human = cli_call(
        human_file,
        ["run", "--preflight"],
        {
            "run": run_request,
            "artifacts": [
                {
                    "name": "main.tf",
                    "content": 'resource "aws_s3_bucket" "cli" { bucket = "synthetic-origin-cli" }',
                }
            ],
        },
        "human-request",
    )
    workflow = state["workflows"]["collected"]

    def payload(kind):
        source = {**SOURCE, "origin": kind}
        if kind == "pull_request":
            source["pr_ref"] = "refs/pull/17/head"
        return {
            "version": 1,
            "workflow_revision_id": workflow["revisionId"],
            "project_id": scope["projectId"],
            "workspace_id": scope["workspaceId"],
            "source": source,
            "inputs": {},
            "idempotency_key": f"origin-{kind}",
        }

    agent = cli_call(PRIVATE / "agent.json", ["run"], payload("cli"), "agent-request")
    from infra_automation.trigger_signing import (
        sign_request,
        KEY_ID_HEADER,
        TIMESTAMP_HEADER,
        NONCE_HEADER,
        SIGNATURE_HEADER,
    )

    service = state["principals"]["service"]
    admitted = {}
    for kind in ("webhook", "pull_request"):
        body = json.dumps(payload(kind), separators=(",", ":")).encode()
        path = "/api/v1/infra-automation/triggers/webhook"
        timestamp, nonce = str(int(time.time())), secrets.token_urlsafe(24)
        signature = sign_request(
            bytes.fromhex(state["secrets"][service["secretEnvRef"]]),
            key_id=service["keyId"],
            method="POST",
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        )
        value, _ = http_json(
            path,
            body,
            {
                KEY_ID_HEADER: service["keyId"],
                TIMESTAMP_HEADER: timestamp,
                NONCE_HEADER: nonce,
                SIGNATURE_HEADER: signature,
                "X-Actor-Type": "human",
                "X-Project-Role": "admin",
            },
        )
        admitted[kind] = value
    write_private(
        RESULTS,
        {
            "humanCli": human,
            "agentCli": agent,
            "webhook": admitted["webhook"],
            "pullRequest": admitted["pull_request"],
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--exercise", action="store_true")
    parser.add_argument("--results", action="store_true")
    args = parser.parse_args()
    guard()
    if args.serve:
        seed_identities()
        print(
            "Disposable signed-origin fixture ready; collected requests are admission-only.",
            flush=True,
        )
        import app

        app.run()
    elif args.exercise:
        exercise()
        print("Actual API and CLI origin requests persisted.", flush=True)
    elif args.results:
        print(json.dumps(read_private(RESULTS), separators=(",", ":")))
    else:
        raise RuntimeError("Choose a disposable fixture operation.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"Disposable signed-origin fixture failed ({type(error).__name__}, status={getattr(error, 'status_code', None)}).",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
