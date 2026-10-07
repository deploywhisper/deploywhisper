---
title: 'Raise verified repository security posture to at least 8'
type: 'chore'
created: '2026-10-07'
status: 'in-review'
baseline_commit: '046b0207dbfd7edebc3ae1b1415246ba333393b9'
context: ['_bmad-output/project-context.md']
---

<frozen-after-approval reason="user authorizes remaining security controls and verified >=8 publication">

## Intent

**Problem:** Published Scorecard is 6.7. Mutable container/Python dependencies, absent fuzzing, incomplete private reporting links and unprotected long-lived branches remain actionable gaps. The user requests a genuine public score of at least 8.

**Approach:** Enforce immutable, verified build inputs; run coverage-guided fuzzing against production redaction; publish a usable security policy/private reporting path; protect long-lived history. Verify actual controls, preserve existing behavior and publish/rescan until the measured target is met or an external authority requirement prevents further progress.

## Boundaries & Constraints

**Always:** Work directly on develop under the user's standing authorization. Preserve local-first/advisory-first behavior, existing application dependencies and production frontend design. Generated lockfiles cover transitive requirements with valid SHA256 hashes, not decorative flags. Fuzz targets execute successfully and exercise production code. Snapshot administrative settings before changes; do not create bypasses simply to improve a score. Keep commits as Lore records and evidence tied to actual scanned commits.

**Ask First:** Required human approvals/merge-policy changes need the pending reviewer-policy answer; release publication needs a concrete version/artifact decision before changing existing release assets. Private report enablement and history protection are authorized low-risk safeguards. If the target requires account registration or contributor participation, report the exact external dependency.

**Never:** Fabricate approvals/contributors, claim an unearned best-practices badge, upload fake signatures, suppress scanner/test failures, expose secrets, or overwrite operator data. Do not claim >=8 until the published API and badge verify it. No runtime dependency additions. Fuzz/dev tools may use the already verified official tooling required for this control.

## I/O & Edge-Case Matrix

| State | Expected behavior | Failure behavior |
| --- | --- | --- |
| Locked install | Python3.10/3.11 and container runtime resolve exact verified distributions | Tampered hashes/version mismatches fail installation |
| Fuzz input | Arbitrary bounded bytes exercise production redaction without crashing; explicit secret removed without input mutation | Real invariant failure/crash fails CI and is repaired |
| Public reporter | Working private GitHub reporting link and documented scope/timeline | Sensitive disclosures stay out of public issues |
| Long-lived branch | Ordinary authorized pushes remain possible; deletion/history rewrites blocked | Required review changes wait for explicit reviewer policy |
| Publisher | Real controls reflected in default-branch report | Failed/partial runs cannot establish target completion |

</frozen-after-approval>

## Code Map

- `requirements.txt`, `requirements-dev.txt`, root input manifests, `scripts/lock-dependencies.sh` — universal runtime/dev SHA256 locks, update flow and parity checks.
- `Dockerfile`, `.github/workflows/ci.yml`, `release.yml`, `publish-skills-registry.yml` — immutable base images and hash-enforced installations.
- `.github/dependabot.yml` — Docker/action/Python/npm update coverage without auto-merge.
- `.clusterfuzzlite/`, `.github/workflows/clusterfuzzlite.yml` — official pinned coverage-guided build/run and synthetic seed corpus.
- `SECURITY.md`, `docs/security/scorecard-eight.md` — functional private reporting policy and measured-control ledger.
- `tests/test_infra/` — lock/install/workflow and fuzz-invariant regressions; existing container expectations adapted to pinned images.
- GitHub private-reporting and branch rulesets — administrative controls with saved prior state; no invented review history.

## Tasks & Acceptance

- [x] Add complete universal runtime/dev hash locks, reproducible generation and parity checks; replace every Docker/CI/release pip install with hash enforcement while preserving workflow behavior.
- [x] Verify and pin root container images; keep automated updates functional, and fix any existing install failure masking exposed by the change.
- [x] Add a genuine pinned ClusterFuzzLite harness/workflow/corpus; validate packaged execution and coverage, plus deterministic malicious/safe invariant tests.
- [x] Enable private vulnerability reporting, link the actual form and document supported versions/acknowledgement/disclosure expectations.
- [x] Protect develop/main against force-push and deletion with recorded settings; handle review/CI requirements only after policy clarification.
- [x] Run lint/actionlint, audits, full local suites, clean compatible Python/container installs, production frontend/Compose browser validation where packaging changes require it; perform layered review.
- [ ] Publish validated controls, run real fuzzing/CI/CodeQL/publisher, verify public report and badge >=8, and record remaining honest limitations.

