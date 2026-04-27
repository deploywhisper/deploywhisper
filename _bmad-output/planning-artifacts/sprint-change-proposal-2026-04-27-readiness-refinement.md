# Sprint Change Proposal: Implementation Readiness Refinement

**Date:** 2026-04-27
**Project:** deploywhisper
**Trigger:** `bmad-check-implementation-readiness` report from 2026-04-27
**Mode:** Batch
**Scope:** Moderate backlog and UX refinement

## 1. Issue Summary

The implementation readiness assessment found that the planning package is strong enough for refined near-term implementation but not fully ready for the complete roadmap. The core issues were:

- `ADM-06` and `ADM-07` had cross-cutting coverage but no concrete story ownership.
- Several stories were too large to execute and validate as single implementation units: `E3-S6`, `E4-S7`, `E5-S1`, `E6-S1`, and `E6-S4`.
- Later roadmap UX coverage was too light for the Skills marketplace, reviewer feedback and calibration, and benchmark dashboards.
- Active story acceptance criteria still need BDD-style refinement during story creation.

Evidence source: `_bmad-output/planning-artifacts/implementation-readiness-report-2026-04-27.md`.

## 2. Impact Analysis

### Epic Impact

- Epic 3 remains valid, but GitHub App work is split into runtime, self-hosted setup documentation/verification, delivery-mode documentation, and advisory policy output contract stories.
- Epic 4 remains valid, but the 20-skill seed catalog is split into four batches of five skills.
- Epic 5 remains valid, but Terraform state import is split by cloud provider and new admin/policy stories explicitly own `ADM-06` and `ADM-07`.
- Epic 6 remains valid, but corpus and comparator work are split into schema/initial batch, expansion, completion quality gate, hosted/LLM comparators, and normalized reporting.

### Story Impact

- Narrowed existing oversized stories rather than deleting them, preserving existing story files and implementation history.
- Added follow-on stories:
  - `E3-S9`, `E3-S10`, `E3-S11`
  - `E4-S10`, `E4-S11`, `E4-S12`
  - `E5-S9`, `E5-S10`, `E5-S11`, `E5-S12`
  - `E6-S9`, `E6-S10`, `E6-S11`, `E6-S12`

### Artifact Conflicts

- PRD goals remain unchanged.
- Architecture remains compatible with the split; no architecture rewrite is required.
- UX specification needed additional interaction detail for later roadmap surfaces.
- Sprint status needed regeneration after the epics changed.

### Technical Impact

No code changes are required by this course correction. The technical impact is planning and delivery sequencing:

- New stories should be created before implementation starts.
- Existing generated story files for narrowed stories may need refresh before being developed further.
- Implementation agents must preserve the local-first, advisory-first, shared-core constraints from project context.

## 3. Recommended Approach

**Chosen path:** Direct Adjustment.

This is the lowest-risk approach because the PRD and architecture remain coherent. The issue is delivery granularity and story ownership, not product direction. Rollback is not useful because the existing planning artifacts are still valuable, and MVP review is not needed because no core requirement became impossible.

**Effort estimate:** Medium.

**Risk level:** Low to medium. The main risk is that existing story files for narrowed stories can drift from the updated epic plan unless refreshed before implementation.

## 4. Detailed Change Proposals

### Epics

**Traceability Matrix**

Old:

```text
ADM-06..07: Cross-cutting governance in E1, E5, and future adapter work
```

New:

```text
ADM-06: E5-S11
ADM-07: E5-S12
```

Rationale: Each PRD admin/governance requirement now has explicit story ownership.

**Oversized Story Splits**

- `E3-S6` narrowed to minimal self-hosted GitHub App runtime.
- `E3-S9` added for self-hosted GitHub App setup documentation and verification.
- `E3-S10` added for GitHub delivery-mode documentation.
- `E3-S11` added for advisory policy adapter output contract.
- `E4-S7` narrowed to the first five seed skills.
- `E4-S10..E4-S12` added for the remaining three seed-skill batches.
- `E5-S1` narrowed to AWS Terraform state import.
- `E5-S9` and `E5-S10` added for GCP and Azure imports.
- `E6-S1` narrowed to corpus schema and first 20 scenarios.
- `E6-S9` and `E6-S10` added for corpus expansion and completion.
- `E6-S4` narrowed to local/open-source comparators.
- `E6-S11` and `E6-S12` added for hosted/LLM comparators and normalized reporting.

### UX Specification

Added flows:

- Public Skills Marketplace Browse Flow.
- Reviewer Feedback and Calibration Flow.
- Benchmark Results Dashboard Flow.

Added components:

- `SkillMarketplaceCard`
- `SkillDetailPanel`
- `FindingFeedbackControl`
- `CalibrationMetricPanel`
- `BenchmarkResultsTable`

Rationale: The later roadmap now has enough UX direction for story creation and implementation planning.

## 5. Implementation Handoff

**Scope classification:** Moderate.

**Handoff recipients:**

- Product Owner / Developer: maintain the corrected story backlog and sprint status.
- Developer agent: create and implement the next selected story from the refreshed sprint status.
- UX owner: refine visual detail later if Epic 4 through Epic 6 enter active implementation.

**Success criteria:**

- Epics explicitly own `ADM-06` and `ADM-07`.
- Oversized stories are split into smaller backlog items.
- UX spec covers marketplace, feedback/calibration, and benchmark surfaces.
- Sprint status is regenerated and valid YAML.
- The next story file is created from the refreshed backlog and marked `ready-for-dev`.

## 6. Checklist Status

- [x] 1.1 Triggering story identified as N/A; trigger came from readiness assessment.
- [x] 1.2 Core problem defined as backlog granularity and ownership gaps.
- [x] 1.3 Evidence captured from readiness report.
- [x] 2.1 Current epic impact evaluated.
- [x] 2.2 Required epic-level changes identified.
- [x] 2.3 Remaining epics reviewed.
- [x] 2.4 No new epic required.
- [x] 2.5 Epic order unchanged.
- [x] 3.1 PRD conflict check completed.
- [x] 3.2 Architecture conflict check completed.
- [x] 3.3 UX impact identified and addressed.
- [x] 3.4 Sprint status follow-up identified.
- [x] 4.1 Direct adjustment selected as viable.
- [x] 4.2 Rollback rejected as not useful.
- [x] 4.3 MVP review rejected as unnecessary.
- [x] 4.4 Recommended path selected.
- [x] 5.1 Issue summary created.
- [x] 5.2 Epic and artifact impacts documented.
- [x] 5.3 Recommendation documented.
- [x] 5.4 MVP impact documented.
- [x] 5.5 Handoff plan established.
- [x] 6.1 Checklist reviewed.
- [x] 6.2 Proposal reviewed for consistency.
- [x] 6.3 Approval treated as implicit from the user's explicit request to follow the handoff step by step.
- [x] 6.4 Sprint status update delegated to the sprint-planning workflow.
- [x] 6.5 Next steps documented.

## 7. Approval and Routing

Approved for implementation by user instruction: "could you please follow the BMad-help handoff recommendation step by step".

Route next to:

1. `bmad-sprint-planning`
2. `bmad-create-story`
