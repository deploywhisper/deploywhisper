"""Exact-source release archives never package dirty checkout contents."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

from scripts.release_artifacts import build_artifacts, validate_release_tag


class ReleaseArtifactsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.repo / "pyproject.toml").write_text(
            '[project]\nname = "deploywhisper"\nversion = "1.4.0rc1"\n'
        )
        (self.repo / "app.py").write_text("print('committed source')\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Synthetic fixture")
        self.sha = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True)

    def build(self, destination, label=None):
        return build_artifacts(
            self.repo,
            self.sha,
            "refs/heads/develop",
            label or f"preview-{self.sha}",
            "example/deploywhisper",
            Path(self.temp.name) / destination,
        )

    def test_archive_uses_exact_commit_and_excludes_untracked_files(self):
        (self.repo / "app.py").write_text("dirty source")
        (self.repo / "secret.env").write_text("untracked")
        output = self.build("dist")
        archive = next(output.glob("*.tar.gz"))
        with tarfile.open(archive) as contents:
            names = contents.getnames()
            self.assertFalse(any(name.endswith("secret.env") for name in names))
            member = next(name for name in names if name.endswith("app.py"))
            self.assertEqual(
                contents.extractfile(member).read(), b"print('committed source')\n"
            )
        manifest = json.loads((output / "source-manifest.json").read_text())
        self.assertEqual(manifest["source_sha"], self.sha)
        self.assertEqual(manifest["version"], "1.4.0rc1")
        self.assertEqual(
            manifest["archive_sha256"], hashlib.sha256(archive.read_bytes()).hexdigest()
        )
        for line in (output / "SHA256SUMS").read_text().splitlines():
            digest, filename = line.split("  ")
            self.assertEqual(
                digest, hashlib.sha256((output / filename).read_bytes()).hexdigest()
            )

    def test_output_is_reproducible_with_zero_gzip_timestamp(self):
        first, second = self.build("first"), self.build("second")
        self.assertEqual(
            {p.name: p.read_bytes() for p in first.iterdir()},
            {p.name: p.read_bytes() for p in second.iterdir()},
        )
        archive = next(first.glob("*.tar.gz")).read_bytes()
        self.assertEqual(archive[4:8], b"\0\0\0\0")
        self.assertTrue(gzip.decompress(archive))

    def test_requires_full_commit_digest_and_matching_preview_label(self):
        with self.assertRaises(ValueError):
            build_artifacts(
                self.repo,
                "HEAD",
                "refs/heads/develop",
                "preview-HEAD",
                "example/deploywhisper",
                self.repo / "out",
            )
        with self.assertRaises(ValueError):
            self.build("bad", "preview-" + "0" * 40)

    def test_source_commit_metadata_wins_over_dirty_metadata(self):
        (self.repo / "pyproject.toml").write_text('[project]\nversion = "0.0.0"\n')
        self.build("release", "v1.4.0-rc.1")
        with self.assertRaises(ValueError):
            self.build("bad-version", "v1.4.0")

    def test_existing_output_cannot_be_overwritten(self):
        output = self.build("existing")
        original = {path.name: path.read_bytes() for path in output.iterdir()}
        with self.assertRaises(ValueError):
            self.build("existing")
        self.assertEqual(
            original, {path.name: path.read_bytes() for path in output.iterdir()}
        )

    def test_missing_commit_cannot_produce_assets(self):
        output = Path(self.temp.name) / "missing"
        with self.assertRaises(subprocess.CalledProcessError):
            build_artifacts(
                self.repo,
                "0" * 40,
                "refs/heads/develop",
                "preview-" + "0" * 40,
                "example/deploywhisper",
                output,
            )
        self.assertFalse(output.exists())

    def test_module_cli_builds_without_runtime_dependencies(self):
        output = Path(self.temp.name) / "cli"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.release_artifacts",
                "build",
                "--repo",
                str(self.repo),
                "--source-sha",
                self.sha,
                "--source-ref",
                "refs/heads/develop",
                "--release",
                f"preview-{self.sha}",
                "--repository",
                "example/deploywhisper",
                "--output-dir",
                str(output),
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=True,
            capture_output=True,
        )
        self.assertTrue((output / "SHA256SUMS").is_file())

    def test_strict_tag_version_validation(self):
        validate_release_tag("v1.3.0", "1.3.0")
        validate_release_tag("v1.4.0-rc.1", "1.4.0rc1")
        for tag, version in [
            ("v1.4.0-rc.1", "1.4.0"),
            ("v1.3.1", "1.3.0"),
            ("../v1.3.0", "1.3.0"),
            ("v01.3.0", "01.3.0"),
        ]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                validate_release_tag(tag, version)


if __name__ == "__main__":
    unittest.main()
