---
stepsCompleted: [step-01-document-discovery, step-02-prd-analysis, step-03-epic-coverage-validation, step-04-ux-alignment, step-05-epic-quality-review, step-06-final-assessment]
assessmentScope: Story 16.3 only
status: ready-for-bounded-implementation
---
# Implementation Readiness Assessment Report

**Date:** 2026-10-13
**Project:** deploywhisper
**Scope:** Story 16.3 closed workflow schema and validator; no production workflow execution or future-story qualification.

**Current disposition:** READY for bounded workflow-v2 implementation after the maintainer-authorized contract correction on 2026-10-13. The initial discrepancy and its resolution are retained below; this is readiness to implement, not acceptance of unexecuted tests or performance results.

## Document inventory

Canonical whole documents: `_bmad-output/planning-artifacts/prd.md`, `prd-infra-automation.md` (feature delta), `architecture.md` (§25), `epics.md`, and `ux-design-specification.md`. Feature UX: `docs/design/infra-automation-ux.md`. No competing sharded canonical documents found. Historical readiness reports and sprint change proposals remain supporting evidence.

Additional authorities: `_bmad-output/project-context.md`; Story 16.3; current `docs/infra-automation/workflow-contract-v2.md`; `sprint-change-proposal-2026-10-13-workflow-v2.md`; historical `docs/infra-automation/contract-v1.md`; Story 16.0 frozen contract fixtures, governance, and feasibility qualification. Canonical selection and routine continuation follow explicit repository source precedence and session authorization; material contract conflicts remain subject to resolution and cannot be waived by this assessment.

## PRD analysis

This bounded delta reassessment preserves the parent 187 FR / 38 NFR inventory and the 60 FR / 12 NFR feature inventory assessed in the 2026-10-10 readiness report. The complete feature addendum was read; this report extracts every requirement owned by Story 16.3 with exact canonical text. It does not claim a new full-parent audit.

| ID | Exact canonical requirement | Stories | Acceptance proof |
| --- | --- | --- | --- |
| IAU15-FR-001 | Support only Tier 0 preflight and Tier 1 human-approved external handoff in v1.5.0; reject apply/destroy, remediation, unattended approvals and unsupported execution profiles. | 16.0, 16.3 | Scope/RFC review and unsupported-mode rejection corpus |
| IAU15-FR-009 | Publish a versioned workflow schema with typed, bounded inputs and explicit supported step input/output contracts. | 16.3 | Schema valid/invalid fixture corpus |
| IAU15-FR-010 | Validate definitions without side effects using bounded YAML bytes/depth/aliases, duplicate-key rejection and an acyclic graph capped at 50 steps. | 16.3 | Parser resource-abuse and cycle/step-limit corpus |
| IAU15-FR-011 | Accept only the closed P0 registry: supported artifact intake, OpenTofu/Terraform collection, analyze, policy gate, approval and GitHub handoff; reject arbitrary scripts/plugins, loops and generic failure/finally execution. | 16.3 | Registry and unsupported-handler denial corpus |
| IAU15-FR-012 | Resolve only typed substitution references to inputs, declared step outputs and run/project metadata; reject unknown references, functions and code evaluation. | 16.3 | Typed-reference and injection fixture corpus |
| IAU15-FR-013 | Require every executable path to a handoff to pass its mandatory successful evidence analysis, policy gate and matching approval; skipped/failed or unrelated ancestors do not qualify. | 16.3, 16.8 | Wrong-branch, skipped-ancestor and alternate-path tests |
| IAU15-NFR-008 | Workflow validation must have p95 <500 milliseconds for the declared 50-step workflow corpus under the reference workload. | 16.3, 16.19 | 1,000-validation timing/correctness benchmark |

Coverage intent: six FRs and one NFR. The feature PRD further fixes the benchmark procedure: 100 warm-up samples, 1,000 measured samples, p50/p95/p99 and failure counts, declared corpus digest and hardware/software profile. Structural validation must not claim runtime success, human authority, fresh evidence, registered target admission, or executable collection. No dependency addition is implicitly approved.

## Epic coverage validation

All seven owned IDs appear with exact text in Epic 16 / Story 16.3: six of six FRs (100%) and one of one NFR. No missing identifier or invented requirement was found. Coverage by identifier is not contract completeness: the initial FR-012 and environment/profile discrepancy against frozen v1 was resolved by the explicit workflow-v2 revision recorded below. The current contract provides bounded input/step/project/run namespaces and explicit source/profile/environment fields without narrowing canonical requirement text. FR-013 explicitly retains runtime success/freshness integration in 16.8; NFR-008 retains integrated release qualification in 16.19.

## UX alignment

Feature UX exists and requires template/YAML validation with inline step/field locations, separate Save/Validate/Publish, and explicit advisory versus exact-plan limitations. These needs align with a pure validator returning bounded sanitized errors; validation never publishes or authorizes execution. Future browser editor/route integration belongs to 16.7, persistence to 16.4, runtime eligibility to 16.5/16.8. No rendered surface is required here: **UI validation not applicable** for the bounded schema slice. The amended feature UX explicitly consumes workflow-v2 templates and bounded errors; actual rendered environment/source display remains future browser-owner proof.

