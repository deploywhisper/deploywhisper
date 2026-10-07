"""Build deterministic release source assets from an exact Git commit."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess


from scripts.release_policy import validate_release_tag


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def read_project_version(repo: Path, source_sha: str) -> str:
    """Read metadata from the source commit, never the mutable working tree."""
    metadata = _git(repo, "show", f"{source_sha}:pyproject.toml").decode()
    project = re.search(r"(?ms)^\[project\]\s*$\n(.*?)(?=^\[|\Z)", metadata)
    version = (
        re.search(r'^version\s*=\s*"([^"\n]+)"\s*$', project.group(1), re.M)
        if project
        else None
    )
    if not version:
        raise ValueError("Source pyproject.toml must have a quoted [project] version")
    return version.group(1)


def build_artifacts(
    repo: Path,
    source_sha: str,
    source_ref: str,
    release: str,
    repository: str,
    output_dir: Path,
) -> Path:
    """Package committed tracked source with Git's deterministic tar headers."""
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError(
            "source-sha must be a full lowercase 40-character Git commit digest"
        )
    if (
        _git(repo, "rev-parse", f"{source_sha}^{{commit}}").decode().strip()
        != source_sha
    ):
        raise ValueError("Source digest must identify a commit")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must be owner/name")
    if not source_ref.startswith(("refs/heads/", "refs/tags/")) or any(
        c.isspace() for c in source_ref
    ):
        raise ValueError("source-ref must be a full branch or tag ref")
    version = read_project_version(repo, source_sha)
    if release.startswith("preview-"):
        if release != f"preview-{source_sha}":
            raise ValueError("Preview label must bind the exact full source digest")
    else:
        validate_release_tag(release, version)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ValueError("Output directory must be empty; assets cannot be overwritten")
    filename = f"deploywhisper-{release}.tar.gz"
    archive = _git(
        repo,
        "archive",
        "--format=tar",
        f"--prefix=deploywhisper-{release}/",
        source_sha,
    )
    # Equivalent to gzip -n: no original filename or wall-clock mtime.
    with (output_dir / filename).open("wb") as stream:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=stream, mtime=0
        ) as compressor:
            compressor.write(archive)
    digest = hashlib.sha256((output_dir / filename).read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "repository": repository,
        "source_ref": source_ref,
        "source_sha": source_sha,
        "release": release,
        "version": version,
        "archive": filename,
        "archive_sha256": digest,
    }
    (output_dir / "source-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    checksums = "".join(
        f"{hashlib.sha256((output_dir / name).read_bytes()).hexdigest()}  {name}\n"
        for name in (filename, "source-manifest.json")
    )
    (output_dir / "SHA256SUMS").write_text(checksums)
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--repo", type=Path, default=Path.cwd())
    build.add_argument("--source-sha", required=True)
    build.add_argument("--source-ref", required=True)
    build.add_argument("--release", required=True)
    build.add_argument("--repository", required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = build_artifacts(
            args.repo,
            args.source_sha,
            args.source_ref,
            args.release,
            args.repository,
            args.output_dir,
        )
    except (ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Release artifact validation failed: {exc}\n")
    print(output)


if __name__ == "__main__":
    main()
