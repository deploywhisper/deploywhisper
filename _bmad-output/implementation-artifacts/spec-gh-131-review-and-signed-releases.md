---
title: 'Enforce independent review and verifiable release delivery'
type: 'feature'
created: '2026-10-07'
status: 'in-review'
baseline_commit: 'e91ae13eabc5ae752af14701eaddeafbcb073f15'
context: ['_bmad-output/project-context.md']
---

<frozen-after-approval reason="user requests real Code-Review/Signed-Releases remediation">

## Intent

**Problem:** Code-Review is0 because no review is required and no recent changes have approved human reviews. Signed-Releases is-1 because all four release objects have no uploaded assets. Current release aliases are pushed before smoke verification and version mismatch only warns.

**Approach:** Prepare enforceable independent review/CI rules without inventing reviewers, and ship real exact-source artifacts with signed SLSA provenance, verification and safe image promotion. Verify a signed workflow preview before asking for concrete reviewer/release decisions needed for public activation/publication.

## Boundaries & Constraints

**Always:** Work directly on develop under existing authorization while no new approvals rule is active. Preserve branch-history safeguards. Keep all signing actions SHA-pinned, OIDC/attestation writes job-scoped to signing, and avoid PR signing triggers. Bind subject hashes, repository, source SHA/ref and signing workflow to actual artifacts. Preserve release smoke/security gates. Do not mutate existing releases/tags/assets or stable aliases to manipulate metrics.

**Ask First:** Reviewer identity/write access and mandatory-approval policy require the pending user answer. New public release/version choice comes after a concrete signed preview;127 commits since1.3.0 make automatic stable patch selection unsafe. A preview workflow artifact does not imply approval to publish a stable release.

**Never:** Forge reviews/signatures/provenance, expose secrets, publish arbitrary branch code as a trusted release, or claim a raised public check before publication/rules verification. No new runtime dependencies. Do not introduce automatic Slack/notification delivery as part of this task.

## I/O & Edge-Case Matrix

| Scenario | Expected behavior | Failure behavior |
| --- | --- | --- |
| Preview on develop | Exact commit archive/checksums signed and verified; retained workflow artifacts only | No release/tag or image alias writes |
| Valid release tag | Version equals packaging metadata; source is authorized release commit | Mismatch/unsafe tag blocks publication |
| Attestation | Actual SLSA bundle preserved as JSONL; archive/digest verification enforces identity/source | Tampered subject, wrong repository/workflow/ref/SHA rejected |
| Image delivery | Candidate digest built and health-tested, signed/verified before alias promotion | Failed smoke/signature cannot change stable aliases |
| Rerun/downgrade | Existing release assets/immutable version never overwritten; older tag cannot demote latest | Fail with actionable error, no silent overwrite |
| Human review | Required approving reviewer has legitimate write access and author cannot self-approve | No guessed role promotion or fake approved event |

</frozen-after-approval>

## Code Map

- `.github/workflows/release.yml` — version/tag checks, full tests/security, candidate digest/smoke, provenance, ordered promotion and real asset publication.
- `.github/workflows/release-artifacts.yml` — reusable/manual preview artifact build, signed provenance and verification; no remote release publication in preview.
- `scripts/release_artifacts.py` — standard-library deterministic git archive/checksums/source manifest and validation helpers.
- `Dockerfile` — existing BUILD_VERSION/BUILD_SHA arguments must actually reach runtime metadata.
- `tests/test_infra/test_release_integrity.py` — version, source hash, provenance-policy/workflow and promotion guards; offline tamper/identity cases where applicable.
- `docs/security/release-integrity.md`, `docs/ci.md` — consumer commands, preview/candidate proposal and controlled activation.
- GitHub rulesets/collaborator roles — pending owner-approved reviewer policy; record prior state before any changes.

## Tasks & Acceptance

- [x] Implement exact-source artifacts, metadata validation/checksums and tests; preserve existing unsigned historical releases.
- [x] Add pinned native GitHub attestations with real JSONL bundles and repository/workflow/ref/SHA verification; run hosted signed preview and reject tamper/wrong identity.
- [x] Repair release tag/version mismatch, unused build metadata, pre-smoke aliases and downgrade/rerun hazards; no alias publication after failed prerequisite.
- [x] Document concrete release candidate, limitations and the reason old releases are unassessed; prepare review policy and currently valid check names.
- [x] Run actionlint, focused/full applicable tests, clean production image behavior where changed, and independent comprehensive review.
- [ ] Once reviewer/version decisions arrive, activate approved review policy and publish approved real signed release; rerun publisher and verify remote Code-Review/Signed-Releases values.

