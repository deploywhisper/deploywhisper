# Independent review and signed release delivery

## Observed gaps

At the start of this work, Code-Review was0: the default branch had no required approval and the sampled30 changesets had no approved reviews. `pramodksahoo` was the only writer/admin; `manisetty` had read access. Basic history protections were active, but they did not require PR approvals. AI review in this workspace does not create a legitimate independent GitHub approval.

Signed-Releases was unassessed(-1), not a passing control. Four published GitHub releases(v1.0.0–v1.3.0) had no uploaded assets. Automatic GitHub source ZIP/tarballs and registry image tags do not constitute uploaded signed release assets for this check. The pinned Scorecard probes skip releases with empty asset lists and only detect recognized signature/provenance filenames; they do not perform cryptographic verification.

## Prepared controls

- A reusable/manual signer builds exact-commit source archives, checksum and source manifests, signs all three with native GitHub/Sigstore SLSA provenance, and verifies repository/workflow/source-ref/SHA and hosted-runner policy before retaining workflow artifacts.
- Release tag/metadata comparison is strict, including canonical prerelease equivalents. Image build arguments reach runtime version and OCI revision labels.
- Docker publishes only a unique candidate before smoke; the exact digest passes health/metadata checks and signed-provenance verification before any stable/version alias promotion.
- Source assets are downloaded from the current run, cryptographically checked, and uploaded only as a new release. Published assets/immutable versions are not overwritten; existing/older stable publication fails closed. Promotion is serialized and rechecks remote state.
- A partial failure after release creation can leave a valid release without promoted registry aliases. Reruns deliberately refuse overwrite; operator recovery must inspect the existing signed assets/digest instead of silently replacing them.

Read [the artifact/consumer verification guide](release-artifacts.md). A source-only preview publishes no tag, release or image alias. Hosted preview and negative cryptographic checks must be recorded before choosing a public release version. OCI registry signing/promotion still requires an authorized real tag and cannot be claimed from artifact-only preview.

## Reviewer decision and release authorization

**Reviewer:** choose an independent person to hold write access and approve changes; explicitly authorize any role promotion. Requiring an approval without that person would block owner-authored PRs. The proposed rule requires one approval, stale-review dismissal, approval after the last push, resolved review threads and current successful CI, with no bypass. It replaces direct pushes to develop/main with PRs. No role or mandatory-review rule has been applied by this preparation.

**Release:** On2026-10-07 the owner authorized stable **v1.4.0**, professional notes comparing v1.3.0 with accepted product changes through Story 12.4, consistent version metadata and signed publication. The earlier 1.4.0-rc.1 suggestion was an unapproved preparation recommendation; stable1.4.0 is now the selected release. Necessary vulnerability fixes and signing infrastructure are included without advertising later product stories. Historical releases/tags/assets remain unchanged.

Preparation uses `release/v1.4.0`, a reviewed merge into main and a main-to-develop back-merge before the immutable tag is pushed. This preserves Git Flow and satisfies the release pipeline's default-branch ancestry guard. Tests, security audit, signed source verification, exact-digest container smoke and OCI provenance verification must pass before publication. Actual release evidence will be recorded separately from the preview results below.

The public score can reflect Signed-Releases only after actual public signed assets exist. Human Code-Review remains a separate unresolved prerequisite under issue#131; no reviewer role or approval was invented for this release.

## Concrete review-policy proposal

[The ruleset proposal](review-policy-proposal.json) is prepared but **not applied**. It targets develop/main, one required approval, no bypass, strict up-to-date checks, stale-review dismissal, last-push approval and resolved review threads. Contexts verified in actual PR#132 check runs (head1dce76d) and current default-branch runs are:

| Required context | GitHub App ID |
| --- | --- |
| CI Summary |15368(github-actions)|
| CodeQL (python) |15368(github-actions)|
| CodeQL (javascript-typescript) |15368(github-actions)|
| CodeQL (actions) |15368(github-actions)|

Do not activate this payload until the owner confirms a legitimate independent writer and accepts PR-only delivery. Historical disabled rulesets include unavailable/stale check names and are not used. Existing history protections stay active.

## Tag integrity and queue policy

Active tag ruleset24638746 prevents updates/deletion of refs/tags/v* with no bypass actors; new version tags can still be created. This protects published tag identity without changing any existing tag/release. A fresh remote peeled-tag comparison is also performed immediately before publication to reject changes while release gates ran. Repository administrators remain a trust boundary because they can edit rulesets.

