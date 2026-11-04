"""Actual local custody files with deterministic publication fault injection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from infra_automation import receiver_custody as module
from tests.test_infra_automation.test_receiver_custody import RAW, binding_for


class CollectionCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.custody = module.ProtectedCustody(Path(self.tmp.name) / "custody")
        self.binding = binding_for(self.custody)
        self.source = self.binding.provenance.source.model_dump(mode="json")
        self.expiry = self.binding.evidence_deadline

    def assert_only_original(self):
        self.assertEqual(
            {p.name for p in self.custody.root.iterdir()},
            {".publish.lock", "synthetic-plan"},
        )
        with self.custody.verify(self.binding) as verified:
            self.assertEqual(verified.data, RAW)

    def test_failed_writes_and_rename_leave_no_partial_custody(self):
        original_write = module.write_all
        for point in ("artifact", "metadata", "rename"):
            calls = []

            def write(fd, raw):
                calls.append(fd)
                if len(calls) == (1 if point == "artifact" else 2):
                    os.write(fd, raw[:3])
                    raise OSError(errno.ENOSPC, "synthetic disk full")
                original_write(fd, raw)

            with self.subTest(point=point):
                target = "_publish_directory" if point == "rename" else "write_all"
                behavior = (
                    {"side_effect": OSError(errno.EIO, "synthetic rename failure")}
                    if point == "rename"
                    else {"side_effect": write}
                )
                with patch.object(module, target, **behavior):
                    with self.assertRaises(OSError):
                        self.custody.publish("new-plan", RAW, self.source, self.expiry)
                self.assert_only_original()

    def test_directory_fsync_failure_leaves_no_authoritative_handle(self):
        real_fsync = os.fsync
        for failure_call in (3, 4):
            calls = []

            def fsync(fd):
                calls.append(fd)
                if len(calls) == failure_call:
                    raise OSError(errno.EIO, "synthetic fsync failure")
                return real_fsync(fd)

            with self.subTest(failure_call=failure_call):
                with patch.object(module.os, "fsync", side_effect=fsync):
                    with self.assertRaises(OSError):
                        self.custody.publish("new-plan", RAW, self.source, self.expiry)
                self.assert_only_original()

    def test_expiry_during_write_prevents_publication(self):
        real_write = module.write_all
        later = datetime.now(timezone.utc) + timedelta(hours=2)
        with patch.object(module, "datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime.now(timezone.utc)

            def write(fd, raw):
                real_write(fd, raw)
                clock.now.return_value = later

            with patch.object(module, "write_all", side_effect=write):
                with self.assertRaises(ValueError):
                    self.custody.publish("new-plan", RAW, self.source, self.expiry)
        self.assert_only_original()

    def test_verify_checks_expiry_after_reading_bytes(self):
        real_read = os.read
        later = datetime.now(timezone.utc) + timedelta(hours=2)
        with patch.object(module, "datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime.now(timezone.utc)

            def read(fd, count):
                result = real_read(fd, count)
                clock.now.return_value = later
                return result

            with patch.object(module.os, "read", side_effect=read):
                with self.assertRaises(ValueError):
                    with self.custody.verify(self.binding):
                        self.fail("Expired bytes were admitted")

    def test_file_reads_use_nonblocking_no_follow_opens(self):
        real_open = os.open
        opened = []

        def checked(path, flags, *args, **kwargs):
            if path in ("artifact", "metadata.json"):
                opened.append(path)
                self.assertTrue(flags & os.O_NONBLOCK)
                self.assertTrue(flags & os.O_NOFOLLOW)
            return real_open(path, flags, *args, **kwargs)

        with patch.object(module.os, "open", side_effect=checked):
            with self.custody.verify(self.binding):
                pass
        self.assertEqual(set(opened), {"artifact", "metadata.json"})

    def test_source_freshness_bounds_custody(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        for collected, deadline, expiry in (
            (
                now - timedelta(hours=2),
                now - timedelta(hours=1),
                now + timedelta(minutes=5),
            ),
            (
                now + timedelta(minutes=1),
                now + timedelta(minutes=30),
                now + timedelta(minutes=20),
            ),
            (now, now + timedelta(minutes=10), now + timedelta(minutes=20)),
        ):
            source = dict(
                self.source,
                collected_at=collected.strftime("%Y-%m-%dT%H:%M:%SZ"),
                source_deadline=deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    self.custody.publish(
                        "new-plan", RAW, source, expiry.strftime("%Y-%m-%dT%H:%M:%SZ")
                    )
                self.assert_only_original()

    def test_verified_descriptor_is_positioned_at_original_bytes(self):
        with self.custody.verify(self.binding) as verified:
            self.assertEqual(os.read(verified.fd, len(RAW) + 1), RAW)

    def test_fifo_substitutions_fail_without_waiting_for_a_writer(self):
        for name in ("artifact", "metadata.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                custody = module.ProtectedCustody(Path(directory) / "custody")
                binding = binding_for(custody)
                path = custody.root / "synthetic-plan" / name
                path.unlink()
                os.mkfifo(path, 0o400)
                with self.assertRaises(ValueError):
                    with custody.verify(binding):
                        self.fail("FIFO admitted")

    def test_failed_staging_open_removes_owned_empty_directory(self):
        real_open = os.open

        def open_file(path, flags, *args, **kwargs):
            if isinstance(path, str) and path.startswith(".pending-"):
                raise OSError(errno.EMFILE, "synthetic descriptor limit")
            return real_open(path, flags, *args, **kwargs)

        with patch.object(module.os, "open", side_effect=open_file):
            with self.assertRaises(OSError):
                self.custody.publish("new-plan", RAW, self.source, self.expiry)
        self.assert_only_original()

    def test_cleanup_does_not_remove_substituted_bundle(self):
        real_publish = module._publish_directory

        def replace_pending(root, pending, handle):
            real_publish(root, pending, "held-original")
            os.mkdir(pending, 0o700, dir_fd=root)
            raise OSError(errno.EIO, "synthetic substitution")

        with patch.object(module, "_publish_directory", side_effect=replace_pending):
            with self.assertRaisesRegex(ValueError, "identity changed"):
                self.custody.publish("new-plan", RAW, self.source, self.expiry)
        self.assertEqual(
            (self.custody.root / "held-original/artifact").read_bytes(), RAW
        )
        self.assertEqual(len(list(self.custody.root.glob(".pending-*"))), 1)
        self.assertFalse((self.custody.root / "new-plan").exists())
