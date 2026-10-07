"""Propose a metrics-only update without checking out or executing bot branch code."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import quote


BRANCH = "feature/refresh-skill-analytics"
CI_BRANCH_PREFIX = "feature/analytics-ci/"
METRICS = "data/skill-analytics.json"
TITLE = "Refresh skill analytics snapshot"
BODY = "Refresh the generated skill analytics snapshot. Human review is required before merging."
COMMIT_MESSAGE = (
    "Keep skill discovery backed by current analytics\n\n"
    "Refresh only the generated metrics snapshot through a reviewed update.\n\n"
    "Confidence: high\nScope-risk: narrow\n"
    "Directive: Review the generated metrics before merging\n"
    "Tested: Snapshot JSON validation and metrics-only tree validation\n"
)


def run(*args: str, input_text: str | None = None, env=None) -> str:
    return subprocess.run(
        args, input=input_text, text=True, capture_output=True, check=True, env=env
    ).stdout.strip()


def git(*args: str, **kwargs) -> str:
    # No branch-provided filters/hooks are run by the plumbing commands below.
    return run("git", "-c", "core.hooksPath=/dev/null", *args, **kwargs)


def propose(repository: str, base: str, snapshot: Path) -> bool:
    git("check-ref-format", "refs/heads/" + base)
    if any(
        path.is_symlink()
        for path in (snapshot, snapshot.parent, Path("data"), Path(METRICS))
    ):
        raise ValueError("Analytics paths must not follow symlinks")
    content = snapshot.read_text(encoding="utf-8")
    if not isinstance(json.loads(content), dict):
        raise ValueError("Analytics snapshot must be a JSON object")
    git("fetch", "origin", "refs/heads/" + base)
    base_sha = git("rev-parse", "FETCH_HEAD")
    remote = git("ls-remote", "--heads", "origin", "refs/heads/" + BRANCH)
    previous = None
    if remote:
        git("fetch", "origin", "refs/heads/" + BRANCH)
        previous = git("rev-parse", "FETCH_HEAD")
        ancestor = git("merge-base", base_sha, previous)
        changed = git("diff", "--name-only", ancestor, previous).splitlines()
        if any(path != METRICS for path in changed):
            raise ValueError(
                "Existing analytics branch contains changes outside the metrics file"
            )

    with tempfile.TemporaryDirectory(prefix="analytics-index-") as temporary:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / "index"))
        git("read-tree", base_sha, env=env)
        blob = git("hash-object", "-w", "--stdin", input_text=content)
        git(
            "update-index",
            "--add",
            "--cacheinfo",
            "100644," + blob + "," + METRICS,
            env=env,
        )
        tree = git("write-tree", env=env)
    # No-op against default branch, including after the previous PR was merged.
    if tree == git("rev-parse", base_sha + "^{tree}"):
        return False
    if previous and tree == git("rev-parse", previous + "^{tree}"):
        commit = previous
    else:
        parents = ["-p", previous or base_sha]
        if previous and git("merge-base", base_sha, previous) != base_sha:
            parents.extend(["-p", base_sha])
        commit_env = dict(
            os.environ,
            GIT_AUTHOR_NAME="github-actions[bot]",
            GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com",
            GIT_COMMITTER_NAME="github-actions[bot]",
            GIT_COMMITTER_EMAIL="41898282+github-actions[bot]@users.noreply.github.com",
        )
        commit = git(
            "commit-tree", tree, *parents, input_text=COMMIT_MESSAGE, env=commit_env
        )

    # Dispatched CI executes the proposed tree, so prove it differs from trusted
    # default code only in the regular metrics blob before authorizing execution.
    if git("diff", "--name-only", base_sha, commit).splitlines() != [METRICS]:
        raise ValueError("Proposed tree must change only the metrics file")
    if not git("ls-tree", commit, "--", METRICS).startswith("100644 blob "):
        raise ValueError("Proposed metrics must be a regular file")

    # Dispatch by a one-shot protected ref, because the PR branch can advance
    # after validation. Both checks still attach to this exact PR-head SHA.
    ci_branch = CI_BRANCH_PREFIX + commit
    rules = json.loads(
        run(
            "gh",
            "api",
            "repos/" + repository + "/rules/branches/" + quote(ci_branch, safe=""),
        )
    )
    if not {"update", "deletion"}.issubset({rule.get("type") for rule in rules}):
        raise ValueError(
            "Analytics CI refs must be protected against updates and deletion"
        )
    ci_remote = git("ls-remote", "--heads", "origin", "refs/heads/" + ci_branch)
    if ci_remote:
        if ci_remote.split()[0] != commit:
            raise ValueError(
                "Existing analytics CI ref does not match the validated commit"
            )
    else:
        git("push", "origin", commit + ":refs/heads/" + ci_branch)
    if commit != previous:
        # Ordinary push rejects concurrent updates instead of overwriting them.
        git("push", "origin", commit + ":refs/heads/" + BRANCH)

    pulls = json.loads(
        run(
            "gh",
            "pr",
            "list",
            "--repo",
            repository,
            "--head",
            BRANCH,
            "--base",
            base,
            "--state",
            "open",
            "--json",
            "number",
        )
    )
    if pulls:
        run(
            "gh",
            "pr",
            "edit",
            str(pulls[0]["number"]),
            "--repo",
            repository,
            "--title",
            TITLE,
            "--body",
            BODY,
        )
    else:
        run(
            "gh",
            "pr",
            "create",
            "--repo",
            repository,
            "--head",
            BRANCH,
            "--base",
            base,
            "--title",
            TITLE,
            "--body",
            BODY,
        )
    for workflow in ("ci.yml", "codeql.yml", "clusterfuzzlite.yml"):
        ci_remote = git("ls-remote", "--heads", "origin", "refs/heads/" + ci_branch)
        if not ci_remote or ci_remote.split()[0] != commit:
            raise ValueError("Analytics CI ref no longer matches the validated commit")
        run("gh", "workflow", "run", workflow, "--repo", repository, "--ref", ci_branch)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    print(
        "Analytics review proposed."
        if propose(args.repo, args.base, args.snapshot)
        else "No analytics changes to propose."
    )


if __name__ == "__main__":
    main()
