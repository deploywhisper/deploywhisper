# Infra automation operator procedures — v1.5.0

These procedures describe the current singleton SQLite, workflow-v2 and
runner/receiver-v1 contracts. They are preparation for Story 16.18 acceptance;
publishing a runbook does not prove that an operator exercise passed. Reports
remain advisory with `should_block=False`. Use the version of these procedures
that accompanies the deployed source and migration head.

## Bootstrap and account recovery

Operate on the trusted application host as the database owner. Set `DATABASE_URL`
to the intended local database through the deployment configuration, and verify
the configured origin and identity profile before issuing evidence. Do not create
a second database to work around a login problem. The first global administrator
still needs explicit [project membership](permissions.md).

Create the private directory outside the checkout, owned by the operator and mode
0700. The paths below are placeholders; the commands create new owner-only
credential files and never overwrite an existing file:

```sh
umask 077
./.venv/bin/python -m cli.identity setup --output /private/operator/setup
./.venv/bin/python -m cli.identity bootstrap --username operator --credential-file /private/operator/setup
```

The password prompt disables terminal echo. For recovery, secure host/database
access first, then use the existing account name:

```sh
./.venv/bin/python -m cli.identity recovery-issue --username operator --output /private/operator/recovery
./.venv/bin/python -m cli.identity recover --credential-file /private/operator/recovery
```

Setup/recovery evidence expires after 300 seconds and is one-use. Recovery
invalidates that account's sessions; it does not approve a workflow or resolve
external work. Remove consumed private files under the operator's secret-retention
policy. Never put a password, bearer, `.env` file or custody bundle in a support
record. See [identity](identity.md) for password-file input, protected descriptor
checks, lost issuance replies, CSRF and trusted proxy setup.

## Change policy and stop new work

All paths in this section start `/api/v1/infra-automation`. Use a current human
session and mutation Origin/CSRF credentials. `GET /settings` with `project_id`
returns the current policy and version. `PATCH /settings` requires project-wide
`automation.admin`, `project_id`, `expected_version`, the complete typed `settings`
object and a screened reason. Retain all returned fields when making a change.
A maintainer may read settings but cannot save them; a workspace-only admin
cannot change project-wide policy.

Set `enabled` to `false` to deny new execution authority. A committed policy
change atomically advances the authorization epoch and appends audit. It does
not prove an already-started external action stopped. Existing authorized history
and same-operation reconciliation remain available. `POST /settings/revoke`
explicitly invalidates earlier authority using project ID, expected policy
version and reason. Neither operation issues replacement approval.

HTTP 409 means reread the current resource and review the change; do not blindly
retry a stale form. HTTP 422 means the typed bounds or lifetime relationship was
invalid. HTTP 429 means capacity is unavailable; retain the original request
identity and inspect current usage. HTTP 503 means authority/storage could not
be verified; do not bypass the check. A quota reduction below current active or
queued usage, workflow count or revision usage is rejected. Approval and
credential TTLs cannot exceed evidence TTL. Human session lifetimes are separate.

`GET /audit` exports scoped screened history with bounded pagination. Save only
necessary nonsecret IDs, digests, correlation IDs, times and outcome facts.
Append-only application APIs are not tamper-proof against a database or host
administrator. The exact payload and environment-default rules are in
[workflows](workflows.md).

## Project policy defaults

These defaults seed an unconfigured project; they do not overwrite persisted
policy or enable execution through environment changes.

| Field | Default |
| --- | ---: |
| `enabled` | false |
| `max_workflows` | 100 |
| `max_revisions_per_workflow` | 100 |
| `max_active_runs` | 10 |
| `max_queued_runs` | 100 |
| `max_artifact_bytes` | 8388608 |
| `retention_seconds` | 604800 |
| `evidence_ttl_seconds` | 3600 |
| `approval_ttl_seconds` | 900 |
| `credential_ttl_seconds` | 900 |

## Engine ceiling defaults

`DEPLOYWHISPER_ENGINE_` plus the uppercase field configures a server ceiling.
Only positive decimal values no greater than the contract maximum are admitted;
restart the coordinator after a changed server configuration. Project policy does
not override these ceilings. Bytes measure retained payload accounting, not the
entire SQLite filesystem footprint. Disk reserve is a separate admission check.

