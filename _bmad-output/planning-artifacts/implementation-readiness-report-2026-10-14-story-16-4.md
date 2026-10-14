---
stepsCompleted: [step-01-document-discovery, step-02-prd-analysis, step-03-epic-coverage-validation, step-04-ux-alignment, step-05-epic-quality-review, step-06-final-assessment]
assessmentScope: Story 16.4 only
status: ready-for-bounded-implementation
---
# Implementation Readiness Assessment Report

**Date:** 2026-10-14
**Project:** deploywhisper
**Scope:** Story 16.4 scoped workflow drafts, immutable revisions, snapshot consumer port, feature policy and screened audit. This report does not qualify production run execution or later release integration.

**Current disposition:** READY for bounded implementation after independent review of the lifecycle contract and interface fixture. The initial IR03 gap and its resolution are retained below; readiness is not acceptance of unexecuted implementation tests.

## Document inventory

Canonical whole documents are `prd.md`, `prd-infra-automation.md` (feature delta), `architecture.md` (§25), `epics.md` and `ux-design-specification.md`, under this planning directory. Feature UX is `docs/design/infra-automation-ux.md`. No competing sharded canonical document was found. Additional authorities are project context, Story 16.4, completed16.2/16.3, the prior readiness assessments, workflow-contract-v2 and the independently versioned frozen v1 protocols. Historical preparation reports remain supporting evidence, not current blockers by themselves. Routine continuation follows the user's autonomous dev-story instruction; a material unresolved contract decision still prevents readiness.

## PRD analysis

The complete feature PRD was read. This scoped reassessment retains the parent 187-FR/38-NFR and feature 60-FR/12-NFR inventory assessed in the 2026-10-10 report; it does not claim a fresh audit of every parent requirement. The six exact requirements assigned to16.4 are:

| ID | Exact canonical requirement | Stories | Required proof |
| --- | --- | --- | --- |
| IAU15-FR-014 | Scope workflow drafts and revisions to one project and optional workspace. | 16.4 | Workflow cross-scope CRUD tests |
| IAU15-FR-015 | Keep published revisions immutable; restore creates a new draft, and drafts cannot execute. | 16.4 | Publish/edit/restore/draft-run lifecycle tests |
| IAU15-FR-016 | Snapshot the published definition, validated inputs, scope and source identity immutably when a run starts; require a repository commit for collected/exact-plan paths and explicitly mark unavailable source for upload-only advisory review. | 16.4, 16.5 | Post-start mutation and rerun snapshot tests |
| IAU15-FR-017 | Disable, revoke or restore epoch changes must invalidate unconsumed grants and prevent new run starts, collection claims, dispatch or grant consumption while preserving read and reconciliation for accepted external work. | 16.4, 16.10, 16.11, 16.18 | Disable/revoke/restore-before-dispatch-or-consume race matrix |
| IAU15-FR-059 | Record append-only application audit events with verified principal/type, role, scope, target, reason, time and before/after digests; expose scoped UI/JSON export without raw artifacts/secrets and document DB-admin trust limits. | 16.4, 16.9, 16.12, 16.18 | Audit event coverage/export authorization and secret corpus |
| IAU15-FR-060 | Let authorized operators configure feature enablement, targets, quotas, retention, TTL and credential lifetimes; reject unsafe reductions, protect pending evidence or invalidate its decision before deletion, and audit each change. | 16.4, 16.18 | Configuration permissions, pending-retention and floor-change tests |

No NFR is exclusively assigned to16.4. Cross-scope isolation, no secret persistence, migration safety, bounded contracts and version-matched operator documentation remain applicable constraints. FR016 snapshot export and FR017 live policy are owned consumer-port contracts here; durable runs/grants/receiver operations and integrated browser/settings/recovery proof remain with their declared later owners. This preserves every canonical requirement while avoiding unsupported future-production claims.

## Epic coverage validation

Epic16 and the dedicated16.4 story include all six IDs with exact canonical text: 6/6 owned FRs, 100% coverage; no missing or invented requirement was found. Identifier coverage does not substitute for the concrete interface design required below. Shared FR016/017/059/060 retain their explicit later owners. Story 16.4 owns no run, task, grant, outbox, target registry or external receiver persistence; typed snapshot, grant-consumer and pending-retention ports provide its acceptance boundary.

## UX alignment

The feature UX exists and aligns with separate Save/Validate/Publish, immutable revision history, explicit upload-source limitations, scoped authority, disabled history/reconciliation and administrator configuration. Browser workflow/editor integration belongs to16.7; integrated settings controls and operational recovery belong to16.18 Packet18.6, using16.4/16.10 APIs. No new rendered surface is needed here: **UI validation not applicable** unless implementation changes one. API diagnostics must support bounded step/field errors without leaking submitted secrets. Backend completion cannot claim those future browser journeys or audit UI are delivered.

## Story quality and dependency assessment

