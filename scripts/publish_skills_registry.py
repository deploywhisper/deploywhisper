"""Sync built-in skills into the external skills registry repository."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from services.skill_manifest_service import load_skill_document


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
SKILL_TESTS_DIR = REPO_ROOT / "tests" / "skill-tests"


def iter_built_in_skill_ids() -> list[str]:
    """Return current built-in skill ids from the source repository."""
    return sorted(
        path.stem.strip().lower()
        for path in SKILLS_DIR.glob("*.md")
        if path.is_file() and path.name.lower() != "readme.md"
    )


def publish_skill(skill_id: str, *, target_repo: Path) -> None:
    """Copy one built-in skill and its scenarios into the target registry repo."""
    source_path = SKILLS_DIR / f"{skill_id}.md"
    target_dir = target_repo / "skills" / skill_id
    if not source_path.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
        return

    document = load_skill_document(
        source_path,
        strict_manifest=True,
        allow_legacy_name=False,
        project_root=REPO_ROOT,
    )
    assert document.manifest is not None

    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_dir / "skill.md")
    (target_dir / "manifest.json").write_text(
        json.dumps(document.manifest.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    source_suite_dir = REPO_ROOT / document.manifest.test_suite_path
    target_tests_dir = target_dir / "tests"
    if target_tests_dir.exists():
        shutil.rmtree(target_tests_dir)
    shutil.copytree(source_suite_dir, target_dir / "tests" / "scenarios")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish built-in skills to registry.")
    parser.add_argument(
        "--target-repo",
        required=True,
        help="Filesystem path to the checked out skills registry repository.",
    )
    parser.add_argument(
        "skill_ids",
        nargs="*",
        help="Optional skill ids to publish. Defaults to all built-in skills.",
    )
    args = parser.parse_args()

    target_repo = Path(args.target_repo).resolve()
    skill_ids = args.skill_ids or iter_built_in_skill_ids()
    for skill_id in skill_ids:
        publish_skill(skill_id.strip().lower(), target_repo=target_repo)


if __name__ == "__main__":
    main()
