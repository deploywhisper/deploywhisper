---
assessmentScope: Story 16.10 only
status: implementation-authorized-verification-pending
---
# Story 16.10 scoped implementation readiness

2026-10-30. This assessment authorizes the bounded registered-target,
precollection-lock, exact-intent/outbox and one-use-grant slice. Story 16.0's
accepted governance/qualification and frozen interfaces, accepted 16.8 decisions,
and the merged Story 16.9 baseline
`501d789460adccdb1765313f996df42583dc96a1` supersede the original unresolved
preparation prose. Stable story/AC/requirement identities remain unchanged.

Independent read-only entry review confirmed that routine owning-story API
refinement under architecture §25.9 requires no additional maintainer approval.
The accepted scope is recorded in
[handoff-contract-v1.md](../../docs/infra-automation/handoff-contract-v1.md).
It adds closed human registry/prepare/read/dispatch/break-lock resources and
relational persistence within the established service/API boundary. This is not
a major protocol change or a new general webhook interface.

## Contract decisions and ownership

- Preserve frozen workflow-v2, decision-v1, receiver-v1, state, cursor and error
  artifacts. Decision bindings use integer scope IDs and retain `revision_id`;
  frozen receiver bindings use string scope IDs and have no revision field.
  An explicit validated mapper converts only canonical scope IDs and omits the
  decision-only revision. Retain separate canonical bytes/digests and relational
  revision linkage; a decision digest is never a receiver digest.
- Resolve registered aliases and acquire canonical locks atomically before
  collection. Preserve immutable workflow/snapshot bytes and retained alias
  lineage. Registry updates, disable/revoke/restore and privileged lock breaks
  cannot revive old authorization.
- Recheck the immutable decision and live identity, policy, target, source,
  custody and deadline facts in the same reserved transaction as the exact
  operation/outbox/grant write. Keep network delivery outside SQLite, credentials
  ephemeral and receiver authentication separate from human/dispatch audiences.
- Qualify online consume/status/terminal service contracts through scoped doubles.
  No public receiver consume/receipt/outcome/reconcile HTTP route is added here.
  Story 16.11 owns the durable real receiver, callback sequencing and parent-run
  terminal reconciliation; 16.14 owns real collection/custody integration and
  16.19 owns integrated production qualification.
- Default material, workflow-ref, delivery and collection ports remain unavailable.
  Environment-backed references and fixed transport policy do not qualify live
  GitHub delivery, production collector admission or universal exactly-once work.

## Verification boundary

This readiness assessment records authorization and interface decisions, not
formal code-review completion or release acceptance. Implementation verification
is still owned by the active story: focused crash/race, binding/credential,
quota/SSRF and API tests; root smoke; the exact API/CLI/infra pytest shard;
repo-wide Ruff/format; local CI and applicable static checks. Record actual
commands/results in the story after execution. No passing broad-suite result is
asserted here. UI validation is not applicable to this backend-only slice.

The story verification record owns final command output, including production
Python 3.11/SQLite portability and fixed-transport API-version proof. Readiness
does not reproduce changing test totals. Broad verification and formal review
must be completed and recorded before story acceptance.

Remaining integration limits: scoped doubles do not establish live receiver or
collector qualification; terminal handoff service proof does not terminalize the
parent run. Story 16.11 must reconcile parent-run outcomes without blind resend,
replacement grants or early lock release. Next workflow after implementation and
recorded verification is formal `bmad-code-review`, followed by fixes and story
status reconciliation through the story owner.


## R4 internal consistency refinement — 2026-11-02

The owning slice now requires a server-owned exact-graph material generation
witness around consumer rechecks. Sequential per-step callback results alone
cannot establish a consistent current authority snapshot. The typed scope binds
selected/required receipt identities and immutable bindings; the read-only
provider attests a stable domain and monotonic per-receipt generations, including
ABA. The default port is unavailable; no production collector, machine issuer or
receiver is enabled. Real implementations must serialize material/custody changes
with admission or retain qualified leases through the effect. Frozen protocols,
public API shapes, persistence schema and existing ACs remain unchanged. This is
a necessary owning-story implementation refinement of current-material admission
under §25.9, recorded in handoff-contract-v1.md; it does not broaden product scope.
