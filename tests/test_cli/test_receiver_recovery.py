"""Private receiver-recovery CLI adapter; issuer authority is tested separately."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

from cli import automation_operations
from pydantic import SecretStr
from services.identity_service import IssuedCredential


class ReceiverRecoveryCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.token = self.private("human-token", "a" * 43)
        self.csrf = self.private("csrf", "b" * 43)
        self.reason = self.private("reason", "Recover the same completed operation")
        self.output = self.root / "receiver-token"
        self.secret = "receiver-reconcile-v1-" + "c" * 43
        self.calls = []
        self.issuer = ModuleType("services.infra_automation_receiver_recovery")
        self.issuer.issue_credential = self.issue
        issuer_patch = patch.dict(sys.modules, {self.issuer.__name__: self.issuer})
        issuer_patch.start()
        self.addCleanup(issuer_patch.stop)

        @contextmanager
        def credentials(service, token, *, csrf_token, mutation):
            self.assertEqual(token, "a" * 43)
            self.assertEqual(csrf_token, "b" * 43)
            self.assertTrue(mutation)
            yield

        credentials_patch = patch(
            "services.project_service.credential_context", credentials
        )
        credentials_patch.start()
        self.addCleanup(credentials_patch.stop)

    def private(self, name, value):
        target = self.root / name
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(value + "\n")
        return target

    def issue(self, store, operation, reason):
        self.assertEqual(store.control, self.root / "control")
        self.assertEqual(operation, "original-operation")
        self.assertEqual(reason, "Recover the same completed operation")
        self.assertTrue(self.output.exists())
        self.assertEqual(self.output.stat().st_size, 0)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.calls.append(operation)
        return IssuedCredential(
            token=SecretStr(self.secret),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

    def run_cli(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = automation_operations.main(
                [
                    "--control",
                    str(self.root / "control"),
                    "receiver-recovery-issue",
                    "--operation",
                    "original-operation",
                    "--token-file",
                    str(self.token),
                    "--csrf-file",
                    str(self.csrf),
                    "--reason-file",
                    str(self.reason),
                    "--output",
                    str(self.output),
                ]
            )
        self.assertNotIn(self.secret, stdout.getvalue() + stderr.getvalue())
        self.assertNotIn("a" * 43, stdout.getvalue() + stderr.getvalue())
        return result, stdout.getvalue(), stderr.getvalue()

    def test_output_inode_is_private_and_reserved_before_issuance(self):
        result, out, err = self.run_cli()
        self.assertEqual(result, 0)
        self.assertEqual(self.output.read_text().strip(), self.secret)
        self.assertEqual(out.strip(), '{"credential_written": true}')
        self.assertEqual(err, "")
        self.assertEqual(self.calls, ["original-operation"])

    def test_existing_or_symlink_output_never_issues_or_overwrites(self):
        self.output.write_text("existing")
        self.assertEqual(self.run_cli()[0], 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.output.read_text(), "existing")
        self.output.unlink()
        self.output.symlink_to(self.token)
        self.assertEqual(self.run_cli()[0], 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.token.read_text().strip(), "a" * 43)

    def test_issuer_or_publication_failure_removes_only_reserved_output(self):
        with patch.object(
            self.issuer, "issue_credential", side_effect=RuntimeError(self.secret)
        ):
            self.assertEqual(self.run_cli()[0], 1)
        self.assertFalse(self.output.exists())
        with patch("cli.identity.os.fsync", side_effect=OSError(self.secret)):
            self.assertEqual(self.run_cli()[0], 1)
        self.assertFalse(self.output.exists())
        self.assertEqual(len(self.calls), 1)
        self.secret = "receiver-reconcile-v1-" + "d" * 43
        self.assertEqual(self.run_cli()[0], 0)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.output.read_text().strip(), self.secret)

    def test_public_human_credential_input_denies_before_issuance(self):
        self.token.chmod(0o644)
        self.assertEqual(self.run_cli()[0], 1)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
