"""Runner enrollment and execution with owner-only credential files."""

from __future__ import annotations

import sys
from cli.identity import _Parser, _private_input, _issue_to_file
from types import SimpleNamespace
from pydantic import SecretStr
from infra_automation.runner.protocol import parse_enrollment
from infra_automation.runner.client import RunnerClient


def main(argv=None) -> int:
    try:
        parser = _Parser(
            description="Enroll a runner; execution requires a qualified local handler."
        )
        commands = parser.add_subparsers(dest="command", required=True)
        poll = commands.add_parser("run")
        poll.add_argument("--url", required=True)
        poll.add_argument("--runner-id", required=True)
        poll.add_argument("--credential-file", required=True)
        poll.add_argument("--max-polls", type=int, default=20)
        enroll = commands.add_parser("enroll")
        enroll.add_argument("--url", required=True)
        enroll.add_argument("--enrollment-file", required=True)
        enroll.add_argument("--credential-file", required=True)
        enroll.add_argument("--output", required=True)
        args = parser.parse_args(argv)
        if args.command == "enroll":
            enrollment = parse_enrollment(_private_input(args.enrollment_file, 131072))
            token = _private_input(args.credential_file, 256)
            client = RunnerClient(args.url, enrollment.runner_id, token)

            def issue():
                value = client.redeem(enrollment)
                return SimpleNamespace(token=SecretStr(value["token"]))

            _issue_to_file(args.output, issue)
            print("Runner credential stored in the protected output file.")
            return 0
        token = _private_input(args.credential_file, 256)
        client = RunnerClient(args.url, args.runner_id, token)
        # No qualified handler ships before Story 16.13/16.14. Fail before
        # polling, which consumes an assignment's transient task capability.
        client.run(max_polls=args.max_polls)
        print("Runner task completed.")
        return 0
    except (Exception, KeyboardInterrupt):
        print("Runner operation unavailable.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
