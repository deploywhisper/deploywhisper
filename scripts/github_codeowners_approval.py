"""Collect one exact GitHub CODEOWNERS approval for release finalization."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def owners(path: Path) -> set[str]:
    return {
        match.group(1).lower()
        for match in re.finditer(
            r"(?<!\S)@([A-Za-z0-9-]+)", path.read_text(encoding="utf-8")
        )
    }


def select_approval(pulls, reviews_by_pull, *, source_commit, base_branch, allowed):
    candidates = [
        pull
        for pull in pulls
        if pull.get("merged_at")
        and pull.get("merge_commit_sha") == source_commit
        and (pull.get("base") or {}).get("ref") == base_branch
    ]
    if len(candidates) != 1:
        raise ValueError("Exact merged release-source pull request required")
    pull = candidates[0]
    author = ((pull.get("user") or {}).get("login") or "").lower()
    latest = {}
    for review in reviews_by_pull(pull["number"]):
        login = ((review.get("user") or {}).get("login") or "").lower()
        if login:
            latest[login] = review.get("state")
    approved = sorted(
        login
        for login, state in latest.items()
        if login in allowed and login != author and state == "APPROVED"
    )
    if not approved:
        raise ValueError("Independent approved CODEOWNERS review required")
    return pull["number"], approved[0]


def gh_json(path):
    pages = json.loads(
        subprocess.check_output(["gh", "api", "--paginate", "--slurp", path], text=True)
    )
    return [item for page in pages for item in page]


def collect(repository, source_commit, base_branch, codeowners_path):
    pulls = gh_json(f"repos/{repository}/commits/{source_commit}/pulls")

    def reviews(number):
        return gh_json(f"repos/{repository}/pulls/{number}/reviews")

    pull, reviewer = select_approval(
        pulls,
        reviews,
        source_commit=source_commit,
        base_branch=base_branch,
        allowed=owners(codeowners_path),
    )
    return {
        "repository": repository,
        "source_commit": source_commit,
        "pull_request": pull,
        "reviewer_login": reviewer,
        "review_state": "APPROVED",
        "codeowners_sha256": hashlib.sha256(codeowners_path.read_bytes()).hexdigest(),
        "collected_by": "github-actions",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--base-branch", required=True)
    parser.add_argument("--codeowners", type=Path, default=Path(".github/CODEOWNERS"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = collect(
            args.repository,
            args.source_commit,
            args.base_branch,
            args.codeowners,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            stream.write(json.dumps(value, sort_keys=True) + "\n")
        return 0
    except (
        OSError,
        ValueError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as error:
        parser.exit(1, f"CODEOWNERS approval unavailable: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
