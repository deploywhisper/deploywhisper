"""Build inputs must enforce complete hash locks, rather than decorative flags."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

import yaml


ROOT = Path(__file__).resolve().parents[2]


def requirements(filename: str) -> dict[str, str]:
    content = (ROOT / filename).read_text().replace("\\\n", " ")
    return {
        re.sub(r"[-_.]+", "-", match.group(1).lower()): line.strip()
        for line in content.splitlines()
        if (match := re.match(r"^([\w.-]+)==", line.strip()))
    }


class HashLockedDependenciesTests(unittest.TestCase):
    def test_pip_rejects_tampered_distribution_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "synthetic_lock_probe-1.0-py3-none-any.whl"
            metadata = "synthetic_lock_probe-1.0.dist-info"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr(
                    f"{metadata}/METADATA",
                    "Metadata-Version: 2.1\nName: synthetic-lock-probe\nVersion: 1.0\n",
                )
                archive.writestr(
                    f"{metadata}/WHEEL",
                    "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
                )
                archive.writestr(f"{metadata}/RECORD", "")
            manifest = Path(directory) / "tampered.txt"
            manifest.write_text(
                "synthetic-lock-probe==1.0 --hash=sha256:" + "0" * 64 + "\n"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--dry-run",
                    "--ignore-installed",
                    "--no-index",
                    "--find-links",
                    directory,
                    "--require-hashes",
                    "-r",
                    str(manifest),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DO NOT MATCH THE HASHES", result.stderr)

    def test_runtime_roots_and_tools_are_hash_locked(self) -> None:
        runtime = requirements("requirements.txt")
        dev = requirements("requirements-dev.txt")
        for filename in ("requirements-runtime.txt", "requirements-dev-input.txt"):
            for name, declaration in requirements(filename).items():
                lock = runtime if filename == "requirements-runtime.txt" else dev
                self.assertIn(name, lock)
                self.assertEqual(
                    declaration.split("==")[1], lock[name].split("==")[1].split()[0]
                )
        for lock in (runtime, dev):
            self.assertGreater(len(lock), 15)
            for declaration in lock.values():
                self.assertRegex(declaration, r"--hash=sha256:[0-9a-f]{64}(?:\s|$)")
        for name, declaration in runtime.items():
            self.assertEqual(declaration.split()[0], dev[name].split()[0])
        self.assertIn("python-multipart", runtime)
        for name in (
            "pytest",
            "pytest-cov",
            "httpx",
            "ruff",
            "mypy",
            "pip-audit",
            "bandit",
        ):
            self.assertIn(name, dev)

    def test_packaging_metadata_matches_runtime_roots(self) -> None:
        metadata = (ROOT / "pyproject.toml").read_text()
        dependencies = metadata.split("dependencies = [", 1)[1].split("]", 1)[0]
        declared = set(re.findall(r'"([^"\n]+==[^"\n]+)"', dependencies))
        roots = {
            line.strip()
            for line in (ROOT / "requirements-runtime.txt").read_text().splitlines()
            if line.strip() and not line.startswith("#")
        }
        self.assertEqual(declared, roots)

    def test_workflow_installs_enforce_hashes(self) -> None:
        for filename in ("ci.yml", "release.yml", "publish-skills-registry.yml"):
            workflow = yaml.safe_load(
                (ROOT / ".github/workflows" / filename).read_text()
            )
            installs = []
            for job in workflow["jobs"].values():
                for step in job.get("steps", []):
                    for line in step.get("run", "").splitlines():
                        if re.search(r"\bpip\s+install\b", line):
                            installs.append(line)
                            self.assertIn("--require-hashes", line, filename)
                            self.assertRegex(line, r"-r requirements(?:-dev)?\.txt\b")
                            self.assertNotIn("--upgrade", line)
            self.assertTrue(installs, filename)

    def test_container_installs_cannot_mask_a_hash_failure(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text()
        install = next(
            line for line in dockerfile.splitlines() if "pip install" in line
        )
        self.assertIn("--require-hashes", install)
        install_run = dockerfile[dockerfile.index("RUN python -m pip install") :].split(
            "\n\n", 1
        )[0]
        self.assertNotIn("|| true", install_run)
        for image in re.findall(r"^FROM (\S+)", dockerfile, re.MULTILINE):
            self.assertRegex(image, r"@sha256:[0-9a-f]{64}$")

    def test_locks_retain_python_and_platform_branches(self) -> None:
        content = (ROOT / "requirements.txt").read_text()
        self.assertIn("python_full_version < '3.11'", content)
        self.assertIn("sys_platform == 'win32'", content)
        script = (ROOT / "scripts/lock-dependencies.sh").read_text()
        self.assertIn("--universal", script)
        self.assertIn("--python-version 3.10", script)
        self.assertIn("--generate-hashes", script)


if __name__ == "__main__":
    unittest.main()
