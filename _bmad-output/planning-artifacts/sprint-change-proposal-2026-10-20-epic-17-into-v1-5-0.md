# Sprint Change Proposal — Epic 17 Retargeted into v1.5.0

- **Date:** 2026-10-20
- **Author:** planning agent, on owner instruction
- **Type:** release-scope course correction
- **Status:** adopted on owner decision
- **Supersedes nothing.** Extends the [2026-10-19 Epic 17 course correction](sprint-change-proposal-2026-10-19-epic-17-live-environment-grounding.md).

## 1. Trigger

The owner directed that **all Epic 17 stories ship in v1.5.0 together with Epic 16**, rather than in the originally planned v1.6.0.

## 2. What changed

Epic 17 was planned as a v1.6.0 lane running in parallel with the v1.5.0 Epic 16 lane. Parallel development was the mechanism; **separate release tags were the safety margin**. The retarget keeps the mechanism and removes the margin.

| | Before (2026-10-19) | After (2026-10-20) |
| --- | --- | --- |
| Epic 17 release | v1.6.0 | v1.5.0 |
| Development independence | Full | Full, unchanged |
| Module, test, branch separation | Enforced | Enforced, unchanged |
| Release independence | Yes | **No — shared tag** |
| Stories gating the tag | 20 (Epic 16) | 31 (20 + 11) |
| Epic 17 story count | 10 | 11 (Story 17.10 added) |

## 3. Analysis

### What the retarget does not change

Nothing architectural. Epic 17 remains read-only, opt-in, disabled by default, and additive. `LEG-ADR-01..10` are untouched. The boundary contract — module ownership, branch prefixes, test shards, append-only shared-file edits, the no-cross-import rule — is unchanged and unrelaxed. Epic 17 still has no code dependency on Epic 16.

### What it does change

**One thing: the release gate.** v1.5.0 now ships only when both epics close. A delay in either lane delays the tag for both. This is a scheduling dependency between maintainers, not a code dependency between modules, and it must not be allowed to become one.

Two consequences follow and are handled by the new Story 17.10:

1. **Release-notes contention.** Story 16.19 owns the v1.5.0 release and its notes file. Two lanes editing that file concurrently is the predictable conflict of this release. Resolved by the fragment pattern (`LEG-ADR-11`): Epic 17 publishes a self-contained fragment under `docs/releases/`; Story 16.19 includes it with a single reference line; Epic 17 never edits Epic 16's file.
2. **Disabled-by-default must be proven, not asserted.** Shipping both epics in one artifact means the claim "grounding is off by default so nothing changes" now carries release weight. A feature can still alter behaviour through import side effects, registry registration, serializer field ordering or settings defaults. `LEG-FR-043` requires a recorded differential against an Epic 16-only build, and `LEG-NFR-013` requires each shard to pass with the other epic's modules absent.

### Risk, stated plainly

**31 stories now gate one release tag, and Epic 17 has zero stories implemented.** Story 17.0 is `ready-for-dev`; everything after it is `backlog` behind a feasibility gate that includes an undecided AWS SDK dependency. Epic 16 is itself a 20-story epic still in early execution. The honest characterization is that this is an ambitious combined release, not a routine one.

This proposal does **not** recommend reversing the decision. It recommends making the decision reversible, which is cheap here precisely because Epic 17 is additive and off by default.

### Mitigation: keep the cut-back path real

Story 17.10 Packet 10.5 requires a **rehearsed** cut-back on a scratch branch, confirming Epic 16's release stays complete and green with Epic 17 removed. Run it early. A cut-back path that has never been executed is an assumption, and discovering that at release time is the same as not having one.

Decision rule: if Epic 17 cannot complete, cut Epic 17 from v1.5.0 and restore it to v1.6.0. Do **not** block Epic 16, and do **not** merge partial grounding to make a date. Partial grounding is worse than none — it produces confident conclusions from incomplete environment facts, which is the exact failure the fail-safe contract (`LEG-NFR-004`) exists to prevent.

## 4. Options considered

| Option | Assessment |
| --- | --- |
| **A. Ship all of Epic 17 in v1.5.0** | **Adopted — owner decision.** Maximum user value in one release; highest schedule risk. Made safe by the rehearsed cut-back path. |
| B. Ship only the thin slice 17.0–17.4 in v1.5.0 | Lower risk, and 17.4 is the first independently valuable increment. Not adopted; the owner asked for the whole epic. Remains the natural fallback if the lane slips. |
| C. Keep Epic 17 in v1.6.0 | The pre-existing plan. Not adopted. |
| D. Merge the epics into one workstream | Rejected. It would destroy the module and review separation that makes parallel work possible, for no release benefit. |

Option B is recorded deliberately: it is the shape a partial cut should take if one becomes necessary, so that the decision is not improvised under release pressure.

## 5. Changes made by this proposal

**No Epic 16 artifact was edited.** No Epic 16 story, tracking row, requirement or module was touched.

| Artifact | Change |
| --- | --- |
| `prd-live-environment-grounding.md` | Release `v1.6.0` → `v1.5.0`; lane table; scope headings; added `LEG-FR-041..043`, `LEG-NFR-013`; story mapping row for 17.10 |
| `epics.md` | Epic 17 release priority rewritten; added Story 17.10 |
| `architecture.md` §26 | Retargeted to v1.5.0; RFC status corrected to Accepted; added `LEG-ADR-11` |
| `epic-16-17-boundary-and-parallelization-plan.md` | Release-lane table, shared-tag explanation, release-notes ownership, joint release gate, three new risk rows |
| `requirements-traceability-matrix.md` | Four new requirement rows; retarget note |
| `sprint-status.yaml` | Added `17-10` key; retarget comment. Epic 17 keys only |
| `story-implementation-status-map.md` | 0/10 → 0/11; retarget note; 17.10 row |
| `epic-17-story-preparation-report.md` | Retarget note; readiness verdict unchanged |
| `17-0` … `17-9` story files | Release line updated to v1.5.0 |
| `17-9` | Packet 9.7 no longer writes release notes; ownership moved to 17.10 |
| `ROADMAP.md` Phase 5 | Accepted status, v1.5.0 target, shared-tag and cut-back note |
| `docs/rfcs/0002-...md`, `docs/live-environment-grounding/README.md` | Target release and status banners |
| **New:** `17-10-v1-5-0-release-integration-and-joint-qualification.md` | Release integration story |

## 6. What this proposal does not claim

- No Epic 17 code exists. No story has been implemented, qualified or tested.
- The retarget is a planning decision. It does not make Epic 17 closer to done.
- Story 17.0's feasibility gates, the AWS SDK dependency decision and the six unresolved RFC questions all remain open and are unaffected by this proposal.
- Neither epic's delivery date is forecast here. The combined scope is stated so the risk is visible, not to imply it has been scheduled.

## 7. Recommended next actions

1. Inform the Epic 16 lane of the shared tag and of the one-line reference it will add in Story 16.19. This is the only thing Epic 16 must do differently.
2. Begin Story 17.0. The AWS SDK dependency decision is now on the v1.5.0 critical path and should be resolved first.
3. Rehearse the Story 17.10 cut-back path **early**, not at release time.
4. Re-evaluate at the Story 17.4 boundary. If the lane is behind at that point, adopt Option B rather than compressing the remaining stories.
