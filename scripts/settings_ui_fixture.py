"""Guarded disposable settings browser fixture; never operates on host data."""

from __future__ import annotations

import os
from pathlib import Path
import runpy
import sys


def guard():
    if (
        os.environ.get("SETTINGS_UI_DISPOSABLE") != "1"
        or not Path("/.dockerenv").is_file()
        or os.geteuid() == 0
        or Path.cwd() != Path("/app")
    ):
        raise RuntimeError("Requires the exact nonroot disposable settings lane.")
    mounts = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        before, after = line.split(" - ", 1)
        if before.split()[4] == "/app/data":
            mounts.append(after.split()[0])
    if mounts != ["tmpfs"]:
        raise RuntimeError("Settings fixture requires disposable tmpfs data.")


def seed_historical_manifest(module, browser):
    """Original INSERTs of explicit synthetic history; no product time bypass."""
    from datetime import datetime, timedelta, timezone
    import secrets

    import config
    from infra_automation.lifecycle import SnapshotDocument
    from models.repositories import infra_automation_reports as reports
    from models.tables import InfraAutomationArtifactManifest, InfraAutomationRun
    from services import infra_automation_service as workflows
    from services import infra_automation_support as support
    from services import project_service as authorization
    from services.identity_service import IdentityService

    scope = browser["projects"]["enabled"]
    workflow = browser["workflows"]["uploaded"]
    operator = browser["accounts"]["operator"]
    identity = IdentityService(
        security_profile=config.settings.identity_profile,
        trusted_origin=config.settings.identity_origin,
    )
    issued = identity.login(operator["username"], operator["password"])
    token, csrf = issued.token.get_secret_value(), issued.csrf_token.get_secret_value()
    old = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=8)
    run_id, manifest_id = secrets.token_hex(24), secrets.token_hex(24)
    try:
        with authorization.credential_context(
            identity, token, csrf_token=csrf, mutation=True
        ):
            exported = workflows.export_run_snapshot(
                workflow["workflowId"], workflow["revisionId"], {}, scope["workspaceId"]
            )
            value = exported.data
            value["captured_at"] = support.utc(old)
            snapshot = support.canonical(value)
            SnapshotDocument.model_validate_json(snapshot)
            content = reports._manifest_payload(
                [("main.tf", b"# synthetic retained browser history\n" * 600)]
            )
            with authorization.authorized_session() as session:
                grant = support.scope(
                    session,
                    scope["projectId"],
                    scope["workspaceId"],
                    "automation.admin",
                    mutation=True,
                )
                session.add(
                    InfraAutomationRun(
                        id=run_id,
                        project_id=scope["projectId"],
                        workspace_id=scope["workspaceId"],
                        requested_by=operator["principalId"],
                        workflow_id=workflow["workflowId"],
                        revision_id=workflow["revisionId"],
                        snapshot_bytes=snapshot,
                        snapshot_digest=support.digest(snapshot),
                        definition_digest=exported.definition_digest,
                        input_digest=exported.input_digest,
                        request_digest=support.digest(
                            b"synthetic historical UI fixture"
                        ),
                        created_at=old,
                        deadline_at=old + timedelta(minutes=5),
                        state="failed",
                        version=1,
                        updated_at=old,
                        last_observed_at=old,
                        cancel_requested=False,
                        cancellation_requested_at=None,
                        retained_bytes=len(snapshot) + len(content),
                        external_possible=False,
                    )
                )
                session.flush()
                session.add(
                    InfraAutomationArtifactManifest(
                        id=manifest_id,
                        run_id=run_id,
                        step_id="intake",
                        project_id=scope["projectId"],
                        workspace_id=scope["workspaceId"],
                        requested_by=operator["principalId"],
                        artifacts_bytes=content,
                        digest=support.digest(content),
                        created_at=old,
                    )
                )
                support.append_audit(
                    session,
                    grant,
                    workspace_id=scope["workspaceId"],
                    event_type="synthetic_historical_ui_fixture",
                    target_id=run_id,
                    reason="Original synthetic historical inserts for post-purge rendering",
                    before_digest=None,
                    after_digest=support.digest(snapshot),
                )
    finally:
        identity.logout(token, csrf_token=csrf)
    browser["historical"] = {
        "runId": run_id,
        "manifestId": manifest_id,
        "runVersion": 1,
        "originalDigest": support.digest(content),
    }
    module["write_private"](Path("/tmp/settings-ui-browser-fixture.json"), browser)  # nosec B108


def install_read_failures(application, browser):
    """Failure-only HTTP injection, confined to the guarded disposable fixture."""
    guard()
    import json
    import stat
    from urllib.parse import quote

    from starlette.responses import JSONResponse

    project_ids = {str(scope["projectId"]) for scope in browser["projects"].values()}
    membership_paths = {
        f"/api/v1/projects/{quote(scope['projectKey'], safe='')}/memberships"
        for scope in browser["projects"].values()
    }

    @application.middleware("http")
    async def settings_read_failure(request, call_next):
        resource = None
        if request.method == "GET":
            if (
                request.url.path == "/api/v1/infra-automation/settings"
                and request.query_params.get("project_id") in project_ids
            ):
                resource = "policy"
            elif request.url.path in membership_paths:
                resource = "membership"
        if resource:
            descriptor = None
            failures = []
            try:
                descriptor = os.open(
                    "/tmp/settings-ui-read-failures.json",  # nosec B108
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                )
                metadata = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != os.geteuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                    or metadata.st_nlink != 1
                    or metadata.st_size > 128
                ):
                    raise ValueError("Invalid disposable failure flag")
                failures = json.loads(os.read(descriptor, 129))
                if not isinstance(failures, list) or any(
                    item not in ("policy", "membership") for item in failures
                ):
                    raise ValueError("Invalid disposable failure flag")
            except FileNotFoundError:
                pass
            except (OSError, ValueError):
                # An invalid flag can only withhold reads, never supply authority.
                failures = ["policy", "membership"]
            finally:
                if descriptor is not None:
                    os.close(descriptor)
            if resource in failures:
                return JSONResponse(
                    {"error": {"code": "authority_unavailable", "details": {}}},
                    status_code=503,
                )
        return await call_next(request)


def main():
    guard()
    module = runpy.run_path("/tmp/trigger_ui_fixture.py")  # nosec B108
    module["guard"]()
    module["seed_identities"]()
    state = module["read_private"](module["SEED_OUTPUT"])
    from sqlalchemy import select
    from models.database import SessionLocal
    from models.repositories.project_memberships import append_audit, upsert_membership
    from models.tables import Project

    operator = state["accounts"]["operator"]
    # Target administration is global. The shared fixture intentionally grants
    # only its two feature projects; this exact disposable lane includes default
    # metadata scope without changing production permission checks.
    with SessionLocal.begin() as session:
        projects = list(session.scalars(select(Project)))
        for project in projects:
            member = upsert_membership(
                session,
                principal_id=operator["principalId"],
                project_id=project.id,
                role="admin",
            )
            append_audit(
                session,
                actor_principal_id=operator["principalId"],
                project_id=project.id,
                target_principal_id=member.principal_id,
                action="synthetic.settings.fixture",
            )
    browser = module["read_private"](module["BROWSER_OUTPUT"])
    seed_historical_manifest(module, browser)
    import app

    install_read_failures(app.fastapi_app, browser)
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"Disposable settings fixture failed ({type(error).__name__}).",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