| Field | Default |
| --- | ---: |
| `global_queued_runs` | 1000 |
| `disk_reserve_bytes` | 67108864 |
| `workflow_active_runs` | 5 |
| `workflow_queued_runs` | 25 |
| `analysis_workers` | 2 |
| `project_bytes` | 67108864 |
| `global_bytes` | 268435456 |
| `attempt_log_bytes` | 1048576 |
| `log_chunk_utf8_bytes` | 16384 |

An unknown delivery retains its active slot and target lock. When capacity is
full, preserve safety cleanup and reconciliation; do not delete a run or its
evidence to make room. Never unlink engine worker-slot files while a supervisor
or worker may live. A dirty reservation requires trusted shutdown and confirmed
termination before local repair. See [engine recovery](engine.md).

## Incident and unknown-operation recovery

1. Disable new execution for the affected project and preserve immutable run,
   target, approval, grant and operation IDs. Record the original request identity
   before any retry. A lost reply may represent an accepted operation.
2. Inspect current run/step/log/report history under current reader permission.
   Distinguish evidence expiry, custody expiry and attempt lease expiry. None
   proves that remote work ended. An expired credential is not fresh authority.
3. Reconcile the original receiver operation using the authenticated
   [receiver protocol](receiver-online-v1.md). Carrier acceptance, receiver
   progress and a verified terminal outcome are separate facts. Never resend
   an uncertain delivery with a replacement grant or operation ID.
4. If evidence is missing or changed, collect and review new evidence before a
   new action. Do not extend the old plan's validity by increasing TTLs or
   reconstruct raw plan bytes from sanitized JSON.
5. An authorized admin may use `POST /targets/{target_id}/break-lock` only after
   investigating the original operation. Supply its actual scope,
   `expected_lock_id`, `expected_version`, screened `reason` and
   `acknowledge_uncertainty: true`. This audited action marks related handoffs
   broken and invalidates available grants. It acknowledges uncertainty; it
   does not certify termination, create approval or authorize another action.

Retain external observations and audit after a break. Follow
[registered target and handoff contracts](handoff-contract-v1.md) for the exact
lock, alias, grant and receipt bindings. Revoke affected accounts/memberships,
runner credentials or signing keys through their owning interfaces; do not erase
nonce history or lower clock floors to regain access.

## Backup, upgrade and restore boundary

`POST /settings/restore-epoch` is an existing project invalidation endpoint. It is
not a coordinated database restore command and does not itself revoke every human
session, stop writers or copy custody. A copied SQLite file alone is not a complete
backup. Restoring old database bytes can restore their sessions and credentials.

The implemented local command is `python -m cli.automation_operations`. It copies
one participating SQLite/artifact/custody domain under a protected control ledger;
it cannot lock an unrelated legacy CLI, remote receiver or unmanaged filesystem
writer. Stop and verify **all** such writers before backup, upgrade or restore.
An exclusive local flock is not proof of remote quiescence. Keep the raw custody
and receiver journal copies inside the same protected operator-local boundary.

### Bind the participating domain once

Upgrade the intended database to the current schema through the normal migration
path first, then stop the app and its background workers. Use canonical paths
with no symlink components. Prepare existing current-user-owned mode 0700
artifact/custody/journal directories, with regular single-link files mode 0400 or
0600. Keep the writable database mode 0600 and its parent directory mode 0700;
live database validation holds that private parent without opening a raw database
descriptor. The control directory must be new, with
an existing protected parent; it must be outside the database and every backed-up
or restored root. Roots must not overlap one another. Declare every additional
journal/key domain that belongs to this installation rather than assuming an
unlisted remote store was captured.

The paths below are illustrative; use the exact deployed database and domains:

```sh
./.venv/bin/python -m cli.automation_operations --control /private/deploywhisper/control initialize --database /private/deploywhisper/app.db --root artifacts=/private/deploywhisper/artifacts --root custody=/private/deploywhisper/custody --root receiver_journal=/private/deploywhisper/receiver-journal
```

`artifacts` and `custody` roles are mandatory. The role name `database` is
reserved for the coordinated SQLite copy and is rejected before any binding or
restore reservation. Initialization binds one installation ID and generation;
it does not authorize execution or bootstrap an account.

Initialization first publishes a private, durable `initializing` intent and its
permanent lifecycle lock, then binds the database. Normal startup and effects
remain blocked in this phase. If interrupted, inspect `status` and use `resume`,
or repeat `initialize` with the identical database and root arguments. Recovery
checks that exact intent, database device/inode, schema, generation and binding;
it never recreates a missing deployed ledger or replaces the lifecycle lock.
An interruption before control publication leaves no database binding, so a new
initialization attempt remains safe. An already `ready` result can be inspected
through `status` or the idempotent readiness check in `resume` after a lost reply.