The story gives maintainers scoped authoring and preserves published evidence against later edits. Six Given/When/Then criteria cover happy paths, cross-scope and nonhuman denial, optimistic publication conflict, immutable snapshot/source identity, live epoch invalidation, and audited safe configuration. Four ordered packets define bounded persistence, service/HTTP, policy/configuration and proof/documentation ownership. WP7 assigns Codex under @pramodksahoo supervision, estimates1–2 engineering person-weeks and requires independent persistence/API review; the estimate is planning effort, not elapsed agent time. Root records actual packet owners before execution.

Dependencies16.2 and16.3 are complete; the root verified16.3 merged as PR158 on develop at `ce4416d`. Earlier16.0 governance/feasibility gates remain accepted within their recorded qualification limits. No future story is needed to prove this slice's ports. Only workflow/revision, scoped policy/epoch and audit/idempotency records needed here may be migrated. Existing memberships and operation transactions must be reused. No future runtime schema or new dependency is justified by this foundation work.

No critical story-structure defect was found. At initial assessment one major readiness item remained until the root froze the concrete interface/fixture design: the prepared narrative deliberately does not assign exact configuration floor numbers, all new route/body/error forms, retention-port behavior, or which lifecycle transitions advance authorization versus restore epochs. These bounded implementation decisions must be coherent with immutable workflow-v2 and frozen independent v1 protocols before implementation consumes them. This is not a request for a new product scope/RFC or a second human approval. Minor stale backlog/gates-unmet text must be reconciled by the implementation owner after readiness.

## Concrete interface acceptance checklist

1. Preserve workflow-v2 exact canonical bytes and digest; no v1 migration or frozen-manifest rewrite. Revalidate at save, publication and snapshot export with trusted profile admission. Empty production profile admission remains fail-closed. Store only screened definitions/inputs; diagnostics and audit cannot echo secrets or unknown submitted keys.
2. Authenticate before exposing object existence; use16.2 live project/workspace capabilities and mutation/CSRF credentials in the same transaction. Admin/maintainer may draft, only human admin may publish, all five permitted human roles may read authorized workflows. Frozen settings read is admin/maintainer; settings mutation is scoped admin. A global identity-admin flag alone does not grant project authority.
3. Freeze typed create/edit/validate/publish/archive/restore/read/list/settings/audit requests and responses with draft expected-version and idempotent publication semantics. A reused principal/operation/key with changed request digest conflicts. Concurrent publication has a database uniqueness/CAS guard, not a pre-check alone. Revision history and archived workflows have no destructive edit endpoint. Restore creates a draft without rewriting history.
4. Keep successful validation results in typed `data` with bounded sanitized diagnostics; do not append fields to closed error-v1. Authentication401, generic permission403, binding conflict409, validation422, quota429 and authority unavailable503 retain the frozen taxonomy and safe correlation IDs. Lists must filter scope before limits/counts; any cursors use the frozen signed principal/scope/filter/snapshot binding and cannot expand authority.
5. Snapshot output has immutable canonical definition, typed validated/defaulted inputs, digests, trusted resolved scope/environment, source variant and captured policy/epoch identity. Null draft workspace may refine only to an authorized concrete workspace. Upload source is explicitly unavailable; collected source requires immutable commit and admitted profile. Export creates no run and cannot qualify a saved-plan receiver or start a handler.
6. Distinguish authoring/history from effectful start/claim/dispatch/consume and live authorization from a cached snapshot. Feature-off defaults must deny new effects; disabling, revocation and restore must invalidate pending authority before any consume. Accepted/unknown work retains permission-checked read/reconciliation, never an implicit new-action permission. Draft restoration versus coordinated database restoration must have explicit epoch semantics.
7. Freeze numeric configuration bounds and rationale; the established collection TTL default is3600 seconds and stricter audited values may shorten it, never extend evidence freshness beyond approved policy. Reuse existing identity lifetime rules rather than silently changing human sessions. Future machine lifetime fields must be typed policy, not a credential issuer. Unsafe changes reject, or atomically invalidate affected pending authority before deletion. Pending-retention doubles must distinguish undecided/pending evidence from accepted/unknown work that remains protected; caller-supplied absence is not evidence that deletion is safe.
8. Append screened audit in the mutation transaction with verified actor/type/role, exact scope, operation target, controlled reason, UTC time and before/after digests. Bound/export only authorized rows with no credentials, artifact bytes or unfiltered raw input. Audit APIs are append-only but not tamper-proof against host/database administrators. Keep actual grants, retention janitor, target registry, receiver and coordinated restore procedures with their later owners.

## Foundation gate disposition

| Gate | Evidence | Disposition for16.4 |
| --- | --- | --- |
| IR01 public RFC | Direct maintainer acceptance and explicit early-window exception in16.0 governance evidence | Satisfied; no invented second human review |
| IR02 executable feasibility |16.0 final qualification and 2026-10-12 review amendment | Satisfied for bounded sequential implementation, not production support |
| IR03 owning interface | Delivered16.2 authority and16.3 workflow-v2; independently reviewed lifecycle contract v1 and interface fixture with archive/policy/publication corrections | Satisfied for bounded implementation; exact typed schemas and executable fixtures are required before dependent consumers |
| IR04 sizing/ownership | WP7 named accountability,1–2 person-week planning estimate, four story packets and independent persistence/API review | Satisfied as planning; root must record actual owners/reviewers |
| Earlier dependencies |16.2/16.3 done; root verifies PR158 merged at `ce4416d` | Satisfied |

