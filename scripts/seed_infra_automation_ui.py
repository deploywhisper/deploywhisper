"""Seed synthetic browser identities only inside an opted-in disposable container.

Mount this script read-only at /tmp/seed_infra_automation_ui.py. Never run it
against an operator database. Copy the 0600 output with docker cp and chmod
0600 on the host before passing its path as AUTOMATION_UI_FIXTURE.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import sys

# The runtime intentionally does not package the development scripts directory.
sys.path.insert(0, "/app")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="/tmp/automation-ui-fixture.json")
    parser.add_argument("--expire-user")
    args = parser.parse_args()
    if (
        os.environ.get("AUTOMATION_UI_DISPOSABLE") != "1"
        or not Path("/.dockerenv").exists()
    ):
        raise SystemExit("Requires an explicitly disposable Docker container.")

    import config
    from infra_automation.lifecycle import AutomationSettings, UpdateSettingsRequest
    from models.database import SessionLocal, init_db
    from models.repositories.project_memberships import append_audit, upsert_membership
    from models.tables import (
        IdentityAccount,
        IdentitySession,
        Project,
        ProjectWorkspace,
    )
    from services.identity_service import IdentityService
    from services import infra_automation_policy, project_service

    if config.settings.identity_profile != "local-development":
        raise SystemExit("Requires the isolated local-development identity profile.")
    if args.expire_user:
        if not args.expire_user.startswith("ui-proof-"):
            raise SystemExit("Only synthetic browser fixture accounts may expire.")
        with SessionLocal.begin() as db:
            account = (
                db.query(IdentityAccount).filter_by(username=args.expire_user).one()
            )
            db.query(IdentitySession).filter_by(principal_id=account.id).update(
                {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
            )
        print("Synthetic browser sessions expired.")
        return

    destination = Path(args.output)
    if destination.parent != Path("/tmp") or destination.exists():
        raise SystemExit("Output must be a new file directly under /tmp.")
    init_db()
    with SessionLocal() as db:
        if db.query(IdentityAccount).first() is not None:
            raise SystemExit("Refusing a database with existing identity accounts.")
    identity = IdentityService(
        security_profile=config.settings.identity_profile,
        trusted_origin=config.settings.identity_origin,
    )
    suffix = secrets.token_hex(5)
    accounts = {}
    for role in ("operator", "viewer", "unassigned", "revoked", "expired"):
        accounts[role] = {
            "username": f"ui-proof-{role}-{suffix}",
            "password": secrets.token_urlsafe(32),
        }
    operator = accounts["operator"]
    setup = identity.issue_setup_credential()
    admin = identity.bootstrap(
        setup.token.get_secret_value(), operator["username"], operator["password"]
    )
    issued = identity.login(operator["username"], operator["password"])
    token, csrf = issued.token.get_secret_value(), issued.csrf_token.get_secret_value()
    operator["principalId"] = admin.principal_id
    for role, credentials in accounts.items():
        if role != "operator":
            account = identity.create_account(
                token,
                credentials["username"],
                credentials["password"],
                csrf_token=csrf,
            )
            credentials["principalId"] = account.principal_id

    operator_pool = []
    for index in range(16):
        credentials = {
            "username": f"ui-proof-author-{index}-{suffix}",
            "password": secrets.token_urlsafe(32),
        }
        account = identity.create_account(
            token,
            credentials["username"],
            credentials["password"],
            csrf_token=csrf,
            is_admin=True,
        )
        credentials["principalId"] = account.principal_id
        operator_pool.append(credentials)

    projects = {}
    # Trusted synthetic fixture writes establish protected scope without making
    # browser authentication depend on preseeded cookies or role headers.
    with SessionLocal.begin() as db:
        for label in ("enabled", "disabled"):
            project = Project(
                project_key=f"ui-proof-{label}-{suffix}",
                display_name=f"UI proof {label} {suffix}",
                authorization_required=True,
            )
            db.add(project)
            db.flush()
            workspace = ProjectWorkspace(
                project_id=project.id,
                workspace_key="synthetic",
                display_name="Synthetic workspace",
                environment="test",
            )
            db.add(workspace)
            db.flush()
            projects[label] = {
                "projectId": project.id,
                "workspaceId": workspace.id,
                "projectName": project.display_name,
                "projectKey": project.project_key,
            }
            members = [
                (accounts[role], "read-only" if role == "viewer" else "admin")
                for role in ("operator", "viewer", "revoked", "expired")
            ] + [(credentials, "admin") for credentials in operator_pool]
            for credentials, membership_role in members:
                member = upsert_membership(
                    db,
                    principal_id=credentials["principalId"],
                    project_id=project.id,
                    role=membership_role,
                )
                append_audit(
                    db,
                    actor_principal_id=admin.principal_id,
                    project_id=project.id,
                    target_principal_id=member.principal_id,
                    action="synthetic.browser.fixture",
                )
    with project_service.credential_context(
        identity, token, csrf_token=csrf, mutation=True
    ):
        for label, project in projects.items():
            infra_automation_policy.update_settings(
                UpdateSettingsRequest(
                    project_id=project["projectId"],
                    expected_version=0,
                    settings=AutomationSettings(enabled=label == "enabled"),
                    reason="Disposable synthetic browser qualification",
                )
            )
    identity.logout(token, csrf_token=csrf)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(
            {"accounts": accounts, "operatorPool": operator_pool, "projects": projects},
            output,
        )
    print(
        "Synthetic browser fixture ready; credentials written to protected /tmp file."
    )


if __name__ == "__main__":
    main()
