---
title: 'Publish the approved DeployWhisper v1.4.0 stable release'
type: 'chore'
created: '2026-10-07'
status: 'in-review'
baseline_commit: '1b2062f286b8d54a8ec5d35643d6c529948a1a90'
context: ['_bmad-output/project-context.md', 'docs/security/release-integrity.md', 'CONTRIBUTING.md']
---

<frozen-after-approval reason="owner explicitly authorized stable version and signed publication">

## Intent

**Problem:** The last public release is v1.3.0, while accepted development through Story 12.4 and subsequent security remediation has accumulated on develop. Existing releases have no uploaded signed assets. Users need an accurate, consistent stable release with verifiable source and container provenance.

**Approach:** Publish stable v1.4.0 using the documented Git Flow release branch and prepared verified release pipeline. Compare v1.3.0 against the accepted implementation, prepare curated notes, synchronize runtime/package/container version defaults, validate the complete application, and publish only after all gates pass. The owner's explicit v1.4.0 request supersedes the earlier suggested unapproved RC; no separate RC is required.

## Boundaries & Constraints

**Always:** Preserve local-first processing, advisory canonical reports, independent deterministic scoring and safe provider/connector boundaries. Include accepted product work only through 12.4, along with necessary security remediation and release signing infrastructure. Use main merge commit as stable tag identity, retain ancestry on default develop before pushing that tag. Retain operator data and restore the existing composed app after disposable end-to-end verification. Keep release assets bound to exact source SHA and workflow identity. Record test evidence and remaining limitations honestly. Existing human-review policy prerequisites stay explicit.

**Ask First:** Only destructive changes to prior public releases, tags, operator data, or collaborator roles require new owner input. Routine reversible fixes, PRs, merges, the approved new tag, source assets and image publication are already authorized.

**Never:** Implement later product stories, advertise unshipped SBOM/native MCP, overwrite existing release versions, move protected tags, fake human GitHub reviews, persist secrets, or change original v1.3.0 notes/assets. Do not announce preview signatures as proof of actual published container signing.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| --- | --- | --- | --- |
| Stable release | Tagv1.4.0, metadata 1.4.0, accepted source | Verified source assets and multi-platform image; latest stable aliases | Publication waits for every gate |
| Identity mismatch | Wrong tag/version/source/signer or altered bytes | Verification rejects publication | Fix before immutable tag creation; investigate exact source if already tagged |
| Existing or older version | Public release/registry tag already exists or downgrade | Guard refuses overwrite | Inspect state, never force replacement |
| Partial promotion | Release exists but image aliases failed | Preserve signed assets and verified candidate | Recover exact verified digest without rebuilding or replacing assets |
| Older installation | Existing DB/settings/sensitive historical data | Normal migration028 and environment-backed keys | Back up database; operator cleans old sensitive data and rotates affected keys |

</frozen-after-approval>

## Code Map

- `pyproject.toml`, `config.py`, `Dockerfile`: distribution/runtime/default image versions.
- `tests/test_api/test_health.py`, `tests/test_api/test_stats.py`, `tests/test_infra/test_release_workflow.py`: version-sensitive regressions.
- `frontend/openapi.json`: generated API version header.
- `README.md`, `CHANGELOG.md`, `SECURITY.md`, `docs/releases/v1.4.0.md`: current version, upgrade and curated release documentation.
- `.github/workflows/release.yml`, `.github/workflows/release-artifacts.yml`, `scripts/release_policy.py`: source/test/security/candidate/signing/publication gates.
- `docs/security/release-integrity.md`: rollout decision and real publication evidence.

## Tasks & Acceptance

**Execution:**
- [x] Audit v1.3.0 comparison and scope; write professional notes and changelog.
- [x] Synchronize version defaults, generated API header and existing version fixtures.
- [x] Run lint, full local CI, smoke, affected shard, full release coverage, dependency audits and composed browser tests.
- [x] Review release preparation with independent adversarial/edge/acceptance checks and fix findings.
- [ ] Commit using Lore, push release branch, PR and merge into main; back-merge main into develop through PR.
- [ ] Validate exact source/metadata/ancestry then push immutable annotated v1.4.0 tag; monitor release gates.
- [ ] Download public assets, independently verify provenance/checksums/negative case and signed OCI digest/aliases; record publication evidence.

**Acceptance Criteria:**
- Given v1.3.0 baseline, when reading notes, then each claimed new feature maps to accepted code through 12.4 and supported compatibility guidance.
- Given source or composed app, when reading package/API/OCI metadata, then all report1.4.0.
- Given the release tag, when Actions runs, then tests/security/source signatures/image smoke/OCI signatures pass before publication.
- Given public source assets and image, when consumer verifies exact source/workflow/digest, then authentication succeeds and tampered bytes fail.
- Given original local app/data, when validation completes, then its service is restored and volume preserved.

