# Story 17.10: v1.5.0 Release Integration and Joint Qualification

Status: backlog
Preparation: refined
Release: v1.5.0 (shared release train with Epic 16) | Priority: P1 within the independent Epic 17 lane

## Story

As a maintainer shipping Epic 16 and Epic 17 under one v1.5.0 tag, I want Epic 17's release documentation published as a self-contained fragment and the two epics proven mutually independent at build and test level, so that a combined release is safe to cut, the release-notes file has exactly one owner, and Epic 17 can still be cut from v1.5.0 cheaply if it is not ready.

## Why this story exists

This story was created on 2026-10-20 when the owner retargeted Epic 17 from v1.6.0 into v1.5.0. The retarget introduced exactly one new cross-epic obligation — a shared release — and this story contains it so that the obligation does not leak into the other ten Epic 17 stories or into Epic 16.

It deliberately does **not** re-prove feature behaviour. Release-wide feature qualification is owned by Story 17.9 and must not be duplicated here.

## Implementation gates

- Blocked until **17.0 through 17.9** have landed their owned contracts. This is the last Epic 17 story.
- **No Epic 16 code dependency.** The single touchpoint is documentation: Story 16.19 includes this story's fragment by reference.
- This story must never edit Epic 16's release-notes file, Epic 16 stories, Epic 16 tracking rows or `infra_automation/`.
- If Epic 17 is cut from v1.5.0, this story is cancelled with it and Epic 16's release is unaffected. Verifying that the cut remains possible is part of AC5.

## Acceptance Criteria

1. **AC1:** Given the v1.5.0 release, when Epic 17 release documentation is published, then it exists as a self-contained fragment under `docs/releases/` owned entirely by Epic 17, and Story 16.19's release-notes file references it with a single added line and no content duplication.
2. **AC2:** Given an operator upgrading to v1.5.0, when they read the upgrade and rollback record, then it states that grounding is disabled by default, that no migration, credential provisioning or IAM change is required to upgrade, and how to disable grounding without downgrading the application.
3. **AC3:** Given grounding disabled, when a v1.5.0 build containing both epics is compared against a build containing Epic 16 alone, then reports, fixtures, schemas, API responses, CLI output and agent output are identical, with the comparison recorded as evidence.
4. **AC4:** Given each epic's test shard, when it runs with the other epic's modules absent from the import graph, then it passes, and a CI check fails the build if either epic imports from the other's module tree.
5. **AC5:** Given a decision to cut Epic 17 from v1.5.0, when the documented cut-back procedure is followed on a scratch branch, then Epic 16's release remains complete and green, proving the cut path is real rather than asserted.
6. **AC6:** Given the combined release, when the release manifest is published, then it names both epics, states that grounding is disabled by default, and does not claim any Epic 17 capability that Story 17.9 did not qualify.

### Requirement Traceability

Coverage intent: delta over the current released baseline. Mapping is an acceptance obligation, not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| LEG-FR-041 | Publish Live Environment Grounding release documentation as a self-contained fragment owned by Epic 17, included by reference from Story 16.19. | Fragment published; 16.19 reference is a single line with no duplicated content |
| LEG-FR-042 | Publish an upgrade and rollback record stating grounding is disabled by default and requires no migration or credential provisioning. | Upgrade/rollback record reviewed against a clean-upgrade exercise |
| LEG-FR-043 | Produce joint-release qualification evidence that a both-epic build with grounding disabled is behaviourally identical to an Epic 16-only build. | Recorded differential comparison across reports, schemas, API, CLI and agent output |
| LEG-NFR-013 | Sharing the release tag must not create a code, test or fixture dependency between the epics. | Per-shard isolation run plus a CI cross-import invariant |

## Tasks / Subtasks and bounded ownership

Execute one bounded packet at a time on `feature/17-10-release-integration`. Each packet owns the named paths.

- [ ] **Packet 10.1: Epic 17 release fragment — owner: maintainer.**
  - Owned write paths: `docs/releases/v1.5.0-live-environment-grounding.md`.
  - Output: a self-contained fragment covering what grounding does, enablement, the required minimal IAM policy, degradation behaviour, snapshot handling, air-gapped use and the disabled-by-default guarantee.
  - Acceptance proof: AC1 — fragment published and self-contained.
  - **Boundary note:** do not edit Epic 16's release-notes file. Supply the Epic 16 lane with the one-line reference to add, and record that handoff in the PR description.
