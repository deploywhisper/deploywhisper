# Story 16.18 restore design review input

Date: 2026-11-10. Status: proposed contract for independent review; no
implementation, live backup, restore or qualification is established here.
Scope: packet 18.2, plus its required startup and packet 18.3 recovery boundaries.

## Existing interfaces and gaps

- `app.py::lifespan` calls `models.database.init_db()` before starting topology
  maintenance and `_start_engine_coordinator()`. The recovery guard must run
  before initialization/migrations, not only before the coordinator.
- `init_db()` bootstraps brownfield revisions, runs Alembic and calls
  `Base.metadata.create_all`. Its schema detection checks exact migration trigger
  definitions. New restore schema/guards must be included in detection and known
  revision handling; do not weaken checks to accommodate a partial restore.
- `services.infra_automation_policy.advance_epoch(..., restore=True)` advances
  policy authorization and restore epochs and audits in its operation transaction.
  It does not quiesce writers, revoke browser sessions or coordinate storage.
- Identity sessions and one-use setup/recovery credentials are separate tables.
  A restored session row can restore possession authority unless invalidated.
- Runners retain hashed credentials, issuer versions, generations and epochs;
  tasks retain staged upload bytes. Coordinator and attempt leases have their own
  fences. Every domain needs explicit invalidation, not a single project flag.
- Existing handoff bindings, grants, carrier facts and target locks are retained
  history. `infra_automation/reconciliation.py` reconciles verified same-operation
  outcomes. `services.infra_automation_targets.break_lock` acknowledges uncertainty
  without authorizing a new action; reuse that contract.
- Custody is a separate owner-only filesystem root with exclusive publication.
  SQLite backup alone cannot capture it or its independently held keys/journals.

## Supported operational boundary

Implement an offline local CLI, with `backup`, `restore`, `status` and guarded
`recovery-complete` operations. Exact executable spelling is selected by the
implementation; this document does not advertise commands that do not exist.
No HTTP restore, general archive extraction, remote backup service or new
dependency is required. All inputs are explicit local paths. Backup output is
sensitive operator-local material, never a diagnostic attachment.

The deployment must install an owner-only control directory **outside all
restored roots**. It contains a stable installation identity, a monotonic
generation ledger, an operation journal and a fixed lifecycle lock inode. The
control root must not be copied over by backup restore. Enforce no-follow held
directory descriptors, owner/mode checks, bounded regular files, one link, and
fsynced exclusive publication/atomic replacement. Reject overlapping roots,
symlink roots/entries, device files and traversal. Require a qualified local
filesystem with supported locking and durability; do not infer NFS guarantees.

Host/DB administrators remain trusted. Someone who rolls back the ledger together
with the entire host can defeat a local rollback fence. Document this explicitly;
it is not solved by checksums or application append-only audit.

## Quiescence is an enforced lock protocol

Every supported app process holds a shared lifecycle lock from **before**
`init_db()` until the entire lifespan and workers stop. Direct mutating CLI,
collection controller, local receiver and custody publishers acquire the same
shared lock for the complete operation, including external-effect boundaries.
Independent processes managing another custody root must participate in its
declared lock domain too. Acquire multiple domain locks in canonical path order.
Never unlink/recreate a lock file while a holder may exist.

The offline CLI acquires all required locks exclusively and nonblocking. Failure
returns an actionable "stop the named writer services" result. A `quiesced=True`
argument or operator checkbox is not proof. While holding exclusive locks, verify
the configured installation/storage-root identity and stop/read-only status of
each declared participating writer domain. Lock ownership plus participation of
all writers is the support contract; a SQLite exclusive transaction alone cannot
prove filesystem or receiver quiescence. Refuse incomplete domain declarations.

An already running external action can continue after local writers stop. It is
not part of local quiescence and is retained as accepted/unknown work. Never
claim service shutdown stopped a deployment. Legacy versions lacking the lock
protocol must be fully stopped before the first migration; mixed-version writers
are unsupported. Real remote receiver/custody deployments without a participating
quiescence mechanism block their coordinated backup qualification.

## Backup transaction and manifest

1. Acquire exclusive domain locks and verify source root identities. Bound total
   file count/bytes and reserve disk space; reject output inside a source root.
