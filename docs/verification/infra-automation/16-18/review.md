# Story 16.18 implementation review

Independent native reviews inspected retention, API replay and offline restore
boundaries during development. Findings below describe defects actually observed
in the initial implementation; they are not claims about an already released
version. Final broad validation is recorded separately.

| Finding | Evidence and correction |
| --- | --- |
| High: operation history after a backup could disappear during restore | Current versions alone were used for the restore floor. Restore now compares the complete current handoff/grant/lock/external-fact history against the incoming snapshot before reserving a generation. Missing or differing records deny; no automatic history merging or uncertainty acknowledgement is fabricated. This deliberately limits which older snapshots can be restored. |
| High: context wrapper translated business errors into 503 | `LifecycleError` inherits `ValueError`; catching it around a yielded operation changed ordinary conflicts, validation and quota responses. Translation is restricted to recovery failures, preserving business exceptions. |
| High: real migrated database rejected quota reclamation | The composed post-purge journey returned 503: migration 032 still forbade decreasing `retained_bytes`. Earlier fixture tests installed manifest guards but omitted that run guard. Migration 040 now retains the complete run immutability predicate while permitting an exact, single-use tombstone-bound debit; a new API regression runs against the complete Alembic head. The first capacity measurement was interrupted and retained as unqualified evidence. |
| Medium: exact accepted preflight replay failed after purge | The old reader demanded removed payload bytes. Exact original digest/size now identifies the retained admission without restoring bytes, charging storage or adding audit events. Changed content still conflicts. |
| Medium: nominal schema checks accepted missing guards | A real Alembic database with its attempt immutability trigger removed still backed up. Backup/restore now use the strict effective startup schema validators, including retention and recovery guards. The independent reproduction now denies without advancing generation. |
| Medium: unconditional POSIX locking import broke disabled profiles | Recovery locking is optional at import; unsupported platforms deny configured recovery while ordinary advisory imports remain available. |
| Failed writes leaked private staging files | Write/fsync/publication cleanup now spans the whole operation. A forced failed write leaves no owned pending file. |
| Empty directories disappeared | Directory identities and modes are now explicit bounded manifest entries and participate in copy and publication fingerprints. |
| Retention bookkeeping could undercount multibyte reasons | Accounting now includes canonical receipt, duplicated scalar and audit representations plus fixed bookkeeping. Positive-growth removals retain the original content. |
| Identity writers did not participate in lifecycle locking | Identity service transactions and the local identity CLI now acquire participation before writes/schema initialization. A regression first demonstrated the missing boundary. |
| High: raw database descriptor validation broke SQLite process locks | A real app/CLI rehearsal observed revoked credentials still authenticating through stale pooled WAL handles. Opening and closing a raw database descriptor released the process's SQLite locks. Validation now holds a protected parent directory, checks private inode metadata and uses only SQLite-managed database opens. Independent OS-lock tests show a competing writer stays blocked; the former raw-close sequence reproduced the loss. Real HTTP revocation now returns 401 and WAL descriptors remain live. |
| Required contract: restored receivers could not reconcile their old operations | Ordinary receiver authentication correctly rejected the generation captured before restore, even after secret rotation. A separately reviewed private issuer now binds current-generation credentials to one consumed historical operation, with status-only or signed-terminal limits. Public unsigned resolution and every bootstrap/consume/action path still deny these credentials. Completed local receivers recover exact acknowledgements without repeating actions. |
| High: expired reconciliation credentials could revive after clock rollback | An expired request rolled back its clock floor, allowing a later earlier-clock request. Registered deny-only observations now retain the verified token's highest observed time under the same outer reservation after business rollback. Independent expiry/rollback reproductions now deny. Wrong verifiers do not write clock observations. |
| High: completion interruption could strand expired human sessions | A crash left the ledger `completing` while the database was either read-only recovery or already committed ready. Offline resume now validates exact restore/completion proof and changes only the ledger phase. Two real interruption cases, missing proof, and ten independently corrupted-proof cases verify denial or recovery without database changes, credentials or policy enablement. |
| Fixture timing: future collected time raced real custody publication | The shared decision fixture deliberately advances its clock to the next second. The new receiver integration test now uses that same injected clock only during custody publication, matching existing receiver fixtures. Production deadlines and publication guards are unchanged; four fresh full-chain repetitions passed. |

The independent restore reviewer reran 16 actual-Alembic tests successfully and
reproduced missing-guard denial, pending-file cleanup and empty-directory copying.
Reviewed module snapshot before the final portability correction:
`sha256:3606b4813e8331c8be34f4de91cbae9e263f03d92597bd3066673b0147eafb61`.
This hash identifies that review snapshot, not the final source.

The raw-descriptor constraint is documented by
[SQLite's locking guidance](https://www.sqlite.org/howtocorrupt.html).
Directory-descriptor validation avoids closing a descriptor for the live database
inode while SQLite owns connections to it. Final operator proof is recorded
separately from this review narrative.

Retained limits: participating local writers and the declared local filesystem
only. Unmanaged remote custody/receiver writers must be stopped and are not
qualified by these locks. Append-only application records do not constrain a
host/database administrator. A backup failing the external-history comparison
requires explicit operator recovery; the tool does not silently discard newer
uncertainty to make an old snapshot usable.
