"""Build deterministic release source assets from an exact Git commit."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import quote


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


SBOM_NAME = "sbom.spdx.json"


def _unique_json(data: bytes) -> dict:
    def reject_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"Duplicate JSON key in lock file: {key}")
            value[key] = item
        return value

    value = json.loads(data, object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object lock file")
    return value


def source_sbom(repo: Path, source_sha: str, repository: str, version: str) -> dict:
    """Describe committed source dependencies, not an installed image inventory."""
    packages = []

    def package(identifier, name, package_version, ecosystem=None, comment=None):
        value = {
            "SPDXID": identifier,
            "name": name,
            "versionInfo": package_version,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "NOASSERTION",
            "copyrightText": "NOASSERTION",
        }
        if ecosystem:
            value["externalRefs"] = [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": f"pkg:{ecosystem}/{quote(name, safe='/')}@{quote(package_version, safe='')}",
                }
            ]
        if comment:
            value["comment"] = comment
        packages.append(value)

    package(
        "SPDXRef-project",
        "deploywhisper",
        version,
        comment=f"Exact source commit {source_sha}; dependency inventory from committed locks. "
        "Includes conditional Python runtime candidates and all npm build/development entries. "
        "Not an installed container/OS inventory or a license determination.",
    )
    requirements = _git(repo, "show", f"{source_sha}:requirements.txt").decode()
    logical = requirements.replace("\\\n", " ")
    for line in logical.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        pin = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9.!+_-]+)(.*)", line)
        if not pin:
            raise ValueError("SBOM requires an exactly pinned runtime lock")
        name, package_version, suffix = pin.groups()
        if not re.search(r"--hash=sha256:[0-9a-f]{64}(?:\s|$)", suffix):
            raise ValueError("SBOM requires hashed runtime lock entries")
        name = re.sub(r"[-_.]+", "-", name).lower()
        identifier = "SPDXRef-python-" + hashlib.sha256(line.encode()).hexdigest()
        package(
            identifier,
            name,
            package_version,
            "pypi",
            "requirements.txt lock entry; hashes cover allowed distribution candidates, "
            "not a claimed installed package. " + line,
        )
    lock = _unique_json(_git(repo, "show", f"{source_sha}:frontend/package-lock.json"))
    if lock.get("lockfileVersion") != 3 or not isinstance(lock.get("packages"), dict):
        raise ValueError("SBOM requires an npm v3 package lock")
    for location, entry in sorted(lock["packages"].items()):
        if location == "":
            continue
        if (
            "node_modules/" not in location
            or not isinstance(entry, dict)
            or entry.get("link")
            or not isinstance(entry.get("version"), str)
            or not entry["version"]
        ):
            raise ValueError("Unsupported npm lock package entry")
        name = entry.get("name") or location.rsplit("node_modules/", 1)[1]
        if not isinstance(name, str) or not name:
            raise ValueError("Unsupported npm package name")
        identifier = "SPDXRef-npm-" + hashlib.sha256(location.encode()).hexdigest()
        package(
            identifier,
            name,
            entry["version"],
            "npm",
            f"frontend/package-lock.json entry {location}; dev={bool(entry.get('dev'))}; "
            f"optional={bool(entry.get('optional'))}",
        )
    if len({item["SPDXID"] for item in packages}) != len(packages):
        raise ValueError("Duplicate lock entries cannot produce a unique SBOM")
    created = datetime.fromtimestamp(
        int(_git(repo, "show", "-s", "--format=%ct", source_sha)), timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"deploywhisper-source-{source_sha}",
        "documentNamespace": f"https://github.com/{repository}/sbom/{source_sha}/source-v1",
        "creationInfo": {
            "created": created,
            "creators": ["Tool: deploywhisper-release-artifacts-v1"],
        },
        "packages": packages,
        "relationships": [
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": "SPDXRef-project",
            }
        ]
        + [
            {
                "spdxElementId": "SPDXRef-project",
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": item["SPDXID"],
            }
            for item in packages[1:]
        ],
    }


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
    sbom = source_sbom(repo, source_sha, repository, version)
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
    (output_dir / SBOM_NAME).write_text(
        json.dumps(sbom, indent=2, sort_keys=True) + "\n"
    )
    checksums = "".join(
        f"{hashlib.sha256((output_dir / name).read_bytes()).hexdigest()}  {name}\n"
        for name in (filename, "source-manifest.json", SBOM_NAME)
    )
    (output_dir / "SHA256SUMS").write_text(checksums)
    return output_dir


def verify_artifacts(repo, source_sha, source_ref, release, repository, output_dir):
    """Regenerate from the trusted explicit source identity and compare every asset."""
    with tempfile.TemporaryDirectory() as temporary:
        expected = build_artifacts(
            repo, source_sha, source_ref, release, repository, Path(temporary)
        )
        for asset in expected.iterdir():
            actual = output_dir / asset.name
            if (
                actual.is_symlink()
                or not actual.is_file()
                or actual.read_bytes() != asset.read_bytes()
            ):
                raise ValueError(
                    f"Release artifact does not match committed source: {asset.name}"
                )
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = argparse.ArgumentParser(add_help=False)
    build.add_argument("--repo", type=Path, default=Path.cwd())
    build.add_argument("--source-sha", required=True)
    build.add_argument("--source-ref", required=True)
    build.add_argument("--release", required=True)
    build.add_argument("--repository", required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    subparsers.add_parser("build", parents=[build])
    subparsers.add_parser("verify", parents=[build])
    args = parser.parse_args()
    try:
        operation = build_artifacts if args.command == "build" else verify_artifacts
        output = operation(
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
