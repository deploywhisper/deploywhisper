# Sprint Change Proposal — Production Material Authority Integration

Status: **APPROVED — co-located qualified profile selected 2026-11-11**.
Mode: batch proposal, based on the requested prerequisite remediation.
This proposal does not approve or install a production authority provider.
The accountable maintainer delegated the best completion approach; the co-located
profile is selected because it matches the singleton/local-custody v1.5.0 support
matrix. The human-pilot waiver alone does not supply technical evidence.

## 1. Issue summary and evidence

Real TLS collection and browser qualification succeeded, but the remaining
Story16.15 Packet15.3 accepted/unknown-dispatch journey cannot execute through the
production composition. The relevant defaults intentionally fail closed:

- `DecisionService` has no installed production material resolver or material
  witness provider; default material resolution returns503.
- `default_registry()` installs upload/shared analysis and configured collection;
  it does not install genuine policy, human-wait or handoff composition.
- The existing local-worker handoff branch explicitly models uncertainty without
  transport. A fixture-installed success handler would not establish production proof.
- `ProtectedCustody` verifies private descriptors/bytes but does not provide an
  authoritative generation domain or admission lease.
- `handoff-contract-v1.md` requires scope-complete monotonic material witnesses,
  ABA/reset detection and lifecycle serialization or retained leases through
  admission. Hashes, unrelated epochs or a constant witness are not substitutes.

Evidence: `docs/verification/infra-automation/16-19/prerequisite-profiles/receiver-faults/`.
Its default-composition probe and32 receiver tests/21 subtests distinguish the
missing production integration from already working receiver component behavior.

The earlier automated repairs remain useful and qualified: durable runner
creation acknowledgement, committed-session mailbox publication, source SBOM
integrity, offline core operations, and actual TLS collection/browser behavior.
They are not rolled back by this proposal.

## 2. Impact analysis

No PRD requirement, canonical ID or Tier0/Tier1 safety obligation is removed.
Affected obligations include FR-011/013, FR-017–021, FR-028, FR-030–043, FR-055,
and NFR-001/009/010/012. Raw plans remain operator-side; approvals remain explicit
verified human actions; unknown delivery retains locks and never causes blind resend.

There is a sequencing conflict:15.3 requires real accepted/unknown E2E,16.19
requires accepted earlier P0 stories, and19.2 currently owns verification
harnesses rather than new production services. Hiding implementation inside19.2
without changing ownership creates a dependency cycle.

Architecture sections25.3,25.7,25.8,25.10 and25.12 need an explicit implementation
owner and admission-authority boundary. Existing protocol versions and data
contracts should be preserved unless the approved design demonstrates a necessary
versioned change. Schema changes must be explicitly reviewed before allocation.

Epic17 remains independent in code, fixtures and runtime. Its observational
snapshots cannot become custody/material authority. Its separate qualification
and release-fragment obligations still gate the sharedv1.5.0 release; this
proposal neither implements nor waives them.

## 3. Recommended approach and alternatives

**Recommended: direct adjustment with explicit integration follow-up packets
under Story16.14, feeding15.3 before final19.2/19.4 qualification.** Preserve
completed bounded slice evidence and all canonical story IDs. Do not relabel old
fixture proofs as production admission.

An alternative is explicitly named prerequisite-remediation subpackets under19.2.
That requires changing16.19's entry/ownership rules to permit remediation before
all prior P0 acceptance, while retaining the all-P0 gate for final qualification
and publication. It must not be an implicit exception to the harness-only scope.

Rollback is not recommended: existing collection, advisory analysis and fail-closed
boundaries are useful and safe. Reducing the MVP to avoid these obligations would
require a separate product decision; it is not recommended here.

### Approved topology decision

1. **Selected — co-located qualified profile:** app, runner/custody authority and receiver
   participate on one operator-controlled host. A reviewed shared coordination
   primitive may serialize admission against all relevant lifecycle writers while
   keeping raw custody inaccessible to the app. Shared directories alone are not
   a lease protocol. Remote-host support remains unqualified.
2. **Deferred — separate-host qualified profile:** define an actual authenticated authority
   service and a fenced lease/serialization protocol through consumer commit,
   including uncertain commit, process death, expiry, reset and recovery. Current
   remote observations or content hashes cannot provide these guarantees.
3. **Rejected for v1.5.0 completion — keep the production path unavailable:** continue independent qualification
   preparation, but do not claim accepted/unknown production E2E or release readiness.

The selected implementation uses an owner-only co-located monotonic material ledger
bound to the existing recovery installation/generation, protected custody and one
shared `DecisionService`/`HandoffService` composition. Separate-host support remains
unqualified. Architecture/security review and fault qualification remain mandatory.

## 4. Detailed proposed edits — not yet applied

### Story16.14 integration ownership

OLD: the existing four packets implement bounded collector/provenance/custody
behavior; production material/witness composition has no concrete owner.

NEW: preserve those completed packets and add explicit follow-ups:

- **14.5 authority design:** inventory every receipt mutation/revocation/restore
  owner; select topology, generation/domain ownership, admission lease or
  serialization lifetime, failure/recovery and exhaustion behavior.
