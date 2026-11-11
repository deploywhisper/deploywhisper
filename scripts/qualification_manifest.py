"""Validate release evidence inventories without granting publication authority."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parents[1]
CATALOG = (
    "_bmad-output/planning-artifacts/infra-automation-requirement-dispositions.json"
)
GATES = (
    "accepted-prerequisites",
    "operator-pilot-or-maintainer-waiver",
    "integrated-real-profile",
    "safety-and-authorization",
    "reference-performance",
    "composed-browser",
    "operations-and-docs",
    "independent-code-security-review",
    "signed-artifacts-sbom-provenance",
)
WAIVER_APPROVAL_PATH = (
    "docs/verification/infra-automation/16-19/maintainer-waiver-approval.json"
)
HEX = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def requirements(root):
    entries = read_json(root / CATALOG)["active_requirements"]
    expected = {f"IAU15-FR-{i:03d}" for i in range(1, 61)} | {
        f"IAU15-NFR-{i:03d}" for i in range(1, 13)
    }
    ids = [row["id"] for row in entries]
    require(
        len(ids) == 72 and set(ids) == expected,
        "Canonical requirement coverage changed",
    )
    return sorted(ids)


def template(root, source_commit):
    require(bool(COMMIT.fullmatch(source_commit)), "Full source commit required")
    return {
        "version": 1,
        "release": "v1.5.0",
        "catalog_sha256": digest((root / CATALOG).read_bytes()),
        "build": {"source_commit": source_commit, "image_digest": None},
        "requirements": [
            {"id": key, "status": "not-run", "evidence": []}
            for key in requirements(root)
        ],
        "gates": [{"id": key, "status": "not-run", "evidence": []} for key in GATES],
    }


def evidence_file(root, name):
    require(isinstance(name, str), "Evidence path must be text")
    path = PurePosixPath(name)
    require(
        bool(name)
        and not path.is_absolute()
        and name == path.as_posix()
        and ".." not in path.parts
        and "\\" not in name,
        "Evidence must use a canonical relative path",
    )
    result = root
    for component in path.parts:
        result = result / component
        require(not result.is_symlink(), "Symlink evidence is not accepted")
    require(result.is_file(), "Evidence file is missing")
    require(root.resolve() in result.resolve().parents, "Evidence escapes repository")
    require(result.stat().st_size <= 32 * 1024 * 1024, "Evidence exceeds size limit")
    return result


def validate(manifest, root):
    require(
        isinstance(manifest, dict)
        and set(manifest)
        == {"version", "release", "catalog_sha256", "build", "requirements", "gates"},
        "Invalid manifest fields",
    )
    require(
        type(manifest["version"]) is int and manifest["version"] == 1,
        "Unsupported version",
    )
    require(manifest["release"] == "v1.5.0", "Wrong release")
    require(
        manifest["catalog_sha256"] == digest((root / CATALOG).read_bytes()),
        "Catalog digest mismatch",
    )
    build = manifest["build"]
    require(
        isinstance(build, dict) and set(build) == {"source_commit", "image_digest"},
        "Invalid build fields",
    )
    require(
        isinstance(build["source_commit"], str)
        and bool(COMMIT.fullmatch(build["source_commit"])),
        "Full source commit required",
    )
    image = build["image_digest"]
    require(
        image is None
        or isinstance(image, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", image),
        "Immutable image digest required",
    )
    blockers = [] if image else ["build:image_digest"]
    for section, expected in (
        ("requirements", requirements(root)),
        ("gates", list(GATES)),
    ):
        rows = manifest[section]
        require(isinstance(rows, list), "Expected row list")
        ids = []
        for row in rows:
            require(
                isinstance(row, dict) and set(row) == {"id", "status", "evidence"},
                "Invalid row fields",
            )
            require(isinstance(row["id"], str), "Invalid row ID")
            ids.append(row["id"])
            require(row["status"] in ("not-run", "failed", "passed"), "Invalid status")
            evidence = row["evidence"]
            require(isinstance(evidence, list), "Expected evidence list")
            require(
                row["status"] != "not-run" or not evidence,
                "Unexecuted row cannot carry results",
            )
            require(
                row["status"] != "passed" or image and evidence,
                "Pass requires immutable build and evidence",
            )
            if row["status"] != "passed":
                blockers.append(row["id"])
            if (
                section == "gates"
                and row["id"] == "operator-pilot-or-maintainer-waiver"
                and row["status"] == "passed"
            ):
                require(
                    any(
                        item.get("path") == WAIVER_APPROVAL_PATH
                        and item.get("verified_by") == "accountable-maintainer:psaho01"
                        and "waiver_kind=accountable-maintainer"
                        in item.get("scope", "")
                        and "approval_evidence=approved-codeowners-review"
                        in item.get("scope", "")
                        for item in evidence
                        if isinstance(item, dict)
                    ),
                    "Maintainer waiver requires named durable CODEOWNERS approval evidence",
                )
            for item in evidence:
                require(
                    isinstance(item, dict)
                    and set(item)
                    == {
                        "path",
                        "sha256",
                        "command",
                        "exit_code",
                        "scope",
                        "verified_by",
                        "source_commit",
                        "image_digest",
                    },
                    "Invalid evidence fields",
                )
                require(
                    item["source_commit"] == build["source_commit"]
                    and item["image_digest"] == image,
                    "Evidence build mismatch",
                )
                require(
                    all(
                        isinstance(item[k], str) and item[k].strip()
                        for k in ("command", "scope", "verified_by")
                    ),
                    "Evidence attribution and scope required",
                )
                require(type(item["exit_code"]) is int, "Exit code must be an integer")
                require(
                    row["status"] != "passed" or item["exit_code"] == 0,
                    "Failed command cannot support pass",
                )
                require(
                    isinstance(item["sha256"], str)
                    and bool(HEX.fullmatch(item["sha256"])),
                    "Invalid evidence digest",
                )
                require(
                    digest(evidence_file(root, item["path"]).read_bytes())
                    == item["sha256"],
                    "Evidence digest mismatch",
                )
        require(
            len(ids) == len(expected)
            and len(set(ids)) == len(ids)
            and set(ids) == set(expected),
            f"Incomplete, duplicate or unknown {section}",
        )
    return {
        "inventory_complete": not blockers,
        "blockers": blockers,
        "publication_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("template")
    create.add_argument("--source-commit", required=True)
    create.add_argument("--output", type=Path, required=True)
    check = actions.add_parser("validate")
    check.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "template":
            value = template(args.root, args.source_commit)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x") as stream:
                stream.write(json.dumps(value, indent=2) + "\n")
            return 0
        result = validate(read_json(args.manifest), args.root)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["inventory_complete"] else 2
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Invalid qualification inventory: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