**Acceptance Criteria:**
- Given a trusted preview source, when signing runs, then actual archive/checksum/provenance exist and strict verification plus negative tamper/identity checks pass without public release effects.
- Given a release, when any version/source/smoke/signing check fails, then publication and stable alias promotion cannot proceed.
- Given an older release or existing version, when retried, then published immutable assets and stable aliases cannot be replaced or downgraded.
- Given owner-approved independent reviewers, when a PR is merged, then required human approvals/CI are enforced and source author cannot self-approve.
- Given approved public artifact publication and review enforcement, when Scorecard runs, then actual improved values are visible and traceable to these controls.

## Spec Change Log

## Design Notes

Scorecard detects recognized provenance/signature filenames but does not validate their cryptography. Native actions/attest JSONL is genuine signed in-toto provenance; preserve its bytes, verify independently, then upload as .intoto.jsonl. Asset-bearing prereleases count; draft/workflow artifacts do not establish public Signed-Releases. The reusable signer identity must identify release-artifacts.yml while source-ref/digest identify the caller's actual commit. Preview remains on develop, actual release signs tag ref. Defaults may prepare a1.4.0-rc.1 proposal but publication awaits user selection and proper metadata update.

## Verification

- Standard-library artifact/tag/version regressions, hash/promotion-workflow tests and actionlint pass.
- Consumer gh attestation verify succeeds on actual signed preview and rejects altered artifact, wrong repo/signer/source identity.
- Full local CI/smoke/exact affected shard and production container version/health pass as required by changed contracts.
- Hosted source CI and artifact-signing preview succeed; no fake attestation files or unsigned release assets uploaded.
- Comprehensive independent code review has no unresolved introduced HIGH/CRITICAL issue.
- Public rules/releases/Scorecard inspected after authorized activation; otherwise report concrete missing decisions.

## Review Fix Record

Three independent BMad review layers identified a remote-tag identity race(Medium), queue replacement(Medium) and missing concrete review contexts(Low). Added fresh peeled remote-tag matching immediately before release creation, active no-bypass immutable version-tag ruleset24638746, and documented queue:max with a bounded100-pending queue. Exact CI Summary/three CodeQL contexts(app15368) verified on real PR#132 and current branch; proposed policy saved but not activated. Follow-up review checks run after these fixes.

The current official actionlint1.7.12 predates GitHub's documented queue field. Raw unsupported-key diagnostic retained; targeted filtering applies only that unsupported field while all other diagnostics remain blocking, plus exact YAML queue contract tests and native GitHub verification. This is a tool-version limit, not an ignored release failure. Full suites rerun on final policy source; initial full1823/smoke539 and affectedshard476+226 were successful before three new remote-tag regressions. Docker actual preview version/revision and healthy API verified on an isolated temporary container; an initial probe lacked APP_HOST=0.0.0.0 and was corrected to match the real release smoke environment. Existing app/data untouched.

## CI aggregate and signing permission corrections

Acceptance recheck found that the pre-existing CI Summary accepted cancelled/skipped core stages and ignored changed-test failures. Reproduced both original acceptance paths, then made the aggregate fail closed: all six core jobs must succeed, changed-tests must succeed on PRs and may only succeed/skip on other events. Actual inline-program boundary regression covers30 states; review recheck clean. The proposed required context can now represent all core gates.

Fresh primary documentation for pinned actions/attest4.2.2 additionally requires job-scoped artifact-metadata:write to create artifact storage records. Added this permission only to trusted artifact/image signing jobs and their reusable caller; promotion has no signing/OIDC/metadata-write scope. Existing least-privilege regression updated to these necessary scopes. Full suites rerun after these final changes; no public-release or reviewer-policy mutation has occurred.

## Review-compatible analytics preparation

Requiring approvals would break the scheduled direct-push analytics job. Prepared a switchable mode while preserving current behavior until activation. Read-only trusted default code fetches data; a separate update job uses Git plumbing without checking out/executing bot-branch code, refuses unrelated/symlink changes, pushes normally and proposes one metrics-only PR. It dispatches CI/CodeQL explicitly because token-created PRs do not trigger automatic PR workflows. No approval/merge is automated. The current repo PR-token setting is disabled; activation must enable appropriate PR creation and use confirmed human CODEOWNERS, as recorded in the local proposal. No setting, collaborator or PR notification was changed by preparing this code.