## Summary and recommendations

**READY for bounded Story 16.4 implementation.** Assessor: Codex independent readiness lane, 2026-10-14. The original IR03 gap is resolved by the concrete contract/fixture and reviewed clarifications recorded below. No unresolved blocking product-scope, architecture or contract choice remains. The minor stale preparation status needs reconciliation during promotion. This assessment does not mark implementation checkboxes complete or claim tests passed.

Continue the already authorized **[DS] `bmad-dev-story`** for16.4. Run isolated migration, permissions, immutable lifecycle, concurrency/idempotency, snapshot, disable/revoke/restore, retention-floor and screened audit export proofs, then required exact shards, every-directory local CI, lint/format, constructor search, diff check and independent trust-boundary review. **[CR] `bmad-code-review`** is the next story workflow after implementation. BMad help catalog and sprint status were checked for this recommendation. No application/database/browser/benchmark tests were run by this readiness lane; only this report was changed.

## Concrete contract reassessment — 2026-10-14

The root supplied [lifecycle contract v1](../../docs/infra-automation/workflow-lifecycle-contract-v1.md) and its [interface fixture](../../tests/fixtures/infra_automation/workflow_lifecycle_v1/contract.json) on branch `feature/16-4-scoped-workflow-revisions`, baseline `ce4416d`. These select exact numeric scope encoding, draft-version and idempotency guards, project-wide policy defaults, live capability mapping, bounded transports, screened audit, immutable snapshot bytes, response diagnostics and signed snapshot-bound cursor semantics. They preserve workflow-v2 and every frozen-v1 artifact. Exact typed schemas and executable fixtures remain first-packet obligations, before dependent consumers.

Configuration is explicitly policy rather than measured qualification: feature defaults off; collection evidence TTL defaults3600 seconds with60–3600 range; approval/automation-credential TTL60–3600 and no greater than evidence TTL; retention defaults604800 seconds with86400 floor; artifact ceiling8MiB, active-run ceiling10; authoring counts and runtime backlog have finite limits. The one-day retention floor exceeds every selected evidence/credential TTL but does not remove independent protection for accepted/unknown work. Human session rules remain unchanged. Lowering count quotas below retained rows rejects. Other effective policy changes advance authorization epoch, with retained accepted/unknown work and a no-delete-before-invalidation port. These choices are bounded, documented operator policy and do not establish production throughput or a retention janitor.

The independent reassessment raised two final live-policy clarifications: archive must invalidate previously exported new-start authority as well as block fresh export; and changes to legacy advisory policy must invalidate or fail the next live check for previously captured authority. Root was asked to bind workflow/archive identity or conservatively advance project epoch, and to recheck current advisory-policy digest or couple its mutation to the epoch. The following closure records the now-explicit decisions; the earlier pending disposition is historical.


### IR03 closure

The revised contract and fixture close both independent findings. The immutable stamp now binds workflow/revision identity, and the live `start` check rereads archive state, denying a snapshot exported before archive while retaining authorized accepted-work reconciliation. Existing advisory-policy save/delete, including integration overrides, advances the configured project’s automation authorization epoch and appends screened audit in the same operation transaction. Change-and-restore cannot revive old stamps; captured policy bytes stay immutable, and current effective-policy digest is rechecked to reject corruption/out-of-band mismatch. This adds live denial without changing advisory scoring semantics or enabling runtime work. The consumer itself must authenticate its operation, then retain `authorized_session` through the policy check and local mutation; a stamp is never a credential.

Publication additionally advances optimistic draft version atomically, preventing two different keys using one expected version from both publishing. Idempotent replay uses the original stored revision digest after live authorization, so a later draft edit does not break a valid original retry or publish changed content under its key. The fixture explicitly records successful version advancement and replay-after-edit behavior.

All eight IR03 design checks are now satisfied at specification level. Freeze exact typed models/serialization and executable request, race, immutable-source, permission, malformed cursor, screening, migration and retention fixtures in the first implementation packets. In particular, prove advisory-policy change-and-restore denial, archive-after-export denial, stale principal/membership/epoch denial and transaction-held consumer races rather than relying on this document as test evidence. Preserve frozen-v1 bytes and workflow-v2 meaning. No new dependency, UI integration, run/runner/grant/outbox/target table, production machine issuer or release qualification is authorized by this READY result.


## Root implementation verification addendum

The bounded implementation has completed its owned acceptance proof and is now **review**. Full local CI passed 2,269 tests, root discovery 823, the exact API/CLI/infra pytest shard 646 and services/workflow shard 1,362; production Python3.11 ran 85 lifecycle/migration tests. Static/security, copied synthetic v1.4.0 upgrade, immutable history, role/scope/CSRF, publication races, snapshot mutation, epoch/retention doubles and container restart checks pass. See the story Dev Agent Record and `docs/verification/infra-automation/16-4/README.md` for exact evidence and existing nonblocking typing debt. UI validation is not applicable. Next BMad step is **bmad-code-review on Story 16.4**, including its Git closure; no later runtime or production release capability is claimed.
