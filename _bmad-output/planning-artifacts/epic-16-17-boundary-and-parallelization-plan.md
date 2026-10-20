# Epic 16 / Epic 17 Boundary and Parallelization Plan

**Created:** 2026-10-19
**Status:** Authoritative for concurrent Epic 16 and Epic 17 execution
**Audience:** Any agent or contributor working either epic

## Purpose

Epic 16 (Evidence-Gated Infrastructure Automation) and Epic 17 (Live Environment Grounding) are being developed **concurrently by different workers** and, since the 2026-10-20 retarget, both ship in **v1.5.0**. This document is the contract that keeps them independent. Read it before editing any file listed in the shared-surface table.

**What the shared release tag changes, and what it does not.** It does not change module ownership, branch prefixes, test shards, review lanes or the no-cross-import rule: development stays fully independent and nothing below is relaxed. It changes exactly one thing — the release gate. v1.5.0 now ships only when **both** epics close, so a delay in either lane delays the tag for both. Treat that as a scheduling dependency between maintainers, never as a code dependency between modules.

## One-sentence separation

> **Epic 16 governs what leaves DeployWhisper. Epic 17 grounds what comes in. Neither needs the other to ship.**

## Dependency assertion

- **Epic 17 has zero dependencies on Epic 16.** No Epic 17 story lists an Epic 16 story as a prerequisite.
- **Epic 16 has zero dependencies on Epic 17.** No Epic 16 acceptance criterion requires grounded context.
- Either epic may be released first, alone, in any order, or with the other cancelled.

If any future story introduces a cross-epic dependency, that is a scope change requiring a course correction — not a story-level decision.

## Why Epic 17 does not reuse the Epic 16 runner

This is deliberate and must not be "optimized" later without an RFC.

Epic 16's runner exists to execute **untrusted repository and provider code** in an isolated profile, under an enrollment, attempt-fencing and lease protocol. Epic 17's collection is a **short, synchronous, inbound, read-only API call issued by the application itself** against a provider endpoint, using the operator's ambient credentials. It executes no customer code.

Routing grounding through the Epic 16 runner would:

1. Import the entire enrollment, attempt, fencing and lease protocol for a read that does not need it.
2. Block **all** Epic 17 value behind Stories 16.12–16.14.
3. Couple two release lanes that currently have no coupling.

Operators who need collection executed inside a private network use **snapshot export and import** (Story 17.7), which achieves the same outcome with no protocol coupling.

## Module ownership

| Path | Owner | Rule |
| --- | --- | --- |
| `infra_automation/` | Epic 16 | Epic 17 must not read, import or modify |
| `services/infra_automation_*.py` | Epic 16 | Epic 17 must not read, import or modify |
| `api/` infra-automation routes | Epic 16 | Epic 17 adds its own routes under a distinct prefix |
| `frontend/src/screens/InfraAutomation*.tsx` | Epic 16 | Epic 17 adds its own screens and tab |
| `tests/test_infra_automation/` | Epic 16 | — |
| `cloud/` | **Epic 17** | Epic 16 must not read, import or modify |
| `services/cloud_context_service.py` | **Epic 17** | Epic 16 must not read, import or modify |
| `api/` live-context routes | **Epic 17** | — |
| `tests/test_cloud/` | **Epic 17** | — |
| `docs/infra-automation/` | Epic 16 | — |
| `docs/live-environment-grounding/` | **Epic 17** | — |

Neither epic imports from the other's module tree. This is a reviewable invariant: a grep for `infra_automation` under `cloud/`, or for `cloud.` under `infra_automation/`, must return nothing.

## Shared surfaces and the conflict protocol

These files are touched by both epics. Each has an explicit rule that makes concurrent edits non-conflicting.

| Shared file | Epic 16 edits | Epic 17 edits | Conflict rule |
| --- | --- | --- | --- |
| `_bmad-output/planning-artifacts/epics.md` | Epic 16 section only | **Appends an Epic 17 section at end of file** | Append-only; never reorder or renumber existing sections |
| `_bmad-output/planning-artifacts/architecture.md` | §25 only | **Appends §26 only** | Append-only; §25 is untouched by Epic 17 |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | `epic-16` keys | **`epic-17` keys in a separate appended block** | Never edit the other epic's keys; keep blocks contiguous and separated by a comment banner |
| `_bmad-output/implementation-artifacts/story-implementation-status-map.md` | Epic 16 rows | **Epic 17 rows in a separate section** | Append-only rows; do not restate the other epic's counts |
| `_bmad-output/planning-artifacts/requirements-traceability-matrix.md` | `IAU15-*` family row | **`LEG-*` family row** | One row each; distinct ID namespaces |
| `evidence/models.py` | May add automation provenance fields | **Adds `live_state` to `EvidenceSourceType` / `ContextSourceType`** | Additive enum members only; never remove or reorder existing members |
| `analysis/risk_scorer.py` | Does not modify scoring | **Adds grounded evidence modifiers** | Epic 16 explicitly does not duplicate or alter scoring (IA-ADR-01); Epic 17 owns scoring integration |
| `analysis/blast_radius.py` | Does not modify | **Consumes live edges** | Epic 17 sole owner |
| `services/topology_service.py` | Does not modify | **Registers the `aws` source handler** | Epic 17 replaces a registry stub slot; no Epic 16 interaction |
| `api/` report serializer | Adds optional `infra_automation_provenance` (`provenance_version: 1`) | **Adds optional `live_context` (`live_context_version: 1`)** | Two independent optional blocks, separately versioned; neither bumps the report schema version |
| `frontend/src/screens/Report.tsx` | Additive provenance rendering | **Additive Live Context tab** | Both additive; coordinate tab ordering in review, do not revert the other's edit |
| `ROADMAP.md`, `CHANGELOG.md` | Epic 16 entries | **Epic 17 entries** | Append-only under distinct headings |
| `requirements.txt` / lock files | Epic 16 adds nothing without an approved decision | **Epic 17 may add an AWS SDK after an approved dependency decision (Story 17.0)** | Both must regenerate locks per existing process; sequence through review if both land in the same window |

