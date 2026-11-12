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

Stable publication does not consume that preliminary inventory directly. After
the release workflow has built and verified the exact multi-architecture image
and source artifacts, it runs `qualification_manifest finalize` with the exact
Git source SHA, OCI digest, tag ref and trusted GitHub run identity. If either
the waiver or independent-review gate is passed, the workflow also collects an
independent approved review for that exact merged commit from a login named by
the committed `.github/CODEOWNERS`. The finalizer rejects unrelated evidence
paths using the canonical `evidence-groups.json` and gate-specific mapping.

The resulting version2 final manifest is attested by the release workflow. The
publication job downloads it, verifies its GitHub attestation and exact
source/image identity, then reruns validation with `--require-final`. Any open
requirement/gate, missing independent CODEOWNERS approval, substituted digest,
untrusted workflow identity or failed source/OCI attestation prevents the
release job from starting.

For each executed requirement or gate, record `passed` or `failed` and evidence
objects with these exact fields:

| Field | Meaning |
| --- | --- |
| `path` | Canonical repository-relative evidence file, no symlink or traversal |
| `sha256` | Lowercase SHA-256 of the exact file bytes |
| `command` | Actual command or independently performed procedure |
| `exit_code` | Actual integer result; successful rows require zero |
| `scope` | Executed tool/runner/receiver/hardware profile and limitations |
| `verified_by` | Actual verifier attribution; operator proof names the operator, while a maintainer waiver names the accountable maintainer and explicitly states that no human pilot occurred |
| `source_commit` | Same full commit as the inventory build |
| `image_digest` | Same immutable image digest as the inventory build |

A passed row requires evidence, matching build identity and a successful command
result. Changed evidence, a changed canonical catalog, missing/duplicate/unknown
IDs, invalid status values, unexecuted rows carrying results and unsafe paths
are rejected. Artifact existence alone never marks a gate passed. Evidence files
are capped at 32 MiB; the inventory is an operator-local review input, not an
untrusted HTTP upload endpoint.

The preliminary validator checks structure, allowed evidence routing and byte
integrity; it does not infer the truth of a human claim from prose. A copied
digest or claimed verifier is not a signature. The post-build finalizer adds the
trusted GitHub review receipt and verified source/OCI attestation boundary.
Independent maintainers must still inspect the actual proof and its scope. Do
not turn fixture success into a production-profile pass.

The nine mandatory gates retain accepted prerequisites, either the independent
operator pilot or an accountable-maintainer waiver, integrated real-profile behavior, safety/authorization, reference
performance, composed-browser qualification, operations/docs, independent
code/security review and signed-artifact/SBOM/provenance verification. Complete
inventory validation does not publish, sign, tag, deploy or authorize any action.
Stable publication still requires all story acceptance and separate authority.

A waiver closes only the independent-execution process gate. It must preserve
`NOT EXECUTED` for the pilot procedures, cite reviewed technical evidence, accept
the residual self-service/runbook-usability risk and leave every performance,
security-review, signing, provenance, support-boundary and publication gate intact.
The manifest validator will pass this gate only with the named maintainer
(`accountable-maintainer:psaho01`) and a source-bound
`docs/verification/infra-automation/16-19/maintainer-waiver-approval.json`
record backed by an approved CODEOWNERS review. A branch-local assertion is not
durable approval evidence.