Configure the app and participating service processes with:

```text
DEPLOYWHISPER_RECOVERY_CONTROL_PATH=/private/deploywhisper/control
```

The default is unset: an uninitialized legacy database is not automatically bound.
After binding, an omitted/mismatched control path or missing/rolled-back ledger
fails closed; removing the environment variable is not a recovery bypass.
Keep the outside ledger intact across every snapshot/restore and do not manually
edit its generation. Cross-host ledger recovery needs separately reviewed
handling. Set `DATABASE_URL` to the bound database in every participating process.

### Capture a coordinated backup

Stop the app first: its lifespan holds a shared participation lock, so offline
commands cannot acquire the exclusive lock while it serves requests. Stop
unmanaged writers and verify their termination independently. Select a new
private output path outside the control, database and captured roots:

```sh
./.venv/bin/python -m cli.automation_operations --control /private/deploywhisper/control status
./.venv/bin/python -m cli.automation_operations --control /private/deploywhisper/control backup --output /private/backups/new-coordinated-snapshot
```

Backup requires phase `ready`. It uses SQLite's backup API for a consistent copy,
checks integrity/foreign keys and effective schema/triggers, copies private roots
including empty directories/modes, records exact file digests and publishes the
snapshot directory atomically. Before publication it verifies the complete
candidate using the same limits as restore, including `manifest.json`, directory
entries, role-prefix depth, total bytes and the manifest's own metadata bound.
A candidate that cannot be restored is not published as a successful backup.
It does not assume that copying the main `.db`
without WAL/artifact/custody coordination is complete. Retain the returned
manifest digest, source/build versions and the operator's quiescence record.

### Restore and recover interruption

Keep writers stopped and the original outside control ledger in place:

```sh
./.venv/bin/python -m cli.automation_operations --control /private/deploywhisper/control restore --backup /private/backups/coordinated-snapshot
./.venv/bin/python -m cli.automation_operations --control /private/deploywhisper/control status
```

The snapshot must belong to this installation and have exactly the declared
roles, valid private files, digests and current schema. Restore compares current
external history before reserving a generation. If **any** current handoff,
grant, target-lock or external-fact row is absent or different in the backup,
or an external-possible run tuple differs, it conservatively refuses. It also
requires current retention tombstones, removal audit events and the matching
removed-payload identities. An older snapshot cannot resurrect purged content
or remove those receipts from active history. These checks precede generation
reservation and preserve the current stores on refusal. This also protects work
accepted after the snapshot: an older backup cannot erase it.
Obtain a sufficiently new consistent backup or separately reviewed manual
recovery. Do not erase the newer rows, fabricate a terminal receipt or silently
break/unlock a target to get an old backup accepted.

Accepted restore permanently reserves a generation above both current and
incoming versions in the outside ledger. It preserves resumable publication
fingerprints, invalidates imported sessions and one-use credentials, advances
policy epochs with execution disabled, revokes runners/enrollments, clears staged
uploads/coordinator ownership and invalidates unconsumed grants. Immutable
bindings, consumed receipts and target locks remain. Restoring the same snapshot
again cannot revive an earlier generation.

After interruption, inspect `status` and run the explicit resume command while
writers remain stopped:

```sh
./.venv/bin/python -m cli.automation_operations --control /private/deploywhisper/control resume
```

Never delete partial-publication markers or reset the generation manually. The
tool retains private old roots during publication; budget for that extra storage
and retain them until recovery is qualified. A refusal is not authorization to
copy a database over the guarded installation by hand.

### Reconcile before clearing the barrier

Successful restore enters `reconciliation_required`. Start the configured app
only in that recovery state to obtain fresh human authentication and inspect
history/reconcile accepted operations. Recovery-mode startup skips the engine
coordinator and topology/backtesting background schedulers; reads, login and
authorized reconciliation remain available. New effects stay denied. Imported
sessions and runner/task credentials cannot be reused.

Use a fresh global human administrator who also has project-wide
`automation.admin` in every configured policy project. Reconcile each original
operation to a verified terminal receipt or use the separately investigated,
audited uncertainty-break procedure above. A held lock, unresolved handoff or
orphan external-possible run prevents completion. No replacement grant/action
comes from completion.

#### Reconcile a completed receiver after credential invalidation

