# Story 16.9 backend-for-UI prerequisite proposal

Status: approved for implementation by the maintainer on 2026-10-29; implementation and verification in progress.
Date: 2026-10-29. Baseline: `develop` at `5693c09` (merged Story 16.8 / PR203).

## Problem and boundary

Story 16.9's approved UI needs current human-decision eligibility and a complete
immutable review packet. Delivered approval views intentionally expose historical
receipt facts only. Rendering their conservative `eligible=false` as a current
decision check would disable valid actions; treating successful reads as approval
permission would invent authority. The existing mutation schema also rejects any
typed-confirmation field and does not enforce high/critical confirmation.

AGENTS.md requires API/flow/validation questions to be raised before changing the
React contract, and backend-for-UI behavior to ship in its own labeled PR. This
proposal is the reviewable prerequisite for that decision. It does not change
frozen workflow/receiver protocols, canonical reports, or product scope.

## Approved bounded contract

1. Add a scoped approval-by-ID read under the existing `/approvals` resource.
   It returns the exact retained generation/version, binding digest, historical
   receipt and a typed immutable report/action summary. Keep existing list serialization and ordinary
   non-high/critical decision semantics compatible; the high/critical validation
   change is an explicit Story16.9 requirement. This read is the deterministic recovery path
   after a lost response or conflict; the client must read it before resubmitting.
2. Derive recommendation/severity, typed insufficient context, confidence,
   blast-radius and rollback context from the verified retained `report_bytes`.
   Include report schema/digest and permanent report URL; never regenerate the
   approved export identity from live report decorations. Bound/screen the
   projection and exclude raw artifacts, grants, credentials and filesystem paths.
3. Use an equivalent typed action/payload summary constructed from the bound
   authorization kind, canonical target, receiver/pipeline identity and revision,
   source commit, environment, unit and payload digests. Do not invent a payload
   body or target registration. Scoped seeded material remains the positive proof
   port; production registry/collection/dispatch/receiver stay later owners.
4. Provide a separate descriptive current decision context on the read: evaluated
   server UTC time, pending-status/current-generation check, reviewer capability,
   shared requester exclusion, server-selected acknowledgement/independent model,
   live evidence/policy/target/custody eligibility, typed limitations/TODOs and
   effective minimum of run, evidence, approval, source and custody deadlines.
   It is not a credential. Reuse the existing same-transaction checks, without
   calling the audit-writing mutation helper from a read. Historical packet and
   receipt reads must survive feature-off or unavailable current material; mark
   decision context unavailable and disable submission in that case. Corrupt or
   inaccessible packet data still uses the existing generic error boundary.
5. Add one bounded optional confirmation string to the decision request. The
   server derives whether it is required from the immutable high/critical severity
   and rechecks it during submission. Proposed exact phrases are `APPROVE <target>`
   for shared approval, `ACKNOWLEDGE <target>` for single-operator approval and
   `REJECT <target>` for rejection, where `<target>` is the bound canonical target.
   Return required phrases descriptively before controls render. No client field
   may select acknowledgement mode. All submissions keep explicit outcome and
   nonblank screened reason. Canonical no-go remains advisory and is interpreted by the existing workflow
   policy; it is not an invented hard block. Typed insufficient context and other
   actual hard eligibility failures remain non-overridable; confirmation and
   reason cannot create a bypass.
6. Preserve CAS and current authority revalidation at mutation time, refreshing
   time after material resolution. Preserve retryable 503 state and the run clock
   floors from 16.8. Unknown fields/vocabulary fail closed. A stale read cannot
   authorize a later submission.
7. Reuse the append-only automation audit storage/export. Preserve the existing
   admin-only project-wide audit export rather than silently granting it to all
   reviewers. Expose authorized historical receipt attribution from its retained
   decision event, including actual principal/type/role/scope/reason/time.
   Define decision-event before/after digests over a versioned screened decision
   state projection (ID, generation/version/status, binding identity and receipt
   attribution), distinct from report/binding byte identity. Do not rewrite old
   events or infer historical roles from current memberships. Return descriptive
   audit-export availability so the UI can render only permitted export actions.

These resource behaviors and confirmation semantics were approved by the maintainer
on 2026-10-29, with explicit direction to deliver this prerequisite first and then
continue Story16.9. Exact typed field names are frozen by the separate reviewed
backend implementation. Existing audit permissions remain unchanged.

## Required proof and handoff

- Real human session/Origin/CSRF and exact scope tests; malicious role/actor fields,
  nonhuman credentials, shared self-approval and unknown confirmation fields deny.
- Pending shared versus single-operator labels match actual server authority;
  high/critical missing/wrong confirmation denies for approve/reject, while a
  correct phrase never overrides stale/missing/insufficient mandatory evidence.
- Immutable summary hashes and canonical `should_block=False` remain unchanged;
  target/action summaries are tied to the retained binding, not UI fixtures.
- Run/receipt clock floors, earliest deadline equality, role/tuple/policy changes,
  unavailable ports, feature-off reads and deterministic receipt recovery pass.
- Concurrent/lost-response submissions cannot mint a second decision. Reads do
  not append false approval audit events. Both decision-state digests and immutable
  historical attribution are covered; admin-only export and screened content hold.
- Search all constructor consumers; run focused tests, exact affected shard,
  root smoke, lint/repo-wide format, typing/security and every-directory local CI.
- Ship in a dedicated `backend-for-ui` PR, independently review it and integrate
  the accepted contract before the single Story16.9 UI branch.
- Then implement the four existing UI packets using the approved v3 primitives,
  followed by Compose-built actual API-seeded keyboard/axe/lost-response tests and
  1440/760 screenshots. No Vite-only or mocked-UI proof replaces that acceptance.

UI implementation and browser acceptance remain entirely outstanding.

## Implementation record

The approved backend is implemented on its dedicated prerequisite branch. New
closed contracts are in `infra_automation/review_contracts.py`; historical/current
packet reads are in `services/infra_automation_review.py`; confirmation and state
audit mutations reuse `services/infra_automation_decisions.py`. The project
service shares a read-safe authority check while preserving mutation credentials
and audit behavior. GET requires selected project scope, with optional workspace
scope. Read context evaluation time is nullable only when current clock authority
is unavailable; historical evidence remains readable without inventing a time.

The frozen behavior and exact phrases are documented in
`docs/infra-automation/approval-review.md`. Current verification/review/delivery
is recorded in `docs/verification/infra-automation/16-9-backend-for-ui/results.md`.
Full UI implementation and browser acceptance remain outstanding until this
separately labeled backend support is integrated.
