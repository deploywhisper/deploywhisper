"""Disposable HTTP runner UX proof; HTTPS enrollment is intentionally unavailable.

Mount with the existing synthetic account seeder. This harness never upgrades
local-development sessions into production authority and never seeds runner
credentials. Positive enrollment and isolated collection need their separately
authorized HTTPS acceptance lane.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import runpy
import stat
import sys

ORIGIN = "http://localhost:8080"
DATABASE = "sqlite:////app/data/deploywhisper.db"
# Guarded disposable container; both credential files use exclusive mode0600 creation.
SEED_OUTPUT = Path("/tmp/runner-ui-account-fixture.json")  # nosec B108
BROWSER_OUTPUT = Path("/tmp/runner-ui-browser-fixture.json")  # nosec B108


def required_environment():
    return {
        "RUNNER_UI_DISPOSABLE": "1",
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
        "lane": "http-denial",
        "accounts": state["accounts"],
        "operatorPool": state["operatorPool"],
        "projects": state["projects"],
    }


def seed():
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
    value = browser_fixture(read_private(SEED_OUTPUT))
    descriptor = os.open(
        BROWSER_OUTPUT, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream, separators=(",", ":"), allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def expire_account(role):
    state = read_private(BROWSER_OUTPUT)
    if role not in {"operator", "viewer", "revoked", "expired"}:
        raise RuntimeError("Unsupported synthetic account role.")
    account = state["accounts"][role]
    from models.database import SessionLocal
    from models.tables import IdentityAccount, IdentitySession

    with SessionLocal.begin() as db:
        actual = (
            db.query(IdentityAccount)
            .filter_by(id=account["principalId"], username=account["username"])
            .one()
        )
        db.query(IdentitySession).filter_by(principal_id=actual.id).update(
            {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
    print("Synthetic browser sessions expired.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument(
        "--expire-account", choices=("operator", "viewer", "revoked", "expired")
    )
    args = parser.parse_args()
    guard()
    if args.expire_account:
        expire_account(args.expire_account)
        return
    if not args.serve:
        raise RuntimeError(
            "Choose the disposable server or fixture maintenance operation."
        )
    seed()
    print(
        "Disposable HTTP runner UI fixture ready; positive enrollment remains unavailable.",
        flush=True,
    )
    import app

    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never print exception details containing fixture credentials or API bodies.
        print("Disposable runner UI fixture failed.", file=sys.stderr)
        raise SystemExit(1) from None
