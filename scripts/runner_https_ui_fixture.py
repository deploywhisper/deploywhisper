"""Opted-in disposable same-origin TLS runner browser qualification."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import sys

ORIGIN = os.environ.get("RUNNER_HTTPS_ORIGIN", "https://localhost:8443")
DATABASE = "sqlite:////app/data/deploywhisper.db"


def main():
    if ORIGIN not in {"https://localhost:8443", "https://localhost:18443"}:
        raise RuntimeError("Unsupported disposable TLS origin")
    expected = {
        "RUNNER_HTTPS_DISPOSABLE": "1",
        "DATABASE_URL": DATABASE,
        "DEPLOYWHISPER_IDENTITY_PROFILE": "https",
        "DEPLOYWHISPER_IDENTITY_ORIGIN": ORIGIN,
        "DEPLOYWHISPER_AUTHORIZATION_PROFILE": "verified",
        "APP_BASE_URL": ORIGIN,
    }
    if not Path("/.dockerenv").exists() or os.geteuid() == 0:
        raise RuntimeError("Nonroot disposable container required")
    if any(os.environ.get(k) != v for k, v in expected.items()):
        raise RuntimeError("Exact TLS fixture configuration required")
    if not any(
        line.split(" - ")[0].split()[4] == "/app/data"
        and line.split(" - ")[1].split()[0] == "tmpfs"
        for line in Path("/proc/self/mountinfo").read_text().splitlines()
    ):
        raise RuntimeError("Disposable tmpfs database required")
    os.umask(0o077)
    sys.path.insert(0, "/app")
    from models.database import init_db, SessionLocal
    from models.tables import IdentityAccount, Project, ProjectWorkspace
    from models.repositories.project_memberships import upsert_membership
    from services.identity_service import IdentityService
    from services import project_service, infra_automation_policy
    from infra_automation.lifecycle import AutomationSettings, UpdateSettingsRequest

    init_db()
    with SessionLocal() as db:
        if db.query(IdentityAccount).first():
            raise RuntimeError("Existing identities refused")
    identity = IdentityService(security_profile="https", trusted_origin=ORIGIN)
    username, password = "tls-proof-" + secrets.token_hex(5), secrets.token_urlsafe(32)
    setup = identity.issue_setup_credential()
    admin = identity.bootstrap(setup.token.get_secret_value(), username, password)
    issued = identity.login(username, password)
    with SessionLocal.begin() as db:
        project = Project(
            project_key="tls-proof",
            display_name="TLS qualification",
            authorization_required=True,
        )
        db.add(project)
        db.flush()
        workspace = ProjectWorkspace(
            project_id=project.id,
            workspace_key="synthetic",
            display_name="Synthetic",
            environment="test",
        )
        db.add(workspace)
        db.flush()
        upsert_membership(
            db, principal_id=admin.principal_id, project_id=project.id, role="admin"
        )
        project_id, workspace_id = project.id, workspace.id
    with project_service.credential_context(
        identity,
        issued.token.get_secret_value(),
        csrf_token=issued.csrf_token.get_secret_value(),
        mutation=True,
    ):
        infra_automation_policy.update_settings(
            UpdateSettingsRequest(
                project_id=project_id,
                expected_version=0,
                settings=AutomationSettings(enabled=True, credential_ttl_seconds=60),
                reason="Disposable HTTPS browser qualification",
            )
        )
    identity.logout(
        issued.token.get_secret_value(), csrf_token=issued.csrf_token.get_secret_value()
    )
    # This explicitly named synthetic profile qualifies administration only.
    # It is never represented as an executed collector profile.
    profiles = json.dumps(
        [
            dict(
                profile_digest=os.environ.get(
                    "RUNNER_HTTPS_PROFILE_DIGEST", "sha256:" + "a" * 64
                ),
                tool="opentofu",
                tool_version="1.13.1",
                runner_version="1.0",
                tags=["linux"],
            )
        ],
        separators=(",", ":"),
    ).encode()
    profile_root = Path("/app/data/operator")
    profile_root.mkdir(mode=0o700)
    profile_path = profile_root / "profiles.json"
    profile_path.write_bytes(profiles)
    os.environ["DEPLOYWHISPER_COLLECTION_PROFILES_PATH"] = str(profile_path)
    os.environ["DEPLOYWHISPER_COLLECTION_PROFILES_SHA256"] = (
        "sha256:" + hashlib.sha256(profiles).hexdigest()
    )
    import config
    from dataclasses import replace

    config.settings = replace(
        config.settings,
        collection_profiles_path=str(profile_path),
        collection_profiles_sha256="sha256:" + hashlib.sha256(profiles).hexdigest(),
    )
    output = Path("/app/data/browser.json")
    output.write_text(
        json.dumps(
            dict(
                origin=ORIGIN,
                username=username,
                password=password,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        )
    )
    # Observe only bounded public outcome categories; never alter results or
    # expose exception text, payloads, credentials or handler inputs.
    from infra_automation.local_workers import SpawnProcessWorkers

    original_poll = SpawnProcessWorkers.poll
    observations = []

    def observed_poll(workers):
        exitcodes = {key: item.process.exitcode for key, item in workers._owned.items()}
        completed = original_poll(workers)
        for item in completed:
            if len(observations) < 128:
                observations.append(
                    {
                        "attempt_id": item.handle.attempt_id,
                        "outcome": item.result.outcome,
                        "crashed": item.crashed,
                        "exitcode_at_poll_entry": exitcodes.get(item.handle.attempt_id),
                    }
                )
        if completed:
            try:
                (profile_root / "worker-observations.json").write_text(
                    json.dumps({"observations": observations}, sort_keys=True)
                )
            except OSError:
                print("Worker observation unavailable", flush=True)
        return completed

    SpawnProcessWorkers.poll = observed_poll
    import app
    import uvicorn

    uvicorn.run(
        app.fastapi_app,
        host="0.0.0.0",
        port=8443,
        proxy_headers=False,
        ssl_certfile="/tls/cert.pem",
        ssl_keyfile="/tls/key.pem",
        log_level="warning",
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Disposable HTTPS fixture failed", file=sys.stderr)
        raise SystemExit(1) from None
