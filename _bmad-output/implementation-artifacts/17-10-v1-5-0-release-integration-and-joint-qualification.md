# Story 17.10: v1.6.0 Release Integration and Qualification

Status: backlog
Preparation: refined
Release: v1.6.0 (independent release train) | Priority: P1 within the independent Epic 17 lane

## Story

As a maintainer shipping Epic 17 on its independent v1.6.0 train, I want its release documentation and compatibility qualification owned by the Epic 17 lane, so grounding can ship safely without coupling or delaying Epic 16.

## Why this story exists

This story was created for the 2026-10-20 shared-tag plan and re-scoped by the approved 2026-11-11 cut-back. Epic 17 again owns a standalone v1.6.0 release; Story 16.19 has no dependency or release-note reference.

It deliberately does **not** re-prove feature behaviour. Release-wide feature qualification is owned by Story 17.9 and must not be duplicated here.

## Implementation gates

- Blocked until **17.0 through 17.9** have landed their owned contracts. This is the last Epic 17 story.
- **No Epic 16 code or release dependency.**
- This story must never edit Epic 16's release-notes file, Epic 16 stories, Epic 16 tracking rows or `infra_automation/`.
- The completed v1.5.0 cut-back is historical evidence that Epic 16 remains independently releasable.

## Acceptance Criteria

1. **AC1:** Given the v1.6.0 release, when Epic 17 documentation is published, then it is owned by Epic 17 and covers enablement, IAM, degradation, snapshots and disabled-by-default behavior.
2. **AC2:** Given an operator upgrading to v1.6.0, when they read the upgrade and rollback record, then it states grounding is disabled by default, requires no credential provisioning and can be disabled without downgrade.
3. **AC3:** Given grounding disabled, when v1.6.0 is compared with the prior release, then reports, fixtures, schemas, API, CLI and agent output remain compatible.
4. **AC4:** Given each epic's shard, when the other epic's modules are absent, then it passes and CI rejects cross-imports.
5. **AC5:** Given the independent release, when qualification runs, then Epic 16 is neither imported nor required.
6. **AC6:** Given the v1.6.0 manifest, when published, then it names Epic 17 and claims only Story17.9-qualified capabilities.

### Requirement Traceability

Coverage intent: delta over the current released baseline. Mapping is an acceptance obligation, not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| LEG-FR-041 | Publish Epic 17-owned v1.6.0 release documentation. | Documentation published against the qualified support matrix |
| LEG-FR-042 | Publish an upgrade and rollback record stating grounding is disabled by default and requires no migration or credential provisioning. | Upgrade/rollback record reviewed against a clean-upgrade exercise |
| LEG-FR-043 | Produce standalone-release compatibility evidence with grounding disabled. | Recorded differential comparison across reports, schemas, API, CLI and agent output |
| LEG-NFR-013 | Epic 17 must not create a code, test or fixture dependency on Epic 16. | Per-shard isolation run plus a CI cross-import invariant |

## Tasks / Subtasks and bounded ownership

Execute one bounded packet at a time on `feature/17-10-release-integration`. Each packet owns the named paths.

- [ ] **Packet 10.1: Epic 17 release fragment — owner: maintainer.**
  - Owned write paths: `docs/releases/v1.6.0-live-environment-grounding.md`.
  - Output: a self-contained fragment covering what grounding does, enablement, the required minimal IAM policy, degradation behaviour, snapshot handling, air-gapped use and the disabled-by-default guarantee.
  - Acceptance proof: AC1 — fragment published and self-contained.
  - **Boundary note:** do not edit Epic 16's release notes.
- [ ] **Packet 10.2: Upgrade and rollback record — owner: maintainer.**
  - Owned write paths: `docs/releases/v1.6.0-live-environment-grounding.md`, `docs/live-environment-grounding/README.md`.
  - Output: an upgrade and rollback record verified by an actual clean-upgrade exercise from the prior release, not by assertion.
  - Acceptance proof: AC2 — recorded upgrade exercise with grounding left disabled.
- [ ] **Packet 10.3: Disabled-by-default differential — owner: verification owner.**
  - Owned write paths: `docs/verification/live-environment-grounding/17-10/`, `tests/test_cloud/`.
  - Output: a recorded differential of reports, fixtures, schemas, API responses, CLI output and agent output between v1.6.0 with grounding disabled and the prior release.
  - Acceptance proof: AC3 — byte- or contract-level equivalence evidence, including any differences found and how they were resolved.
- [ ] **Packet 10.4: Cross-epic isolation CI invariant — owner: core implementer.**
  - Owned write paths: `tests/test_cloud/`, `scripts/ci-local.sh`.
  - Output: per-shard isolation runs plus a CI check that fails if `cloud/` imports `infra_automation/` or the reverse. Include a deliberate failing case proving the check detects a violation.
  - Acceptance proof: AC4 — isolation runs green and the violation case correctly fails.
  - **Boundary note:** the check is authored in the Epic 17 lane but asserts a symmetric rule. Adding it to `scripts/ci-local.sh` is an append-only edit to a shared file; coordinate the merge order with the Epic 16 lane.
- [x] **Packet 10.5: Cut-back decision — owner: maintainer.**
  - Owned write paths: `docs/verification/live-environment-grounding/17-10/`.
  - Output: the approved 2026-11-11 planning cut-back, with no runtime code to remove and Epic16 validation unchanged.
  - Acceptance proof: AC5 — `sprint-change-proposal-2026-11-11-epic-17-cutback.md`.
- [ ] **Packet 10.6: Combined release manifest — owner: maintainer.**
  - Owned write paths: `docs/verification/live-environment-grounding/17-10/`, `ROADMAP.md`.
  - Output: a v1.6.0 manifest naming Epic 17, stating the disabled-by-default posture, and claiming only what Story 17.9 qualified.
  - Acceptance proof: AC6 — manifest reviewed against the 17.9 qualification matrix for over-claiming.

## Dev Notes

- Epic 17 owns its v1.6.0 release documentation. It must not edit or depend on Epic16 release notes.
- AC3 is the substantive one. "Disabled by default" is an easy claim and a frequently false one: a feature can still alter behaviour through import side effects, registry registration, serializer field ordering, settings defaults or migration state. Diff the real outputs rather than reasoning about the flag.
- The 2026-11-11 cut-back is retained as historical evidence that the release lanes are separable.
- Do not let this story absorb unfinished work from 17.0–17.9. If an earlier story is incomplete, finish it or delay v1.6.0 rather than papering over the gap.
- Honest-claim discipline applies to release copy with full force. Any capability described in the fragment must trace to a qualified Story 17.9 result.

### Project Structure Notes

- New paths: `docs/releases/v1.6.0-live-environment-grounding.md`, `docs/verification/live-environment-grounding/17-10/`.
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