## Story quality and dependency assessment

Story 16.3 delivers useful author feedback and prevents unsupported definitions from entering later lifecycle operations. Its six GWT criteria and four ordered bounded packets are appropriately separated: schema → parser/references → graph → qualification/docs. No database migration, server route, executable collector, publication, or future-story entity is needed. Dependency 16.0 is satisfied by its final qualification and 2026-10-12 review amendment. The root reports merged 16.2 at develop `5c32eec` (PR157); this is useful baseline context, not an additional prerequisite for a pure validator.

WP7 assigns Codex under @pramodksahoo supervision, estimates 1–2 engineering person-weeks, and requires independent schema/graph/security review. The estimate is planning effort, not elapsed agent time. Root must record actual packet owners and reviewers before closure. The epic's gate language and version references are now aligned. The story's historical preparation-only Dev Record remains a snapshot to reconcile during execution, not fresh qualification evidence.

### Initial contract discrepancy — resolved 2026-10-13

The frozen v1 schema and qualification prototype use `version: 1` inherited from the closed base; only typed `step_id` plus enumerated `output` references; required `project_id` and `workspace_id`; AND prerequisites; and no workflow-level inputs, run/project substitution namespace, environment, source variant, or collection profile selector. Policy and handoff bind `target_id` and `authorization_kind`; source/profile/environment appear in other contracts and later runtime bindings. At initial assessment, Story AC1 and architecture §25.5 instead named `workflow_version`; FR-012 and parser packet require broader substitutions; AC4 and schema packet require environment binding; the schema packet also names source variants. Silently adding those fields to closed v1 would change frozen wire/canonical digests and violate change control. Silently omitting them while claiming all original acceptance would also be incorrect.

The initial assessment was **NEEDS WORK** pending a material choice: preserve frozen v1 and explicitly reduce/reconcile this slice, or revise the contract under its change-control rule. The maintainer selected option 2, revising the contract to support the broader requirements. The [course correction](sprint-change-proposal-2026-10-13-workflow-v2.md) records that choice, rejected alternatives, affected owners and independent review corrections. This preserves the initial issue as resolved history rather than waiving it.

The reviewed [workflow-v2 contract](../../docs/infra-automation/workflow-contract-v2.md) now explicitly requires strict `workflow_version: 2`, five bounded scalar input types, all four typed reference namespaces, uploaded/collected source variants, admitted immutable profile catalogs and symbolic target/environment matching. Workspace may be null only for project-scoped authoring; later runtime owners must resolve an authorized concrete workspace before v1 machine operations. No automatic v1 conversion or nested version is accepted. Receiver/runner and other operation protocols retain their independently versioned v1 forms; report v2 and `tuple-json-utf8-v1` canonicalization remain unchanged.

The PRD amendment, architecture §25.5/§25.9, Epic16/Story16.3, release version matrix, project context and feature UX consistently select this authority. The contract addresses the independent review's nominal identifier typing, finite substitution inputs/output handles, context-scope equality, profile authorization for every gate, immutable result/digest consistency, sanitized in-process diagnostics and separate v2 manifest. No additional blocking ambiguity was found in this bounded reassessment.

### Nonblocking implementation boundaries

- AND dependencies eliminate conditional bypass: every declared prerequisite must succeed. Structural checks must follow exact artifact → analysis → gate → decision → handoff lineage, not merely a common ancestor or list order. Unknown skip/failure/finally/OR syntax rejects; runtime still rechecks success/freshness/current authority.
- Retain resource maximums: UTF-8 128 KiB, depth 16, 50 steps, no anchors/aliases/merge/duplicate keys or implicit timestamps. Smaller configured limits may tighten policy; larger values cannot expand the v2 hard ceilings; aggregate diagnostics also have a hard ceiling of 50. Bound and sanitize aggregate errors without reflecting submitted secrets.
- Intake/collection resource parameters are only positive safe-integer artifact bytes ≤8 MiB and timeout ≤600 seconds. Schema descriptions never register executable collectors or qualify a runtime profile. Collection selects a literal profile digest from a trusted immutable catalog of at most 16 records; an empty catalog denies collection. Catalog entries describe allowed tool/authorization kinds and install no executable. Unknown profile/command syntax fails closed.
- Reuse installed Pydantic/PyYAML; confirm actual dependency versions/APIs, no new DSL/template dependency. Preserve the frozen `tuple-json-utf8-v1` algorithm while defining new v2 typed defaults/nulls and fixtures. Prove existing frozen-v1 hashes unchanged, and separately hash the v2 contract/schema/positive/negative vectors in the new manifest.
- NFR-008 requires a recorded 50-step corpus, 100 warmups, 1,000 correct measured results, p50/p95/p99, failures and host/runtime identifiers. Qualify the declared reference profile or explicitly retain reference-profile performance as unqualified; a local result is only a local result. No benchmark number is asserted here.
- Register `tests/test_infra_automation` explicitly in local CI and the services pytest shard. Run exact relevant CI commands, root unittest smoke, every-directory local CI, Ruff lint/format, diff check, bounded hostile-input/graph fixtures and independent review. Use no default application database during pure qualification.