One legacy prompt-gate regression matched the old Bash source string and failed after the fail-closed CI summary change. Replaced the implementation-string assertion with execution of the real gate using a failed LLM shard; it verifies failure rather than a particular syntax. Existing prompt-suite ordering and matrix checks remain. Final complete suites run after this fixture and reviewed-automation integration.

## Ready-for-preview verification

Review layers rechecked remote-tag binding, queue semantics, required-CI aggregate and immutable reviewed-automation dispatch with no remaining introduced defect. Three new regressions close mutable PR-ref dispatch after tree validation; effective one-shot-ref protections and matching remote SHA are required before each workflow. Source refs are preserved against updates/deletion under active namespace rule24641350. Default analytics mode/roles remain unchanged.

Local Docker proof uses custom1.3.0-preview version and source revision, verifies OCI labels/runtime settings and a healthy isolated API; no operator volume/app modification. Runtime app/React source is unchanged, so UI validation not applicable for these release/automation changes; previous composed-app validation remains recorded in the predecessor task. Final source suites: smoke555tests with one optional skip; full/local and exact-shard counts follow after completion. Raw actionlint queue diagnostic retained; only the documented unsupported-key diagnostic is narrowly filtered, all other diagnostics block.

Final pre-preview verification:full local CI1839tests across9dirs, all suites passed(oneoptionalskip); smoke555(oneoptionalskip); affectedshard492passed+256subtests. Focused policy/asset/automation regressions and review rechecks pass. Ruff306files and all supported actionlint fields pass, raw queue-only unsupported diagnostic recorded. Existing B104 medium unchanged. Real Docker preview version/revision/health passed. No public release/tag/aliases or reviewer-role settings changed; active immutableversion-tag/CI-ref rules protectintegrity. Next:hostedattestationpreview, strictpositive/negative verification, then missingownerchoices.

## Cryptographic preview and fuzz correction

Source commit25fcb6d successfully ran native signed-preview37603120228; independent strictverification succeeded for all three subjects. Five negative policy/tamper cases rejected as expected. Full hosted CI/CodeQL on that source succeeded. Fuzz run37603119351 found a real redaction-marker corruption invariant failure; no secret disclosure was observed. Preserved the full synthetic337-byte crash, fixed production placeholder handling without altering harness assertions, and added stable-marker/actual-secret regressions. Associated53tests+147subtests and read-only review passed. Mandatory-review proposal and analytics CI dispatch now include real fuzzing. Final updated source/application verification and re-signed preview follow.

Final fuzz-fix source validation:full localCI1841tests(all9dirs, oneoptional skip), smoke555(oneoptional skip), exactshard492+257subtests, all17rebuiltbrowsertests(no browser skips), production marker53securitytests+147subtests, unchangedharness/corpus crashreplay, cleanreview. Existingapprestoredhealthy; onlydisposabletestvolume removed. Requiresfreshhostedfuzz/signing/CI onthisfixedsource beforeownerdecisionhandoff.

Corrected source509d723 ran signed-preview37605206305 successfully; independent verification confirmed all three assets and rejected altered bytes plus four wrong-policy identities. Final localCI1841all9dirs, smoke555(oneoptional skip), shard492+257subtests, all17rebuiltbrowsertests(no skips), independent markerfixreview passed; original app restored healthy. CodeQL success on corrected source, fresh hosted fuzz/CI pending at this recording. Last task(public approval policy/approved release/rescore) remains unchecked because both owner decisions are still missing.

## Owner-decision handoff

All independent preparation and verification complete on509d723: hostedCI37605204825, CodeQL37605204721, signedpreview37605206305 and retained-crash fuzz37605204817 success. Fuzz36,044executions/coverage1,063/features4,624/no crashes. Exact signed archive/checksum/manifest verify and five negative integrity/identity cases reject. Public release/required-review activation task stays unchecked and Story12.6 in-progress because no reviewer-role or public-version authorization has arrived. Rootcode/evidence committed/pushed; final evidence change docs/tracking only. Next owner inputs: independent username/write-access/PR-only human-codeowner policy and concrete public release version.
