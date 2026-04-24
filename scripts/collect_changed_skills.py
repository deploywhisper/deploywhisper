"""Collect changed skill ids for registry publishing workflows."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


ZERO_SHA = "0000000000000000000000000000000000000000"


def _iter_built_in_skill_ids() -> list[str]:
    from scripts.publish_skills_registry import iter_built_in_skill_ids

    return iter_built_in_skill_ids()


def _changed_skill_ids(before: str, after: str) -> list[str]:
    diff = subprocess.run(
        ["git", "diff", "--name-only", f"{before}...{after}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    skills: set[str] = set()
    for path in diff:
        normalized = path.strip()
        if normalized.startswith("skills/") and normalized.endswith(".md"):
            skills.add(Path(normalized).stem.lower())
        elif normalized.startswith("tests/skill-tests/"):
            parts = Path(normalized).parts
            if len(parts) >= 3:
                skills.add(parts[2].lower())
    return sorted(skills)


def main() -> int:
    output_path = Path(sys.argv[1])
    event_name = os.getenv("EVENT_NAME", "").strip()
    before = os.getenv("BEFORE_SHA", "").strip()
    after = os.getenv("AFTER_SHA", "").strip()

    if event_name == "workflow_dispatch" or before == ZERO_SHA:
        skill_ids = _iter_built_in_skill_ids()
    else:
        skill_ids = _changed_skill_ids(before, after)

    with output_path.open("a", encoding="utf-8") as handle:
        handle.write("skill_ids=" + ",".join(skill_ids) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
