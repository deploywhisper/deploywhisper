# Story 16.16 formal code review — 2026-11-05

Reviewed baseline `0f18c01` through `36778fd`, independently of development review.
Three fresh native reviewers performed blind diff review, edge-case tracing and
acceptance audit. Working tree was clean. Initial review outcome: **changes requested**. Final outcome: **approved after repairs**.
All seven actionable findings are repaired, independently rechecked and verified. No human product decision is needed for these bounded corrections.

| ID | Severity / source | Finding and consequence |
| --- | --- | --- |
| R1 | High / edge + root | A valid two-unit workflow with downstream collection depending on an upstream human decision is admitted, but the decision requires the not-yet-collectable whole bundle. Isolated service probe reproduced queued admission followed by409 material denial. Reject this unschedulable dependency at admission. |
| R2 | Medium / blind | Latest inventory check precedes idempotency lookup, so a lost accepted response cannot be replayed after a later map revision. Preserve exact replay while keeping new starts bound to current revision. |
| R3 | Medium / blind | Lost start response leaves an unresolved marker forever, with no same-key replay or adoption. Provide explicit bounded recovery with the exact retained payload and idempotency identity. |
| R4 | Medium / edge | Workflow/revision paging stays enabled while start awaits authority/files. Executed component probe changed selection/confirmation but observed the old request submit. Disable paging during the pending operation. |
| R5 | Medium / blind | Backend path length counts Unicode codepoints; browser counts UTF-16 code units. A300-supplementary-character path is valid backend input but rejected by the browser. Align path semantics. |
| R6 | Medium / acceptance | Every row error marks the ID input invalid, while the actual invalid prerequisite/source input has no association. Error summaries do not navigate to fields. Implement the approved accessible field-error behavior. |
| R7 | Medium / root + edge | Lost save revision2 followed by revision3 cannot be adopted: the UI lists only latest revisions while recovery requires revision2. Add bounded authorized revision history and explicit verified adoption. |

Independent initial proof: unit-map/service/API60tests52subtests pass. Ten screenshot
hashes/dimensions and nine historical log hashes match their records. These earlier
passing tests do not cover the new findings. Previous internal review remains
historical evidence, not the outcome of this fresh review.

## Existing dependency follow-up

D1 (deferred, pre-existing): GitHub reports medium `brace-expansion` advisory GHSA-q2hr-2g5m-vwhr in unchanged root `package-lock.json`. Confirmed open through Dependabot alert8 during branch publication. This does not originate in the story diff; dependency maintenance remains separate. See the deferred-work register.

## Repair verification and closure

- R1/R2: independent probes verify rejection before collection/analysis, policy-only ancestry compatibility, exact accepted replay after supersession, and denial of changed payloads/new stale admissions.
- R3: explicit replay retains a cloned exact payload/key and current credentials. A failed replay (including a confirmed gateway rejection) never establishes that the original ambiguous request failed; only successful readback resolves it. The final browser injects a labelled client/gateway429 fault before retry transmission, then performs the identical real API replay and verifies one original run.
- R4/R5: pending paging controls are disabled; source-path lengths count Unicode codepoints consistently with the backend.
- R6/R7: field diagnostics associate with the actual control and keyboard summary links; bounded scoped history exposes the exact earlier persisted revision for explicit adoption after a later save.

Fresh validation on the repaired source:

| Check | Result |
| --- | --- |
| Root unittest discovery | 1,866 tests, 3 skips; exit0,832.746s |
| API/CLI/infrastructure pytest | 754 passed, 1 skipped, 2,358 subtests; exit0,438.03s |
| Automation pytest | 1,063 passed, 1 skipped, 3,081 subtests; exit0,498.31s |
| Focused backend | 95 tests, 57 subtests pass |
| Frontend | 438 tests plus2compatibility checks; typecheck/build pass |
| Actual Compose review | 4 tests pass,45.4s;18screenshots, zero axe critical/serious, visual94/100 |
| Real collection | 49 checks qualified; current integrity9tests73subtests pass |
| Static/security | Ruff/repository-wide formatting565files and scoped Bandit pass;318existing-code mypy diagnostics remain outside changed unit modules |

The earlier all-directory CI baseline remains in results.md; this review reran the
full root suite and exact affected CI shards rather than claiming a fresh single
successful ci-local.sh invocation. Source/build details, the interrupted test-only
response-body probe, earlier successful run and final fault-qualified proof are
preserved in [review browser proof](review-browser-proof.md).

No introduced findings remain open. D1 is the pre-existing dependency follow-up.
The backend and UI are separate Git Flow branches targeting develop; the backend
is labelled backend-for-ui. Publication receipts are reported by the workflow.
