"""Local operator bootstrap and recovery with protected credential custody."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import getpass
import os
from pathlib import Path
import stat
import sys
import warnings

from models.database import init_db
from services.identity_service import IdentityService, IssuedCredential


class _CliError(Exception):
    """Deliberately carries no caller-controlled message."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error echoes unknown arguments, possibly secrets.
        raise _CliError()


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description="Local DeployWhisper identity administration.")
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser(
        "setup", help="Issue first-account evidence to a new private file."
    )
    setup.add_argument("--output", required=True)
    bootstrap = commands.add_parser(
        "bootstrap", help="Create the first local administrator."
    )
    bootstrap.add_argument("--username", required=True)
    bootstrap.add_argument("--credential-file", required=True)
    bootstrap.add_argument(
        "--password-file",
        help="Private file, or - for a protected nonterminal pipe; otherwise prompt securely.",
    )
    issue = commands.add_parser(
        "recovery-issue", help="Issue operator recovery evidence to a new private file."
    )
    issue.add_argument("--username", required=True)
    issue.add_argument("--output", required=True)
    recover = commands.add_parser(
        "recover", help="Recover an account using one-use evidence."
    )
    recover.add_argument("--credential-file", required=True)
    recover.add_argument(
        "--password-file",
        help="Private file, or - for a protected nonterminal pipe; otherwise prompt securely.",
    )
    return parser


def _line(value: str, limit: int) -> str:
    # Remove only the file's optional line terminator, never password spaces.
    if value.endswith("\n"):
        value = value[:-1]
        if value.endswith("\r"):
            value = value[:-1]
    if (
        not value
        or "\n" in value
        or "\r" in value
        or len(value.encode("utf-8")) > limit
    ):
        raise _CliError()
    return value


def _check_private_descriptor(fd: int, *, allow_pipe: bool = False) -> None:
    info = os.fstat(fd)
    pipe = allow_pipe and stat.S_ISFIFO(info.st_mode)
    # Anonymous pipes have no path another user can open. On macOS their fixed
    # mode is 0660 and cannot be changed; linked FIFOs still require private modes.
    anonymous_pipe = pipe and info.st_nlink == 0
    if (
        not (stat.S_ISREG(info.st_mode) or pipe)
        or info.st_uid != os.getuid()
        or (not anonymous_pipe and stat.S_IMODE(info.st_mode) not in {0o400, 0o600})
    ):
        raise _CliError()


def _private_input(path: str, limit: int) -> str:
    # O_NONBLOCK prevents an attacker-controlled FIFO from hanging before fstat.
    # Fail closed on platforms lacking the descriptor-level no-symlink boundary.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        _check_private_descriptor(fd)
        content = bytearray()
        while len(content) <= limit + 2:
            chunk = os.read(fd, limit + 3 - len(content))
            if not chunk:
                break
            content.extend(chunk)
        if len(content) > limit + 2:
            raise _CliError()
        return _line(content.decode("utf-8"), limit)
    finally:
        os.close(fd)


def _password(path: str | None) -> str:
    if path == "-":
        if sys.stdin.isatty():
            raise _CliError()
        _check_private_descriptor(sys.stdin.fileno(), allow_pipe=True)
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        content = stream.read(1027)
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        return _line(content, 1024)
    if path is not None:
        return _private_input(path, 1024)
    if not sys.stdin.isatty():
        raise _CliError()
    # getpass otherwise falls back to an echoing read on unsupported terminals.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return _line(getpass.getpass("New password: "), 1024)


def _issue_to_file(path: str, issue: Callable[[], IssuedCredential]) -> None:
    target = Path(path)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    info = os.fstat(fd)
    try:
        # A restrictive caller umask must not make the evidence unreadable.
        os.fchmod(fd, 0o600)
        issued = issue()
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            fd = -1
            stream.write(issued.token.get_secret_value() + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        # Delete only our newly reserved inode if issuance or writing failed.
        try:
            current = target.lstat()
            if (current.st_dev, current.st_ino) == (info.st_dev, info.st_ino):
                target.unlink()
        except FileNotFoundError:
            pass
        raise
    finally:
        if fd >= 0:
            os.close(fd)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        init_db()
        service = IdentityService()
        if args.command == "setup":
            _issue_to_file(args.output, service.issue_setup_credential)
        elif args.command == "recovery-issue":
            _issue_to_file(
                args.output, lambda: service.issue_recovery_credential(args.username)
            )
        else:
            token = _private_input(args.credential_file, 128)
            password = _password(args.password_file)
            if args.command == "bootstrap":
                service.bootstrap(token, args.username, password)
            else:
                service.recover(token, password)
        print("Identity operation completed.")
        return 0
    except (Exception, KeyboardInterrupt):
        # Database/OS/validation failures may include bound secrets or paths.
        print("Identity operation failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