## Foundation gate disposition

| Gate | Current evidence | Story 16.3 consequence |
| --- | --- | --- |
| IR-01 public RFC | Committed direct maintainer decision/governance record; explicit RFC-specific early-window exception. | Satisfied; no second independent human approval inferred. |
| IR-02 executable feasibility | 16.0 WP7 final verification and 2026-10-12 qualification review amendment. | Satisfied for its bounded disposable profile, not production/release support. |
| IR-03 owning interface | Maintainer-authorized workflow-v2 contract, recorded course correction, independent contract review corrections and aligned planning documents; historical v1 retained. | Satisfied for bounded implementation design. New schema/vectors/manifest and executable contract checks are required in the first packet before dependent validator work is accepted. |
| IR-04 ownership/sizing | WP7 named accountability, 1–2 person-week estimate and independent schema/graph/security discipline; four bounded story packets. | Satisfied as planning; actual packet/reviewer assignment remains root execution record. |
| Earlier dependency | 16.0 done with final review amendment; no future story required for pure validation. | Satisfied. |

## Summary and recommendations

**READY for bounded Story 16.3 workflow-v2 implementation.** Assessor: Codex independent readiness lane, 2026-10-13. The sole material blocker was resolved by an explicit maintainer choice and reviewed major-version contract; no unresolved blocking design choice remains. Historical preparation status must still be reconciled by the root as execution advances. Readiness does not mark any implementation checkbox or acceptance proof complete.

The implementation boundary is pure parsing, typed schema/substitution, exact AND-success lineage, canonical output, bounded diagnostics and measured qualification. Root records packet owners, freezes the new schema/vectors/manifest, and executes schema → parser/references → graph → qualification/docs in dependency order. Preserve all frozen-v1 bytes; reject missing/v1/unknown workflow majors rather than translating them. Do not add routes, tables, collector execution, authority, dispatch or arbitrary extension points.

Before review, actual verification must include:

1. Closed v2 positive/negative vectors and schema parity; unchanged frozen-v1 hashes and independently verifiable v2 manifest; canonical defaults/nulls/order/digest consistency and consumer major rejection.
2. Parser exact-boundary/one-over hostile cases, zero aliases/anchors/merge/duplicate/non-string keys, bounded diagnostics with no reflected submitted data, and zero execution/network/filesystem effects during validation.
3. Nominal input/reference types, missing/unknown values, metadata scope/environment equality, bounded immutable output handles, every profile/authorization pairing, symbolic matching, cycle/diamond/alternate/unrelated-branch lineage and rejected skip/failure/OR syntax. Structural success is never future runtime success or authority.
4. A declared 50-step corpus, 100 warmups and 1,000 correctness-checked samples on the stated Linux 4-vCPU/8-GiB reference allocation; record actual host/virtualization quotas, OS/CPU/runtime/corpus identity, p50/p95/p99 and failures. AC6 remains unqualified until measured p95 is below 500 ms; no Mac or preparation result substitutes for Linux qualification. Full integrated release-load verification remains 16.19.
5. Explicit new-directory registration/discovery, repository constructor/fixture search, relevant exact pytest shard(s), root unittest smoke, every-directory local CI, Ruff lint/repository-wide format, diff check and independent schema/graph/security review. Use isolated test data; no default application database is needed by this pure slice.

BMad next step is continuation of the already requested **[DS] `bmad-dev-story`**, followed by a fresh **[CR] `bmad-code-review`**. This readiness lane changed only this report and ran no application/database/benchmark/browser tests. UI validation remains inapplicable for the pure backend contract scope. No production runtime, profile qualification, benchmark result or stable-release claim follows from this readiness result.


## Root implementation verification addendum — 2026-10-14

The earlier readiness decision has now been exercised. Story16.3 is **review**;
its Dev Agent Record contains named packet owners, independent contract/security
and exported-schema review, the complete 39-file change list and actual checks.
The new manifest and all 16 frozen-v1 hashes match. Full local CI passed all ten
explicit test directories (2,178 tests); root discovery, both affected pytest
shards, production Docker/Python3.11 smoke, packaging and configured static gates
also passed, subject to the recorded pre-existing nonblocking type-check debt and
missing PyYAML stubs. No UI surface changed.

The [standalone measurement](../../docs/verification/infra-automation/16-3/README.md)
records 100 warmups plus 1,000 correct validations, p95 42.562708 ms under the
recorded Linux four-CPU/8-GiB container limits. This closes owned AC6, not the
integrated runtime/release workload. BMad help routes next to **[CR]
`bmad-code-review` on Story16.3** in fresh context, including its Git closure.

Review follow-up (2026-10-14): the three-layer code review fixed JSON scalar/canonical compatibility and Python3.10 test imports, then approved Story16.3 as done. Fresh all-directory CI passed 2,184 tests; source-matched Linux requalification records p95 1.714917 ms. The earlier development measurement remains historical evidence. See the [review report](../implementation-artifacts/16-3-code-review-2026-10-14.md).