## Spec Change Log

-2026-10-07: Owner authorizes stable v1.4.0 and signed publication; the older suggested RC is historical. Explicit authorization overrides skill checkpoints requiring redundant approval and its local-only remote restriction.

## Design Notes

Back-merge main to default develop before tag push so tag-triggered ancestry policy is satisfied. Release signing infrastructure is operational delivery support; it does not extend the product feature scope past12.4. Private frontend npm packages remain0.0.0 as development tooling; application version is Python/runtime metadata.

## Verification

- `bash scripts/ci-local.sh`, root unittest, affected API/CLI/infra pytest, release coverage>=60: successful existing regressions.
- Ruff check/format, frontend typecheck/test/build, pip/npm audits, migration to head: successful or documented pre-existing nonblocking limitations.
- Disposable compose atlocalhost8080 with all17Playwright tests: all pass and original app restored.
- Shared release policy validate v1.4.0, official Actions CI/CodeQL/fuzz/release: all blocking gates pass.
- Strict gh attestation verify for all three public source subjects and OCI digest, checksum check, altered archive negative test: expected results.

## Preparation review triage

- Three independent reviews found one actionable documentation patch: contributor release/hotfix instructions tagged before the default-branch back-merge and directly pushed develop. Updated both to PR back-merge, ancestry check, then immutable tag.
- Fixed joined-word typos in new authorization prose. Versioned README/support-line updates are deliberately staged release payload changes and will ship with successful publication; final availability is verified before completion.
- Resolved conditional old-image-label concern against actual registry latest: OCI version1.3.0, source4f2f51ef4ef4829f8c7a391c73dae18271d47576. The publication guard is checked against actual remote state.
- Partial release creation/alias promotion recovery remains the documented operator path: verify public signed assets and exact candidate digest, then recover only aliases. Never rebuild/overwrite immutable source or move its tag. Automated rerun refusal is intentional.
- Generated OpenAPI JSON was stale; refreshed from current create_app().openapi() and regenerated types with no type diff. Browser build first failed during a temporary stale-schema generation and is rerun after correction.

## Local verification evidence

2026-10-07: all blocking local commands passed. Full local CI1,841; smoke555(one optional skip); affected shard492+257subtests; complete release suite1,840passed+one optional skip+1,295subtests,95.18%coverage; frontend56/typecheck/build;17/17composed browser tests; migration, lint/format, audits and real publication guard passed. Generatedschema drift was resolved before the successful composed build. Original compose service is restored healthy, original volume preserved. Hosted PR/source/publication checks follow before closure.

## Security gate iteration

PR#151 CodeQL alert aggregation failed despite analysis-job success. Independent triage identified actual quadratic query/authorization scans(90/91/93), repaired with failing-before-fix subprocess regressions and preserved question-mark/quoted credential behavior. URL/YAML/path/HTML/cookie/transport guards and synthetic fixtures were verified separately; legacy password verification is an explicit compatibility risk, not a false positive. An independent edge review compared30,000generated old/new pattern cases with identical semantics and confirmed linear full-boundary growth. Complete local/hosted suites and composed tests are rerun after this security source change. See docs/security/v1.4.0-security-triage.md for individual dispositions.

## Corrected-source final local verification

Source d2cb917 passed all blocking local checks: fullCI1,845tests; full release suite1,844passed+one optional skip+1,318subtests at95.18%coverage; smoke555; affected shard492+257subtests;43focusedsecuritytests+142subtests;17/17disposable composed browser tests. Original app restored healthy. PRCodeQL alert check reports no open findings; three repaired alerts verified by rescan,15guarded paths individually false-positive, four synthetic fixtures, one explicitly accepted legacy-verification compatibility risk. Five obsolete root dependency graph alerts classified inaccurate with clean locks/install/audits. No query exclusions or human approval fabrication.

## Hosted changed-selection fixture correction

Final hosted service/API shards and fuzz passed, but changed-test feedback failed normalized incident-scope error screening. A two-test reproduction proved an earlier GitHub fixture reloads project_service, replacing its exception class while incident imports retain the old binding. Full service discovery normally refreshes these imports, hiding the selection-order mismatch. The submission regression fixture now temporarily binds the handler to the current resolver exception class through ExitStack, restoring it afterward. No production code or credential assertions changed. The reproducing GitHub case plus all submission regressions pass eight tests. Exact1,314-test changed selection and1,093-test service discovery are replayed before final merge; hosted checks rerun on this correction.
