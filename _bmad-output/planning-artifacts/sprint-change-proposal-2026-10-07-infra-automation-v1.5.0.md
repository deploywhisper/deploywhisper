---
project: deploywhisper
date: 2026-10-07
workflow: bmad-correct-course
mode: batch
status: accepted-for-planning-applied
scope: major-product-and-architecture-addition
release: v1.5.0
implementation_status: not-started
authorization: explicit-user-instruction-to-use-reviewed-plan
---

# Sprint Change Proposal: v1.5.0 Infrastructure Automation

## 1. Issue summary and authorization

The owner requested that Infrastructure Automation become the highest-priority feature for v1.5.0, with product/technical research, a Kestra comparison and a practical release plan. The reviewed [release plan](infra-automation-v1.5.0-release-plan.md) narrows the original 34-story vision to a production-qualified preflight and verified external-handoff capability. The owner then explicitly directed: “bmad-correct-course using this plan, followed by PRD/architecture updates and implementation-readiness review.”

That instruction authorizes adoption of the reviewed release scope and the reversible planning updates in this batch. It does not authorize infrastructure mutation, dependency installation, public RFC publication/acceptance, or declaring the unimplemented feature production-ready. No further approval is needed to prepare and assess these artifacts. Public governance acceptance and executable feasibility proof remain separately recorded implementation gates.

### Evidence and input authority

- Accepted implementation baseline: v1.4.0, [release verification](../../docs/verification/v1.4.0-release.json) and [current tracking](../implementation-artifacts/sprint-status.yaml).
- Research: [technical assessment](research/technical-infra-automation-research-2026-10-07.md), including current identity, runner, durability and integration gaps.
- Reviewed plan: [v1.5.0 release plan](infra-automation-v1.5.0-release-plan.md), adopted by the latest user instruction.
- Original input: [v0.2 feature PRD](../../docs/deploywhisper-infra-automation-prd.md), retained as the historical vision/source inventory; its stale v1.4.0 phases and proposed story numbers are not current implementation authority.
- Current authoritative requirements: [parent PRD](prd.md) plus [scoped Infra Automation addendum](prd-infra-automation.md). The addendum replaces the draft's release scope without removing the broader future vision.

## 2. Impact analysis

### Product and epic impact

Add Epic 16: Evidence-Gated Infrastructure Automation, with 20 adopted stories 16.0–16.19. Retain all existing Epic 0–15 IDs, acceptance criteria and statuses. The resulting roadmap contains 121 stories across 17 epics: 84 done, 15 ready-for-dev, 2 review and 20 backlog. None of the new stories is implemented or ready for feature development solely because this course correction was approved.

The release priority changes immediately: Epic 16 planning/qualification first; Story 12.5 is the parallel SBOM release-enabler lane. Automation-relevant backup/restore/restricted-network work from 12.7/12.8 and feature-specific documentation are mandatory release conditions. Broader Epic 13/14 work stays mapped for later delivery. Stories 12.3, 12.4, 12.6 and 13.8 retain their completed records. Epic 15's two acceptance-documentation follow-ups retain review status.

### Architecture, privacy and UX impact

This is a major addition to the product boundary: collection agents, verified authority, durable orchestration and remote handoff are new planned subsystems. The shared analysis core remains authoritative for findings, severity and Evidence Law; workflow gate/enforcement decisions remain separate from canonical advisory reports.

The target release supports uploaded artifacts and a qualified isolated OpenTofu/Terraform collector, authenticated decisions, strict evidence/action binding, durable outbox/receiver recovery, explicit unit preflights and a self-hosted GitHub receiver with trusted local saved-plan custody. It excludes direct apply within DeployWhisper, arbitrary scripts, broad collector/integration catalogs, autonomous approval, AI workflow generation and PostgreSQL/HA performance claims.

The React UX receives a dedicated feature surface, preserving the existing Dashboard information budget and approved design system. Approvals show exact source/evidence/target/expiry; workflow and external deployment state are distinguished. Uncertain delivery, disable/revocation, cancellation after handoff, acknowledgements and separation-of-duties limitations must be visible. No UI rendering changes are made in this planning task.

## 3. Path forward

Select direct roadmap adjustment plus bounded release-scope refinement. Rollback of v1.4.0 was rejected: accepted delivery is the prerequisite, not the problem. Replacing DeployWhisper with a general orchestration/deployment platform was rejected because it expands execution and maintenance obligations beyond this release's supported boundary.

Preserve canonical IDs and change delivery priority. The original suggestion to reuse 12.5 for automation was rejected because 12.5 already names unfinished SBOM work and 12.6 is shipped signing/provenance. New product scope belongs to Epic 16; package version numbers do not require numerical story execution order.

Use the reviewed effort range only as preliminary planning context. There is no adopted calendar date or staffing commitment. Story 16.0 must close the identity, fenced-claim, collector isolation, saved-plan custody and receiver crash/retry feasibility gates before downstream feature stories are promoted to ready-for-dev. The proposed architecture/RFC is reviewable now; feasibility has not been experimentally proved by these document edits.

## 4. Detailed changes applied

