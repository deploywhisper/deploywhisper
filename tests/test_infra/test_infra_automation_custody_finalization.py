"""Bounded fault injection for disposable saved-plan publication."""

from __future__ import annotations

import errno
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock


FIXTURES = (
    Path(__file__).resolve().parents[1] / "fixtures/infra_automation/qualification/16_0"
)
receiver_spec = importlib.util.spec_from_file_location(
    "receiver", FIXTURES / "receiver/prototype.py"
)
receiver = importlib.util.module_from_spec(receiver_spec)
receiver_spec.loader.exec_module(receiver)
spec = importlib.util.spec_from_file_location(
    "custody_finalization_probe", FIXTURES / "real_custody/probe.py"
)
probe = importlib.util.module_from_spec(spec)
with mock.patch.dict(sys.modules, {"receiver": receiver}):
    spec.loader.exec_module(probe)


class CustodyFinalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = b"synthetic saved plan\x00" * 100
        for patcher in (
            mock.patch.object(probe, "ROOT", self.root),
            mock.patch.object(probe, "OWNER_UID", os.getuid(), create=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        original_read = Path.read_bytes

        def staging_read(path):
            if path == Path("/staging/original.plan"):
                return self.raw
            return original_read(path)

        patcher = mock.patch.object(Path, "read_bytes", staging_read)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_enospc_after_key_creation_allows_retry_without_published_partial(self):
        original_open = os.open

        def full_disk(path, flags, *args, **kwargs):
            if re.fullmatch("[0-9a-f]{64}", Path(path).name):
                raise OSError(errno.ENOSPC, "injected ciphertext creation failure")
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(probe.os, "open", side_effect=full_disk):
            with self.assertRaises(OSError) as caught:
                probe.finalize()
        self.assertEqual(caught.exception.errno, errno.ENOSPC)
        self.assertFalse((self.root / "key").exists())
        self.assertFalse((self.root / "finalized").exists())
        record = probe.finalize()
        self.assertEqual(probe.read(record), self.raw)

    def test_interrupted_record_creation_allows_retry(self):
        original_open = os.open

        def interrupted(path, flags, *args, **kwargs):
            if Path(path).name == "record.json":
                raise InterruptedError("injected record publication interruption")
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(probe.os, "open", side_effect=interrupted):
            with self.assertRaises(InterruptedError):
                probe.finalize()
        self.assertFalse((self.root / "finalized").exists())
        record = probe.finalize()
        self.assertEqual(probe.read(record), self.raw)

    def test_short_writes_preserve_all_original_bytes(self):
        original_write = os.write
        with mock.patch.object(
            probe.os, "write", side_effect=lambda fd, body: original_write(fd, body[:7])
        ):
            record = probe.finalize()
        self.assertEqual(probe.read(record), self.raw)
        self.assertEqual(record["raw_digest"], hashlib.sha256(self.raw).hexdigest())

    def test_second_finalize_denied_and_original_bytes_unchanged(self):
        record = probe.finalize()
        self.raw = b"different plan"
        with self.assertRaises(FileExistsError):
            probe.finalize()
        self.assertEqual(
            hashlib.sha256(probe.read(record)).hexdigest(), record["raw_digest"]
        )

    def test_zero_length_write_denies_and_retry_recovers(self):
        with mock.patch.object(probe.os, "write", return_value=0):
            with self.assertRaises(OSError) as caught:
                probe.finalize()
        self.assertEqual(caught.exception.errno, errno.EIO)
        self.assertFalse((self.root / "finalized").exists())
        self.assertFalse((self.root / ".pending").exists())
        self.assertEqual(probe.read(probe.finalize()), self.raw)

    def test_interrupted_write_retries_before_publication(self):
        original_write = os.write
        interrupted = False

        def write(fd, body):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise InterruptedError()
            return original_write(fd, body)

        with mock.patch.object(probe.os, "write", side_effect=write):
            record = probe.finalize()
        self.assertEqual(probe.read(record), self.raw)

    def test_failed_directory_publication_removes_staging_and_allows_retry(self):
        with mock.patch.object(probe.os, "rename", side_effect=InterruptedError):
            with self.assertRaises(InterruptedError):
                probe.finalize()
        self.assertFalse((self.root / ".pending").exists())
        self.assertFalse((self.root / "finalized").exists())
        self.assertEqual(probe.read(probe.finalize()), self.raw)

    def test_error_after_publication_keeps_complete_original_and_denies_retry(self):
        def fail_after_publication(point):
            if point == "after_publish":
                raise OSError(errno.EIO, "injected after publication")

        with self.assertRaises(OSError):
            probe.finalize(fail_after_publication)
        record = probe.load_record()
        self.assertEqual(probe.read(record), self.raw)
        with self.assertRaises(FileExistsError):
            probe.finalize()

    def test_abandoned_pending_directory_is_discarded_on_retry(self):
        pending = self.root / ".pending"
        pending.mkdir(mode=0o700)
        (pending / "key").write_bytes(b"partial abandoned attempt")
        (pending / "key").chmod(0o400)
        record = probe.finalize()
        self.assertEqual(probe.read(record), self.raw)
        self.assertFalse(pending.exists())

    def test_symlink_bundle_record_and_key_are_denied(self):
        record = probe.finalize()
        published = self.root / "finalized"
        for filename in ("record.json", "key", record["handle"]):
            path = published / filename
            original = path.read_bytes()
            path.unlink()
            path.symlink_to(self.root / "absent")
            try:
                with self.subTest(filename=filename), self.assertRaises(OSError):
                    if filename == "record.json":
                        probe.load_record()
                    else:
                        probe.read(record)
            finally:
                path.unlink()
                path.write_bytes(original)
                path.chmod(0o400)
        published.rename(self.root / "original")
        published.symlink_to(self.root / "original", target_is_directory=True)
        with self.assertRaises(OSError):
            probe.read(record)


if __name__ == "__main__":
    unittest.main()