- **14.6 material and witness implementation:** derive exact bindings from retained
  source/manifest/report/attempt/policy/unit/target facts and the qualified operator
  authority. No client eligibility booleans, invented custody availability or
  inferred generation fallback. Default remains unavailable until qualified.
- **14.7 runtime composition:** wire the same qualified authority into API decisions
  and handoffs; implement real policy evaluation, durable human waiting/resume and
  handoff preparation/dispatch/reconciliation through existing services. No dummy
  success handler, arbitrary plugin, automatic approval or direct apply/destroy.
- **14.8 integrated prerequisite proof:** actual collected evidence through policy,
  authenticated shared review, durable receiver admission, lost acceptance reply,
  cancellation and same-operation reconciliation, with one effect and retained locks.

Rationale: production implementation receives a visible owner before its dependent
browser proof and release-wide qualification. Historical bounded completion is retained.

### Story16.15 Packet15.3 proof allocation

OLD: “real runner E2E with lease loss, log limits and accepted/unknown dispatch.”

NEW: retain that full obligation but track separate rows for actual collection,
lease/log/network fault proof; existing explicitly scoped API/component presentation
fault tests; and production accepted/unknown proof dependent on14.5–14.8.
No parent checkbox closes until its mandatory rows have appropriate evidence.

### Story16.19 qualification sequencing

OLD:19.2 verifier-owned harnesses/fixtures can appear to absorb missing production
integration; entry simultaneously requires all earlier P0 acceptance.

NEW:19.2 independently verifies the completed production composition;19.4 repeats
final-build browser journeys including accepted/unknown states. Preparatory
inventory work may continue, but no fixture success promotes a production gate.
The SBOM capability is implemented before release; actual signed/public artifact
verification remains a trusted-develop/release-event gate, avoiding a publish-before-
qualification cycle. Stable public writes still require separate authority.

### PRD, architecture, epics, UX and context

- PRD: retain all72 requirements and release exit; clarify implementation/proof
  ownership in sequencing and update affected story mappings after approval.
- Architecture: document the selected material-authority and lifecycle boundary,
  same-provider API/handoff composition, human-wait semantics and fail-closed startup.
- Epics/story contexts: synchronize14/15/19 allocation and applicable16.16 combined-
  material and16.18 restore/retention dependencies; do not renumber canonical stories.
- UX: preserve flows/designs; distinguish evidence tiers and truthful accepted/unknown
  states without asserting real external effects from fixture adapters.
- Project context and traceability: name the approved owner and prerequisite,
  preserve scope/domain/generation/lease guards, and retain all open release gates.

## 5. Implementation handoff and success criteria

Change classification: **architecture-sensitive integration; approved for bounded implementation**.
Architect/maintainer own topology and authority semantics; developer owns the
approved adapters/composition; security/verifier owns independent protocol and
fault review; UI verifier owns actual dependent journeys. No new dependency is
assumed or authorized by this proposal.

Expected write areas after approval: a narrowly scoped decision-material module,
operator-side witness/custody authority, application composition/configuration,
existing decision/engine/coordinator/handoff services, and focused regression and
real-profile harnesses. Avoid speculative production entities or general plugin APIs.

Required negative proofs include wrong scope/report/branch, stale or removed
material, changed policy/target/custody, wrong witness count/scope/domain, ABA,
reset, exhaustion, expiry during final reads, commit rollback, process death,
restart while awaiting human input, duplicate dispatch and consume-versus-revoke/
restore races. Positive proof requires one actual approved operation and one receiver effect
using a named, approved non-destructive qualification action (for example, one
fixed marker in an owned disposable workspace). Topology selection does not
authorize public GitHub dispatch, provider actions or infrastructure mutation.
Actual GitHub delivery needs its own declared target, credentials and action
authority; local transport evidence is labelled accordingly. Ambiguous outcomes
remain reconcilable without resend.

The earlier conditional5–9 engineering-day estimate assumed these ports already
existed and is not a reliable delivery estimate for the newly identified work.
Re-estimate after topology and mutation ownership are approved. Human/external
approval elapsed time and production-environment availability are separate.

## Checklist and approval state

- [x]1.1–1.3 Trigger, scope and concrete evidence recorded.
- [x]2.1–2.5 Epic/dependency impact and alternatives assessed; no new epic required.
- [x]3.1–3.4 PRD/architecture/UX/CI/operations impacts identified.
- [x]4.1–4.4 Direct adjustment recommended; rollback and silent scope reduction rejected.
- [x]5.1–5.5 Specific proposed edits, ownership and success criteria drafted.
- [x]6.1–6.2 Independent architecture and whole-artifact impact reviews completed.
- [x]6.3 Co-located topology selected under delegated maintainer authority.
- [x]6.4 Story ownership changes approved without requirement removal.
- [x]6.5 Production implementation handed to developer/security/verification lanes.

Approval record: **APPROVED FOR BOUNDED CO-LOCATED IMPLEMENTATION**. The separate
human-pilot waiver does not waive technical composition, review, signing/provenance
or publication obligations.