**Acceptance Criteria:**
- Given current manifests, when clean installs run, then exact hashes are enforced and existing app/test behavior works on supported runtime Python.
- Given bounded arbitrary bytes and synthetic secrets, when the packaged fuzzer runs, then production functions are instrumented with coverage and genuine crashes fail rather than being swallowed.
- Given an outside reporter, when they follow the security policy, then a private reporting path exists without exposing incident data.
- Given protected branches, when force/deletion operations are attempted, then history protections deny them; normal approved workflow behavior remains possible.
- Given validated committed controls, when the official publisher completes, then report commit and badge show an actual score >=8.

## Spec Change Log

## Design Notes

Current risk-weighted projection for full hashing/policy/fuzzing plus basic history protection is around 8.0; this is a planning estimate only. SAST/review history, contributor diversity and account-issued badges cannot be manufactured. Signing/provenance belong to real versioned release delivery; no historical artifacts are retroactively mislabeled. Pending reviewer-policy choice must not block independent implementation.

## Verification

- Hash-enforced install succeeds in clean Python3.10/3.11 and Docker; tampered synthetic hash rejected.
- Meaningful unit/integration regressions, Ruff, actionlint and dependency audits pass.
- Full local CI/root smoke/exact affected shard and production Compose Playwright pass as appropriate.
- Official packaged fuzz build/run and GitHub fuzz workflow complete with nonzero coverage.
- Layered review has no unresolved introduced defects.
- Published Scorecard API and badge commit/value verify >=8; retain raw public evidence and workflow links.

## Implementation and Review Record

- Added complete universal runtime/dev locks and ordinary input manifests; all flagged installs now enforce hashes. Removed unrestricted pip upgrades and Docker install-failure masking. Clean Linux Python3.10/3.11 installs, real tampered-hash rejection, byte-identical regeneration, audits and focused regressions pass. Python3.10 proof covers dependency installation, not pre-existing app usage of Python3.11 APIs.
- Pinned verified Python/Node builder/runtime digests. Added Docker and fuzz dependency update coverage. Packaging metadata includes the previously runtime-only multipart dependency without introducing a new runtime root.
- Real packaged fuzzer:61seconds/12976executions, coverage757→1054. Separate pinned runner with networking disabled:61seconds/15116executions, coverage757→1038, features1714→3535; official runner build checks pass. Five invariant regressions and31existing content-security tests pass. Hosted workflow still pending publication. Upstream action descriptor pins do not freeze its delegated helper-image v1 tags; that transitive limitation is documented.
- Private vulnerability reporting enabled and working GitHub form linked. History-only ruleset24634960 blocks force-push/deletion on develop/main; existing disabled rules unchanged and no bypass configured. Reviewer-policy question remains unanswered, so independent approvals and required merge checks were not enabled.
- All three independent review layers completed. One P2 setup/update documentation gap repaired in README/CONTRIBUTING/CI docs and generator comment; acceptance recheck clean. Checkout concern dismissed after confirming official CFL code clones/checkout itself. No unresolved introduced defect remains.
- Initial live-provider Python shard:457passed/222subtests, one pre-existing CLI fixture failure because an active Ollama provider returned a narrative when the test assumed unavailable. Repaired the fixture with an explicit unavailable completion client; kept all degraded/security assertions, targeted regression passed without endpoint override. Final local CI and shard use an unavailable local endpoint like hosted CI for deterministic unit checks; the actual production-provider path was independently exercised by browser validation.
- Composed production build passed. All17browser tests passed, zero skips, against isolated deploywhisper-score8 on localhost8080 with both disposable security flags enabled. Original app restored healthy; only disposable test volume removed. Frontend typecheck and56unit tests passed. Root smoke521tests passed, one optional skip. Final CI/shard counts follow after completion.

Final validation: full local CI **1,805 tests across nine directories**, all suites passed (one optional live-provider skip); smoke **521 tests**, one optional skip; exact API/CLI/infra shard **458 passed +222 subtests**; **56 frontend unit tests** and all **17 production Compose browser tests**, no browser skips. Runtime/dev/fuzz audits each zero. Ruff (**300 files**), actionlint and diff checks pass; existing medium B104 remains unchanged. Hosted publication/fuzz/CI and the actual >=8 report remain the final unchecked task.
