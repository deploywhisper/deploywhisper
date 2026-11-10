# Packet 18.1: retained manifest identity and payload removal

This is the concrete design for the first bounded retention slice of Story
16.18. It is a design record, not implementation or qualification evidence.
Estimate: 4–6 implementation/review units for migration, service, reader changes,
regressions and independent review. Operational custody cleanup and the other
story packets remain separate acceptance obligations.

## Scope and invariants

Remove only the screened payload stored in
`infra_automation_artifact_manifests.artifacts_bytes`. Preserve its manifest row,
original digest, run/step/scope/requester identity, creation time, collection
provenance and foreign-key relationships. Linked reports, decision exports,
artifact snapshots and protected runner/receiver custody are not erased by this
operation. Do not describe this slice as whole-artifact or raw-custody erasure.

Use the reserved payload marker `b"[]"`. Admitted manifests contain at least one
artifact, so this marker cannot be an accepted artifact set. The existing
manifest length check permits the two-byte marker; no rebuild of the
foreign-key-referenced manifest table is necessary. The original digest continues
to identify the removed original payload; it is never recomputed over the marker.

## Tombstone and guarded transition

Migration 040, following the inspected head
`039_add_signed_trigger_intake`, adds an append-only tombstone table. Allocate
the exact revision name only after rechecking the head. A tombstone has a unique
manifest identity, run/project/workspace identity, original payload digest and
byte length, actor identity, UTC deletion time and bounded screened reason.
Retain a canonical digest/representation of the tombstone for audit and precise
payload quota accounting. Do not store the removed bytes or a raw filename list
in the tombstone or audit event.

Keep manifest delete/replace and identity/scope guards. Replace only the manifest
update guard with a condition permitting the one-way transition from the exact
original payload to `b"[]"` when its exact tombstone already exists. All other
columns must remain unchanged. Reject marker reversal, a second payload change,
digest changes, altered provenance, replacement identities and tombstone
update/delete/replace. The marker and tombstone must agree; either alone is a
corrupt/partial state that fails closed.

The authenticated service inserts the tombstone, changes the payload, adjusts
accounting and appends the audit event in one rollback-capable transaction.
An exception at any boundary restores the original payload and counter and
leaves no committed tombstone. Database and host administrators remain trusted;
application append-only guarantees do not make their SQL access tamper-proof.

## Service and eligibility

Expose a typed request for `purge_manifest(manifest_id, expected_run_version,
reason)` through the existing scoped admin mutation boundary. Reuse the existing
reserved `authorized_session`, live scope guards and reason screening. Do not
accept a caller-supplied authority stamp, deletion time, byte count or digest as
proof.

Reload the manifest and run inside that transaction. Validate their immutable
scope/snapshot binding and compare the expected run version. Use current
server time, reject rollback below retained clock floors, and require the current
retention duration and evidence lifetime to have elapsed.

This first slice protects all nonterminal runs. It also denies removal when the
run has a pending or approved decision or unresolved/unknown external work.
Keep held or broken locks and uncertain operations protected; an operator's
uncertainty acknowledgement does not authorize deletion or new execution.
Use current database state, not the caller's projection of status. The
conservative protection path satisfies the story's protect-or-invalidate choice
without altering approved receipts or weakening decision immutability.

Exact retries return the retained tombstone without a second deletion, quota
debit or audit event. Recheck current read/mutation scope before doing so. A
changed identity or conflicting expected operation must fail with the existing
bounded conflict envelope.

## Readers and evidence authority

Separate manifest metadata/history loading from live payload loading. Authorized
history/report-link readers retain the original manifest digest, scope and
provenance and expose an explicit retained-content removal status. They must
not call a payload validator merely to render retained metadata.

`manifest_files` and worker/evidence-material consumers reject a matching
tombstone/marker with a deliberate unavailable-content conflict, rather than
passing an empty artifact set or reporting generic digest corruption. Untagged
digest mismatches remain corruption and fail closed. Removed content cannot
qualify a decision, resume collection, recreate a report or grant handoff
authority. Never reconstruct the missing bytes from later mutable data.

## Reclaimed bytes and storage safety

Keep `claims._charge()` positive-only. Add a narrowly scoped repository adjustment
for this transaction: remove the exact previous payload byte length and add the
marker plus the exact retained canonical tombstone bytes and any documented
fixed bookkeeping charge. Never debit linked report/decision/custody copies that
remain stored. Verify integer bounds, safe-integer overflow, the immutable
snapshot byte floor, run CAS and clock floor before applying the adjustment.

For a net reduction, cleanup must remain possible while normal admission is
blocked by quota or disk reserve; do not run the new-work capacity reservation
check on a negative delta. If the retained tombstone is larger than the original
payload, handle the positive delta through existing capacity checks or retain
the payload; never falsely report reclaimed capacity. SQLite may reuse freed
pages without reducing the physical database file. Do not promise immediate
filesystem reclamation or run uncoordinated VACUUM as part of this operation.

## Startup and migration compatibility

`models.database._infra_automation_schema_complete` compares exact expected
trigger definitions for migration 033. It must understand the effective 040
manifest guard; otherwise a correctly migrated database fails startup. Likewise,
startup repair/reinstallation must not silently reinstall the original 033 guard
over the retention guard or accept 040 tables without their guards.

Validate 040's complete table/constraints/guards before recognizing its 033 guard
override. Before 040 is present, require the unchanged historical guard. Add 040
to known revisions and revision-completeness checks. Partial tables, missing or
altered guards and interrupted history must fail closed instead of being hidden
by `create_all`. Repeated initialization of a complete database must preserve the
same effective guards and tombstones.

## Regression-first proof

Write and run failing tests before implementing each boundary:

- Current admin succeeds; nonadmin, cross-project/workspace and invalid mutation
  credentials deny without changing bytes, counters or audit.
- Nonterminal, pending/approved decision, held/broken lock and unknown external
  operation cases preserve content and authority; terminal eligible content is
  removable only after retention and evidence floors.
- Concurrent CAS/deletion and decision/dispatch races serialize through the same
  reservation; stale requests cannot remove newly protected evidence.
- The original digest/scope/provenance and foreign-key links remain stable;
  tombstones cannot be edited, deleted, replaced or used to restore payload.
- History stays readable while payload/material access deliberately denies;
  untagged corruption still fails closed.
- Exact replay is idempotent; changed requests do not double-debit or append
  duplicate audit events.
- Inject failures after tombstone insertion, payload mutation, accounting and
  audit; every unsuccessful operation rolls back atomically.
- Cover quota saturation, low disk reserve, SQLite FULL, small-payload positive
  accounting, counter corruption/underflow and backward clocks.
- Upgrade a prior-head database, interrupt migration, remove/alter guards and
  repeat startup; only the complete effective schema is accepted.

Run the story-required root smoke, full local CI, affected API/CLI/infra and
automation shards, repo Ruff lint/format and configured security checks after
implementation. Record actual commands/results separately from this design.
UI validation is not applicable to this design-only document; any later rendered
retention status requires the composed-app browser proof before review.