GitHub's current documented concurrency queue:max retains up to100pending release runs rather than silently replacing one pending run with the next. The installed latest actionlint1.7.12(released2026-03-30) predates that field and reports only an unsupported-key diagnostic. All other diagnostics remain blocking; the new field is checked against native GitHub documentation and exact YAML contract tests. This is a recorded validator-version gap, not a claim that the raw old linter accepted it.

## Reviewed automation activation prerequisites

Scheduled analytics currently pushes directly. The prepared opt-in mode(`DEPLOYWHISPER_REVIEWED_UPDATES=true`) instead generates a snapshot with read-only credentials and submits a metrics-only PR from trusted default code. It never executes bot-branch code, rejects unrelated changes/symlinks, and uses normal pushes. It explicitly dispatches CI and CodeQL because PRs created by GITHUB_TOKEN do not automatically run PR workflows. No automatic approval or merge is performed. Default mode remains unchanged until activation.

The repository currently has default_workflow_permissions=read and can_approve_pull_request_reviews=false. GitHub's setting combines token-based PR creation/approval permission; enabling it is needed for this automated PR submission. To keep required approval genuinely human, the proposal requires code-owner review and activation must first update CODEOWNERS to contain the owner plus the confirmed independent human writer. Neither an app/bot approval nor an author self-review can satisfy those human code-owner approvals. Do not activate the proposal until that roster, write access and reviewed-update mode are ready. No such role/settings activation was inferred in this preparation.

Reviewed-mode CI uses immutable one-shot source branches feature/analytics-ci/<full SHA>, protected by active no-bypass ruleset24641350(update/deletion prohibited). The helper requires effective protections, rejects wrong existing refs, verifies the remote target before both dispatches and never dispatches from the mutable PR branch. This closes a branch-change race after local tree validation. The CI namespace is reserved; no CI ref or analytics PR has been created by this preparation. Administrators remain trusted because they can alter these rules.

## Signed preview and discovered fuzz defect

[Signed preview37603120228](https://github.com/deploywhisper/deploywhisper/actions/runs/37603120228) succeeded on25fcb6d. Downloaded native bundles verified archive/checksums/manifest under strict repo/signer/ref/digest policy. Independent negative tests rejected altered bytes, different repository, signer workflow, source ref and source digest. These results authenticate a workflow preview, not a public software release.

A concurrent real hosted fuzz run found marker corruption: a discovered value such as `[REDAC` could damage generated `[REDACTED]` strings. No generated credential disclosure was demonstrated. The production replacement now preserves whole markers while still redacting actual marker fragments and longer marker-containing credentials. Original337-byte crash is retained as a synthetic seed and all unchanged harness invariants pass. Security regressions and independent review verify the fix. Rebuilt application/browser and hosted fuzz verification follow before readiness; no failure is suppressed. Proposed merge policy now also requires actual Production redaction fuzzing(app15368), and reviewed analytics explicitly dispatches that workflow against the immutable verified CI ref.

## Final corrected-source preview

[Preview37605206305](https://github.com/deploywhisper/deploywhisper/actions/runs/37605206305) succeeded on509d723 with the marker fix. Independent verification again accepted archive/checksums/manifest and rejected all five altered-byte/identity/ref/digest cases. [The verification record](../verification/release-attestation-preview.json) retains both runs; neither is a public software release. CodeQL passed on corrected source. Full hosted CI and retained-crash-seed fuzzing complete before source readiness is claimed. No reviewer-role/approval rules or public version choice were guessed.

## Verified preparation before stable authorization

Corrected source509d723 passed [full CI37605204825](https://github.com/deploywhisper/deploywhisper/actions/runs/37605204825), [CodeQL37605204721](https://github.com/deploywhisper/deploywhisper/actions/runs/37605204721), [signed preview37605206305](https://github.com/deploywhisper/deploywhisper/actions/runs/37605206305) and [real fuzz37605204817](https://github.com/deploywhisper/deploywhisper/actions/runs/37605204817). Fuzzing completed36,044executions, coverage1,063/features4,624, no crashes. Independent three-subject verification and all five negative cases passed; local suites1841tests, smoke555, affectedshard492+257subtests, all17productionbrowsertests passed.

Preparation evidence above predates the owner's stable v1.4.0 authorization. At that point Code-Review was0 and Signed-Releases was unassessed(-1). The reviewer role/PR-only human-codeowner decision remains pending. Public release version is now authorized as described above; registry signing/promotion remains unverified until the real release gates finish. No old release/tag/assets are modified.
