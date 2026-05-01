# Sprint Change Proposal: Final PRD Realignment

**Project:** deploywhisper  
**Date:** 2026-05-01  
**Prepared for:** psaho01  
**Workflow:** BMad Correct Course  
**Status:** Corrective addendum applied after implementation-readiness review  

**Note:** Sections 1-7 record the earlier final-PRD realignment proposal and are retained as historical context. Section 8 records the current readiness-correction pass applied by user request on 2026-05-01.

---

## 1. Issue Summary

The product PRD has been finalized after team discussion and market research, and it now materially changes the product direction, delivery phases, and epic structure.

The current implementation plan is no longer a reliable source of truth:

- `_bmad-output/planning-artifacts/prd.md` now defines a self-hosted, fully open-source, Evidence-Law-first, AI-safety, benchmark-honest, documentation-first, and CNCF-ready product direction.
- `_bmad-output/planning-artifacts/architecture.md` still reflects an older architecture direction centered on 6 roadmap epics and v3-era pillars.
- `_bmad-output/planning-artifacts/epics.md` still reflects the older 6-epic implementation roadmap plus a brownfield hardening track.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` tracks story status against the old epic/story inventory.
- Existing story files through the current 5.x/6.x plan may contain useful implementation detail, but they should not be treated as authoritative until they are re-triaged against the finalized PRD and revised epics.

This is not a single-story correction. It is a major planning realignment triggered by finalized product strategy.

### Change Trigger

The trigger is a strategic PRD pivot and finalization, not a technical failure in one story.

Issue type:

- Strategic pivot or market change.
- New requirements emerged from stakeholder discussion and market research.
- Existing architecture, epics, stories, and sprint tracking are now stale relative to the finalized PRD.

### Evidence

The finalized PRD includes major product commitments and requirement families that exceed the current architecture and epics:

- Fully open-source and self-hosted-only posture.
- Explicit no-SaaS, no hosted control plane, no open-core, and no paid enterprise-only feature boundaries.
- Evidence Law as a product-wide trust guarantee.
- Project, workspace, and RBAC model before hardening persistence and connectors.
- Day-zero incident memory and public risk patterns.
- AI-generated infrastructure safety and agent-native interfaces.
- External scanner ingestion and conflict handling.
- Benchmark corpus, calibration, honest failure reporting, and backtesting.
- Open governance, maintainer ownership, CODEOWNERS, RFC process, CNCF readiness, and documentation as part of done.
- Fourteen PRD epics, while the current epic artifact still has six main epics.

---

## 2. Impact Analysis

### Epic Impact

The current epic set must be replaced or substantially rewritten.

Current `epics.md` structure:

- Brownfield Hardening Track.
- Epic 1: Trusted Evidence Core.
- Epic 2: Report & Review Experience.
- Epic 3: GitHub-Native Delivery.
- Epic 4: AI Skills Marketplace.
- Epic 5: Context Moat.
- Epic 6: Benchmarks & Calibration.

Final PRD epic structure:

- Epic 0: Open Governance, Traceability, and Maintainer Ownership.
- Epic 1: Project, Workspace, and RBAC Foundation.
- Epic 2: Trusted Evidence Core and Evidence Law.
- Epic 3: Report and Review Experience.
- Epic 4: Day-Zero Risk Patterns and Incident Memory.
- Epic 5: Workflow-Native Delivery.
- Epic 6: Benchmarks, Calibration, and Honest Failure Reporting.
- Epic 7: Context Moat.
- Epic 8: Existing Security Tool Integration.
- Epic 9: Skills Ecosystem.
- Epic 10: AI Infrastructure Safety and Agent-Native Review.
- Epic 11: Optional Enforcement Adapters.
- Epic 12: Security and Supply Chain Hardening.
- Epic 13: Documentation and User Enablement.
- Epic 14: CNCF Readiness.

Required changes:

- Regenerate epics from the finalized PRD and updated architecture.
- Preserve useful older epic/story content only when it maps cleanly to new acceptance criteria.
- Re-sequence early work around governance, project/workspace scope, and Evidence Law before deeper workflow, context, agent, and ecosystem expansion.
- Treat documentation, governance, security, and benchmark deliverables as first-class roadmap work, not peripheral tasks.

### Story Impact

Current stories should be frozen for planning purposes until re-triaged.

Recommended classification for existing story files:

- `keep`: Story still directly maps to a revised epic and acceptance criteria.
- `revise`: Story intent is still useful but acceptance criteria, scope, or epic ownership must change.
- `split`: Story contains multiple concerns that now belong in different revised epics.
- `archive`: Story is obsolete under the finalized PRD.
- `superseded`: Story was useful in the old plan but is replaced by a broader or more precise new story.

The current `sprint-status.yaml` should not be updated until the revised epics and story inventory are approved.

### Artifact Conflicts

#### PRD

Status: Current source of truth.

Required action:

- Preserve finalized PRD as the planning input.
- Do not rework PRD unless later architecture or readiness checks reveal direct inconsistency.

#### Architecture

Status: Stale relative to finalized PRD.

Required action:

- Update architecture to align with the final PRD.
- Add or revise architecture sections for open-source/self-hosted-only posture, project/workspace/RBAC boundaries, Evidence Law enforcement, day-zero incident memory, AI-agent interfaces, external scanner ingestion, benchmark infrastructure, governance/supporting docs, supply-chain hardening, and CNCF readiness.
- Remove or rewrite any architecture language implying SaaS, hosted control plane, open-core, or vendor-managed deployment assumptions.
- Reconcile the target architecture with the current Python/NiceGUI/FastAPI/SQLite baseline and the local-first advisory core.

#### Epics

Status: Stale relative to finalized PRD.

Required action:

- Regenerate `epics.md` after architecture alignment.
- Use the finalized PRD's 14-epic structure unless architecture work finds a strong reason to merge or phase epics differently.
- Include requirement traceability, documentation acceptance criteria, dependencies, sequencing, and baseline-vs-roadmap guidance.

#### UX Design

Status: Partially useful but stale.

Required action:

- Preserve the useful verdict-first, evidence-on-demand, visible-uncertainty, and one-screen operational review principles.
- Update UX guidance to cover Evidence Law status, project/workspace scope, confidence ledger, context TODOs, day-zero/public risk patterns, external scanner context, report diff, agent-readable outputs where visible, and documentation links.
- Remove assumptions that conflict with the self-hosted/open-source/community-facing product posture.

#### Sprint Status

Status: Stale tracking artifact.

Required action:

- Freeze current sprint status.
- Regenerate sprint planning only after revised epics and readiness check are complete.
- Preserve current status as historical implementation context, not current roadmap authority.

### Technical Impact

The finalized PRD changes implementation priority and technical sequencing:

- Project/workspace scoping should be handled earlier than many connector, history, and feedback features.
- Evidence Law enforcement should become a core invariant with tests and schema guarantees.
- External scanner output must be labeled as external evidence and cannot automatically create high/critical DeployWhisper findings without DeployWhisper evidence/scoring.
- AI-agent interfaces require stable machine-readable output, prompt-injection controls, and advisory-only guardrails.
- Benchmark and honest failure reporting become product infrastructure, not post-launch polish.
- Governance, docs, supply-chain security, and release process work need explicit stories and acceptance criteria.

---

## 3. Recommended Approach

Recommended path: **Hybrid: Major replan with artifact preservation.**

Do not roll back completed implementation work. Do not directly patch the old 6-epic plan. Instead:

1. Freeze current story/sprint tracking.
2. Update architecture against the finalized PRD.
3. Regenerate epics and stories from the finalized PRD and updated architecture.
4. Run implementation readiness validation.
5. Reconcile current code and existing stories against revised epic acceptance criteria.
6. Generate a new prioritized sprint plan.
7. Resume story creation and development from the revised plan.

### Alternatives Considered

#### Option 1: Direct Adjustment

Decision: Not viable.

Reason:

- The PRD now has fourteen epics and multiple new requirement families.
- The current epic structure has six epics and cannot absorb the change cleanly without becoming confusing and internally inconsistent.

#### Option 2: Potential Rollback

Decision: Not recommended.

Reason:

- Existing code and stories contain useful baseline capabilities.
- The issue is planning drift, not necessarily defective implementation.
- Rolling back completed work would increase risk and lose useful product baseline.

#### Option 3: PRD MVP Review

Decision: Already completed by the finalized PRD.

Reason:

- The PRD itself now defines scope by phase and release exit criteria.
- The correct next step is not to reopen MVP strategy, but to align architecture, epics, and stories to the finalized PRD.

### Effort and Risk

Effort estimate: High.

Risk level: High if old story tracking remains active; Medium if artifacts are frozen and regenerated in order.

Primary risk:

- Continuing implementation against stale epics will create code/documentation drift and false progress.

Primary mitigation:

- Freeze old story authority, regenerate planning artifacts, and only then re-triage implementation status.

---

## 4. Detailed Change Proposals

### Proposal A: Freeze Current Sprint Tracking

Artifact: `_bmad-output/implementation-artifacts/sprint-status.yaml`

Current behavior:

```text
Tracks old epics and story IDs as active implementation state.
```

Proposed behavior:

```text
Mark current sprint status as historical/stale pending final-PRD realignment.
Do not use existing story status as roadmap authority until revised epics and sprint plan are generated.
```

Rationale:

The current status file reflects the old epic structure and can mislead future implementation agents.

### Proposal B: Update Architecture

Artifact: `_bmad-output/planning-artifacts/architecture.md`

Current behavior:

```text
Architecture is organized around older v3 direction and six roadmap epics.
```

Proposed behavior:

```text
Rewrite architecture around the finalized PRD's self-hosted, open-source, Evidence-Law-first, project-scoped, AI-safety, benchmark, external-scanner, governance, documentation, and CNCF-readiness commitments.
```

Rationale:

Architecture must become the technical bridge between PRD intent and implementable epics.

### Proposal C: Regenerate Epics

Artifact: `_bmad-output/planning-artifacts/epics.md`

Current behavior:

```text
Defines six main epics plus a brownfield hardening track.
```

Proposed behavior:

```text
Replace or substantially rewrite with epics aligned to PRD Section 33, phased scope, release exit criteria, and requirement families.
```

Rationale:

The epic artifact must match the finalized PRD before stories can be trusted.

### Proposal D: Reconcile Existing Stories

Artifact: `_bmad-output/implementation-artifacts/*.md`

Current behavior:

```text
Existing stories represent older planning slices and current implementation assumptions.
```

Proposed behavior:

```text
Create a story reconciliation report mapping each existing story to keep, revise, split, archive, or superseded.
Only stories mapped cleanly to revised epics should remain active.
```

Rationale:

Some prior work remains valuable, but story status must be re-established against the new acceptance criteria.

### Proposal E: Regenerate Sprint Plan

Artifact: `_bmad-output/implementation-artifacts/sprint-status.yaml`

Current behavior:

```text
Tracks old roadmap execution state.
```

Proposed behavior:

```text
Generate a new prioritized sprint plan after revised epics pass implementation readiness.
```

Rationale:

Sprint planning depends on stable epics and acceptance criteria.

---

## 5. Implementation Handoff

Change scope classification: **Major**.

This requires Product Manager / Solution Architect handoff before Developer implementation resumes.

### Recommended Workflow Route

1. `bmad-create-architecture`
   - Owner: Architect workflow.
   - Input: finalized PRD, project context, current architecture, current codebase constraints.
   - Output: updated `architecture.md`.

2. `bmad-create-epics-and-stories`
   - Owner: PM/PO planning workflow.
   - Input: finalized PRD and updated architecture.
   - Output: revised `epics.md` and story inventory.

3. `bmad-check-implementation-readiness`
   - Owner: readiness validation workflow.
   - Input: finalized PRD, updated architecture, revised epics/stories, UX if retained.
   - Output: readiness report and required corrections.

4. Story/code reconciliation
   - Owner: Developer/Reviewer workflow.
   - Input: revised epics and current codebase.
   - Output: story implementation status map and alignment report.

5. `bmad-sprint-planning`
   - Owner: sprint planning workflow.
   - Input: revised and readiness-checked epics.
   - Output: new `sprint-status.yaml`.

6. `bmad-create-story` / `bmad-dev-story` / `bmad-code-review`
   - Owner: implementation workflows.
   - Input: prioritized sprint status.
   - Output: validated, implemented, reviewed stories.

### Success Criteria

- `architecture.md` explicitly aligns with the finalized PRD.
- `epics.md` reflects the finalized PRD and updated architecture.
- Existing stories are classified as keep, revise, split, archive, or superseded.
- `sprint-status.yaml` is regenerated only after revised epics pass readiness.
- No new implementation work starts from stale story status.
- Future stories include documentation acceptance criteria where user-facing, operator-facing, integration-facing, or contributor-facing behavior changes.

---

## 6. Checklist Completion

| Checklist Item | Status | Notes |
| --- | --- | --- |
| 1.1 Triggering story identified | N/A | Trigger is finalized PRD and strategic planning drift, not one story. |
| 1.2 Core problem defined | Done | Existing architecture, epics, stories, and sprint status are stale relative to final PRD. |
| 1.3 Supporting evidence gathered | Done | PRD, architecture, epics, UX, sprint status, and prior alignment reports reviewed. |
| 2.1 Current epic viability assessed | Done | Current 6-epic structure is not viable as-is. |
| 2.2 Epic-level changes determined | Done | Regenerate around finalized PRD epic structure. |
| 2.3 Remaining epics reviewed | Done | All existing epics impacted. |
| 2.4 Obsolete/new epics identified | Done | Multiple new PRD epics absent from current epics. |
| 2.5 Priority changes considered | Done | Governance/project scope/Evidence Law must move earlier. |
| 3.1 PRD conflicts checked | Done | PRD is source of truth; downstream artifacts conflict. |
| 3.2 Architecture conflicts checked | Done | Architecture requires major update. |
| 3.3 UX conflicts checked | Done | UX is partially reusable but stale. |
| 3.4 Secondary artifacts checked | Done | Sprint status and story files require reconciliation. |
| 4.1 Direct adjustment evaluated | Done | Not viable. |
| 4.2 Rollback evaluated | Done | Not recommended. |
| 4.3 MVP review evaluated | Done | PRD already completed the strategic review. |
| 4.4 Recommended path selected | Done | Hybrid major replan with artifact preservation. |
| 5.1 Issue summary created | Done | Included above. |
| 5.2 Impact documented | Done | Included above. |
| 5.3 Path forward documented | Done | Included above. |
| 5.4 MVP/action plan defined | Done | Use PRD phases and release exits. |
| 5.5 Handoff plan established | Done | Architect/PM/readiness/developer sequence defined. |
| 6.1 Checklist reviewed | Done | Applicable items addressed. |
| 6.2 Proposal accuracy reviewed | Done | Proposal is consistent with discovered artifacts. |
| 6.3 User approval obtained | Action-needed | Proposal is pending approval. |
| 6.4 Sprint status updated | Action-needed | Must wait until proposal approval and regenerated epics. |
| 6.5 Handoff confirmed | Action-needed | Next handoff should be architecture update. |

---

## 7. Approval Request

Recommended approval decision:

Approve this Correct Course proposal and route next to `bmad-create-architecture`.

Approval means:

- Current story/sprint status is treated as historical until re-triaged.
- Architecture becomes the next planning artifact to update.
- Epics are regenerated only after architecture alignment.
- Story reconciliation and new sprint planning happen after implementation readiness validation.

---

## 8. Corrective Addendum: Implementation Readiness Story-Shape Fix

**Trigger:** `bmad-check-implementation-readiness` generated `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` and marked the regenerated plan **NOT READY**.

**Issue type:** Requirements traceability and story-shape defect discovered during readiness validation.

**Evidence:**

- HIS-01, HIS-02, HIS-03, HIS-04, and ADM-01 appeared in the PRD and epics requirements inventory but had no concrete story-level implementation path.
- ADM-04 covered incident import but not admin management of incident ingestion/indexing lifecycle.
- Several stories were too broad for reliable single-agent implementation.
- Acceptance criteria needed more negative-path, permission, degraded-state, redaction, and conflict handling.

### Checklist Outcome

| Checklist Area | Status | Notes |
| --- | --- | --- |
| Trigger and context | Done | Readiness report is the trigger and evidence source. |
| Epic impact | Done | Epic 1, 2, 3, 4, 6, 8, 9, 10, 12, and 13 required story-shape edits. |
| PRD impact | Done | No PRD change required; requirements remain valid. |
| Architecture impact | Done | No architecture change required for this correction; architecture already supports the missing concepts. |
| UX impact | Done | UX remains directionally aligned but still needs a later freshness update for RBAC/scanner/admin/agent states. |
| Path forward | Done | Direct adjustment is viable for this readiness defect. Rollback and MVP review are not needed. |
| Sprint status | N/A | Sprint planning remains blocked until readiness passes; existing sprint status is historical and should not be regenerated here. |

### Applied Changes

Artifact: `_bmad-output/planning-artifacts/epics.md`

1. Updated the FR Coverage Map and Epic List primary coverage so:
   - HIS-01..02 map to Epic 2.
   - HIS-03 maps to Epic 3.
   - ADM-04 maps to Epic 4.
   - HIS-04 maps to Epic 6.
   - ADM-01..02 map to Epic 12.

2. Added missing concrete story paths:
   - Story 2.9: Durable Report Persistence and Audit Metadata.
   - Story 3.8: Historical Report Search and Filtering.
   - Story 4.7: Incident Ingestion Management and Indexing.
   - Story 6.6: Risk Trend Review.
   - Story 12.2: Provider Settings Administration.

3. Split or narrowed oversized stories:
   - Story 1.1 now covers only project/workspace records.
   - Story 1.3 now covers project-scoped report persistence.
   - Story 1.4 now covers project-scoped learning and context records.
   - Story 9.6 now covers Skill contribution workflow.
   - Story 9.7 now covers Skill analytics and deprecation signals.
   - Epic 12 now separates raw artifact/secrets audit, provider settings, connector credential handling, Scorecard/CodeQL, SBOM/checksums, signing/provenance, operations docs, and air-gapped docs.
   - Epic 13 now separates API/report references, CLI/evidence/agent references, connector guides, workflow integration guides, docs CI, and release/upgrade notes.

4. Added stronger negative/degraded-path criteria for:
   - Invalid or unauthorized project/workspace operations.
   - Cross-project report/context leakage prevention.
   - Redacted or missing evidence inspection.
   - Invalid incident import and stale incident index state.
   - No-match or low-confidence incident similarity.
   - Sparse/bias-limited calibration data.
   - Scanner conflict representation across UI/API/CLI/PR output.
   - Agent cross-project access denial.
   - Provider configuration failure and narrative degradation.

### Recommended Next Step

Re-run `bmad-check-implementation-readiness` against the corrected epics. If it passes, proceed to `bmad-sprint-planning`.