### Protocol when both epics must touch the same file

1. Prefer **append-only** edits at the end of the file or section.
2. Never revert, reorder or reformat the other epic's content — this is an explicit repository rule already in force for story branches.
3. If a true conflict arises, the **later-merging branch rebases**. Do not resolve by deleting the other epic's content.
4. Shared-file edits are called out explicitly in the PR description so the reviewer can check both lanes.

## The one intended integration point

**Direction: Epic 16 reads Epic 17. One-directional. Optional. Presentation-time only.**

Once both epics land, Epic 16's approval inbox (Story 16.9) may render Epic 17's `live_context` report block, so an approver sees grounded blast radius, divergence and recoverability alongside the decision controls.

Constraints on this integration:

- It is a **read of an additive optional field**, not a code dependency.
- Story 16.9 must render correctly when `live_context` is **absent**, which is the default and the only state until Epic 17 ships.
- Story 17.8 must render correctly with **no automation run** present.
- Neither story's acceptance criteria may be rewritten to require the other.
- The integration is tracked as a **post-both-epics follow-up**, not as work inside either epic.

## Release lanes

| | Epic 16 | Epic 17 |
| --- | --- | --- |
| Release | v1.5.0 | v1.5.0 (retargeted 2026-10-20 from v1.6.0) |
| Branch prefix | `feature/16-*` | `feature/17-*` |
| Integration branch | `develop` | `develop` |
| Test shard | `tests/test_infra_automation` | `tests/test_cloud` |
| Independently developable? | Yes | Yes |
| Independently releasable? | **No — shared v1.5.0 tag** | **No — shared v1.5.0 tag** |

Both lanes merge to `develop` under the existing Git Flow process.

### Release-notes ownership

Story 16.19 owns the v1.5.0 release and its notes file. To keep that ownership unambiguous and to avoid a shared-file conflict in the most contended artifact of the release, Epic 17 does **not** edit it. Instead:

- Story 17.10 publishes a **self-contained Epic 17 fragment** under `docs/releases/`.
- Story 16.19 **includes that fragment by reference**, a one-line addition on the Epic 16 side.
- If the Epic 17 fragment does not exist at release time, Story 16.19 ships the v1.5.0 notes without it rather than blocking on Epic 17 authorship.

This is the only new cross-epic touchpoint created by the retarget, and it is documentation-only.

### Joint release gate

- Neither epic may tag v1.5.0 alone.
- With grounding disabled — the default — a build containing both epics must be behaviourally identical to one containing Epic 16 alone. Story 17.10 owns that proof (`LEG-FR-043`).
- Each test shard must pass with the other epic's modules absent from the import graph (`LEG-NFR-013`).
- If Epic 17 cannot complete in time, the correct response is to **cut Epic 17 from v1.5.0 and restore it to v1.6.0**, not to block Epic 16 or to merge partial grounding. Because grounding is disabled by default and additive, this cut is low-cost at any point before the tag.

## Risk register for concurrent execution

| Risk | Mitigation |
| --- | --- |
| Both epics edit `evidence/models.py` enums simultaneously | Additive members only; small, isolated commits; enum order never changed |
| Both edit the report serializer | Two independently named and versioned optional blocks; neither bumps report schema version |
| Dependency lock churn from an AWS SDK addition | Epic 17 dependency decision happens in 17.0, well before 17.2 implementation; lock regeneration sequenced through review |
| Reviewer fatigue across two large lanes | Epic 17 front-loads a thin, independently valuable slice (17.0–17.4) so review arrives in small, demoable units |
| Maintainer capacity contention | Real and acknowledged; addressed in the course correction, which does **not** propose de-scoping Epic 16 |
| Accidental cross-epic import | Reviewable grep invariant stated in "Module ownership", promoted to a CI check by `LEG-NFR-013` |
| **Shared release tag couples two large lanes** | 31 stories now gate one tag. Mitigated by the documented Epic 17 cut-back path above: grounding is disabled by default and additive, so removing it from v1.5.0 stays cheap until the tag is cut |
| Release-notes file contention in 16.19 | Epic 17 publishes a separate fragment; 16.19 includes it by reference and never waits on Epic 17 to edit its file |

## Checklist before opening any PR in either lane

- [ ] My branch is `feature/16-*` or `feature/17-*` and was cut from `develop`.
- [ ] I did not import from the other epic's module tree.
- [ ] Every shared-file edit I made is append-only, or is explicitly called out in the PR description.
- [ ] I did not modify the other epic's rows, keys or sections in tracking artifacts.
- [ ] I did not introduce a dependency on an unshipped story in the other epic.
- [ ] If I touched the report serializer, my block is optional, separately versioned, and absent-by-default.
