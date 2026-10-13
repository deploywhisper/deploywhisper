"""Local identity CLI custody and recovery contracts using synthetic secrets."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cli import identity
from models.database import Base
from models.tables import IdentityAccount
from services.identity_service import IdentityError, IdentityService

# Public input for disposable test accounts, never an operator credential.
# Disk fixtures use this known value directly rather than copying secret state.
SYNTHETIC_CLI_INPUT = "public identity fixture input only"


class IdentityCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = create_engine(f"sqlite:///{self.root / 'identity.db'}")
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.time = datetime(2026, 10, 12, tzinfo=timezone.utc)
        self.service = IdentityService(self.factory, now=lambda: self.time)
        self.password = SYNTHETIC_CLI_INPUT
        self.password_path = self.private_file("password", SYNTHETIC_CLI_INPUT + "\n")
        self.setup_path = self.root / "setup"
        self.init_patch = patch.object(identity, "init_db")
        self.init_mock = self.init_patch.start()
        self.service_patch = patch.object(
            identity, "IdentityService", return_value=self.service
        )
        self.service_patch.start()
        self.addCleanup(self.service_patch.stop)
        self.addCleanup(self.init_patch.stop)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.engine.dispose)

    def private_file(self, name, value):
        path = self.root / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(value)
        return path

    @contextmanager
    def password_pipe(self, content):
        read_fd, write_fd = os.pipe()
        with os.fdopen(write_fd, "wb") as writer:
            writer.write(content)
        with os.fdopen(read_fd, "r", encoding="utf-8") as reader:
            yield reader

    def run_cli(self, *arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = identity.main(list(map(str, arguments)))
        self.assertNotIn(self.password, stdout.getvalue() + stderr.getvalue())
        return result, stdout.getvalue(), stderr.getvalue()

    def bootstrap(self):
        self.assertEqual(self.run_cli("setup", "--output", self.setup_path)[0], 0)
        self.assertEqual(
            self.run_cli(
                "bootstrap",
                "--username",
                "operator",
                "--credential-file",
                self.setup_path,
                "--password-file",
                self.password_path,
            )[0],
            0,
        )

    def browser_service(self):
        return IdentityService(
            self.factory,
            now=lambda: self.time,
            security_profile="https",
            trusted_origin="https://identity.invalid",
        )

    def test_setup_bootstrap_has_private_output_and_replay_denial(self):
        result, out, err = self.run_cli("setup", "--output", self.setup_path)
        self.assertEqual(result, 0)
        token = self.setup_path.read_text().strip()
        self.assertEqual(len(token), 43)
        self.assertEqual(stat.S_IMODE(self.setup_path.stat().st_mode), 0o600)
        self.assertNotIn(token, out + err)
        arguments = (
            "bootstrap",
            "--username",
            "operator",
            "--credential-file",
            self.setup_path,
            "--password-file",
            self.password_path,
        )
        self.assertEqual(self.run_cli(*arguments)[0], 0)
        self.assertEqual(self.run_cli(*arguments)[0], 1)
        with self.factory() as db:
            self.assertEqual(len(list(db.scalars(select(IdentityAccount)))), 1)
        self.init_mock.assert_called()

    def test_recovery_requires_possession_invalidates_session_and_is_one_use(self):
        self.bootstrap()
        browser = self.browser_service()
        issued = browser.login("operator", self.password)
        recovery = self.root / "recovery"
        self.assertEqual(
            self.run_cli(
                "recovery-issue", "--username", "operator", "--output", recovery
            )[0],
            0,
        )
        new_password = self.private_file(
            "replacement", "new synthetic operator password\n"
        )
        arguments = (
            "recover",
            "--credential-file",
            recovery,
            "--password-file",
            new_password,
        )
        forged = self.private_file("forged", "a" * 43)
        self.assertEqual(
            self.run_cli(
                "recover", "--credential-file", forged, "--password-file", new_password
            )[0],
            1,
        )
        self.assertEqual(self.run_cli(*arguments)[0], 0)
        self.assertEqual(self.run_cli(*arguments)[0], 1)
        with self.assertRaises(IdentityError):
            browser.resolve_session(issued.token.get_secret_value())
        browser.login("operator", new_password.read_text().strip())

    def test_setup_and_recovery_exact_expiry(self):
        self.run_cli("setup", "--output", self.setup_path)
        self.time += timedelta(seconds=300)
        self.assertEqual(
            self.run_cli(
                "bootstrap",
                "--username",
                "operator",
                "--credential-file",
                self.setup_path,
                "--password-file",
                self.password_path,
            )[0],
            1,
        )
        self.setup_path.unlink()
        self.bootstrap()
        recovery = self.root / "recovery"
        self.run_cli("recovery-issue", "--username", "operator", "--output", recovery)
        self.time += timedelta(seconds=300)
        self.assertEqual(
            self.run_cli(
                "recover",
                "--credential-file",
                recovery,
                "--password-file",
                self.password_path,
            )[0],
            1,
        )

    def test_existing_output_is_not_overwritten_or_issued(self):
        self.run_cli("setup", "--output", self.setup_path)
        token = self.setup_path.read_text()
        with patch.object(
            self.service,
            "issue_setup_credential",
            wraps=self.service.issue_setup_credential,
        ) as issue:
            self.assertEqual(self.run_cli("setup", "--output", self.setup_path)[0], 1)
            issue.assert_not_called()
        self.assertEqual(self.setup_path.read_text(), token)
        self.assertEqual(
            self.run_cli(
                "bootstrap",
                "--username",
                "operator",
                "--credential-file",
                self.setup_path,
                "--password-file",
                self.password_path,
            )[0],
            0,
        )

    def test_output_symlink_denied_and_failed_issuance_removes_new_file(self):
        target = self.private_file("existing", "unchanged")
        link = self.root / "link"
        link.symlink_to(target)
        self.assertEqual(self.run_cli("setup", "--output", link)[0], 1)
        self.assertEqual(target.read_text(), "unchanged")
        with patch.object(
            self.service,
            "issue_setup_credential",
            side_effect=RuntimeError(self.password),
        ):
            self.assertEqual(self.run_cli("setup", "--output", self.setup_path)[0], 1)
        self.assertFalse(self.setup_path.exists())

    def test_input_rejects_symlink_directory_fifo_and_unsafe_modes(self):
        self.run_cli("setup", "--output", self.setup_path)
        link = self.root / "link"
        link.symlink_to(self.password_path)
        fifo = self.root / "fifo"
        os.mkfifo(fifo, 0o600)
        for path in (link, self.root, fifo):
            with self.subTest(path=path):
                self.assertEqual(
                    self.run_cli(
                        "bootstrap",
                        "--username",
                        "operator",
                        "--credential-file",
                        self.setup_path,
                        "--password-file",
                        path,
                    )[0],
                    1,
                )
        for mode in (0o644, 0o640, 0o660, 0o700, 0o200):
            self.password_path.chmod(mode)
            with self.subTest(mode=mode):
                self.assertEqual(
                    self.run_cli(
                        "bootstrap",
                        "--username",
                        "operator",
                        "--credential-file",
                        self.setup_path,
                        "--password-file",
                        self.password_path,
                    )[0],
                    1,
                )
        self.password_path.chmod(0o400)
        self.assertEqual(
            self.run_cli(
                "bootstrap",
                "--username",
                "operator",
                "--credential-file",
                self.setup_path,
                "--password-file",
                self.password_path,
            )[0],
            0,
        )

    def test_input_requires_current_owner(self):
        self.run_cli("setup", "--output", self.setup_path)
        with patch.object(identity.os, "getuid", return_value=os.getuid() + 1):
            self.assertEqual(
                self.run_cli(
                    "bootstrap",
                    "--username",
                    "operator",
                    "--credential-file",
                    self.setup_path,
                    "--password-file",
                    self.password_path,
                )[0],
                1,
            )

    def test_malformed_and_oversized_input_does_not_consume_setup(self):
        self.run_cli("setup", "--output", self.setup_path)
        for content in (
            b"\xff",
            b"x" * 1025,
            b"x" * 15 + b"\nextra",
            b"x" * 1025 + b"\n",
        ):
            self.password_path.write_bytes(content)
            self.assertEqual(
                self.run_cli(
                    "bootstrap",
                    "--username",
                    "operator",
                    "--credential-file",
                    self.setup_path,
                    "--password-file",
                    self.password_path,
                )[0],
                1,
            )
        self.password_path.write_text(SYNTHETIC_CLI_INPUT)
        self.assertEqual(
            self.run_cli(
                "bootstrap",
                "--username",
                "operator",
                "--credential-file",
                self.setup_path,
                "--password-file",
                self.password_path,
            )[0],
            0,
        )

    def test_password_stdin_is_bounded_non_tty_and_never_echoed(self):
        self.run_cli("setup", "--output", self.setup_path)
        arguments = (
            "bootstrap",
            "--username",
            "operator",
            "--credential-file",
            self.setup_path,
            "--password-file",
            "-",
        )
        with (
            self.password_pipe((self.password + "\n").encode()) as stdin,
            patch.object(identity.sys, "stdin", stdin),
            patch.object(stdin, "isatty", return_value=True),
        ):
            self.assertEqual(self.run_cli(*arguments)[0], 1)
        with (
            self.password_pipe(b"x" * 1025) as stdin,
            patch.object(identity.sys, "stdin", stdin),
        ):
            self.assertEqual(self.run_cli(*arguments)[0], 1)
        with (
            self.password_pipe((self.password + "\n").encode()) as stdin,
            patch.object(identity.sys, "stdin", stdin),
        ):
            self.assertEqual(self.run_cli(*arguments)[0], 0)

    def test_redirected_password_file_enforces_custody_without_consuming_setup(self):
        self.run_cli("setup", "--output", self.setup_path)
        arguments = (
            "bootstrap",
            "--username",
            "operator",
            "--credential-file",
            self.setup_path,
            "--password-file",
            "-",
        )
        for mode in (0o644, 0o640, 0o660, 0o700):
            self.password_path.chmod(mode)
            with (
                self.subTest(mode=mode),
                self.password_path.open() as stdin,
                patch.object(identity.sys, "stdin", stdin),
            ):
                self.assertEqual(self.run_cli(*arguments)[0], 1)
        self.password_path.chmod(0o400)
        with (
            self.password_path.open() as stdin,
            patch.object(identity.sys, "stdin", stdin),
        ):
            self.assertEqual(self.run_cli(*arguments)[0], 0)

    def test_password_stdin_requires_a_current_owner_and_real_supported_descriptor(
        self,
    ):
        with (
            self.password_pipe(self.password.encode()) as stdin,
            patch.object(identity.sys, "stdin", stdin),
            patch.object(identity.os, "getuid", return_value=os.getuid() + 1),
            self.assertRaises(identity._CliError),
        ):
            identity._password("-")
        with patch.object(identity.sys, "stdin", io.StringIO(self.password)):
            with self.assertRaises((identity._CliError, OSError)):
                identity._password("-")
        with open(os.devnull) as stdin, patch.object(identity.sys, "stdin", stdin):
            with self.assertRaises(identity._CliError):
                identity._password("-")
        receiver, sender = socket.socketpair()
        with receiver, sender:
            sender.sendall(self.password.encode())
            sender.shutdown(socket.SHUT_WR)
            with (
                receiver.makefile("r") as stdin,
                patch.object(identity.sys, "stdin", stdin),
            ):
                with self.assertRaises(identity._CliError):
                    identity._password("-")

    def test_password_stdin_accepts_private_files_and_private_named_fifo(self):
        for mode in (0o400, 0o600):
            self.password_path.chmod(mode)
            with (
                self.password_path.open() as stdin,
                patch.object(identity.sys, "stdin", stdin),
            ):
                self.assertEqual(identity._password("-"), self.password)
        fifo = self.root / "stdin-fifo"
        os.mkfifo(fifo, 0o600)
        for mode in (0o600, 0o644, 0o666):
            fifo.chmod(mode)
            read_fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
            with os.fdopen(os.open(fifo, os.O_WRONLY), "wb") as writer:
                writer.write(self.password.encode())
            with (
                os.fdopen(read_fd) as stdin,
                patch.object(identity.sys, "stdin", stdin),
            ):
                if mode == 0o600:
                    self.assertEqual(identity._password("-"), self.password)
                else:
                    with self.assertRaises(identity._CliError):
                        identity._password("-")

    def test_real_cli_private_stdin_and_rejected_public_file_preserve_setup(self):
        environment = {
            **os.environ,
            "DATABASE_URL": f"sqlite:///{self.root / 'subprocess.db'}",
        }

        def invoke(*arguments, **kwargs):
            result = subprocess.run(
                [sys.executable, "-m", "cli.identity", *map(str, arguments)],
                env=environment,
                cwd=Path(__file__).resolve().parents[2],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                **kwargs,
            )
            self.assertNotIn(self.password, result.stdout + result.stderr)
            return result.returncode

        self.assertEqual(invoke("setup", "--output", self.setup_path), 0)
        arguments = (
            "bootstrap",
            "--username",
            "operator",
            "--credential-file",
            self.setup_path,
            "--password-file",
            "-",
        )
        self.password_path.chmod(0o644)
        with self.password_path.open() as stdin:
            self.assertEqual(invoke(*arguments, stdin=stdin), 1)
        self.password_path.chmod(0o600)
        with self.password_path.open() as stdin:
            self.assertEqual(invoke(*arguments, stdin=stdin), 0)
        recovery = self.root / "subprocess-recovery"
        self.assertEqual(
            invoke("recovery-issue", "--username", "operator", "--output", recovery),
            0,
        )
        self.assertEqual(
            invoke(
                "recover",
                "--credential-file",
                recovery,
                "--password-file",
                "-",
                input=self.password + "\n",
            ),
            0,
        )

    def test_default_password_prompt_requires_terminal_and_safe_getpass(self):
        self.run_cli("setup", "--output", self.setup_path)
        arguments = (
            "bootstrap",
            "--username",
            "operator",
            "--credential-file",
            self.setup_path,
        )
        with (
            patch.object(identity.sys, "stdin", io.StringIO()),
            patch.object(identity.getpass, "getpass") as prompt,
        ):
            self.assertEqual(self.run_cli(*arguments)[0], 1)
            prompt.assert_not_called()
        with (
            patch.object(identity.sys.stdin, "isatty", return_value=True),
            patch.object(identity.getpass, "getpass", return_value=self.password),
        ):
            self.assertEqual(self.run_cli(*arguments)[0], 0)

    def test_argument_and_runtime_errors_do_not_print_secrets(self):
        for arguments in (
            ("setup", "--password", self.password),
            (self.password,),
            ("recover",),
            (),
        ):
            result, out, err = self.run_cli(*arguments)
            self.assertEqual(result, 1)
            self.assertEqual(out, "")
            self.assertEqual(err, "Identity operation failed.\n")
        with patch.object(identity, "init_db", side_effect=RuntimeError(self.password)):
            result, out, err = self.run_cli("setup", "--output", self.setup_path)
            self.assertEqual(
                (result, out, err), (1, "", "Identity operation failed.\n")
            )

    def test_secure_prompt_refuses_getpass_echo_fallback(self):
        import warnings

        self.run_cli("setup", "--output", self.setup_path)

        def unsafe_prompt(*args):
            warnings.warn("cannot disable echo", identity.getpass.GetPassWarning)
            self.fail("Unsafe getpass fallback was permitted")

        with (
            patch.object(identity.sys.stdin, "isatty", return_value=True),
            patch.object(identity.getpass, "getpass", side_effect=unsafe_prompt),
        ):
            self.assertEqual(
                self.run_cli(
                    "bootstrap",
                    "--username",
                    "operator",
                    "--credential-file",
                    self.setup_path,
                )[0],
                1,
            )

    def test_output_is_readable_even_under_restrictive_umask(self):
        previous = os.umask(0o777)
        try:
            self.assertEqual(self.run_cli("setup", "--output", self.setup_path)[0], 0)
        finally:
            os.umask(previous)
        self.assertEqual(stat.S_IMODE(self.setup_path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
