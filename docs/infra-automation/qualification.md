# Release qualification evidence inventory

Story 16.19 aggregates 60 functional requirements and 12 nonfunctional
requirements from the canonical disposition catalog. A prepared inventory is
not a passed qualification, an independent review, or release authorization.

Create a new candidate inventory using an exact Git commit:

```sh
python scripts/qualification_manifest.py template \
  --source-commit <full-40-character-commit> --output <new-manifest.json>
python scripts/qualification_manifest.py validate <manifest.json>
```

The template records the catalog digest, exact commit, all 72 requirement IDs
and nine mandatory gate IDs. Every row begins `not-run`; the image digest is
unset. Supply the immutable `sha256:` image digest only after building the
candidate. Never substitute a tag, branch name or mutable image reference.

The validator returns exit 2 for a structurally valid but incomplete inventory,
exit 1 for invalid or stale evidence, and exit 0 only when the inventory is
complete. Its JSON always reports `publication_authorized: false`. The checked-in
[preparatory inventory](../verification/infra-automation/16-19/qualification-manifest.json)
is intentionally incomplete. Regenerate for the actual immutable release build;
it does not claim that uncommitted preparation belongs to its source commit.

For each executed requirement or gate, record `passed` or `failed` and evidence
objects with these exact fields:

| Field | Meaning |
| --- | --- |
| `path` | Canonical repository-relative evidence file, no symlink or traversal |
| `sha256` | Lowercase SHA-256 of the exact file bytes |
| `command` | Actual command or independently performed procedure |
| `exit_code` | Actual integer result; successful rows require zero |
| `scope` | Executed tool/runner/receiver/hardware profile and limitations |
| `verified_by` | Actual verifier attribution; a human gate requires the real human operator |
| `source_commit` | Same full commit as the inventory build |
| `image_digest` | Same immutable image digest as the inventory build |

A passed row requires evidence, matching build identity and a successful command
result. Changed evidence, a changed canonical catalog, missing/duplicate/unknown
IDs, invalid status values, unexecuted rows carrying results and unsafe paths
are rejected. Artifact existence alone never marks a gate passed. Evidence files
are capped at 32 MiB; the inventory is an operator-local review input, not an
untrusted HTTP upload endpoint.

The validator checks structure and integrity, not the truth of a human's claim
or the semantics of a result file. A copied digest or a claimed verifier is not
a signature. Independent maintainers must inspect the actual proof, its scope,
source/build identity, requirement coverage and external attestations. Reusing
one report across requirements is valid only when it really establishes each
requirement. Do not turn fixture success into a production-profile pass.

The nine mandatory gates retain accepted prerequisites, the independent human
pilot, integrated real-profile behavior, safety/authorization, reference
performance, composed-browser qualification, operations/docs, independent
code/security review and signed-artifact/SBOM/provenance verification. Complete
inventory validation does not publish, sign, tag, deploy or authorize any action.
Stable publication still requires all story acceptance and separate authority.