- [ ] **Packet 10.2: Upgrade and rollback record — owner: maintainer.**
  - Owned write paths: `docs/releases/v1.5.0-live-environment-grounding.md`, `docs/live-environment-grounding/README.md`.
  - Output: an upgrade and rollback record verified by an actual clean-upgrade exercise from the prior release, not by assertion.
  - Acceptance proof: AC2 — recorded upgrade exercise with grounding left disabled.
- [ ] **Packet 10.3: Disabled-by-default differential — owner: verification owner.**
  - Owned write paths: `docs/verification/live-environment-grounding/17-10/`, `tests/test_cloud/`.
  - Output: a recorded differential of reports, fixtures, schemas, API responses, CLI output and agent output between a both-epic build with grounding disabled and an Epic 16-only build.
  - Acceptance proof: AC3 — byte- or contract-level equivalence evidence, including any differences found and how they were resolved.
- [ ] **Packet 10.4: Cross-epic isolation CI invariant — owner: core implementer.**
  - Owned write paths: `tests/test_cloud/`, `scripts/ci-local.sh`.
  - Output: per-shard isolation runs plus a CI check that fails if `cloud/` imports `infra_automation/` or the reverse. Include a deliberate failing case proving the check detects a violation.
  - Acceptance proof: AC4 — isolation runs green and the violation case correctly fails.
  - **Boundary note:** the check is authored in the Epic 17 lane but asserts a symmetric rule. Adding it to `scripts/ci-local.sh` is an append-only edit to a shared file; coordinate the merge order with the Epic 16 lane.
- [ ] **Packet 10.5: Cut-back rehearsal — owner: maintainer.**
  - Owned write paths: `docs/verification/live-environment-grounding/17-10/`.
  - Output: a scratch-branch rehearsal of removing Epic 17 from v1.5.0, confirming Epic 16's release remains complete and green, with the procedure written down.
  - Acceptance proof: AC5 — recorded rehearsal result.
  - **Note:** this is the insurance policy for the shared tag. Run it early rather than at release time, when it is useless.
- [ ] **Packet 10.6: Combined release manifest — owner: maintainer.**
  - Owned write paths: `docs/verification/live-environment-grounding/17-10/`, `ROADMAP.md`.
  - Output: a manifest naming both epics, stating the disabled-by-default posture, and claiming only what Story 17.9 qualified.
  - Acceptance proof: AC6 — manifest reviewed against the 17.9 qualification matrix for over-claiming.

## Dev Notes

- The fragment pattern exists to remove a conflict, not to add ceremony. The v1.5.0 release-notes file is the single most contended artifact of this release; two lanes editing it at the same time is the predictable failure. One owner, one reference line.
- AC3 is the substantive one. "Disabled by default" is an easy claim and a frequently false one: a feature can still alter behaviour through import side effects, registry registration, serializer field ordering, settings defaults or migration state. Diff the real outputs rather than reasoning about the flag.
- AC5 is deliberately a rehearsal, not a plan. A cut-back path that has never been executed is an assumption. Running it early converts the shared release tag from a risk into a reversible decision.
- Do not let this story absorb unfinished work from 17.0–17.9. If an earlier story is incomplete at this point, the correct outcomes are to finish it or to cut Epic 17 from v1.5.0 — not to paper over the gap in release documentation.
- Honest-claim discipline applies to release copy with full force. Any capability described in the fragment must trace to a qualified Story 17.9 result.

### Project Structure Notes

- New paths: `docs/releases/v1.5.0-live-environment-grounding.md`, `docs/verification/live-environment-grounding/17-10/`.
- Shared file touched: `scripts/ci-local.sh`, append-only.
- No application module is modified by this story beyond test additions under `tests/test_cloud/`.

### References

- [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md)
- [Canonical feature PRD](../planning-artifacts/prd-live-environment-grounding.md)
- [Epic 17 stories](../planning-artifacts/epics.md)
- [Architecture Section 26](../planning-artifacts/architecture.md)
- [Epic 16/17 boundary plan](../planning-artifacts/epic-16-17-boundary-and-parallelization-plan.md)
- [Story 17.9 qualification](17-9-extensibility-cli-agent-and-qualification.md)
- [Operator guide](../../docs/live-environment-grounding/README.md)
- [Project implementation context](../project-context.md)

## Dev Agent Record

### Agent Model Used
Planning preparation only; implementation agent records its model at execution.

### Debug Log References
Not executed.

### Completion Notes List
- Story specification prepared; no implementation, release publication, differential comparison, rehearsal or runtime test performed.
- Commands and proofs above are future obligations, not results.
- UI validation not applicable: this story changes documentation, verification evidence and CI checks only.

### File List
- `_bmad-output/implementation-artifacts/17-10-v1-5-0-release-integration-and-joint-qualification.md` (story specification only).
