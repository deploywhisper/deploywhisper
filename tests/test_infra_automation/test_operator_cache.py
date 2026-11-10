"""Bounded offline cache verification never fetches or executes artifacts."""

from __future__ import annotations

import hashlib
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from infra_automation.runner.cache import verify_cache
from infra_automation.runner.cache import main
from unittest.mock import patch


class OperatorCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.cache = self.root / "cache"
        self.cache.mkdir(mode=0o700)
        self.file = self.cache / "tofu"
        self.file.write_bytes(b"synthetic-pinned-tool")
        self.file.chmod(0o600)
        self.manifest = self.root / "pins.json"
        self.document = {
            "version": 1,
            "files": [
                {
                    "path": "tofu",
                    "size": self.file.stat().st_size,
                    "sha256": self.digest(self.file.read_bytes()),
                }
            ],
        }
        self.save()

    def digest(self, raw):
        return "sha256:" + hashlib.sha256(raw).hexdigest()

    def save(self):
        self.manifest.write_text(json.dumps(self.document))
        self.manifest.chmod(0o600)
        self.pin = self.digest(self.manifest.read_bytes())

    def verify(self, **kwargs):
        return verify_cache(self.cache, self.manifest, self.pin, **kwargs)

    def test_exact_private_cache_returns_only_bounded_totals(self):
        self.assertEqual(
            self.verify(),
            {
                "version": 1,
                "files": 1,
                "bytes": self.file.stat().st_size,
                "manifest_digest": self.pin,
            },
        )

    def test_tamper_unlisted_links_and_permissions_deny(self):
        self.file.write_bytes(b"different-same-length")
        with self.assertRaises(ValueError):
            self.verify()
        self.file.write_bytes(b"synthetic-pinned-tool")
        for mode in (0o644, 0o666):
            self.file.chmod(mode)
            with self.assertRaises(ValueError):
                self.verify()
        self.file.chmod(0o600)
        extra = self.cache / "extra"
        extra.write_bytes(b"unlisted")
        with self.assertRaises(ValueError):
            self.verify()
        extra.unlink()
        os.link(self.file, extra)
        with self.assertRaises(ValueError):
            self.verify()
        extra.unlink()
        extra.symlink_to(self.file)
        with self.assertRaises(ValueError):
            self.verify()

    def test_manifest_identity_and_bounds_deny_without_reflecting_content(self):
        with self.assertRaises(ValueError):
            verify_cache(self.cache, self.manifest, "sha256:" + "0" * 64)
        with self.assertRaises(ValueError):
            self.verify(max_bytes=1)
        for value in (0, True, 1073741825):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.verify(max_bytes=value)
        for path in ("../tofu", "/tofu", "a//tofu", "secret\nname"):
            self.document["files"][0]["path"] = path
            self.save()
            with self.assertRaisesRegex(ValueError, "Offline cache unavailable"):
                self.verify()

    def test_empty_duplicates_and_unknown_fields_deny(self):
        entry = dict(self.document["files"][0])
        for files in (
            [],
            [entry, entry],
            [{**entry, "command": "execute"}],
            [{**entry, "size": True}],
        ):
            self.document["files"] = files
            self.save()
            with self.assertRaises(ValueError):
                self.verify()

    def test_nested_private_cache_and_directory_bounds(self):
        nested = self.cache / "providers"
        nested.mkdir(mode=0o700)
        self.file.rename(nested / "tofu")
        self.document["files"][0]["path"] = "providers/tofu"
        self.save()
        self.assertEqual(self.verify()["files"], 1)
        nested.chmod(0o755)
        with self.assertRaises(ValueError):
            self.verify()

    def test_fifo_and_replaced_file_deny(self):
        original = self.file.read_bytes()
        self.file.unlink()
        os.mkfifo(self.file, 0o600)
        with self.assertRaises(ValueError):
            self.verify()
        self.file.unlink()
        self.file.write_bytes(original)
        self.file.chmod(0o600)
        real_read = os.read
        replaced = False

        def replace_after_read(fd, maximum):
            nonlocal replaced
            value = real_read(fd, maximum)
            if not replaced:
                replacement = self.cache / "replacement"
                replacement.write_bytes(original)
                replacement.chmod(0o600)
                replacement.replace(self.file)
                replaced = True
            return value

        with patch(
            "infra_automation.runner.cache.os.read", side_effect=replace_after_read
        ):
            with self.assertRaises(ValueError):
                self.verify()

    def test_cli_failure_never_reflects_arguments(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(main(["--unknown-synthetic-secret"]), 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn("synthetic-secret", stderr.getvalue())