2. Create a private sibling staging directory. Record an immutable backup ID,
   installation ID, source app/build and schema versions, current ledger
   generation, root roles, and creation time. Exclude the control ledger itself.
3. Under local writer quiescence use SQLite's backup API to produce the database
   copy. Do not copy a live DB file while ignoring its WAL. Check the resulting
   copy with integrity/foreign-key checks and record the actual migration head.
4. Copy declared artifact, custody and receiver-journal roots through held private
   descriptors without following links. Preserve required owner-only modes and
   exact bytes. Include manifest/tombstone and custody metadata needed to locate
   originals; independently supplied secret/key material follows its existing
   protected operator policy and never appears in the public manifest or logs.
5. Manifest entries contain relative role/path, bounded size, mode and digest;
   record an aggregate manifest digest. No raw artifact or secret is audit data.
   Hashes detect corruption, not malicious replacement by the trusted operator.
6. Fsync files and directories, then publish the complete backup by exclusive
   rename. A crash/ENOSPC before publication leaves an identifiable private
   incomplete backup; it is never accepted as a complete input. Release locks.

## Generation reservation prevents repeated-restore ABA

Incrementing epochs in the incoming backup alone is unsafe: restoring the same
backup twice can reproduce an earlier epoch and revive previously issued keys.
Use the outside-backup ledger as the installation's monotonic restore fence.

With exclusive locks held, compute a generation strictly greater than the ledger
high-water mark and all relevant version/generation values in both the current
installation database and the verified incoming database. Values must be strict
positive integers below the existing JavaScript-safe integer ceiling; overflow
denies restore. Reserve and fsync this generation in the ledger **before changing
any active root**. An interrupted attempt consumes its generation permanently.

The ledger has a bounded current state and durable journal of interrupted
operations, never automatic reset to generation one. It binds installation ID,
generation, operation ID, manifest digest and phase. A DB row binds the installed
database to that same installation ID and active generation. Missing/corrupt
ledger, mismatched DB generation, incomplete journal or missing configured root
denies normal startup; never recreate those values from the incoming snapshot.

Normal runtime epoch increments can exceed the last restore generation. The next
reservation therefore considers both DBs, not just `ledger + 1`. Credentials
remain checked against the exact current project epoch, account version and
runner generation; the global restore generation does not replace those checks.

Fresh-host recovery is a separate explicit offline initialization path. Reserve a
new installation identity and generation, bind it before any listener starts,
and invalidate all imported credentials. It must not silently adopt a copied
ledger or enable an imported machine manifest. Cross-host clone and loss of the
control ledger require dedicated qualification; ordinary startup never guesses.

## Restore publication and crash states

1. Lock all domains, verify the complete bounded backup and installation identity,
   inspect source/head compatibility and preflight free space. Preserve the
   current roots as protected rollback material. A v1.4.0 database is upgraded
   only in private staging using the supported Alembic path; unknown/newer or
   partially recognized schemas deny. Never migrate the only backup in place.
2. Reserve a new generation and fsync journal phase `restore_reserved`. This
   persistent phase blocks startup even if the first root replacement has not
   happened. Startup must not automatically finish or abandon this operation.
3. Prepare all roots privately. Apply migrations and the invalidation transaction
   described below to the staged DB. Record `staged_verified` with exact root
   identities and digests after successful validation/fsync.
4. Publish each root using journaled per-root operations while all exclusive locks
   remain held. There is no claim of atomic rename across multiple filesystems.
   Before/after each rename, journal and fsync enough identity to determine which
   old/new root is installed. Never resolve ambiguity by deleting either copy.
5. Check installed DB/root identities and integrity, then record a matching DB
   recovery row and journal phase `reconciliation_required`. Only this phase may
   start in recovery mode. Pending/mixed publication denies all normal startup.
6. Any rollback, including one restoring the pre-operation roots, also reserves a
   **new** generation and applies credential invalidation. Do not make an old
   snapshot usable by removing the marker or lowering the ledger.

Crash recovery is an explicit offline resume operation against the same immutable
backup/operation identities. It repeats verified idempotent stages, never reissues
grants or reruns external actions. Missing/mismatched material remains blocked.

## One invalidation transaction, retained history

In the staged database, after schema upgrade and before publication:

- Set each existing automation policy's restore epoch to the reserved generation;
  advance authorization epoch and CAS version strictly past their prior values.
  Default feature enablement remains off for recovery. Old immutable snapshots
  and decision bindings retain their original bytes and epochs.
- Revoke all imported human sessions and outstanding one-use setup/recovery
  credentials. Advance every imported account's authentication version above its
  previous value, using the new generation as a floor. Preserve account identity,
  memberships, password verifiers and audit history; fresh login/recovery creates
  fresh credentials through the existing identity path.
- Revoke runner credentials and unconsumed enrollments; advance runner generations
  above their previous values. Require explicit new enrollment/rotation after
  recovery. Clear staged task uploads using the existing cleanup rules. Imported
  task credentials cannot pass the new runner/epoch/lease fences.
- Fence coordinator ownership and local attempts through reviewed monotonic
  lease/version transitions. Do not rewrite immutable attempt or run identities.
  No worker claim resumes merely because an imported lease timestamp is future.
- Retain all grant identities and consumption history. Unconsumed grants become
  unusable through the new epochs and recovery guard; consumed grants remain
  consumed. Do not manufacture consumption receipts or replacement grants.
- Preserve external facts, receiver sequences/nonces, operation records, canonical
  target locks and uncertainty flags. Do not terminalize an external operation
  because its credential or local lease expired.
- Append a bounded restore audit/operation record binding the reserved generation,
  backup manifest digest, schema versions and named local recovery actor. Existing
  human session authentication must not be required for this offline operator
  operation, and its local actor must not impersonate a verified human session.

Exact table mutation statements and trigger-permitted transitions require
implementation review. Do not bypass guards by permanently disabling triggers,
rewriting immutable bindings or deleting audit history. A policy restore-epoch
call alone does not satisfy this transaction.

## Recovery-mode authority and outbound barrier

The recovery row and matching outside journal are a deny-only input at all new
effects: human/machine run admission, coordinator claim, runner task issuance,
collection, handoff preparation/dispatch, grant consume and receiver action
begin/resume. Check it within the same reserved operation transaction as the
effect, after material callbacks where relevant. Guarding only UI/startup is
insufficient; direct service and machine entrypoints must deny too.

Recovery mode permits fresh identity login/recovery, authorized historical reads,
receiver status/receipt ingestion, revocation and same-operation reconciliation.
Existing receiver credentials may authenticate retained operation status under
their separate audience; they cannot overcome epoch/barrier checks for a new
action. Imported machine request manifests have stale restore epochs and must be
reprovisioned explicitly after recovery. Never put their secret values in output.

`recovery-complete` requires a fresh verified scoped admin and a nonreflective
reason. Recheck every retained accepted/consumed/uncertain operation and sibling,
including those absent from a paginated UI. Require authenticated terminal proof
or an explicit existing audited lock-break acknowledgment for each unresolved
operation. A broken operation remains broken and cannot resume. An operator
acknowledgment never proves the remote action stopped; no automatic resend is
introduced. Resolve all affected domains before atomically recording completion
and switching the ledger to the matching ready generation. An interruption
between DB/ledger completion updates remains fail-closed and explicitly resumable.
Re-enablement and credential provisioning are separate audited operator actions.

## Required proof and unavailable qualification inputs

Deterministic tests must cover every journal boundary, ENOSPC/short writes,
no-follow/path/root substitution, active lock holders, digest/size/schema drift,
WAL backup integrity, migration interruption, v1.4.0 upgrade, repeated restoration
of one snapshot, rollback after later credentials were issued, ledger loss,
counter overflow, stale human/machine/runner/task/consume races and unknown-lock
preservation. Startup and direct-service tests must prove the recovery barrier.

Live coordinated qualification requires operator-declared protected artifact and
custody roots, control-ledger location on a qualified durable filesystem,
participating receiver/journal/key domains and stop/lock mechanisms, a disposable
version-authentic v1.4.0 DB copy, current pinned tool/profile identities, and a
fresh authorized recovery principal. These are not supplied merely by the story
or synthetic fixtures. The current offline ARM64/OpenTofu collection proof does
not qualify host power loss, remote receivers, cloud IAM or other filesystems.
Run crash/process tests separately from actual durable-storage fault exercises;
record exact commands, versions and boundaries. Missing live inputs block their
qualification, not independent guarded implementation or deterministic tests.