Restore changes receiver account generations as well as human/runner authority.
Installing another ordinary receiver secret cannot make the immutable old
snapshot match that new generation. Use the dedicated reconciliation credential
for the **original consumed operation**, with its original receipt and binding.
It never restores the old receiver credential or action grant.

While the installation is in `reconciliation_required`, the fresh global human
configuration administrator with operation-scope administration may issue a
short-lived credential through the eighth local operator command:

```sh
./.venv/bin/python -m cli.automation_operations --control /private/deploywhisper/control receiver-recovery-issue --operation ORIGINAL_OPERATION --token-file /private/operator/fresh-session --csrf-file /private/operator/fresh-csrf --reason-file /private/operator/receiver-recovery-reason --output /private/operator/new-receiver-recovery-token
```

Use the actual retained operation ID and protected fresh human/CSRF/reason files.
The output must be new: the writer reserves an owner-only, single-link mode 0600
file and refuses existing files/symlinks. Stdout reports only
`{"credential_written": true}`. There is no HTTP issuer or browser secret form.
The server retains a verifier, not recoverable plaintext. If issuance committed
but the reply/file was lost, explicitly issue again into a new private output;
this rotates the verifier and invalidates the prior token. Do not automatically
replay issuance or attempt to retrieve plaintext from storage.

The credential binds installation/generation, exact operation/source/binding/
consumed receipt, current enabled receiver account and the live human issuer's
generations/permissions. It expires within the current policy credential TTL;
rotation is bounded to 100 issues per operation per restore generation and
subject to storage/disk quotas. The server selects its mode:

| Server-selected mode | Permitted recovery |
| --- | --- |
| `status_terminal` | Read the original retained status/consumed receipt and submit a signed terminal `succeeded`/`failed` callback for that same unresolved consumed operation. |
| `status_only` | Read an already verified terminal operation, including its exact callback acknowledgement after a lost reply. It cannot submit a callback or upgrade to terminal-writing authority. |

Both modes deny bootstrap, grant consumption, action authorization, nonterminal
progress callbacks and the public unsigned terminal-resolution service method.
They cannot approve, replan, recollect, resend delivery, issue another grant or
execute an infrastructure action. An unconsumed grant, broken operation/lock,
wrong receiver/scope, changed original binding/receipt, revoked issuer or expired
credential denies. Observed expiry advances a retained credential clock floor;
moving the clock backward cannot revive it. Wrong token verifiers cannot move
that floor. Another restore or receiver/issuer-generation change invalidates use.

Transfer the private token only through the operator's protected local/receiver
credential mechanism, preserving owner-only custody. Never place it in argv,
URLs, settings, image/cache manifests, audit reasons or support logs. The
existing receiver's HTTPS adapter must use this credential for its status and
signed outcome requests; the unchanged wire audience does not enlarge its
authority. Actual protected transfer to a production receiver is a separate
qualification obligation.

For the supplied reference implementation, retain the **same** protected receiver
ledger, action mode, operation ID and binding digest. Configure its existing
operator-owned server adapter with the new bearer and use the complete bearer
text encoded as bytes for `ReferenceReceiver`'s `callback_secret`; do not decode
the token's hexadecimal suffix as a new signing key. Invoke only:

```python
receiver.recover_completed(original_operation_id, original_binding_digest)
```

Here `receiver` is the existing `ReferenceReceiver` composed by the operator with
that ledger/server adapter and credential. This method requires an exact local
`complete` record, original consume/payload/receipt/binding, retained terminal
callback and matching original completed marker or saved-plan digest receipt.
An `intent`, `received`, `action_started`, `reconcile` or missing local row stays
unresolved. Do not call `run()` or blanket `flush_callbacks()` with this recovery
credential: they can revisit operations outside its privilege ceiling.

The helper first checks authenticated status. An exact retained original or
previously persisted recovery callback acknowledgement resolves a lost reply
without another callback. Only an eligible unresolved server operation permits
re-signing the unchanged original terminal event; the helper preserves its
source/message/nonce/sequence and durably writes a bounded recovery-outbox
candidate before sending. A terminal status with missing/conflicting exact
acknowledgement remains unresolved. Lost replies and token rotation never justify
a new event identity or action. Repeated recovery leaves the action count
unchanged. The outbox is bounded to 100 candidates; a full outbox still permits
recognizing an existing exact acknowledgement.

