# Sprint Change Proposal: v1.4.0 Delivery Status Reconciliation

**Date:** 2026-10-07
**Workflow:** bmad-correct-course (batch, applied)
**Scope:** Minor administrative/documentation correction
**Authorization:** User explicitly requested correction of all epics/stories and required statuses against implementation through 12.4 and released v1.4.0. This authorizes the reversible reconciliation; no additional scope, release mutation or governance activation is inferred.

## 1. Issue Summary

Story 12.4 and stable v1.4.0 delivery have overtaken the execution summaries. Nine earlier accepted stories still show `review`, two already-completed story files disagree with their sprint `ready-for-dev` entries, and eleven completed epics remain `in-progress`. The May alignment/status summaries incorrectly present creation readiness as present implementation status. Signing Story 12.6 is already done but contains obsolete pending-publication prose. Release/upgrade documentation for 13.8 was delivered out of order.

### Evidence

- [Published v1.4.0](https://github.com/deploywhisper/deploywhisper/releases/tag/v1.4.0), published 2026-10-07T13:06:47Z, stable/non-draft; source `935f3bbc88907948de8ae25bd2a361d04044ebc6`.
- Public assets: archive, SHA256SUMS, source-manifest.json, artifact.intoto.jsonl. No SBOM asset is present.
- [PR #132](https://github.com/deploywhisper/deploywhisper/pull/132) delivered 12.4; [PR #153](https://github.com/deploywhisper/deploywhisper/pull/153) merged independently verified release evidence into develop.
- `docs/verification/v1.4.0-release.json`, `docs/verification/v1.4.0-scorecard.json`, `spec-v1-4-0-signed-release.md` and per-story completion/review-fix records.
- Current [status map](../implementation-artifacts/story-implementation-status-map.md) inventories all 101 stories with merged delivery links and remaining work. Changed earlier-story merge commits were checked as ancestors of the starting integration HEAD.

## 2. Impact Analysis

All 16 epics and 101 current stories were assessed. Result: **84 done, 15 ready-for-dev, 2 review; Epics 0–11 done; Epics 12–15 in-progress**. Story 12.4 is the latest sequential accepted implementation, with 12.6 and 13.8 accepted out of order. Retrospectives remain optional; none was performed by this reconciliation.

PRD requirements, architecture decisions and UX acceptance remain valid. PRD milestone maturity names are distinct from package release versions: stable v1.4.0 does not establish full GA/CNCF exit criteria. No acceptance criteria are removed, new epic is added, or product scope deferred beyond V1. Archive story numbers remain historical. Requirements traceability `Mapped` describes planning coverage rather than finished delivery.

Technical impact is limited to BMad tracking and documentation. Runtime/API/UI/CLI/release pipeline behavior is unaffected. Pending generated stories now refer to current React conventions. Repository release notes explicitly disclose the existing registry/governance follow-ups and missing SBOM; the published GitHub release object is untouched.

### Omitted Epic 15 migration track

The inventory check also found eight existing Epic 15 stories absent from sprint tracking. They are reconstructed from unchanged epic definitions and merged PRs #92, #96–#102. Stories 15.0–15.5 are accepted done. Stories 15.6/15.7 are implemented but remain review because the parity audit still lists 12 historical parity labels without a current disposition crosswalk and initiative Part D2/G closure is not recorded. PR #99 explicitly leaves history decisions; PR #100 leaves dark-mode/provider-capability decisions. Epic 15 remains in progress; no parity decision or UI change is guessed. The May alignment inventory remains a historical 93-story snapshot; current plan is 101 stories across 16 epics.

## 3. Recommended Approach

Apply direct adjustment within the existing roadmap. Low effort and narrow risk; no delivery rescheduling beyond making the next unfinished item explicit. Rollback was rejected because accepted shipped behavior is not the source of the tracking defect. MVP/PRD reduction was rejected because the remaining requirements still apply. Completion is based on existing accepted delivery and evidence, not inferred from the version number alone.

## 4. Detailed Change Proposals (applied)

| Story | Sprint status before → after | Rationale |
| --- | --- | --- |
| 0-4-establish-rfc-and-decision-process | `ready-for-dev` → `done` | Accepted merged delivery; see status map and story closeout note |
| 1-2-project-aware-analysis-submission | `review` → `done` | Accepted merged delivery; see status map and story closeout note |
| 2-2-terraform-plan-json-intake | `review` → `done` | Accepted merged delivery; see status map and story closeout note |
| 2-5-evidence-law-runtime-gate | `review` → `done` | Accepted merged delivery; see status map and story closeout note |
| 4-6-deployment-outcome-capture | `review` → `done` | Accepted merged delivery; see status map and story closeout note |
| 5-5-rerun-on-commit-and-report-comparison | `review` → `done` | Accepted merged delivery; see status map and story closeout note |
| 5-6-future-adapter-output-contract | `ready-for-dev` → `done` | Accepted merged delivery; see status map and story closeout note |
| 6-1-benchmark-corpus-v1 | `review` → `done` | Accepted merged delivery; see status map and story closeout note |
| 6-2-benchmark-runner | `review` → `done` | Accepted merged delivery; see status map and story closeout note |
| 6-4-outcome-calibration-metrics | `review` → `done` | Accepted merged delivery; see status map and story closeout note |
| 7-1-project-scoped-topology-context | `review` → `done` | Accepted merged delivery; see status map and story closeout note |
| 13-8-release-notes-and-upgrade-notes | `ready-for-dev` → `done` | Accepted merged delivery; see status map and story closeout note |

For 0.4 and 5.6 only the sprint tracker was stale; story headers already said done. Nine earlier `review` headers now record administrative accepted-delivery closeout with merged evidence. This does not rewrite earlier review outcomes or claim a new implementation review today. Story 13.8 now has completed task checks and a release AC mapping based on existing preparation reviews and publication verification; the optional registry follow-up is made explicit in repository notes.

| Artifact | Before | After |
| --- | --- | --- |
| sprint-status.yaml | Epics 0–10 in-progress | Epics 0–11 done; 12–15 in-progress; 84 done stories, 15 ready, 2 review |
| epics.md | Readiness-review status and unreconciled historical overview | Implementation-in-progress; current release/epic inventory; unchanged requirements |
| story-implementation-status-map.md | May creation readiness; only 0.1 identified as review | All 101 current statuses with merged evidence and remaining work |
| story-alignment-report.md | May table presented as current | Explicit historical snapshot with current tracker links |
| requirements-traceability-matrix.md | Mapped/no-gap could be mistaken for implemented | Explicit separation of planning coverage and current delivery gaps |
| 12.6 story | Present-tense pending-publication debug note | Published/verified; earlier preparation notes explicitly historical |
| 15 pending story files | Unqualified generated readiness/retired UI guidance | Existing release credit plus remaining acceptance; current React guidance |
| docs/releases/v1.4.0.md | Known registry issue only in evidence/publication records | Known issue and follow-up section, missing SBOM stated explicitly |

### Remaining acceptance inventory

All rows retain `ready-for-dev`; existing partial delivery must be reused and checked, not rebuilt or treated as complete.

| Story | Existing baseline credit | Remaining acceptance |
| --- | --- | --- |
| 12.5 | Checksums, source manifest, signed provenance and verification instructions shipped. | Generate, publish and verify actual release SBOMs; checksum delivery alone does not meet AC1. |
| 12.7 | Release notes cover backup before migration and migration 028. | Complete tested backup/restore, upgrade/rollback and retention runbooks for supported deployments. |
| 12.8 | Local-source Skills and local-only model operation are documented. | Complete restricted-network/air-gapped setup, dependencies, update and verification guidance. |
| 13.1 | README documentation links exist. | Complete docs landing/navigation structure and journey-based information architecture acceptance. |
| 13.2 | Quick start, synthetic examples and evidence/schema docs exist. | Complete an end-to-end first-analysis and report-interpretation walkthrough covering uncertainty, rollback and context TODOs. |
| 13.3 | Current OpenAPI snapshot and report-v2 documentation exist. | Audit API/webhook/error/schema reference completeness and generated-reference drift. |
| 13.4 | CLI, evidence-model and agent JSON/interface docs exist. | Audit complete CLI/evidence/agent reference coverage and examples against actual contracts. |
| 13.5 | Terraform-state and Kubernetes connector docs exist. | Complete connector permissions, credential setup, degraded behavior, troubleshooting and UI/API/CLI link coverage. |
| 13.6 | Action/App/self-hosted and enforcement integration guides exist. | Audit all story-required workflow coverage, links and contracts; preserve the external Action runtime boundary. |
| 13.7 | Selected doc-contract tests run in CI. | Complete repository-wide doc/link/generated-reference/command-example drift checks or explicit accepted-gap catalog. |
| 14.1 | Governance/security/release/benchmark evidence exists. | Build consolidated CNCF readiness checklist with explicit unmet maturity gates. |
| 14.2 | No verified external adopter evidence was located. | Establish permission-based adopter/usage records; never invent adoption. |
| 14.3 | Maintainer responsibilities and current coverage gaps are documented. | Define promotion, inactivity/contributor ladder and periodic maintainer-coverage review. |
| 14.4 | Scorecard and release verification provide security evidence. | Add broader contribution, issue-response, review, maintainer, docs and benchmark-cadence metrics. |
| 14.5 | Existing artifacts provide parts of an application evidence package. | Assemble the CNCF application package and disclose adoption/maintainer/community gaps. |

## 5. Implementation Handoff

Developer/maintainer: reconcile metadata (applied), then invoke `bmad-dev-story` for **12.5 SBOM and Release Checksums** in a fresh task. Reuse checksums/provenance, add missing SBOM delivery and verification, preserve immutable v1.4.0 artifacts. Follow with 12.7/12.8, remaining Epic 13 docs and Epic 14 readiness. Skip already-delivered 12.6 and 13.8. Optional retrospectives may be run separately for completed epics.

Product/architecture handoff is unnecessary: there is no requirements/architecture change. Owner-controlled follow-ups remain independent-human approval policy, optional public registry publisher credential, and legacy sensitive-data/share remediation. Previously recorded deferred work remains tracked; administrative closeout does not erase it.

Success criteria: all 101 story headers match sprint entries; every done epic has only done stories; all existing planned epics/stories are represented without renumbering; no pending acceptance is checked off; all current summaries agree with verified v1.4.0. Documentation-only validation checks schema/inventory/status consistency, links, diffs and existing documentation tests. Historical release tests remain attributed to their original evidence and are not described as rerun results.

## 6. Change Navigation Checklist and Workflow Completion

- [x] 1.1–1.3: Trigger, problem and evidence established (12.4/v1.4.0 tracking drift).
- [x] 2.1–2.5: All epics reviewed; no new scope, removal or renumbering; resume at 12.5.
- [x] 3.1–3.4: PRD/architecture/UX impacts assessed; requirements unchanged; tracking/doc conflicts corrected.
- [x] 4.1–4.4: Direct adjustment selected; rollback and MVP reduction rejected.
- [x] 5.1–5.5: Issue, impact, rationale, detailed changes and handoff recorded.
- [x] 6.1–6.5: Reconciliation applied under explicit user update instruction; sprint tracker and handoff updated. Validation results recorded below when complete.

BMad Help after this workflow: optional `bmad-retrospective` for completed epics; next delivery `bmad-dev-story` for existing ready Story 12.5 followed by `bmad-code-review`. No sprint regeneration or implementation-readiness rerun is required because acceptance scope is unchanged; the omitted existing Epic 15 inventory is now restored.

### Epic 15 detailed metadata changes

Before: Epic 15 and Stories 15.0–15.7 exist in `epics.md` but have no tracker entries or dedicated delivery records. After: eight reconstructed story files, six done/two review; epic in-progress; retrospective optional. Existing definitions and linked historical verification are preserved. Developer/maintainer handoff: obtain approved dispositions for the 12 parity rows and reconcile initiative checklist evidence before closing 15.6/15.7. This acceptance follow-up is separate from the next sequential delivery Story 12.5.

## Validation Results — This Reconciliation

- `./.venv/bin/python -m unittest discover -s tests/test_docs -q`: 51 tests passed.
- Python/YAML inventory consistency check: all 101 story headers match tracker entries; all 16 epics match child completion; all 101 epic story definitions are represented; retrospective states remain optional; summary links resolve.
- `git diff --check`: passed after removing trailing whitespace from the new proposal.
- Read-only independent audits checked early/late delivery and the omitted UI migration track. Historical release validation remains attributed to the release evidence, not rerun here.
- Runtime/UI/Python code was not changed; full application and browser reruns are not applicable to this metadata/documentation-only task.
