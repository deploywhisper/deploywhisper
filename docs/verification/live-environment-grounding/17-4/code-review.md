# Story 17.4 code review

**2026-11-23 · Changes requested.** Blind Hunter, Edge Case Hunter, and Acceptance Auditor examined the 20-file working-tree diff against `495d1d4` on `feature/17-4-plan-reality-divergence`. Story and sprint tracking returned to `in-progress`.

## Findings

| Priority | Finding | Evidence and expected behavior |
| --- | --- | --- |
| P1 | An unchanged sampled attribute can clear CI for a change to an unobserved attribute. | `analysis/divergence.py:475` iterates fixed comparable fields without checking whether they cover the plan's changes. At `:581`, any checked field can support `match`. For example, an ingress or egress edit on a security group can clear CI because a different field such as VPC ID agrees. Require enough evidence for the planned mutation or classify it as unknown. AC1, AC5 and AC6. [Divergence scope](../../../rfcs/0002-live-environment-grounding.md#plan-versus-reality-divergence) |
| P1 | Name-like IDs can match the wrong AWS scope. | `analysis/divergence.py:300` checks region only when the plan values specify it. When the ARN is absent or screened, the matcher accepts an equal scope-local ID without proving that the account and region agree. A retained observation for a same-named resource in a different scope can clear the gate or produce a false finding. Require trusted scope binding for those identifiers while preserving account masking. AC1, AC2 and AC5. |
| P1 | Old observations and unproven chronology can clear CI. | `services/divergence_service.py:99` uses retained availability and `:155` gates on row statuses. A retained observation older than the existing live freshness policy can still clear CI and omit the grounding uncertainty signal. In addition, `analysis/divergence.py:225` produces unknown freshness when the date is missing or unusable, while `:516` rejects only a known pre-plan observation. Respect snapshot freshness at analysis time and require verifiable plan-to-observation ordering for a definitive gate result. The plan-age warning remains a separate measure. AC3, AC5, AC6 and LEG-NFR-004. |
| P2 | An incomplete or errored recorded plan can pass the gate. | `analysis/divergence.py:619` and `:631` use only `resource_changes`. They do not account for planner error, incomplete-plan flags, or deferred changes. A matching visible subset, including an empty subset, can return exit 0. Reject unusable input or carry unresolved deferred changes into the gate. AC5 and AC6. [Terraform plan JSON reference](https://developer.hashicorp.com/terraform/internals/json-format#plan-representation) |
| P2 | Confirmed drift can hide missing comparison evidence from report-level context. | `analysis/divergence.py:581` permits a `diverged` row with `comparable_facts_incomplete`. `services/analysis_service.py:2564` sets partial and insufficient context only when a row is unknown or unreadable. Preserve the verified finding and propagate the gap to the report so aggregate confidence reflects that incomplete coverage. LEG-NFR-004. |
| P2 | Temporal checks can hide an actual read denial. | `analysis/divergence.py:516` returns unknown before the unreadable check at `:528`. A denied observation that predates the plan loses its unreadable status and missing permission. Keep the read failure and the temporal limitation distinguishable. AC1 and AC6. |
| P3 | The caution path waits for a narrative that it discards. | `services/analysis_service.py:2610` invokes narrative generation before `:2623` replaces its output with the deterministic caution briefing. Choose the deterministic branch before the provider call. AC4 briefing path. |

## Scope

The separately scheduled work owns production AWS acquisition, snapshot import and report UI. Absence of an individual tag fact remains unresolved until a qualified observation can prove absence. Pure creates remain a case without prior-state comparison evidence.

## Verification

- A fresh focused pytest run covered comparison, the severity floor, retained-report integration, both gates, and cloud/evidence regressions. It passed 204 tests and 376 subtests.
- Repo-wide Ruff lint and formatting passed. The complete diff, including untracked implementation files, passed Git's whitespace check.
- All nine runtime source hashes match the recorded dev-story verification, including the prior full local CI run of 3,894 tests across 12 shards with three skips. The new findings concern cases outside that coverage.

## Fix verification

All seven action items have implementation fixes and offline regression coverage. The [verification packet](README.md#review-follow-up-verification) covers scope and timing eligibility, unsupported changes, invalid plan states, report uncertainty, denial fidelity, and the deterministic briefing. Story 17.4 is back in review.

## Re-review on 2026-11-23

**Changes requested.** Blind Hunter, Edge Case Hunter, and Acceptance Auditor reviewed the 22-file working-tree diff against `495d1d4`. The seven original regressions remain covered. The following cases extend beyond that coverage.

| Priority | Finding | Evidence and expected behavior |
| --- | --- | --- |
| P1 | The divergence gate can evaluate a different plan than the shared analysis intake. | `services/divergence_service.py:105` selects from raw JSON submissions by shape and format version, separate from the shared intake at `services/intake_service.py:319` and `:407`. A plan excluded by sensitive-file intake can still drive the comparison when another artifact makes the submission eligible. An additional Terraform plan with an unqualified format can also escape the comparison's one-plan check. Bind the gate and its findings to exactly one admitted plan. Reject ambiguous or excluded selections. AC1, AC2 and AC5. |
| P1 | Contradictory recorded prior values can support a false match. | `analysis/divergence.py:677` selects `prior_state` values when available and `:453` uses `change.before` only for mutation coverage by field name. When both sources provide different values for a comparable field, the gate can count that field as covered even though the live value disagrees with the change's declared before state. Until the sources reconcile, represent the affected comparison as unverified. AC1, AC5 and AC6. |
| P2 | A denial can be attributed to a resource in the wrong scope. | `analysis/divergence.py:654` attaches unreadable status and the permission after checking only address and family. Scope/identity verification at `:700` is bypassed for this branch. Verify identity before attributing the denial. Preserve the verified denial when timing alone is inconclusive. AC1 and AC6. [AWS resource identifiers](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference-arns.html) |
| P2 | A snapshot can age out during admission finalization after the last freshness check. | `services/analysis_service.py:2828` checks age before the publication body exits. `services/cloud_context_service.py:1011` then verifies evidence and retention before commit. If the snapshot crosses the age cutoff during that work, the gate can still use the cached current result. Apply the freshness fence at finalization and cover the interval after the publication body. AC5 and LEG-NFR-004. |
| P2 | Grounded publication masks ordinary report storage failures. | The publication body at `services/analysis_service.py:2799` runs inside `divergence_admission`. Its unit of work wraps arbitrary exceptions at `services/cloud_context_service.py:548`, then `services/divergence_service.py:60` translates them to unavailable evidence. The API can return 404 and the CLI exit 2 for a report storage failure. Preserve rollback and distinguish persistence failures with the established API 500 and CLI exit 1 contract. |
| P2 | An invalid UTC offset can establish a definitive chronology. | `analysis/divergence.py:34` permits out-of-range offset minutes and `:224` delegates to `datetime.fromisoformat`, which normalizes some invalid offsets. Validate the offset components before using them to order the plan and observation. AC3 and AC5. |

### Scope and verification

- Permanent structured comparison in the report retrieval API remains assigned to Story 17.8 under LEG-ADR-08 and LEG-FR-034. Story 17.4 continues to persist its evidence-linked finding and return the structured comparison through CLI and analysis submission.
- Deliberate empty plans and supported older producer artifacts without newer optional completion fields remain valid inputs. The earlier fix rejects explicit incomplete or errored plans and recorded deferred changes.
- Fresh focused pytest passed 216 tests and 391 subtests. Ruff lint, repo-wide formatting, and the complete diff whitespace check passed. All nine runtime source hashes match the previous full local CI run of 3,906 tests and the tested offline Python 3.11 image.

### Re-review fix verification

All six re-review action items have implementation fixes and offline regression coverage. The [verification packet](README.md#re-review-follow-up-verification) records the matching plan intake, comparison and commit boundaries, and persistence error tests. Story 17.4 is back in review.

## Closeout review on 2026-11-23

**Changes requested.** The three review layers checked the 23-file working-tree diff against `495d1d4`. The latest fixes cover report write/commit errors, the shared plan selection, conflicting evidence, scope-qualified denials, stale observations and malformed UTC offsets. The remaining storage error occurs between a successful write and commit.

| Priority | Finding | Evidence and expected behavior |
| --- | --- | --- |
| P2 | Post-write verification still misclassifies a report persistence failure. | `services/cloud_context_service.py:1025` flushes and verifies newly stored evidence after the report body returns. An operational database error there is outside the consumer error wrapper at `services/divergence_service.py:107` and occurs before the UOW marks the commit phase at `:70`. The generic cloud wrapper can convert it to HTTP 404 or CLI exit 2 even though report publication failed and rolled back. Preserve the persistence error contract for this finalization phase while keeping evidence policy and authorization failures distinct. |
| P3 | Timestamp conversion truncates comparison precision. | `analysis/divergence.py:34` accepts fractional seconds beyond microseconds. Parsing at `:225` discards the extra digits, so plan generation later than the observation within the same rounded microsecond can be classified as ordered. Preserve the ordering or treat unsupported nonzero precision as unverified. |

Fresh focused pytest passed 257 tests and 405 subtests. Ruff lint, repo-wide formatting, and the complete diff whitespace check passed. All nine runtime source hashes match the recorded 3,922-test full CI run and the offline Python 3.11 image. Closeout remains blocked and the index is empty.

## Re-review on 2026-11-26

**Changes requested.** Blind Hunter, Edge Case Hunter, and Acceptance Auditor reviewed all 23 working-tree files, including untracked files, against `495d1d4` on `feature/17-4-plan-reality-divergence`. Four patch findings remain open. Story and sprint status are `in-progress`.

| Priority | Finding | Evidence and expected behavior |
| --- | --- | --- |
| P1 | A tag-only change on a security group can clear CI with ingress unverified. | `analysis/divergence.py:63` compares VPC ID only for security group scalar fields, while `:660` checks completeness against the planned changes. The existing AWS projection emits identical complete facts for the selected group before and after an out-of-band CIDR rule change. A recorded tag edit with unchanged prior/planned ingress can therefore return `match` and exit 0. Require evidence for security-critical recorded attributes on touched resources or leave their comparison unknown. AC1, AC4, AC5, AC6 and LEG-NFR-004. [AWS projection](../../../../cloud/aws/catalog.json) · [RFC divergence example](../../../rfcs/0002-live-environment-grounding.md#plan-versus-reality-divergence) |
| P2 | A contradictory no-op or duplicate change can clear CI. | `analysis/divergence.py:848` skips ordinary no-op rows before validating identity uniqueness at `:861` and without checking that the recorded before and after agree. A matching fixture relabelled as a no-op with different before and after termination protection returned no rows and exit 0. Including that row beside its original update also returned exit 0. Validate action consistency and uniqueness of the plan's change identities before filtering legitimate no-ops. AC5 and AC6. |
| P2 | Post-write evidence verification can misclassify a report storage failure. | The open closeout item at `services/cloud_context_service.py:1025` persists. Injecting a database operational error during publication verification returned HTTP 404 and CLI exit 2 with `grounding_evidence_unavailable`. Zero reports committed. Keep the rollback and return HTTP 500 and CLI exit 1 with `report_persistence_failed`. |
| P3 | Sub-microsecond timestamp truncation can clear CI for an observation that predates the plan. | The open closeout item at `analysis/divergence.py:225` persists. An observation starting at `12:00:00Z` and a plan timestamp of `12:00:00.0000001Z` produced `current`, `match` and exit 0. Preserve the ordering or report it as unverified. AC3, AC5 and AC6. |

### Verification

- Fresh focused pytest covered the divergence engine, severity floor, API/CLI gates, retained-report publication, shared plan intake, observation freshness, and cloud and evidence suites. It passed 237 tests and 397 subtests.
- Repo-wide Ruff lint and formatting passed, as did the complete diff whitespace check.
- The re-review used synthetic fixtures and local database fault injection. Full local CI and the offline container checks were run in the previous review cycle. UI validation is outside this story's scope.

### Fix verification on 2026-11-27

All four findings have implementation fixes. The focused regression run passed 268 tests and 422 subtests. The [verification packet](README.md#2026-11-27-review-follow-up-verification) records the security group projection, action validation, publication fault injection, and timestamp cases.

## Re-review on 2026-11-27

**Changes requested.** Blind Hunter, Edge Case Hunter, and Acceptance Auditor reviewed all 23 working-tree files against `495d1d4`. The previous six regression tests passed for the scenarios they cover. Two adjacent cases still require changes. Story and sprint status are `in-progress`.

| Priority | Finding | Evidence and expected behavior |
| --- | --- | --- |
| P1 | A tag-only EC2 plan can clear CI despite observed security group attachment drift. | The AWS catalog retains direct EC2 security group IDs at `cloud/aws/catalog.json:24`. The comparator checks covered scalars and tags at `analysis/divergence.py:603` and `:647`, and its rule-specific completeness check at `:541` covers only security group resources. An isolated API run used a recorded EC2 tag edit and a retained AWS projection with a different attached group. It returned HTTP 200, `match`, and `requires_caution=false` while checking only the tag. Compare qualified attachment facts when available, with a caution floor for confirmed drift, and leave the comparison unresolved when the evidence cannot verify them. AC1, AC4, AC5, AC6. |
| P2 | A repository-level database error on the final snapshot read still looks like missing grounding evidence. | The retention check at `services/cloud_context_service.py:1026` calls the snapshot repository. Its `Session.get` error is translated to `CloudSnapshotIntegrityError` at `models/repositories/cloud_snapshots.py:215`, outside the operational-error catch at `services/divergence_service.py:71`. The current test injects above that translation. Fault injection at the actual database read, after the report write, returned HTTP 404 and CLI exit 2 with `grounding_evidence_unavailable`. Both attempts rolled back and left zero reports. Preserve the operational failure through rollback and return HTTP 500 and CLI exit 1 with `report_persistence_failed`. |

Fresh focused pytest passed 268 tests and 422 subtests. Repo-wide Ruff lint and formatting and the complete diff whitespace check passed. All nine runtime files and all three updated regression test files still match the prior verification hashes. The 3,928-test full CI run and offline container checks are from the fix cycle.

### EC2 attachment and snapshot storage fix verification

Both findings have implementation fixes. The API regression proves that EC2 attachment drift fails the gate and publishes evidence for each live group. The storage regression injects faults below the repository boundary and verifies the public error contracts on both sides of the report write. The [verification packet](README.md#ec2-attachment-and-snapshot-storage-fix-verification) records the checks and results.

### Git Flow closeout on 2026-11-27

All review items are resolved. The closeout matched the complete candidate against the validated 27-file diff and the offline image source hashes. The independent recheck passed seven tests and 17 subtests for both latest findings. Fresh focused pytest passed 67 tests and 53 subtests across comparison, collection, the API, and report publication. Ruff lint, formatting, scoped Bandit, and the complete diff whitespace check passed. The feature branch targets `develop` through a PR.
