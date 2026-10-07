"""Release version, non-overwrite, downgrade and workflow ordering regressions."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts.release_policy import (
    guard_publication,
    registry_exists,
    validate_tag,
    version_key,
    main,
    verify_remote_tag,
)

ROOT = Path(__file__).resolve().parents[2]


class ReleasePolicyTests(unittest.TestCase):
    @patch("scripts.release_policy.subprocess.check_output")
    def test_remote_tag_accepts_lightweight_and_peeled_annotated_commits(self, output):
        source = "a" * 40
        for response in (
            f"{source}\trefs/tags/v1.4.0\n",
            f"{'b' * 40}\trefs/tags/v1.4.0\n{source}\trefs/tags/v1.4.0^{{}}\n",
        ):
            output.return_value = response
            verify_remote_tag("v1.4.0", source)
        self.assertEqual(
            output.call_args.args[0],
            [
                "git",
                "ls-remote",
                "--exit-code",
                "--",
                "origin",
                "refs/tags/v1.4.0",
                "refs/tags/v1.4.0^{}",
            ],
        )

    @patch("scripts.release_policy.subprocess.check_output")
    def test_remote_tag_rejects_moved_missing_malformed_and_network_errors(
        self, output
    ):
        source = "a" * 40
        for response in (
            "",
            f"{'b' * 40}\trefs/tags/v1.4.0\n",
            f"{source}\trefs/tags/v1.4.0\n{'b' * 40}\trefs/tags/v1.4.0^{{}}\n",
            f"{source}\trefs/tags/other\n",
            "malformed",
        ):
            output.return_value = response
            with self.assertRaises(ValueError):
                verify_remote_tag("v1.4.0", source)
        for status in (2, 128):
            output.side_effect = subprocess.CalledProcessError(
                status, ["git", "ls-remote"]
            )
            with self.assertRaises(subprocess.CalledProcessError):
                verify_remote_tag("v1.4.0", source)

    def test_remote_tag_checks_real_local_lightweight_and_annotated_tags(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["git", "init", "-q", directory], check=True)
            command = [
                "git",
                "-C",
                directory,
                "-c",
                "user.name=Release test",
                "-c",
                "user.email=release-test@example.invalid",
                "-c",
                "commit.gpgsign=false",
            ]
            subprocess.run(
                [
                    *command,
                    "commit",
                    "--allow-empty",
                    "-qm",
                    "Synthetic release source",
                ],
                check=True,
            )
            source = subprocess.check_output(
                ["git", "-C", directory, "rev-parse", "HEAD"], text=True
            ).strip()
            subprocess.run([*command, "tag", "v1.4.0"], check=True)
            subprocess.run(
                [*command, "tag", "-a", "v1.4.1", "-m", "Synthetic annotated tag"],
                check=True,
            )
            verify_remote_tag("v1.4.0", source, directory)
            verify_remote_tag("v1.4.1", source, directory)
            with self.assertRaisesRegex(ValueError, "moved"):
                verify_remote_tag("v1.4.0", "a" * 40, directory)
            with self.assertRaises(subprocess.CalledProcessError):
                verify_remote_tag("v1.4.2", source, directory)

    def test_cli_uses_existing_tomli_when_tomllib_is_unavailable(self):
        import tomli

        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory) / "pyproject.toml"
            metadata.write_text('[project]\nversion = "1.4.0rc1"\n')
            args = [
                "release_policy.py",
                "validate",
                "--tag",
                "v1.4.0-rc.1",
                "--metadata",
                str(metadata),
            ]
            with (
                patch.dict(sys.modules, {"tomllib": None, "tomli": tomli}),
                patch.object(sys, "argv", args),
                patch("builtins.print") as output,
            ):
                main()
            self.assertEqual(
                output.call_args_list[1].args, ("image_version=1.4.0-rc.1",)
            )
            self.assertEqual(output.call_args_list[2].args, ("is_prerelease=true",))

    def test_metadata_must_match_full_stable_or_prerelease(self):
        for tag, metadata in (
            ("v1.3.0", "1.3.0"),
            ("v1.4.0-rc.1", "1.4.0rc1"),
            ("v1.4.0-rc.1", "1.4.0-rc.1"),
            ("v1.4.0-beta.2", "1.4.0b2"),
        ):
            self.assertEqual(validate_tag(tag, metadata), tag[1:])
        for tag, metadata in (
            ("v1.4.0-rc.1", "1.4.0"),
            ("v1.4.0", "1.4.0rc1"),
            ("1.3.0", "1.3.0"),
        ):
            with self.assertRaises(ValueError):
                validate_tag(tag, metadata)

    def test_reject_noncanonical_or_unsafe_versions(self):
        for value in (
            "01.2.3",
            "1.02.3",
            "1.2.3-rc.01",
            "1.2.3-rc",
            "1.2.3+build",
            "1.2.3\n",
            "1.2",
            "1.2.3;echo unsafe",
        ):
            with self.assertRaises(ValueError):
                version_key(value)

    def test_numeric_and_prerelease_order(self):
        self.assertLess(version_key("1.9.0"), version_key("1.10.0"))
        self.assertLess(version_key("1.4.0-rc.9"), version_key("1.4.0-rc.10"))
        self.assertLess(version_key("1.4.0-rc.10"), version_key("1.4.0"))

    def test_existing_release_including_draft_refuses_replacement(self):
        for draft in (True, False):
            with self.assertRaisesRegex(ValueError, "already exists"):
                guard_publication(
                    "1.4.0",
                    [{"tag_name": "v1.4.0", "draft": draft, "prerelease": False}],
                    None,
                )

    def test_stable_alias_downgrade_checks_both_sources(self):
        with self.assertRaisesRegex(ValueError, "downgrade"):
            guard_publication("1.9.0", [], "1.10.0")
        with self.assertRaisesRegex(ValueError, "downgrade"):
            guard_publication(
                "1.9.0",
                [{"tag_name": "v1.10.0", "draft": False, "prerelease": False}],
                "1.8.0",
            )
        guard_publication("1.4.0-rc.1", [], "1.5.0")
        guard_publication("1.10.1", [], "1.10.0")
        with self.assertRaises(ValueError):
            guard_publication("1.10.1", [], "")

    @patch("scripts.release_policy.subprocess.run")
    def test_registry_absence_is_distinguished_from_errors(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, stderr="manifest unknown")
        self.assertFalse(registry_exists("ghcr.io/example/test:1.0.0"))
        for error in (
            "unauthorized",
            "connection timed out",
            "503 Service Unavailable",
        ):
            run.return_value = subprocess.CompletedProcess([], 1, stderr=error)
            with self.assertRaises(ValueError):
                registry_exists("ghcr.io/example/test:1.0.0")
        run.return_value = subprocess.CompletedProcess([], 0)
        self.assertTrue(registry_exists("ghcr.io/example/test:1.0.0"))


class ReleaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.safe_load(
            (ROOT / ".github/workflows/release.yml").read_text()
        )

    def test_candidate_only_build_and_digest_smoke_precede_signing(self):
        steps = self.workflow["jobs"]["docker"]["steps"]
        build = next(step for step in steps if step.get("id") == "build")
        self.assertIn(
            "candidate-${{ github.run_id }}-${{ github.run_attempt }}",
            build["with"]["tags"],
        )
        smoke = next(step for step in steps if step["name"].startswith("Smoke test"))
        attest = next(step for step in steps if step.get("id") == "attest")
        self.assertIn('"$IMAGE@$DIGEST"', smoke["run"])
        self.assertLess(steps.index(smoke), steps.index(attest))
        self.assertEqual(
            attest["uses"], "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6"
        )
        verify = next(step for step in steps if step["name"].startswith("Verify OCI"))
        for constraint in (
            "--bundle-from-oci",
            "--signer-workflow",
            "--source-digest",
            "--source-ref",
            "--deny-self-hosted-runners",
        ):
            self.assertIn(constraint, verify["run"])

    def test_promotion_waits_for_source_and_image_and_guards_reruns(self):
        release = self.workflow["jobs"]["release"]
        self.assertEqual(set(release["needs"]), {"validate", "docker", "artifacts"})
        self.assertFalse(self.workflow["concurrency"]["cancel-in-progress"])
        self.assertEqual(self.workflow["concurrency"]["queue"], "max")
        steps = release["steps"]
        verify = next(
            step for step in steps if step["name"].startswith("Verify source")
        )
        guard = next(
            step for step in steps if step["name"].startswith("Recheck publication")
        )
        publish = next(
            step for step in steps if step["name"].startswith("Create new release")
        )
        promote = next(
            step for step in steps if step["name"].startswith("Promote verified")
        )
        self.assertLess(steps.index(verify), steps.index(guard))
        self.assertLess(steps.index(guard), steps.index(publish))
        self.assertLess(steps.index(publish), steps.index(promote))
        self.assertNotIn("--clobber", publish["run"])
        self.assertLess(
            publish["run"].index("verify-remote-tag"),
            publish["run"].index("gh release create"),
        )
        self.assertNotIn("notify", self.workflow["jobs"])

    def test_required_ci_summary_rejects_failed_cancelled_skipped_and_missing_gates(
        self,
    ):
        import json
        import os
        import sys

        ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        step = next(
            s
            for s in ci["jobs"]["report"]["steps"]
            if s["name"] == "Determine overall CI result"
        )
        script = step["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        names = (
            "quality",
            "security",
            "frontend",
            "test",
            "docker",
            "migration",
            "changed-tests",
        )
        success = {name: {"result": "success"} for name in names}
        cases = [("pull_request", success, True)]
        for name in names:
            for state in ("failure", "cancelled", "skipped", "missing"):
                data = {key: dict(value) for key, value in success.items()}
                data[name] = {} if state == "missing" else {"result": state}
                cases.append(("pull_request", data, False))
        push = {key: dict(value) for key, value in success.items()}
        push["changed-tests"]["result"] = "skipped"
        cases.append(("push", push, True))
        for event, data, accepted in cases:
            with self.subTest(event=event, states=data):
                result = subprocess.run(
                    [sys.executable, "-c", script],
                    env={
                        **os.environ,
                        "NEEDS_JSON": json.dumps(data),
                        "EVENT_NAME": event,
                    },
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    result.returncode == 0, accepted, result.stdout + result.stderr
                )

    def test_docker_runtime_metadata_has_safe_existing_default(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertIn("ARG BUILD_VERSION=1.4.0", dockerfile)
        self.assertIn('APP_VERSION="${BUILD_VERSION}"', dockerfile)
        self.assertIn('org.opencontainers.image.revision="${BUILD_SHA}"', dockerfile)
