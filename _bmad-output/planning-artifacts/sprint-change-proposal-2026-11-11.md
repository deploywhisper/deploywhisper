# Sprint Change Proposal — Accountable-Maintainer Pilot Waiver

Date: 2026-11-11
Status: Approved by accountable maintainer
Scope: Moderate governance and acceptance correction
Handoff: Product Owner / Developer, then Story 16.19 qualification

## 1. Issue Summary

Story 16.18 and Story 16.19 require an independent human self-service pilot.
The complete agent-executed technical qualification now passes, but no separate
human operator performed the runbook. On 2026-11-11 the accountable maintainer
explicitly approved proceeding and delegated the best bounded completion approach.

The project must not convert that approval into a fabricated human result. The
change therefore adds a release-specific waiver path: the accountable maintainer
may waive only independent human execution, explicitly accept the residual
self-service/runbook-usability risk, and preserve `NOT EXECUTED` for every pilot
procedure. The waiver is not pilot evidence and cannot broaden supported profiles.

Evidence reviewed:

- `docs/verification/infra-automation/16-19/prerequisite-profiles/README.md`
- `docs/verification/infra-automation/16-19/validation-summary.json`
- `docs/verification/infra-automation/16-19/prerequisite-review.md`
- `docs/verification/infra-automation/16-18/acceptance-audit.md`
- `docs/verification/infra-automation/16-18/review-fixes-validation-summary.json`

## 2. Impact Analysis

### Epic and story impact

- Epic 16 remains viable; no new epic or resequencing is required.
- Story 16.18 Packet 18.5 may close through this approved waiver because its
  technical recovery, documentation, metrics, 30-minute capacity, offline and
  browser evidence already passed. Story 16.18 can move to `done`.
- Story 16.19 may enter `in-progress`.
- Story 16.19 reference performance, safety, independent review, signed-artifact
  and publication gates remain unchanged.
- Epic 17 and its single release-note reference boundary are unaffected.

### Artifact impact

- Canonical infra-automation PRD: clarify IAU15-NFR-011/012 proof options and
  add the one-release waiver rule.
- Epic 16 / Stories 16.18–16.19: apply the same narrow proof language.
- Architecture §25.10: permit a representative operator pilot or explicit
  accountable-maintainer waiver; preserve every technical gate.
- UX specification: no change. No product interaction or runtime behavior changes.
- Qualification tooling: rename the gate from `independent-human-pilot` to
  `operator-pilot-or-maintainer-waiver` so an automated manifest cannot misstate
  what happened.
- Operator record and release limitations: record the waiver, maintainer approval,
  residual risk and unexecuted procedures.

### Technical impact

No runtime, API, schema, model, dependency or UI behavior changes. This is a
governance/acceptance correction plus validation-tool wording.

## 3. Recommended Approach

Selected approach: Direct Adjustment.

Direct adjustment is low implementation effort and medium governance risk. It
preserves completed engineering work and makes the accepted residual risk visible.
Rollback is not viable because it would discard qualified safety work without
creating human evidence. MVP reduction is unnecessary because the supported
technical profile remains viable.

Risk controls:

1. Keep every human-pilot procedure `Not executed`.
2. State that the waiver proves no human usability or implementer-independence outcome.
3. Do not expand the supported tool, runner, receiver, platform or network matrix.
4. Do not waive reference performance/saturation, technical review, signing,
   SBOM/provenance, defect or publication gates.
5. Carry the missing independent self-service validation as a visible release
   limitation and post-release follow-up.

## 4. Detailed Change Proposals

### PRD / NFR-011 proof

Old:

> Docs CI and operator self-service installation/recovery pilot.

New:

> Docs CI and either an independent operator self-service installation/recovery
> pilot or a written accountable-maintainer waiver that reviews executed technical
> qualification, states that no human pilot occurred, accepts residual self-service
> usability risk, and cannot replace technical or release gates.

### Architecture release gate

Old:

> ... SBOM/signing/provenance and a representative pilot.

New:

> ... SBOM/signing/provenance and either a representative operator pilot or an
> explicit accountable-maintainer waiver. A waiver records `NOT EXECUTED`, accepts
> residual usability risk and cannot waive any technical or publication gate.

### Story 16.19 AC5

Old:

> When a separate operator uses release-matched docs ...

New:

> When a separate operator completes the runbook, or the accountable maintainer
> explicitly waives only independent human execution after reviewing current
> technical evidence and accepting residual self-service risk ...

All stale-authority invalidation, restore, reconciliation, docs and support-limit
outcomes remain mandatory.

### Human pilot record

New status:

> WAIVED BY ACCOUNTABLE MAINTAINER — NOT EXECUTED

Every procedure remains `Not executed`; the record adds the approval, reviewed
evidence, residual risk and scope limitations.

## 5. Implementation Handoff

Classification: Moderate.

- Product Owner / maintainer: owns the explicit one-release waiver and residual risk.
- Developer: updates planning/story/tooling artifacts, closes Story 16.18, promotes
  Story 16.19 to `in-progress`, and continues remaining qualification packets.
- Reviewer/security reviewer: independently verifies the final code, evidence and
  release decision before publication.
- Release maintainer: authorizes and performs public writes only after every
  remaining mandatory gate passes.

Success criteria:

- No artifact claims a human pilot occurred.
- The renamed qualification gate validates fail-closed.
- Story 16.18 is closed with the waiver and existing technical evidence.
- Story 16.19 resumes without weakening performance, review, signing or publication.

## 6. Checklist Completion

- [x] 1.1–1.3 Trigger, problem and evidence documented.
- [x] 2.1–2.5 Epic impact, dependencies and sequencing assessed.
- [x] 3.1 PRD conflict and exact proof-language change identified.
- [x] 3.2 Architecture §25.10 change identified; no runtime architecture change.
- [N/A] 3.3 UX changes; no product interaction changes.
- [x] 3.4 Tooling, docs, story and sprint artifacts identified.
- [x] 4.1 Direct adjustment viable: low effort, medium governance risk.
- [x] 4.2 Rollback not viable.
- [x] 4.3 MVP reduction unnecessary.
- [x] 4.4 Direct adjustment selected.
- [x] 5.1–5.5 Proposal, impact, rationale, action plan and handoff complete.
- [x] 6.1–6.2 Proposal reviewed for completeness and consistency.
- [x] 6.3 Explicit user approval received on 2026-11-11.
- [x] 6.4 Story/sprint updates assigned to implementation handoff.
- [x] 6.5 Responsibilities and success criteria defined.

## Approval Record

The accountable maintainer explicitly approved the waiver and instructed the
agent to choose the best bounded approach, complete the task and resume Story 16.19.
This approval applies only to the independent-human-execution gate and does not
authorize fabricated evidence or public release writes.
