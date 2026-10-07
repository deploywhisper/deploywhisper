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

## Pending owner decisions

**Reviewer:** choose an independent person to hold write access and approve changes; explicitly authorize any role promotion. Requiring an approval without that person would block owner-authored PRs. The proposed rule requires one approval, stale-review dismissal, approval after the last push, resolved review threads and current successful CI, with no bypass. It replaces direct pushes to develop/main with PRs. No role or mandatory-review rule has been applied by this preparation.

**Release:** develop is127 commits ahead of v1.3.0. A1.4.0-rc.1 prerelease is the suggested reviewable candidate, not an approved version. Publishing it requires matching packaging metadata1.4.0rc1, a validated tag/source and successful release gates. Old releases/tags/assets remain unchanged. A new asset-bearing signed-provenance prerelease is assessable by Scorecard, but a draft/workflow preview is not. Do not publish a stable patch containing this entire development span solely to increase a metric.

The public score cannot reflect these two controls until the real review process and approved public release are in place. Remaining decisions are owner responsibilities under issue#131. Local/hosted test and signature evidence will be appended after validation.

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