| Artifact/section | Before | After and rationale |
| --- | --- | --- |
| Parent PRD §4.4 and release scope | Unqualified Terraform-runner exclusion; no new Infra Automation release contract | Narrow operator-controlled collection exception with no apply/provision/remediate; v1.5.0 scope links to the canonical addendum. Existing 187 FR and 38 NFR identities retained. |
| Feature requirements | v0.2 assumes implementation through 12.2 and Phase A in future v1.4.0; 179 mixed release/vision rows | Canonical bounded v1.5.0 addendum with active FR/NFR IDs, proof and story mappings; every original row explicitly adopted/revised, partially revised or deferred in the disposition inventory. |
| Architecture | Shared analysis architecture, no complete authority/runner/durable handoff target design | Additive target-design section and eight decision records covering identity, fenced state, approved action, custody, isolation, operations and optional AI. Planned design is distinguished from implemented baseline. |
| RFC | No recorded RFC for the new trust boundary | Complete [RFC 0001](../../docs/rfcs/0001-infra-automation-preflight-and-handoff.md), Proposed pending public/CODEOWNERS review and the documented minimum review window. User planning authorization is recorded without inventing public acceptance. |
| UX | No current feature-specific workflow/approval/runner contracts | [Infra Automation UX](../../docs/design/infra-automation-ux.md) and canonical UX reference; root `/infra-automation` routes and all required states/authority boundaries defined. |
| Epics/stories | Epic 16 absent from current epic plan | Add 20 dependency-linked user stories with explicit acceptance/proof and requirement coverage; no existing story renumbered. |
| Sprint tracker | 101 current stories; next sequential delivery 12.5 | Add 20 backlog entries; explicit release-priority metadata selects Epic 16 planning/qualification and 12.5 release enablement. Preserve every existing development-status entry. |
| Traceability/status/context | Current summaries cover the 101-story baseline only | Add active feature requirements and original-row dispositions, update the 121-story inventory and mandatory future implementation boundaries, preserve historical snapshots. |

## 5. Handoff and success criteria

**Product/maintainer:** Own adopted scope, backlog priority and explicit disposition of future vision items. Maintain canonical parent/addendum authority and stable shipped IDs.

**Architect/security/governance reviewers:** Review RFC 0001, the target architecture and Story 16.0 evidence. Resolve supported identity/session membership, collector/plan-custody isolation, atomic claim/approval/receiver contracts and recovery behavior before feature implementation. Public acceptance follows the [RFC process](../../docs/rfcs/README.md); no public review has been simulated.

**Developer/QA:** Prepare Story 16.0 as a bounded planning/feasibility task, with testable proof obligations and dedicated fixtures. Future feature stories require normal create-story → dev-story → code-review progression and their own regression/docs checks; browser-facing changes require the composed app. Run 12.5 release-enabler work as a separately scoped story. Do not mutate real infrastructure, add tooling dependencies or publish a release as part of this document workstream.

**Readiness reviewer:** Independently evaluate document authority, full FR/NFR extraction, original-row disposition, epic coverage, dependency sequence, UX/architecture agreement and unresolved implementation gates. Record the result in [the readiness report](implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md). A NOT READY result is a completed assessment, not a failed document workflow.

Success criteria for this planning task: canonical scope is consistent; all active requirements have an acceptance path; all 179 original requirement rows have explicit dispositions; new story IDs are unique/dependency-valid; previous statuses are unchanged; priority is explicit; no unrun test or public approval is claimed; readiness findings have named owners and next actions.

## 6. Change-navigation checklist

| Checklist items | Outcome |
| --- | --- |
| 1.1–1.3 Trigger and evidence | Done: new feature/release priority plus researched code/vendor findings. |
| 2.1–2.5 Epic impact/order | Done: Epic 16 added; existing epics remain valid; numeric IDs preserved and priority changed. |
| 3.1–3.4 Artifact conflicts | Done: PRD/architecture/UX/tracking authority aligned; runtime implementation remains unchanged. |
| 4.1–4.4 Options | Done: direct adjustment/bounded release selected; rollback and general deployment-platform expansion rejected. |
| 5.1–5.5 Proposal and handoff | Done: evidence, scope, edits, dependency sequencing, risks and owners documented. |
| 6.1–6.3 Review/authorization | Done: scope adopted from the explicit latest user instruction; batch planning changes applied. Public RFC acceptance is separate and pending. |
| 6.4 Tracking | Done: all 20 backlog entries are present and all 133 prior development-status entries are unchanged. |
| 6.5 Next step | Story 16.0 planning/feasibility and public RFC review; downstream feature coding remains gated. |

## 7. Validation and completion record

Final validation and readiness results are recorded below after the independent assessment. The workflow produces an adopted planning change and a candid implementation gate report; it does not declare the future feature implemented.

### Completed assessment and validation

- PRD/architecture/UX/course-correction updates and backlog integration: complete as planning artifacts; no feature implementation.
- Readiness: **NOT READY**, four open gates (IR-01 public RFC acceptance; IR-02 unrun feasibility spikes; IR-03 final wire/report/UI contracts; IR-04 bounded story refinement). Three alignment findings (state vocabulary, implicit forward acceptance proof, inherited ownership granularity) were corrected.
- Coverage: parent 187 FR + 38 NFR retained; new 60 FR + 12 NFR mapped; all 179 original source rows dispositioned (89 adopted-revised, 45 partial-revised, 45 deferred). 121 unique stories; all 20 new entries backlog.
- `./.venv/bin/python -m unittest discover -s tests/test_docs -q`: 51 passed.
- Aggregate Python/YAML/JSON assertions: complete requirement text/proof mappings, original source digest, prior-status preservation, earlier-only story dependencies, 16.14 receiver dependency, local links/frontmatter and new-document whitespace passed.
- `git diff --check`: passed. No application code or runtime configuration changed; no Compose/cloud/runner/load/production test or public RFC review was represented as executed.
- BMad Help after review: next **Create Story** (`bmad-create-story`) for 16.0 planning/governance/feasibility qualification; prepare the separate 12.5 release enabler in its own workstream. Rerun readiness after gate closure; then prepare/promote only dependency-satisfied implementation stories.

The authorized task is complete: the reviewed plan is adopted for planning, the canonical product/technical contracts are aligned and the independent readiness result is recorded. Public RFC acceptance remains pending under the existing process; this is not an additional permission request or a claimed bypass of its review window.
