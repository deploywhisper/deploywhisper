"""Actual Git object checkout rejects untrusted sources and inherited execution."""

from __future__ import annotations
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import stat
import tempfile
import unittest
from unittest.mock import patch
from infra_automation.runner.source import (
    SourceRegistration,
    materialize_source,
    tree_digest,
    load_registration,
)


class RunnerSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir(mode=0o700)
        self.git = shutil.which("git")
        self.command("init", "-q")
        self.files = {
            "main.tf": b'resource "null_resource" "fixture" {}',
            "source.lock": b'{"module":"vendored"}',
        }
        for name, raw in self.files.items():
            (self.repo / name).write_bytes(raw)
        self.command("add", ".")
        self.command(
            "-c",
            "user.name=Synthetic",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "fixture",
        )
        self.commit = self.command("rev-parse", "HEAD").strip()
        self.registration = SourceRegistration(
            repository_path=str(self.repo),
            commit=self.commit,
            trust="protected_revision",
            tree_digest=tree_digest(
                {
                    k: "sha256:" + hashlib.sha256(v).hexdigest()
                    for k, v in self.files.items()
                }
            ),
            lock_digests={
                "source.lock": "sha256:"
                + hashlib.sha256(self.files["source.lock"]).hexdigest()
            },
        )
        self.registration_file = self.root / "source-registration.json"
        self.registration = self.protect(self.registration)
        self.output = self.root / "snapshots"
        self.output.mkdir(mode=0o700)
        real_materialize = materialize_source

        def tracked(*args, **kwargs):
            result = real_materialize(*args, **kwargs)
            self.addCleanup(result.close)
            return result

        patcher = patch.object(
            sys.modules[__name__], "materialize_source", side_effect=tracked
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def protect(self, value):
        raw = value.model_dump_json().encode()
        self.registration_file.write_bytes(raw)
        self.registration_file.chmod(0o600)
        return load_registration(
            self.registration_file, "sha256:" + hashlib.sha256(raw).hexdigest()
        )

    def command(self, *args):
        return subprocess.check_output(
            [self.git, "-C", str(self.repo), *args], stderr=subprocess.DEVNULL
        ).decode()

    def test_checkout_is_exact_private_snapshot_without_git_configuration(self):
        snapshot = materialize_source(self.registration, self.output)
        self.assertEqual(
            (snapshot.path / "main.tf").read_bytes(), self.files["main.tf"]
        )
        self.assertFalse((snapshot.path / ".git").exists())
        snapshot.verify()
        self.assertEqual(snapshot.commit, self.commit)
        self.assertEqual(snapshot.digest, self.registration.tree_digest)

    def test_hostile_configs_hooks_helpers_never_execute(self):
        marker = self.root / "executed"
        hook = self.repo / ".git/hooks/post-checkout"
        hook.write_text("#!/bin/sh\ntouch " + str(marker))
        hook.chmod(0o755)
        for key in (
            "core.fsmonitor",
            "core.sshCommand",
            "credential.helper",
            "tar.tar.command",
            "uploadpack.packObjectsHook",
        ):
            self.command("config", key, "!touch " + str(marker))
        hostile = self.root / "hostile"
        hostile.write_text("[alias]\n archive = !touch " + str(marker) + "\n")
        self.command("config", "include.path", str(hostile))
        with patch.dict(
            os.environ,
            {
                "GIT_CONFIG_GLOBAL": str(hostile),
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.fsmonitor",
                "GIT_CONFIG_VALUE_0": "touch " + str(marker),
                "GIT_SSH_COMMAND": "touch " + str(marker),
            },
        ):
            materialize_source(self.registration, self.output).verify()
        self.assertFalse(marker.exists())

    def test_untrusted_commit_option_symlink_and_mutation_deny(self):
        for changes in ({"trust": "pull_request"}, {"commit": "--help"}):
            with self.assertRaises(ValueError):
                materialize_source(
                    self.registration.model_copy(update=changes), self.output
                )
        snapshot = materialize_source(self.registration, self.output)
        target = snapshot.path / "main.tf"
        target.chmod(0o600)
        target.write_text("changed")
        with self.assertRaises(ValueError):
            snapshot.verify()
        (self.repo / "escape").symlink_to("/etc/passwd")
        self.command("add", "escape")
        self.command(
            "-c",
            "user.name=Synthetic",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "symlink",
        )
        bad = self.registration.model_copy(
            update={"commit": self.command("rev-parse", "HEAD").strip()}
        )
        bad = self.protect(bad)
        with self.assertRaises(ValueError):
            materialize_source(bad, self.output)

    def test_alternate_object_store_and_lock_mutation_deny(self):
        alternates = self.repo / ".git/objects/info/alternates"
        alternates.write_text("/outside")
        with self.assertRaises(ValueError):
            materialize_source(self.registration, self.output)
        alternates.unlink()
        bad = self.registration.model_copy(
            update={"lock_digests": {"source.lock": "sha256:" + "0" * 64}}
        )
        bad = self.protect(bad)
        with self.assertRaises(ValueError):
            materialize_source(bad, self.output)

    def test_unprotected_registration_and_registration_substitution_deny(self):
        direct = SourceRegistration.model_validate(self.registration.model_dump())
        with self.assertRaises(ValueError):
            materialize_source(direct, self.output)
        snapshot = materialize_source(self.registration, self.output)
        self.registration_file.write_text("{}")
        with self.assertRaises(ValueError):
            snapshot.verify()

    def test_only_pinned_vendored_modules_are_supported(self):
        from infra_automation.runner.source import _validate_modules

        _validate_modules(
            {
                "main.tf": b'module "child" { source = "./modules/child" }',
                "modules/child/main.tf": b'resource "null_resource" "fixture" {}',
            }
        )
        for source in (
            "https://example.invalid/module",
            "registry/module/aws",
            "../../outside",
            "/etc",
            "${var.source}",
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                _validate_modules(
                    {
                        "main.tf": (
                            'module "child" { source = "' + source + '" }'
                        ).encode()
                    }
                )
        with self.assertRaises(ValueError):
            _validate_modules(
                {
                    "a/main.tf": b'module "b" { source = "../b" }',
                    "b/main.tf": b'module "a" { source = "../a" }',
                }
            )

    def test_object_symlink_hardlink_and_snapshot_symlink_deny(self):
        objects = self.repo / ".git/objects"
        target = next(path for path in objects.rglob("*") if path.is_file())
        alias = objects / "alias"
        alias.symlink_to(target)
        with self.assertRaises(ValueError):
            materialize_source(self.registration, self.output)
        alias.unlink()
        os.link(target, alias)
        with self.assertRaises(ValueError):
            materialize_source(self.registration, self.output)
        alias.unlink()
        snapshot = materialize_source(self.registration, self.output)
        snapshot.path.chmod(0o755)
        victim = snapshot.path / "main.tf"
        victim.unlink()
        victim.symlink_to("/etc/passwd")
        snapshot.path.chmod(0o555)
        with self.assertRaises(ValueError):
            snapshot.verify()

    def test_invalid_json_modules_and_nested_escape_deny(self):
        from infra_automation.runner.source import _validate_modules

        for files in (
            {"main.tf.json": b"{broken"},
            {"main.tf.json": b'{"module":{"child":{"source":"./x"}},"module":{}}'},
            {"a/main.tf": b'module "child" { source = "../../outside" }'},
            {
                "main.tf": b'module "child" { source = "./x" version = "1.0" }',
                "x/main.tf": b"",
            },
        ):
            with self.assertRaises(ValueError):
                _validate_modules(files)
        _validate_modules(
            {"a/main.tf": b'module "child" { source = "../b" }', "b/main.tf": b""}
        )

    def test_parser_is_bounded_and_timeout_kills_and_reaps_child(self):
        import time
        from infra_automation.runner import source

        with self.assertRaises(ValueError):
            source._validate_modules({"main.tf": b" " * 131073})
        with self.assertRaises(ValueError):
            source._validate_modules({"main.tf": b"{" * 10000})
        children = []
        original = source.subprocess.Popen

        def observe(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            return child

        started = time.monotonic()
        with (
            patch.object(source, "_MODULE_VALIDATOR", "import time; time.sleep(30)"),
            patch.object(source.subprocess, "Popen", side_effect=observe),
            self.assertRaises(ValueError),
        ):
            source._validate_modules({"main.tf": b""}, deadline=started + 0.2)
        self.assertLess(time.monotonic() - started, 2)
        self.assertIsNotNone(children[0].returncode)

    def test_snapshot_context_cleanup_and_revoked_registration(self):
        with materialize_source(self.registration, self.output) as snapshot:
            path = snapshot.path
            self.registration_file.write_text("{}")
        self.assertFalse(path.exists())
        self.assertTrue(self.repo.exists())
        self.assertTrue(self.registration_file.exists())
        snapshot.close()

    def test_cleanup_refuses_replaced_root_and_never_follows_symlink(self):
        snapshot = materialize_source(self.registration, self.output)
        original = snapshot.path.with_name(snapshot.path.name + "-original")
        snapshot.path.rename(original)
        snapshot.path.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            snapshot.close()
        self.assertTrue((self.repo / "main.tf").exists())
        snapshot.path.unlink()
        original.rename(snapshot.path)
        snapshot.close()
        self.assertFalse(snapshot.path.exists())

    def test_every_tool_configuration_extension_rejects_escaping_modules(self):
        import json
        from infra_automation.runner.source import _validate_modules

        for suffix in (".tf", ".tf.json", ".tofu", ".tofu.json"):
            content = (
                json.dumps(
                    {"module": {"outside": {"source": "/opt/deploywhisper/source"}}}
                ).encode()
                if suffix.endswith(".json")
                else b'module "outside" { source = "/opt/deploywhisper/source" }'
            )
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                _validate_modules({"main" + suffix: content})

    def test_public_or_group_accessible_staging_is_denied(self):
        for mode in (0o755, 0o750):
            self.output.chmod(mode)
            with self.subTest(mode=oct(mode)), self.assertRaises(ValueError):
                materialize_source(self.registration, self.output)
        self.output.chmod(0o700)

    def test_all_configuration_formats_enforce_byte_and_module_policies(self):
        import json
        from infra_automation.runner.source import _validate_modules

        for suffix in (".tf", ".tf.json", ".tofu", ".tofu.json"):
            for target in (
                "https://example.invalid/module",
                "${var.module}",
                "../../outside",
                "/opt/deploywhisper/source",
            ):
                raw = (
                    json.dumps({"module": {"child": {"source": target}}}).encode()
                    if suffix.endswith(".json")
                    else ('module "child" { source = "' + target + '" }').encode()
                )
                with (
                    self.subTest(suffix=suffix, target=target),
                    self.assertRaises(ValueError),
                ):
                    _validate_modules({"main" + suffix: raw})
            with (
                self.subTest(suffix=suffix, case="oversized"),
                self.assertRaises(ValueError),
            ):
                _validate_modules({"main" + suffix: b" " * 131073})
            root = (
                json.dumps({"module": {"child": {"source": "./child"}}}).encode()
                if suffix.endswith(".json")
                else b'module "child" { source = "./child" }'
            )
            leaf = b"{}" if suffix.endswith(".json") else b""
            with self.subTest(suffix=suffix, case="vendored"):
                _validate_modules({"main" + suffix: root, "child/main" + suffix: leaf})

    def test_staging_replacement_during_admission_cannot_redirect_copies(self):
        from infra_automation.runner import source

        original = source._validate_modules
        moved = self.root / "original-staging"

        def replace(*args, **kwargs):
            original(*args, **kwargs)
            self.output.rename(moved)
            self.output.mkdir(mode=0o700)
            (self.output / "foreign").write_text("untouched")

        with (
            patch.object(source, "_validate_modules", side_effect=replace),
            self.assertRaises(ValueError),
        ):
            materialize_source(self.registration, self.output)
        self.assertEqual((self.output / "foreign").read_text(), "untouched")
        self.assertEqual(list(moved.iterdir()), [])
        self.assertEqual(sorted(p.name for p in self.output.iterdir()), ["foreign"])

    def test_publication_permission_race_keeps_private_envelope_and_cleans(self):
        from infra_automation.runner import source

        original = os.fchmod
        observed = []

        def relax(descriptor, mode):
            if mode == 0o555 and not observed:
                self.output.chmod(0o755)
                envelope = next(self.output.iterdir())
                observed.append(stat.S_IMODE(envelope.stat().st_mode))
            return original(descriptor, mode)

        with (
            patch.object(source.os, "fchmod", side_effect=relax),
            self.assertRaises(ValueError),
        ):
            materialize_source(self.registration, self.output)
        self.assertEqual(observed, [0o700])
        self.assertEqual(list(self.output.iterdir()), [])
        self.output.chmod(0o700)

    def test_parent_replacement_after_publication_preserves_foreign_tree(self):
        snapshot = materialize_source(self.registration, self.output)
        envelope_name = snapshot.path.parent.name
        moved = self.root / "original-staging"
        self.output.rename(moved)
        self.output.mkdir(mode=0o700)
        foreign = self.output / envelope_name / "tree"
        foreign.mkdir(parents=True)
        (foreign / "sentinel").write_text("foreign")
        with self.assertRaises(ValueError):
            snapshot.verify()
        snapshot.close()
        self.assertEqual((foreign / "sentinel").read_text(), "foreign")
        self.assertFalse((moved / envelope_name).exists())

    def test_staging_permission_relaxation_invalidates_snapshot_but_safe_cleanup_remains(
        self,
    ):
        snapshot = materialize_source(self.registration, self.output)
        self.assertEqual(stat.S_IMODE(snapshot.path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(snapshot.path.stat().st_mode), 0o555)
        self.assertEqual(
            stat.S_IMODE((snapshot.path / "main.tf").stat().st_mode), 0o444
        )
        self.output.chmod(0o750)
        with self.assertRaises(ValueError):
            snapshot.verify()
        snapshot.close()
        self.assertEqual(list(self.output.iterdir()), [])
        self.output.chmod(0o700)
