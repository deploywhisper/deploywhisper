"""Exercise reviewed analytics updates against real Git history and mocked PR calls."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

from scripts import prepare_analytics_update as update


ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class ReviewedAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.remote = root / "remote.git"
        self.checkout = root / "checkout"
        self.snapshot = root / "snapshot.json"
        self.snapshot.write_text('{"skills": {"terraform": 2}}\n')
        self.command("git", "init", "--bare", str(self.remote))
        self.command("git", "init", "-b", "develop", str(self.checkout))
        self.command("git", "config", "user.name", "Synthetic owner", cwd=self.checkout)
        self.command(
            "git", "config", "user.email", "owner@example.invalid", cwd=self.checkout
        )
        (self.checkout / "data").mkdir()
        (self.checkout / update.METRICS).write_text('{"skills": {}}\n')
        (self.checkout / "trusted.py").write_text("# trusted code\n")
        self.commit("Initial trusted source")
        self.command(
            "git", "remote", "add", "origin", str(self.remote), cwd=self.checkout
        )
        self.command("git", "push", "origin", "develop", cwd=self.checkout)
        self.gh_calls = []

    @staticmethod
    def command(*args, cwd=None):
        return subprocess.run(
            args, cwd=cwd, check=True, capture_output=True, text=True
        ).stdout.strip()

    def commit(self, message):
        self.command("git", "add", ".", cwd=self.checkout)
        self.command("git", "commit", "-m", message, cwd=self.checkout)

    def propose(self, pulls=(), rules=None, gh_effect=None):
        original = update.run

        def mocked_run(*args, **kwargs):
            if args[0] == "gh":
                self.gh_calls.append(args)
                if gh_effect:
                    gh_effect(args)
                if args[1] == "api":
                    return json.dumps(
                        rules
                        if rules is not None
                        else [{"type": "update"}, {"type": "deletion"}]
                    )
                return json.dumps(pulls) if args[1:3] == ("pr", "list") else ""
            return original(*args, **kwargs)

        with working_directory(self.checkout), patch.object(update, "run", mocked_run):
            return update.propose("synthetic/example", "develop", self.snapshot)

    def remote_commit(self, ref):
        return self.command("git", "--git-dir", str(self.remote), "rev-parse", ref)

    def remote_racing_commit(self, tree, parent):
        return self.command(
            "git",
            "-c",
            "user.name=Synthetic racer",
            "-c",
            "user.email=racer@example.invalid",
            "--git-dir",
            str(self.remote),
            "commit-tree",
            tree,
            "-p",
            parent,
            "-m",
            "Concurrent synthetic update",
        )

    def test_creates_only_metrics_change_and_leaves_trusted_checkout(self):
        default = self.remote_commit("develop")
        self.assertTrue(self.propose())
        proposed = self.remote_commit(update.BRANCH)
        paths = self.command(
            "git", "diff", "--name-only", default, proposed, cwd=self.checkout
        )
        self.assertEqual(paths, update.METRICS)
        self.assertEqual(self.remote_commit("develop"), default)
        self.assertEqual(
            self.command("git", "branch", "--show-current", cwd=self.checkout),
            "develop",
        )
        self.assertEqual((self.checkout / "trusted.py").read_text(), "# trusted code\n")
        self.assertTrue(any(call[1:3] == ("pr", "create") for call in self.gh_calls))
        self.assertEqual(
            [call for call in self.gh_calls if call[1:3] == ("workflow", "run")],
            [
                (
                    "gh",
                    "workflow",
                    "run",
                    workflow,
                    "--repo",
                    "synthetic/example",
                    "--ref",
                    update.CI_BRANCH_PREFIX + proposed,
                )
                for workflow in ("ci.yml", "codeql.yml", "clusterfuzzlite.yml")
            ],
        )
        created = next(
            i for i, call in enumerate(self.gh_calls) if call[1:3] == ("pr", "create")
        )
        dispatched = [
            i
            for i, call in enumerate(self.gh_calls)
            if call[1:3] == ("workflow", "run")
        ]
        self.assertTrue(all(i > created for i in dispatched))
        self.assertEqual(
            self.remote_commit(update.CI_BRANCH_PREFIX + proposed), proposed
        )
        self.assertFalse(
            any(
                "--force" in call or "--auto" in call or "review" in call
                for call in self.gh_calls
            )
        )

    def test_existing_branch_fast_forwards_and_retains_new_default_code(self):
        self.propose()
        previous = self.remote_commit(update.BRANCH)
        (self.checkout / "trusted.py").write_text("# newer trusted code\n")
        self.commit("Advance trusted default")
        self.command("git", "push", "origin", "develop", cwd=self.checkout)
        self.snapshot.write_text('{"skills": {"terraform": 3}}\n')
        self.assertTrue(self.propose(pulls=[{"number": 7}]))
        proposed = self.remote_commit(update.BRANCH)
        self.command(
            "git", "merge-base", "--is-ancestor", previous, proposed, cwd=self.checkout
        )
        self.assertEqual(
            self.command("git", "show", proposed + ":trusted.py", cwd=self.checkout),
            "# newer trusted code",
        )
        self.assertTrue(any(call[1:4] == ("pr", "edit", "7") for call in self.gh_calls))
        self.assertEqual(
            self.command(
                "git", "diff", "--name-only", "develop", proposed, cwd=self.checkout
            ),
            update.METRICS,
        )

    def test_refuses_branch_with_unreviewed_code_without_executing_it(self):
        self.command("git", "checkout", "-b", update.BRANCH, cwd=self.checkout)
        (self.checkout / "trusted.py").write_text(
            "raise RuntimeError('never execute branch code')\n"
        )
        self.commit("Synthetic unreviewed code")
        self.command("git", "push", "origin", update.BRANCH, cwd=self.checkout)
        malicious = self.remote_commit(update.BRANCH)
        self.command("git", "checkout", "develop", cwd=self.checkout)
        with self.assertRaisesRegex(ValueError, "outside the metrics"):
            self.propose()
        self.assertEqual(self.remote_commit(update.BRANCH), malicious)
        self.assertEqual(self.gh_calls, [])

    def test_repeated_snapshot_reuses_commit_and_existing_pr(self):
        self.propose()
        previous = self.remote_commit(update.BRANCH)
        self.assertTrue(self.propose(pulls=[{"number": 7}]))
        self.assertEqual(self.remote_commit(update.BRANCH), previous)

    def test_unprotected_ci_namespace_fails_before_push_or_pr(self):
        with self.assertRaisesRegex(
            ValueError, "protected against updates and deletion"
        ):
            self.propose(rules=[{"type": "deletion"}])
        self.assertEqual(
            self.command(
                "git", "--git-dir", str(self.remote), "branch", "--list", "feature/*"
            ),
            "",
        )
        self.assertFalse(any(call[1] in {"pr", "workflow"} for call in self.gh_calls))

    def test_existing_incorrect_ci_ref_is_rejected(self):
        self.propose()
        validated = self.remote_commit(update.BRANCH)
        self.command(
            "git",
            "--git-dir",
            str(self.remote),
            "update-ref",
            "refs/heads/" + update.CI_BRANCH_PREFIX + validated,
            self.remote_commit("develop"),
        )
        self.gh_calls.clear()
        with self.assertRaisesRegex(ValueError, "does not match the validated commit"):
            self.propose()
        self.assertFalse(any(call[1] in {"pr", "workflow"} for call in self.gh_calls))

    def test_racing_pr_branch_does_not_change_dispatched_commit(self):
        validated = None
        raced = None

        def race_after_pr_created(args):
            nonlocal validated, raced
            if args[1:3] != ("pr", "create"):
                return
            validated = self.remote_commit(update.BRANCH)
            raced = self.remote_racing_commit(
                self.remote_commit("develop^{tree}"), validated
            )
            self.command(
                "git",
                "--git-dir",
                str(self.remote),
                "update-ref",
                "refs/heads/" + update.BRANCH,
                raced,
            )

        self.assertTrue(self.propose(gh_effect=race_after_pr_created))
        self.assertNotEqual(validated, raced)
        self.assertEqual(self.remote_commit(update.BRANCH), raced)
        dispatched = [
            call[-1] for call in self.gh_calls if call[1:3] == ("workflow", "run")
        ]
        self.assertEqual(dispatched, [update.CI_BRANCH_PREFIX + validated] * 3)
        self.assertEqual(self.remote_commit(dispatched[0]), validated)

    def test_unchanged_and_invalid_snapshots_never_create_pr(self):
        self.snapshot.write_text((self.checkout / update.METRICS).read_text())
        self.assertFalse(self.propose())
        self.snapshot.write_text("[]")
        with self.assertRaisesRegex(ValueError, "JSON object"):
            self.propose()
        self.assertEqual(self.gh_calls, [])

    def test_symlink_snapshot_or_output_is_rejected(self):
        target = self.snapshot.with_name("target.json")
        target.write_text(self.snapshot.read_text())
        self.snapshot.unlink()
        self.snapshot.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            self.propose()
        self.snapshot.unlink()
        self.snapshot.write_text(target.read_text())
        output = self.checkout / update.METRICS
        output.unlink()
        output.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            self.propose()
        self.assertEqual(self.gh_calls, [])

    def test_symlink_data_directory_is_rejected(self):
        data = self.checkout / "data"
        moved = self.checkout / "synthetic-target"
        data.rename(moved)
        data.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            self.propose()
        self.assertEqual(self.gh_calls, [])

    def test_concurrent_branch_change_is_rejected_without_force_push(self):
        self.propose()
        previous = self.remote_commit(update.BRANCH)
        self.snapshot.write_text('{"skills": {"terraform": 4}}\n')
        original_git = update.git
        pushes = []

        def racing_git(*args, **kwargs):
            if args[0] == "push" and args[-1].endswith(":refs/heads/" + update.BRANCH):
                pushes.append(args)
                competing = self.remote_racing_commit(
                    self.remote_commit(previous + "^{tree}"), previous
                )
                self.command(
                    "git",
                    "--git-dir",
                    str(self.remote),
                    "update-ref",
                    "refs/heads/" + update.BRANCH,
                    competing,
                )
            return original_git(*args, **kwargs)

        with (
            patch.object(update, "git", racing_git),
            self.assertRaises(subprocess.CalledProcessError) as rejected,
        ):
            self.propose()
        self.assertTrue(pushes)
        self.assertEqual(rejected.exception.cmd[3], "push")
        self.assertIn("rejected", rejected.exception.stderr)
        self.assertFalse(
            any("force" in argument for args in pushes for argument in args)
        )

    def test_workflow_keeps_read_only_snapshot_and_opt_in_pr_privileges(self):
        workflow = yaml.load(
            (ROOT / ".github/workflows/refresh-skill-analytics.yml").read_text(),
            Loader=yaml.BaseLoader,
        )
        jobs = workflow["jobs"]
        self.assertIn("!= 'true'", jobs["refresh"]["if"])
        self.assertIn("== 'true'", jobs["reviewed-snapshot"]["if"])
        self.assertEqual(
            jobs["reviewed-snapshot"]["permissions"],
            {"contents": "read", "issues": "read"},
        )
        self.assertEqual(
            jobs["reviewed-update"]["permissions"],
            {"contents": "write", "pull-requests": "write", "actions": "write"},
        )
        self.assertEqual(jobs["reviewed-update"]["needs"], "reviewed-snapshot")
        for job_name in ("reviewed-snapshot", "reviewed-update"):
            checkout = jobs[job_name]["steps"][0]
            self.assertEqual(
                checkout["with"]["ref"], "${{ github.event.repository.default_branch }}"
            )
            self.assertEqual(checkout["with"]["persist-credentials"], "false")
        self.assertEqual(
            jobs["reviewed-update"]["concurrency"]["cancel-in-progress"], "false"
        )


if __name__ == "__main__":
    unittest.main()
