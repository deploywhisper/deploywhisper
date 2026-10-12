# Story 16.0 retained qualification code review

2026-10-09. Scope: disposable WP2/WP3 and the permitted synthetic WP5 fault
slice, plus screened evidence. The BMad code-review layers used a diff-only
Blind Hunter, a project-reading Edge Case Hunter and a story-aware Acceptance
Auditor. Root Codex integrated fixes. This is internal technical review, not
independent human RFC approval or production qualification.

All layers returned findings. Five deduplicated patch families were retained;
none required an ambiguous scope decision, and none was dismissed or waived.
Each received a failing regression before the fix.

| Finding | Fix and verification |
| --- | --- |
| Session rotation refreshed absolute lifetime | Preserve the original authentication creation time across rotation; repeated rotation cannot extend the one-hour deadline |
| Unencodable credentials raised errors | Bound and validate UTF-8 before hashing or abuse-accounting; lone-surrogate requests deny, bootstrap/reset reject safely |
| Measurement could publish passing evidence after failure | Refuse publication on failed tests, unverified matrix totals or failed measured cryptographic verification; regressions preserve the prior artifact and require a nonzero result |
| Malformed JSON/scope inputs raised errors | Stream at most 4,096 bytes, require a JSON object and scalar scoped strings; malformed/non-object/oversized requests and non-scalar IDs deny |
| Receipts could disagree with the authorized receiver | Persist configured logical identity, bind admission/start and generated receipts to it, compare terminal sender with configured and stored identity; signed wrong-receiver receipt cannot succeed or unlock |

The Acceptance Auditor reran the first corrected three-module suite: 40 tests
passed. The final measured-crypto failure regression increased WP2 to 18 methods;
the root rerun then passed **41 tests** (18 identity, 11 SQLite, 12 receiver).
The Edge Case Hunter verified the final measurement guard and found no
unresolved item. Exact commands and broader checks are in the manifest.

The root also fixed the initial generic SQLite fixture import to a unique
namespace and explicit connection closing; a newly exposed WAL initialization
lock race then received bounded configuration handling. Receiver unknown-to-
terminal reconciliation requires independently observed exact durable synthetic
effect evidence; a signature alone never proves an action occurred.

Public RFC review/decision, actual Linux tool/provider containment, real saved
binary-plan custody, separate OS identities, encryption policy, integrated
network/browser/production runtime, final contract freeze and readiness remain
open. A clean review of this bounded slice cannot complete Story 16.0 or promote
downstream stories. No public message or approval was sent by this review.

## Final contract and real-profile review — 2026-10-10

Independent contract review found two additional defects: integer1 was coerced into the enrollment boolean, and unordered graph references could raise KeyError before local validation. Both received failing regressions and fixes. The reviewer reran 15 tests, accepted 240 valid workflow permutations and denied 725 mutated negative boundaries with controlled ValueError outcomes. No finding remains.

Independent real-profile verification executed `DW16_REAL_LINUX=1 ./.venv/bin/python -m pytest tests/test_infra/test_infra_automation_real_linux_qualification.py -q`: 3 passed, 6 subtests passed in 13.74s, exit 0. It checked actual image/catalog/source identities, separated UIDs, containment/resource/process controls, real saved-plan custody, seven attacks, five crashes, 30 tuple mutations and changed-plan rejection. A wording finding was corrected: the harness checks image/schema/catalog/source/control values; it does not claim to verify the complete profile checksum at runtime.

The qualified profile SHA is `1f91ca01dcfce0a06b6ab19cba7f145dae499a551608f0cdc8386c25dd1cbf49`. Anchored tmpfs establishes process/receiver-container restart with bounded stores; host power-loss durability, production integration, capacity and universal redaction remain assigned downstream. These limits were reviewed and do not represent those broader capabilities as delivered.

The maintainer's direct RFC decision, reaffirmed on 2026-10-10, is recorded separately. Independent technical agents supply no second human approval. Final readiness and repository validation close the bounded Story 16.0 scope.

## Follow-up review and fixes — 2026-10-12

The repeat BMad review identified four actionable items: incomplete evidence could pass the qualification gate; fast completed processes could escape output limits; interrupted custody finalization left an orphan key; and the manifest's scope summary contradicted actual saved-plan evidence. Story16.0 and dependent promotion were reopened while these were resolved.

Regression-first tests reproduced each executable defect before implementation. The gate now checks complete, typed case sets and exact crash outcomes. It denies final combined output overflow before truncating readback. Custody writes complete objects to private staging, serializes finalizers, publishes one directory atomically and recovers abandoned unpublished work. Published bundles remain immutable. The scope summary now accurately distinguishes real disposable Linux/saved-plan proof from downstream production support.

Independent follow-up layers completed: diff-only Blind Hunter found no actionable executable defect; Edge Case Hunter passed 22 tests/1,088 subtests and independently synchronized two finalizers, observing exactly one publication and one refusal with original bytes intact and no pending staging; Acceptance Auditor repeated both the regression suite and actual Linux suite (3 passed/6 subtests in15.27seconds), finding no remaining acceptance defect. This is technical review, not additional human governance approval.

The new actual evidence includes 519 short-write calls, kernel ENOSPC after key creation, and abrupt receiver exit73 after key creation, before publication and after publication. Unpublished cases recover; the published case denies replacement and verifies the original saved plan. New image/profile identity and superseded identities are recorded in WP4/WP5. Final repository validation and digest synchronization are recorded in the manifest and story closeout, rather than inferred from the narrower targeted checks.

The additional changed-test discovery regression found in the existing PR check was fixed with four failing-first behavior tests. A separate bounded review confirmed actual test selection, fixture exclusion, failure propagation and execution under macOS Bash3.2. The final infrastructure rerun passed253tests/1skip, and the three new regression modules passed26tests/1,092subtests.
