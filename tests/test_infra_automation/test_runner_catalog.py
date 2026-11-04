"""Protected catalogs cannot become server-selected commands."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from pydantic import ValidationError
from infra_automation.runner.catalog import (
    CatalogDocument,
    CommandRequest,
    build_argv,
    load_catalog,
)


class RunnerCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name).resolve() / "catalog.json"
        self.value = {
            "version": 1,
            "image_id": "sha256:" + "a" * 64,
            "files": [
                {
                    "path": p,
                    "sha256": "sha256:" + "b" * 64,
                    "kind": "probe" if p.endswith(".py") else "tool",
                }
                for p in (
                    "/usr/local/bin/python",
                    "/usr/local/bin/tofu",
                    "/opt/deploywhisper/probe.py",
                    "/opt/deploywhisper/provider_probe.py",
                    "/opt/deploywhisper/bootstrap.py",
                )
            ],
        }
        self.raw = json.dumps(self.value).encode()
        self.path.write_bytes(self.raw)
        self.path.chmod(0o600)
        self.digest = "sha256:" + hashlib.sha256(self.raw).hexdigest()

    def test_fixed_argv_and_closed_parameters(self):
        catalog = load_catalog(self.path, self.digest)
        self.assertEqual(
            build_argv(
                catalog,
                CommandRequest(command="qualification_probe", mode="environment"),
            ),
            (
                "/usr/local/bin/python",
                "-I",
                "/opt/deploywhisper/probe.py",
                "environment",
            ),
        )
        for value in (
            {"command": "sh"},
            {"command": "tool_version", "argv": ["-destroy"]},
            {"command": "qualification_probe", "mode": "--help"},
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                CommandRequest.model_validate(value)

    def test_mutation_permissions_symlink_and_missing_pin_deny(self):
        self.path.write_text("{}")
        with self.assertRaises(ValueError):
            load_catalog(self.path, self.digest)
        self.path.write_bytes(self.raw)
        self.path.chmod(0o666)
        with self.assertRaises(ValueError):
            load_catalog(self.path, self.digest)
        self.path.chmod(0o600)
        alias = self.path.parent / "alias"
        alias.symlink_to(self.path)
        with self.assertRaises(ValueError):
            load_catalog(alias, self.digest)
        c = CatalogDocument.model_validate(
            {**self.value, "files": self.value["files"][:1]}
        )
        with self.assertRaises(ValueError):
            build_argv(c, CommandRequest(command="qualification_probe", mode="plan"))

    def test_duplicate_fields_and_unsafe_container_paths_deny(self):
        self.path.write_text('{"version":1,"version":1}')
        raw = self.path.read_bytes()
        with self.assertRaises(ValueError):
            load_catalog(self.path, "sha256:" + hashlib.sha256(raw).hexdigest())
        for path in ("/var/run/docker.sock", "/opt/../secret", "-option", "/opt/a\\b"):
            with self.subTest(path=path), self.assertRaises(ValidationError):
                CatalogDocument.model_validate(
                    {
                        **self.value,
                        "files": [
                            {
                                "path": path,
                                "sha256": "sha256:" + "b" * 64,
                                "kind": "tool",
                            }
                        ],
                    }
                )

    def test_watchdog_is_a_fixed_qualification_probe_only(self):
        catalog = load_catalog(self.path, self.digest)
        self.assertEqual(
            build_argv(
                catalog, CommandRequest(command="qualification_probe", mode="watchdog")
            ),
            ("/usr/local/bin/python", "-I", "/opt/deploywhisper/probe.py", "watchdog"),
        )
        with self.assertRaises(ValidationError):
            CommandRequest(command="tool_version", mode="watchdog")

    def test_watchdog_load_is_a_fixed_qualification_probe_only(self):
        catalog = load_catalog(self.path, self.digest)
        self.assertEqual(
            build_argv(
                catalog,
                CommandRequest(command="qualification_probe", mode="watchdog_load"),
            ),
            (
                "/usr/local/bin/python",
                "-I",
                "/opt/deploywhisper/probe.py",
                "watchdog_load",
            ),
        )
        with self.assertRaises(ValidationError):
            CommandRequest(command="tool_version", mode="watchdog_load")

    def test_unsupported_standalone_provider_command_is_not_advertised(self):
        with self.assertRaises(ValidationError):
            CommandRequest(command="provider_probe")