See the independently reviewed [receiver recovery design](../verification/infra-automation/16-18/receiver-recovery-design.md),
[actual restored-service results](../verification/infra-automation/16-18/receiver-recovery-results.md)
and [reference-receiver restart/CLI results](../verification/infra-automation/16-18/receiver-runtime-recovery-results.md).
Those tests exercise actual migrations/services, a coordinated restore and
in-process HTTPS routes with synthetic effect material. They do not prove live
TLS, production secret transfer, a real infrastructure outcome, an independent
human pilot or host-power-loss durability. The original live-profile gates
remain open.

Obtain a fresh session and CSRF value through the existing identity channel, keep
each in its own current-user-owned mode 0400/0600 private single-link file, and
prepare a screened nonempty reason in another private file. The credential files
contain only the corresponding value, never JSON or a literal embedded in shell
history. Stop the recovery app after login so the local completion command can
acquire the exclusive participation lock; complete before that session expires:

```sh
./.venv/bin/python -m cli.automation_operations --control /private/deploywhisper/control recovery-complete --token-file /private/operator/fresh-session --csrf-file /private/operator/fresh-csrf --reason-file /private/operator/recovery-reason
```

Use the same database, identity profile and trusted origin configuration as the
recovery app. If credentials expire while the ledger is `completing`, follow the
completion-resume procedure below first. Once `reconciliation_required` is
restored, restart the app in recovery mode and obtain fresh credentials rather
than editing persisted sessions. Completion audits the actual
verified human and reason. After phase `ready`, explicitly restart the app before
background workers run again; a running recovery-mode app does not start them
automatically. Review policies and deliberately re-enable execution/re-enroll
rotated identities as required; completion itself does not enable policy.

#### Resume an interrupted completion

If completion was interrupted with the outside ledger in `completing`, keep the
app and participating writers stopped. Inspect `status`, then run the same
offline owner command:

```sh
./.venv/bin/python -m cli.automation_operations --control /private/deploywhisper/control resume
```

This acquires the exclusive participation lock and checks the current database's
schema, integrity, installation, generation, manifest digest and original
`restored` event before changing the outside ledger. It handles only these
consistent outcomes:

| Retained database proof | Result of `resume` |
| --- | --- |
| Still `reconciliation_required`, with no completed event | Return the ledger to `reconciliation_required`. Start the recovery app, obtain a fresh login, reconcile as required and explicitly run verified `recovery-complete` again. |
| Already `ready`, with exactly the deterministic completed event matching this operation/generation/backup digest and a human actor | Publish ledger `ready` for the completion transaction that already committed. Restart the app explicitly before its background workers run. |

Missing or contradictory proof denies recovery. This branch creates no database
business writes, credentials, epochs, approval or policy enablement. It does not
make an expired session valid; it either restores the opportunity for fresh
authentication or acknowledges the already verified durable completion.

Completion resume relies on current retained database proof, not the old backup
file or its database fingerprint: legitimate login/reconciliation writes may
have changed the restored database. This does not relax the separate snapshot
and publication checks for `restore_reserved`/`publishing`. Never reset phase,
generation or completion events manually to bypass a refusal.

### Test the v1.4.0 upgrade on an immutable copy

Stop and privately copy the released v1.4.0 database, whose actual Alembic head is
`028_add_narrative_guidance_payload`. Protect the source copy with mode 0400 and
use a new output path. The command upgrades that copy, never the source/live DB:

```sh
./.venv/bin/python -m cli.automation_operations --control /private/deploywhisper/control upgrade-copy --source /private/upgrade/v140-readonly.db --output /private/upgrade/new-current.db
```

The [released-source exercise](../verification/infra-automation/16-18/upgrade-results.json)
used `v1.4.0@935f3bb` and a synthetic report: source unchanged, 37 report columns
preserved exactly, destination schema 042, integrity `ok` and no foreign-key
violations. This is a real released-schema migration exercise, not a live
installation or power-loss qualification. A destructive downgrade is not a safe
rollback for immutable audit and operation history. Preserve the coordinated
snapshot and separately investigated recovery plan instead.

Ordinary failed `upgrade-copy` attempts remove only their positively owned,
unpublished staging database and private SQLite sidecars. Existing outputs,
foreign replacement inodes and an ambiguously published output are preserved.
SIGKILL or power loss cannot execute process cleanup and can leave private
`.upgrade-*` files for operator inspection; no automatic startup scavenger is
claimed. Never delete the source or a possibly published result to retry.

The [restore implementation/results](../verification/infra-automation/16-18/restore-results.md)
and [handoff source hashes](../verification/infra-automation/16-18/restore-source-hashes.json)
record the deterministic migration/interruption/replay tests and exact scope.
Shared integration edits require refreshed evidence; a handoff hash file alone
does not attest to a later build. Live custody/receiver restore and rotation,
unmanaged-writer coordination, restricted-network recovery, the self-service
operator pilot and host-power-loss durability remain separate explicit gates.

