"""Validate release evidence inventories without granting publication authority."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

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
EVIDENCE_GROUPS = "docs/verification/infra-automation/16-19/evidence-groups.json"
FINALIZATION_FIELDS = {
    "generated_by",
    "repository",
    "workflow_ref",
    "run_id",
    "source_attestation_verified",
    "oci_attestation_verified",
    "codeowners_approval",
    "evidence_source_commit",
    "evidence_image_digest",
}
GATE_EVIDENCE = {
    "accepted-prerequisites": {
        "docs/verification/infra-automation/16-19/release-decision.md"
    },
    "operator-pilot-or-maintainer-waiver": {WAIVER_APPROVAL_PATH},
    "integrated-real-profile": {
        "docs/verification/infra-automation/16-19/prerequisite-profiles/receiver-faults/composition-implementation.json"
    },
    "safety-and-authorization": {
        "docs/verification/infra-automation/16-19/development-validation.json"
    },
    "reference-performance": {
        "docs/verification/infra-automation/16-19/reference-performance/capacity-final/operator-capacity.json"
    },
    "composed-browser": {
        "docs/verification/infra-automation/16-19/prerequisite-profiles/README.md"
    },
    "operations-and-docs": {
        "docs/verification/infra-automation/16-19/development-validation.json"
    },
    "independent-code-security-review": {
        "docs/verification/infra-automation/16-19/prerequisite-review.json"
    },
    "signed-artifacts-sbom-provenance": {
        "docs/verification/infra-automation/16-19/release-decision.md"
    },
}
EVIDENCE_ONLY_PREFIXES = (
    "_bmad-output/implementation-artifacts/",
    "docs/verification/infra-automation/16-19/",
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


def requirement_evidence(root):
    groups = read_json(root / EVIDENCE_GROUPS)["groups"]
    result = {}
    for group in groups:
        paths = set(group["evidence"])
        require(paths, "Requirement evidence group must not be empty")
        for requirement in group["requirements"]:
            require(
                requirement not in result,
                "Requirement appears in multiple evidence groups",
            )
            result[requirement] = paths
    require(
        set(result) == set(requirements(root)),
        "Evidence groups do not cover the canonical requirements",
    )
    return result


def codeowners(root):
    raw = (root / ".github/CODEOWNERS").read_text(encoding="utf-8")
    return {
        match.group(1).lower() for match in re.finditer(r"(?<!\S)@([A-Za-z0-9-]+)", raw)
    }


def validate_approval(value, root, source_commit, repository):
    require(
        isinstance(value, dict)
        and set(value)
        == {
            "repository",
            "source_commit",
            "pull_request",
            "reviewer_login",
            "review_state",
            "codeowners_sha256",
            "collected_by",
        },
        "Invalid CODEOWNERS approval receipt",
    )
    require(value["repository"] == repository, "Approval repository mismatch")
    require(value["source_commit"] == source_commit, "Approval source mismatch")
    require(
        type(value["pull_request"]) is int and value["pull_request"] > 0,
        "Approval pull request required",
    )
    require(value["review_state"] == "APPROVED", "Approved review required")
    require(value["collected_by"] == "github-actions", "Trusted collector required")
    require(
        isinstance(value["reviewer_login"], str)
        and value["reviewer_login"].lower() in codeowners(root),
        "Reviewer is not a configured CODEOWNER",
    )
    require(
        value["codeowners_sha256"]
        == digest((root / ".github/CODEOWNERS").read_bytes()),
        "CODEOWNERS digest mismatch",
    )


def source_changes(root, evidence_source_commit, source_commit):
    return subprocess.check_output(
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--name-only",
            f"{evidence_source_commit}..{source_commit}",
            "--",
        ],
        text=True,
    ).splitlines()


def require_evidence_only_changes(paths):
    require(
        all(
            isinstance(path, str)
            and path
            and any(path.startswith(prefix) for prefix in EVIDENCE_ONLY_PREFIXES)
            for path in paths
        ),
        "Runtime source changed after qualification evidence was collected",
    )


def finalize(
    manifest,
    root,
    *,
    source_commit,
    image_digest,
    repository,
    workflow_ref,
    run_id,
    codeowners_approval=None,
    changed_paths=None,
):
    """Create the trusted-workflow manifest after the candidate digest exists."""
    require(bool(COMMIT.fullmatch(source_commit)), "Full source commit required")
    require(
        isinstance(image_digest, str)
        and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest)),
        "Immutable image digest required",
    )
    require(
        bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)),
        "Repository must be owner/name",
    )
    require(
        isinstance(workflow_ref, str)
        and workflow_ref.startswith("refs/tags/")
        and not any(character.isspace() for character in workflow_ref),
        "Finalization requires an exact release tag ref",
    )
    require(isinstance(run_id, str) and run_id.isdigit(), "Workflow run ID required")
    value = deepcopy(manifest)
    evidence_source_commit = value["build"]["source_commit"]
    evidence_image_digest = value["build"]["image_digest"]
    require(
        isinstance(evidence_source_commit, str)
        and bool(COMMIT.fullmatch(evidence_source_commit))
        and isinstance(evidence_image_digest, str)
        and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", evidence_image_digest)),
        "Preliminary evidence build identity is incomplete",
    )
    if changed_paths is None:
        changed_paths = source_changes(root, evidence_source_commit, source_commit)
    require_evidence_only_changes(changed_paths)
    value["version"] = 2
    value["build"] = {
        "source_commit": source_commit,
        "image_digest": image_digest,
    }
    passed_review = (
        next(
            row
            for row in value["gates"]
            if row["id"] == "independent-code-security-review"
        )["status"]
        == "passed"
    )
    passed_waiver = (
        next(
            row
            for row in value["gates"]
            if row["id"] == "operator-pilot-or-maintainer-waiver"
        )["status"]
        == "passed"
    )
    if passed_review or passed_waiver:
        validate_approval(codeowners_approval, root, source_commit, repository)
    value["finalization"] = {
        "generated_by": "github-actions",
        "repository": repository,
        "workflow_ref": workflow_ref,
        "run_id": run_id,
        "source_attestation_verified": True,
        "oci_attestation_verified": True,
        "codeowners_approval": codeowners_approval,
        "evidence_source_commit": evidence_source_commit,
        "evidence_image_digest": evidence_image_digest,
    }
    result = validate(value, root, require_final=True, changed_paths=changed_paths)
    require(result["release_gate_passed"], "Qualification blockers remain")
    return value


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


def validate(
    manifest,
    root,
    *,
    expected_source_commit=None,
    expected_image_digest=None,
    require_final=False,
    changed_paths=None,
):
    version = manifest.get("version") if isinstance(manifest, dict) else None
    expected_fields = {
        "version",
        "release",
        "catalog_sha256",
        "build",
        "requirements",
        "gates",
    }
    if version == 2:
        expected_fields.add("finalization")
    require(
        isinstance(manifest, dict) and set(manifest) == expected_fields,
        "Invalid manifest fields",
    )
    require(
        type(version) is int and version in {1, 2},
        "Unsupported version",
    )
    require(not require_final or version == 2, "Final manifest required")
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
    if expected_source_commit is not None:
        require(
            build["source_commit"] == expected_source_commit,
            "Expected source commit mismatch",
        )
    if expected_image_digest is not None:
        require(image == expected_image_digest, "Expected image digest mismatch")
    finalization = manifest.get("finalization")
    if version == 2:
        require(
            isinstance(finalization, dict) and set(finalization) == FINALIZATION_FIELDS,
            "Invalid finalization fields",
        )
        require(
            finalization["generated_by"] == "github-actions"
            and finalization["source_attestation_verified"] is True
            and finalization["oci_attestation_verified"] is True,
            "Trusted attestations are required",
        )
        require(
            isinstance(finalization["repository"], str)
            and bool(
                re.fullmatch(
                    r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
                    finalization["repository"],
                )
            )
            and isinstance(finalization["workflow_ref"], str)
            and finalization["workflow_ref"].startswith("refs/tags/")
            and isinstance(finalization["run_id"], str)
            and finalization["run_id"].isdigit(),
            "Invalid trusted workflow identity",
        )
        require(
            isinstance(finalization["evidence_source_commit"], str)
            and bool(COMMIT.fullmatch(finalization["evidence_source_commit"]))
            and isinstance(finalization["evidence_image_digest"], str)
            and bool(
                re.fullmatch(
                    r"sha256:[0-9a-f]{64}",
                    finalization["evidence_image_digest"],
                )
            ),
            "Invalid evidence build identity",
        )
        if changed_paths is None:
            changed_paths = source_changes(
                root,
                finalization["evidence_source_commit"],
                build["source_commit"],
            )
        require_evidence_only_changes(changed_paths)
    blockers = [] if image else ["build:image_digest"]
    requirement_paths = requirement_evidence(root)
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
                        for item in evidence
                        if isinstance(item, dict)
                    ),
                    "Preliminary waiver inventory requires the named maintainer record",
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
                evidence_source = (
                    finalization["evidence_source_commit"]
                    if version == 2
                    else build["source_commit"]
                )
                evidence_image = (
                    finalization["evidence_image_digest"] if version == 2 else image
                )
                require(
                    item["source_commit"] == evidence_source
                    and item["image_digest"] == evidence_image,
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
            if row["status"] == "passed":
                allowed = (
                    requirement_paths[row["id"]]
                    if section == "requirements"
                    else GATE_EVIDENCE[row["id"]]
                )
                require(
                    all(item["path"] in allowed for item in evidence),
                    "Evidence path does not establish this row",
                )
        require(
            len(ids) == len(expected)
            and len(set(ids)) == len(ids)
            and set(ids) == set(expected),
            f"Incomplete, duplicate or unknown {section}",
        )
    if version == 2:
        passed_review = (
            next(
                row
                for row in manifest["gates"]
                if row["id"] == "independent-code-security-review"
            )["status"]
            == "passed"
        )
        passed_waiver = (
            next(
                row
                for row in manifest["gates"]
                if row["id"] == "operator-pilot-or-maintainer-waiver"
            )["status"]
            == "passed"
        )
        if passed_review or passed_waiver:
            validate_approval(
                finalization["codeowners_approval"],
                root,
                build["source_commit"],
                finalization["repository"],
            )
        signed = (
            next(
                row
                for row in manifest["gates"]
                if row["id"] == "signed-artifacts-sbom-provenance"
            )["status"]
            == "passed"
        )
        require(not signed or version == 2, "Signed artifacts require final manifest")
    release_gate_passed = version == 2 and not blockers
    return {
        "inventory_complete": not blockers,
        "blockers": blockers,
        "release_gate_passed": release_gate_passed,
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
    check.add_argument("--expected-source-commit")
    check.add_argument("--expected-image-digest")
    check.add_argument("--require-final", action="store_true")
    finish = actions.add_parser("finalize")
    finish.add_argument("manifest", type=Path)
    finish.add_argument("--source-commit", required=True)
    finish.add_argument("--image-digest", required=True)
    finish.add_argument("--repository", required=True)
    finish.add_argument("--workflow-ref", required=True)
    finish.add_argument("--run-id", required=True)
    finish.add_argument("--codeowners-approval", type=Path)
    finish.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "template":
            value = template(args.root, args.source_commit)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x") as stream:
                stream.write(json.dumps(value, indent=2) + "\n")
            return 0
        if args.action == "finalize":
            approval = (
                read_json(args.codeowners_approval)
                if args.codeowners_approval is not None
                else None
            )
            value = finalize(
                read_json(args.manifest),
                args.root,
                source_commit=args.source_commit,
                image_digest=args.image_digest,
                repository=args.repository,
                workflow_ref=args.workflow_ref,
                run_id=args.run_id,
                codeowners_approval=approval,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x") as stream:
                stream.write(json.dumps(value, indent=2) + "\n")
            return 0
        result = validate(
            read_json(args.manifest),
            args.root,
            expected_source_commit=args.expected_source_commit,
            expected_image_digest=args.expected_image_digest,
            require_final=args.require_final,
        )
        print(json.dumps(result, sort_keys=True))
        passed = (
            result["release_gate_passed"]
            if args.require_final
            else result["inventory_complete"]
        )
        return 0 if passed else 2
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Invalid qualification inventory: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
