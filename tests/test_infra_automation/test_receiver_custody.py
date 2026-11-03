"""Custody tests use actual protected files and kernel link/permission checks."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

from infra_automation.receiver_custody import (
    ProtectedCustody,
    _publish_directory,
    digest,
)
from infra_automation.receiver_protocol import ReceiverBinding

RAW = b"deploywhisper-synthetic-v1\nmarker only\n"


def binding_for(custody, *, raw=RAW):
    vectors = (
        Path(__file__).resolve().parents[1]
        / "fixtures/infra_automation/qualification/16_0/contracts/valid.json"
    )
    binding = copy.deepcopy(json.loads(vectors.read_text())["receiver"][0]["binding"])
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expiry = (now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    source = {
        "version": 1,
        "kind": "collected",
        "repository_id": "synthetic-repository",
        "commit_sha": "a" * 40,
        "collector_id": "synthetic-collector",
        "profile_digest": digest(b"profile"),
        "screened_transport_digest": binding["screened_artifact_digests"][0],
        "redaction_version": binding["redaction_version"],
        "collected_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_deadline": expiry,
    }
    record = custody.publish("synthetic-plan", raw, source, expiry)
    binding.update(
        authorization_kind="exact_plan",
        evidence_deadline=expiry,
        approval_deadline=expiry,
        provenance={
            "version": 1,
            "authorization_kind": "exact_plan",
            "source": source,
            "custody": record.model_dump(mode="json"),
        },
    )
    return ReceiverBinding.model_validate(binding)


class CustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "custody"
        self.custody = ProtectedCustody(self.root)
        self.binding = binding_for(self.custody)
        self.artifact = self.root / "synthetic-plan" / "artifact"

    def test_original_bytes_and_open_fd_survive_path_replacement(self):
        with self.custody.verify(self.binding) as verified:
            self.assertEqual(verified.data, RAW)
            self.artifact.unlink()
            self.artifact.write_bytes(b"replacement")
            self.assertEqual(os.fstat(verified.fd).st_nlink, 0)
            self.assertEqual(verified.data, RAW)
        with self.assertRaises(ValueError):
            with self.custody.verify(self.binding):
                pass

    @unittest.skipUnless(
        sys.platform.startswith("linux") and os.geteuid() == 0,
        "Linux root is required to qualify independent receiver UIDs",
    )
    def test_linux_kernel_denies_other_uid_and_receiver_uid_retains_access(self):
        # No mocks or preexec hook: subprocess drops real/effective uid, gid,
        # and supplementary groups using the standard library credential API.
        receiver_uid, attacker_uid = 10002, 10003
        parent = Path(self.tmp.name)
        parent.chmod(0o755)
        owned = parent / "uid-isolation"
        owned.mkdir(mode=0o700)
        os.chown(owned, receiver_uid, receiver_uid)
        script = """
import json, os, sys
from pathlib import Path
from infra_automation.receiver_custody import ProtectedCustody
from infra_automation.receiver_protocol import ReceiverBinding
from tests.test_infra_automation.test_receiver_custody import RAW, binding_for
root = Path(sys.argv[1])
mode = sys.argv[2]
if mode == "publish":
    custody = ProtectedCustody(root / "custody")
    binding = binding_for(custody)
    (root / "binding.json").write_text(binding.model_dump_json())
elif mode == "attack":
    try:
        (root / "custody/synthetic-plan/artifact").read_bytes()
    except PermissionError:
        print(json.dumps({"uid": os.getuid(), "denied": True}))
    else:
        raise AssertionError("Foreign UID read protected receiver bytes")
else:
    custody = ProtectedCustody(root / "custody")
    binding = ReceiverBinding.model_validate_json((root / "binding.json").read_text())
    with custody.verify(binding) as verified:
        assert verified.data == RAW
        assert os.fstat(verified.fd).st_uid == os.getuid()
    print(json.dumps({"uid": os.getuid(), "verified": True}))
"""

        def child(uid, mode):
            result = subprocess.run(
                [sys.executable, "-c", script, str(owned), mode],
                user=uid,
                group=uid,
                extra_groups=(),
                cwd=Path(__file__).resolve().parents[2],
                capture_output=True,
                text=True,
                timeout=20,
                check=True,
            )
            return result.stdout

        child(receiver_uid, "publish")
        artifact = owned / "custody/synthetic-plan/artifact"
        self.assertEqual(artifact.stat().st_uid, receiver_uid)
        self.assertEqual(artifact.stat().st_mode & 0o777, 0o400)
        denied = json.loads(child(attacker_uid, "attack"))
        self.assertEqual(denied, {"uid": attacker_uid, "denied": True})
        verified = json.loads(child(receiver_uid, "verify"))
        self.assertEqual(verified, {"uid": receiver_uid, "verified": True})

    def test_kernel_publication_refuses_existing_directory(self):
        root = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.mkdir("new-staging", 0o700, dir_fd=root)
            with self.assertRaises(FileExistsError):
                _publish_directory(root, "new-staging", "synthetic-plan")
            self.assertTrue((self.root / "new-staging").is_dir())
            self.assertEqual(self.artifact.read_bytes(), RAW)
        finally:
            os.close(root)

    def test_no_overwrite(self):
        source = self.binding.provenance.source.model_dump(mode="json")
        with self.assertRaises(FileExistsError):
            self.custody.publish(
                "synthetic-plan", RAW, source, self.binding.evidence_deadline
            )

    def test_real_symlink_hardlink_overwrite_missing_and_replacement_denied(self):
        for mutation in (
            "symlink",
            "hardlink",
            "overwrite",
            "missing",
            "replacement",
            "permissions",
        ):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                custody = ProtectedCustody(Path(directory) / "custody")
                binding = binding_for(custody)
                artifact = custody.root / "synthetic-plan/artifact"
                if mutation == "symlink":
                    artifact.unlink()
                    artifact.symlink_to(self.artifact)
                elif mutation == "hardlink":
                    os.link(artifact, custody.root / "second-link")
                elif mutation == "overwrite":
                    artifact.chmod(0o600)
                    artifact.write_bytes(b"changed")
                    artifact.chmod(0o400)
                elif mutation == "missing":
                    artifact.unlink()
                elif mutation == "replacement":
                    replacement = custody.root / "replacement"
                    replacement.write_bytes(RAW)
                    replacement.chmod(0o400)
                    replacement.replace(artifact)
                else:
                    artifact.chmod(0o644)
                with self.assertRaises((ValueError, OSError)):
                    with custody.verify(binding):
                        pass

    def test_expiry_source_and_digest_mismatch(self):
        for modify in (
            lambda b: b.update(evidence_deadline="2020-01-01T00:00:00Z"),
            lambda b: b["provenance"]["source"].update(repository_id="other"),
            lambda b: b["provenance"]["custody"].update(
                raw_local_digest=digest(b"other")
            ),
        ):
            raw = self.binding.model_dump(mode="json")
            modify(raw)
            with self.assertRaises(ValueError):
                with self.custody.verify(ReceiverBinding.model_validate(raw)):
                    pass
