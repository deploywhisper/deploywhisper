# Story 16.15 formal BMad code review

2026-11-05. Original outcome: **Changes requested**.

Current repair disposition: **R1–R3 resolved and independently verified**; see [fresh repair evidence](review-fixes.md). Story remains **in-progress** for the separate acceptance gates. Original findings below are retained as history.

Reviewed `8095877..440e683`, including the backend commit `db73571` and UI commit `440e683`:61 files,6138 text-diff lines, with screenshot binaries excluded from textual review. Blind Hunter, Edge Case Hunter and Acceptance Auditor completed independently. Prior development-review repairs were inspected as current code, not presumed correct.

Triage: **three P2 patch findings**, no new decision-needed or deferred code findings. The previously documented supplemental HTTPS verification decision and positive real-run browser proof remain separate open acceptance gates. This review request did not authorize that lane.

## R1 — P2: One unknown revocation blocks revoking unrelated runners

Location: `frontend/src/screens/runnerMutationState.ts:20–22,33–35`; UI enforcement at `frontend/src/screens/InfraAutomationRunners.tsx:165`. Affects AC2/AC3 operator credential recovery.

The store holds one revocation slot for the entire session/workspace. After runner A's revoke response is lost or returns503, the slot remains unknown. Every row's revoke button is disabled by `mutations.revocation`, so runner B cannot be revoked even though it is unrelated. Navigation and fresh health reads do not resolve the slot. Issuing new credentials can still be enabled while all revocations are blocked.

The leader executed the actual transpiled `RunnerMutationStore`: begin revoke A, mark it unknown, then begin revoke B under the same scope. B returned null, while beginning enrollment succeeded. This reproduces the same predicate used by the UI without a live external request.

Repair: retain pending/unknown revocations per target runner, with a bounded map and ticket identity. Keep duplicate revocation of A guarded without disabling independent revocation of B. Do not make health refresh blindly settle unknown effects. Add same-scope two-runner recovery coverage.

## R2 — P2: Unrecognized 4xx clears an uncertain issuance guard

Location: `frontend/src/screens/InfraAutomationRunners.tsx:139–142`. Affects AC3's uncertain one-time response handling.

The catch path treats any400/401/403/404/409/422/429 status as a definite rejection, without checking the parsed application error code. An HTML403 or unrecognized proxy response therefore removes the pending issuance marker and enables another enrollment/rotation, although it cannot establish that the original issuance did not commit. The collection mutation adapter already distinguishes recognized application rejections from unknown responses.

Reproduced using the actual transpiled runner API adapter, API client, marker store and the catch expression from the current component, with a controlled HTML403 response:

```text
status=403; code=null; ambiguous=false; issuance_reenabled=true
```

No network request or real credential was involved. The result demonstrates client classification, not a claimed live proxy failure.

Repair: require a recognized, appropriate structured application error before settling a submitted mutation as rejected. Retain unknown state for non-JSON/unrecognized4xx. Keep local pre-send validation failures distinct from submitted operations, and add both enrollment and rotation regressions.

## R3 — P2: Readiness and dispatch select different bounded candidate sets

Location: `services/infra_automation_collection_views.py:185–189`; comparison: `services/infra_automation_runner_tasks.py:59–68`. Affects AC2 and IAU15-FR-046's truthful routing/correction contract.

The new readiness projection sorts active registrations by credential expiry descending before its1000-row limit. Actual dispatch sorts active registrations by ID before the same limit. Expired active registrations are retained and do not consume current enrollment slots, so the sets can differ under normal retained history. The new UI can repeatedly say a compatible runner is available while unchanged real admission cannot select it.

The independent edge reviewer reproduced this in an isolated fixture database with1000 expired active registrations ordered before a current valid runner. Readiness returned `eligible`; `queue_assignment` returned `None`, failed the attempt and wrote `runner.no_eligible_runner`. No concurrent state change explained the difference.

Repair: share the bounded candidate-selection rules between readiness and dispatch, retaining live credential/permission/tag/profile/version checks. Add an integration regression proving parity with retained expired history; do not rely on future retention work to make the current claim true. The underlying dispatcher ceiling predates this story, but the new contradictory readiness result is introduced by this change.

## Dismissed hypotheses

- Attempt-state fallthrough: persisted attempts have exactly pending/claimed/running/succeeded/failed/timed_out/cancelled, all handled. The extra run-state names in frontend defensive parsing do not establish a reachable backend defect.
- Ordinary same-session refresh changing `identity.epoch`: `IdentityProvider.refresh` increments it only when session identity changes. Other increment paths withhold or clear mutation CSRF/loading authority. No runnable same-session duplicate-submission path was established from this hypothesis.

## Verification and acceptance

Fresh focused backend service/API tests: **23 passed,20 subtests**,3.97s. Fresh full UI unit suite: **377 passed**, plus two OpenAPI compatibility checks. These tests omit the three counterexamples; passing development/browser tests do not override them.

The acceptance audit found no additional runtime-contract defect. It confirmed that positive HTTPS enrollment and real isolated-runner recovery/browser proof remain explicitly unqualified. Existing HTTP access tests and synthetic component cases do not close AC6. Keep that gate open alongside R1–R3.

Only review documentation and tracking were changed. No runtime edits, commit, push, PR, TLS-lane execution or app-container interruption occurred. BMad Help routes next to `bmad-dev-story` for these review repairs, followed by the still-required acceptance work.