## Retention boundary

Retention is not authorization. Pending/current decisions and accepted/unknown
external work need their supporting evidence protected. A terminal run alone is
not proof that every related remote operation is resolved. Deletion must preserve
immutable scope/digests, manifest identity, audit and a tombstone, and atomically
protect or invalidate authority before removing content. Cleanup must not unlock
unknown work or make old grants usable.

The current cleanup API is `POST /manifests/{manifest_id}/purge`, using a scoped
admin human session with Origin and CSRF mutation credentials. Obtain the exact
manifest ID from the authorized run's report/evidence history and read the run's
current `version`. Review the target scope and retention age before submitting.
The path carries the manifest ID; the body has only `expected_run_version` and a
screened reason. For example, replace the illustrative version with the actual
read version:

```json
{
  "expected_run_version": 1,
  "reason": "Remove expired screened manifest content after retention review"
}
```

The operation requires a terminal run and expired retention/evidence lifetime.
It conservatively protects every pending/approved decision, any external handoff
and every unresolved lock, including held/broken locks. It removes only the
screened manifest payload when doing so frees accounted storage after receipt
costs. The same transaction preserves manifest identity/digest and relational
links, appends the immutable deletion tombstone and audit, and adjusts run
version/accounting. Missing content deliberately denies further evidence use;
historical metadata remains readable. An identical request by the same actor
recovers its original receipt; a changed request conflicts.

HTTP 409 may indicate stale version, protected work, unexpired content or a
payload too small to reclaim space after retaining the receipt. Reread and
investigate; do not change the version or reason automatically to bypass a
protection. A successful receipt reports `content_status: "removed"` with the
original digest/size and deletion attribution. It grants no fresh authority.
There is no deletion CLI in this slice.

Removal of screened manifest content does not erase linked report exports,
artifact snapshots, decision material or raw-local custody. Never run an ad hoc
SQL DELETE, truncate payloads or drop immutability triggers as an operator
retention procedure. Track custody and staged-upload expiry separately; preserve
bundles backing pending approved work.

## Observations and acceptance record

Use the scoped run/step/log APIs, runner health pages and approval/delivery facts
as the current observability sources. Pages are bounded and may omit later
arrivals from a traversal; follow all cursor pages and preserve explicit gaps.
Do not advertise these reads as a new metrics-export endpoint. An inaccessible
scope is not zero usage. Record counts by state, queue age, step failures,
runner stale/offline counts, approvals by outcome, delivery-unknown counts,
quota/disk failures, durations and CPU/RSS/disk high-water marks without raw
artifacts, user inputs or credentials. Hash any retained evidence logs locally.

The Story 16.18 self-service pilot and real 30-minute saturation exercise are
not run by this documentation packet. Acceptance still needs 10 active runs,
at most 2 concurrent analysis jobs and 20 online runners for that interval, with
resource samples, errors, queue/storage bounds, restart/cleanup observations and
no corrupted transitions. The earlier 16.5 run used synthetic online slot ports;
it does not qualify 20 real runners. A unit test or short diagnostic cannot be
reported as this exercise. Record hardware, OS/architecture, source/build/tool
versions, exact commands, scope, sample interval, start/end times and known misses.

## Contributions to earlier operations stories

| Story | Contribution from these automation procedures | Original acceptance still open |
| --- | --- | --- |
| [12.7](../../_bmad-output/implementation-artifacts/12-7-backup-restore-upgrade-and-retention-docs.md) | Automation epochs, protected evidence, unknown-operation recovery and coordinated snapshot obligations. | Tested complete backup/restore, upgrade/rollback, logs and maintenance procedures across the original supported SQLite and PostgreSQL paths. Epic 16's singleton SQLite scope does not implement PostgreSQL or close this story. |
| [12.8](../../_bmad-output/implementation-artifacts/12-8-air-gapped-and-restricted-network-guide.md) | [Offline collection, network boundaries and credential rotation](network.md). | Full air-gapped installation and deterministic core-analysis exercise, dependencies, optional providers/registries/connectors/updates and verification. Offline collector proof does not close core-install acceptance. |

No original story checkbox, production support claim or release gate is closed by
this contribution matrix. See [collection limits](collection.md) and record
actual proof in the Story 16.18 verification directory before changing status.
