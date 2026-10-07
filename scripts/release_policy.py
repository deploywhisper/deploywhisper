"""Fail-closed version and publication policy for the release workflow."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

_VERSION = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-(alpha|beta|rc)\.(0|[1-9][0-9]*))?"
)


def version_key(value: str) -> tuple[int, int, int, int, int]:
    """Accept only canonical stable or release-candidate SemVer values."""
    match = _VERSION.fullmatch(value)
    if not match:
        raise ValueError(f"Unsupported release version: {value!r}")
    major, minor, patch, phase, number = match.groups()
    order = {"alpha": 0, "beta": 1, "rc": 2, None: 3}
    return int(major), int(minor), int(patch), order[phase], int(number or 0)


def validate_tag(tag: str, metadata: str) -> str:
    if not tag.startswith("v"):
        raise ValueError("Release tag must start with v")
    version = tag[1:]
    version_key(version)
    pep440 = re.sub(
        r"-(alpha|beta|rc)\.([0-9]+)$",
        lambda match: {"alpha": "a", "beta": "b", "rc": "rc"}[match[1]] + match[2],
        version,
    )
    if metadata not in (version, pep440):
        raise ValueError(
            f"Release tag {version} must equal project metadata {metadata}"
        )
    return version


def validate_release_tag(tag: str, metadata: str) -> None:
    """Shared tag/packaging validation for source and container publication."""
    validate_tag(tag, metadata)


def guard_publication(
    version: str, releases: list[dict], registry_latest: str | None
) -> None:
    target = version_key(version)
    for release in releases:
        tag = release["tag_name"]
        if tag == f"v{version}":
            raise ValueError(
                f"Release {tag} already exists; refusing to replace assets"
            )
        if target[3] == 3 and not release["draft"] and not release["prerelease"]:
            if not tag.startswith("v"):
                raise ValueError(f"Cannot compare existing release {tag!r}")
            if version_key(tag[1:]) > target:
                raise ValueError(f"Refusing to downgrade stable aliases from {tag}")
    if target[3] == 3 and registry_latest is not None:
        if version_key(registry_latest) > target:
            raise ValueError(f"Refusing to downgrade registry latest {registry_latest}")


def registry_exists(image: str) -> bool:
    result = subprocess.run(  # noqa: S603 -- fixed executable, no shell
        ["docker", "manifest", "inspect", image],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return True
    # Auth, network and server errors are never treated as an absent tag.
    if (
        "manifest unknown" in result.stderr.lower()
        or "no such manifest" in result.stderr.lower()
    ):
        return False
    raise ValueError(f"Cannot establish registry tag state: {result.stderr.strip()}")


def check_remote(version: str, image: str, repository: str) -> None:
    version_key(version)
    response = subprocess.check_output(  # noqa: S603 -- fixed executable, no shell
        ["gh", "api", "--paginate", "--slurp", f"repos/{repository}/releases"],
        text=True,
    )
    releases = [release for page in json.loads(response) for release in page]
    if registry_exists(f"{image}:{version}"):
        raise ValueError(f"Immutable image version {version} already exists")
    latest = None
    if "-" not in version and registry_exists(f"{image}:latest"):
        subprocess.run(  # noqa: S603 -- fixed executable, no shell
            ["docker", "pull", "--platform", "linux/amd64", f"{image}:latest"],
            check=True,
        )
        latest = subprocess.check_output(  # noqa: S603 -- fixed executable, no shell
            [
                "docker",
                "image",
                "inspect",
                "--format",
                '{{index .Config.Labels "org.opencontainers.image.version"}}',
                f"{image}:latest",
            ],
            text=True,
        ).strip()
    guard_publication(version, releases, latest)


def verify_remote_tag(tag: str, source_sha: str, remote: str = "origin") -> None:
    """Require the current remote tag's peeled commit to be the signed source."""
    if not tag.startswith("v"):
        raise ValueError("Release tag must start with v")
    version_key(tag[1:])
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("Signed source must be a full lowercase commit SHA")
    ref = f"refs/tags/{tag}"
    output = subprocess.check_output(  # noqa: S603 -- fixed executable, no shell
        ["git", "ls-remote", "--exit-code", "--", remote, ref, f"{ref}^{{}}"],
        text=True,
    )
    refs = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 2 or fields[1] not in {ref, f"{ref}^{{}}"}:
            raise ValueError("Remote returned an unexpected release tag response")
        digest, name = fields
        if not re.fullmatch(r"[0-9a-f]{40}", digest) or name in refs:
            raise ValueError("Remote returned an invalid or duplicate release tag")
        refs[name] = digest
    if ref not in refs:
        raise ValueError(f"Remote release tag {tag} is missing")
    commit = refs.get(f"{ref}^{{}}", refs[ref])
    if commit != source_sha:
        raise ValueError(
            f"Remote release tag {tag} moved away from signed source {source_sha}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--tag", required=True)
    validate.add_argument("--metadata", type=Path, default=Path("pyproject.toml"))
    guard = subparsers.add_parser("guard")
    guard.add_argument("--version", required=True)
    guard.add_argument("--image", required=True)
    guard.add_argument("--repository", required=True)
    remote_tag = subparsers.add_parser("verify-remote-tag")
    remote_tag.add_argument("--tag", required=True)
    remote_tag.add_argument("--source-sha", required=True)
    remote_tag.add_argument("--remote", default="origin")
    args = parser.parse_args()
    try:
        if args.command == "validate":
            try:
                import tomllib
            except (
                ModuleNotFoundError
            ):  # Python 3.10 uses the existing locked dependency.
                import tomli as tomllib

            metadata = tomllib.loads(args.metadata.read_text())["project"]["version"]
            version = validate_tag(args.tag, metadata)
            print(f"version={args.tag}")
            print(f"image_version={version}")
            print(f"is_prerelease={str('-' in version).lower()}")
        elif args.command == "verify-remote-tag":
            verify_remote_tag(args.tag, args.source_sha, args.remote)
        else:
            check_remote(args.version, args.image, args.repository)
    except (ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Release policy rejected publication: {error}\n")


if __name__ == "__main__":
    main()
