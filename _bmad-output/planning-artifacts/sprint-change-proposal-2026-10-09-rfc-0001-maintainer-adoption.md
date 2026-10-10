# RFC 0001 maintainer-directed adoption and qualification completion

Date: 2026-10-09. Mode: batch, under the maintainer's explicit approval/finalization request. Classification: minor governance/contract adjustment within existing Story 16.0; no new epic, runtime feature or release scope.

## Trigger and evidence

Story 16.0 retained RFC acceptance as pending despite the owner now directly stating they are the maintainer and approve the RFC. The original public window has not elapsed; the actual review history is preserved in the [decision](../../docs/verification/infra-automation/16-0/maintainer-decision-2026-10-09.md). Newer explicit maintainer direction is the authority for immediate adoption, not timeout or presumed review.

## Impact checklist

- [x] Trigger/impact (1.1–1.3): direct maintainership approval and request to finish the existing story.
- [x] Epic impact (2.1–2.5): Epic16 remains bounded; preserve 16.0–16.19, dependency order, earlier history and 12.5. No epic removal/resequencing.
- [x] Artifact conflicts (3.1–3.4): RFC decision, Story16.0 AC2 governance wording, architecture25 authority/ADRs, project context, readiness and evidence records must describe real direct approval with its exception; product/API/UI runtime is unchanged.
- [x] Options (4.1–4.4): direct adjustment selected. Rollback would discard useful passing qualification; reducing mandatory security/custody evidence would violate the requested contract. No MVP reduction.
- [x] Proposal (5.1–5.5): edits and handoff below retain every technical acceptance gate.
- [x] Approval (6.1–6.3): owner explicitly approves RFC and asks to finalize best choices; this authorizes this narrow correction. No additional approval is requested for the same action.
- [x] Handoff (6.4–6.5): root records adoption/readiness; native qualification executor proves actual Linux/custody; contract executor freezes typed fixtures; independent technical reviewers rerun/review before closure.

## Specific before/after edits

| Artifact | Before | Authorized adjustment |
| --- | --- | --- |
| RFC0001 decision | Proposed; approving maintainers absent | Accepted on 2026-10-09 by direct @pramodksahoo decision; specific early-window exception, honest public history and human coverage |
| Story16.0 AC2/WP1 | Acceptance only after seven days of public review | Recorded real maintainer outcome under ordinary process or explicit maintainer-specific exception; no invented platform discussion, dates or approvals |
| Architecture/context | RFC Proposed; eight ADRs conditional | Accepted bounded scope, with finalized choices/evidence recorded before qualifying their technical assumptions |
| Qualification | Missing operator profile blocks WP4 | Prepare the declared pinned non-root Linux/OpenTofu profile before executing real offline synthetic probes; no lower profile substitution or app dependency changes |
| Contract/readiness | Draft/unqualified contracts and open gates | Freeze concrete version1 fixtures against tests and real qualification; close IRs only for actual evidence |

## Handoff and success criteria

Direct implementation within Story16.0. Maintain public decision chronology and coverage limits, run all mandatory negative/crash/custody/containment cases, freeze compatible contracts, rerun readiness and full validation, then review and close the story on its feature branch. Later stories still own production implementation, real integrated browser/network/operations and v1.5.0 release qualification. Initial effort remains the existing 1–2 person-week qualification packet; exact downstream estimates are updated from actual results, not approval alone.

This adjustment does not globally amend governance, waive any real containment/custody/authority test, authorize autonomous decisions or direct apply, or declare a production release ready.
