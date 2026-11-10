"""Private local automation backup/recovery commands; no remote action replay."""

from __future__ import annotations

import argparse
import json
import sys

from infra_automation.operator_recovery import (
    RecoveryError,
    RecoveryStore,
    upgrade_database_copy,
)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RecoveryError()


def parser():
    result = Parser(description="Offline participating-domain automation recovery.")
    result.add_argument("--control", required=True)
    commands = result.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("initialize")
    initialize.add_argument("--database", required=True)
    initialize.add_argument(
        "--root",
        action="append",
        required=True,
        help="Protected role=/canonical/path; artifacts and custody are required.",
    )
    backup = commands.add_parser("backup")
    backup.add_argument("--output", required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--backup", required=True)
    commands.add_parser("resume")
    commands.add_parser("status")
    complete = commands.add_parser("recovery-complete")
    receiver_issue = commands.add_parser("receiver-recovery-issue")
    receiver_issue.add_argument("--operation", required=True)
    receiver_issue.add_argument("--output", required=True)
    for command in (complete, receiver_issue):
        for name in ("token-file", "csrf-file", "reason-file"):
            command.add_argument("--" + name, required=True)
    upgrade = commands.add_parser("upgrade-copy")
    upgrade.add_argument("--source", required=True)
    upgrade.add_argument("--output", required=True)
    return result


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        store = RecoveryStore(args.control)
        if args.command == "initialize":
            roots = {}
            for item in args.root:
                role, separator, path = item.partition("=")
                if not separator or not path or role in roots:
                    raise RecoveryError()
                roots[role] = path
            value = store.initialize(args.database, roots)
        elif args.command == "backup":
            value = store.backup(args.output)
        elif args.command == "restore":
            value = store.restore(args.backup)
        elif args.command == "resume":
            value = store.resume()
        elif args.command == "status":
            value = store.status()
        elif args.command == "upgrade-copy":
            value = upgrade_database_copy(args.source, args.output)
        else:
            import config
            from cli.identity import _private_input
            from services.identity_service import IdentityService
            from services import project_service as authorization

            service = IdentityService(
                security_profile=config.settings.identity_profile,
                trusted_origin=config.settings.identity_origin,
            )
            token = _private_input(args.token_file, 4096)
            csrf = _private_input(args.csrf_file, 4096)
            reason = _private_input(args.reason_file, 1024)
            with authorization.credential_context(
                service, token, csrf_token=csrf, mutation=True
            ):
                if args.command == "receiver-recovery-issue":
                    from cli.identity import _issue_to_file
                    from services.infra_automation_receiver_recovery import (
                        issue_credential,
                    )

                    _issue_to_file(
                        args.output,
                        lambda: issue_credential(store, args.operation, reason),
                    )
                    value = {"credential_written": True}
                else:
                    value = store.complete(reason)
        # No paths, reasons, raw manifest entries or bearer values in CLI output.
        print(
            json.dumps(
                {
                    key: value[key]
                    for key in (
                        "phase",
                        "generation",
                        "installation_id",
                        "manifest_digest",
                        "files",
                        "schema_revision",
                        "credential_written",
                    )
                    if key in value
                },
                sort_keys=True,
            )
        )
        return 0
    except Exception:
        print(
            "Automation operation unavailable; verify private configuration and recovery state.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
