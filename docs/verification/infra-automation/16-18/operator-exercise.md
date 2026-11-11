# Local operator runbook exercise — Story 16.18

Executed 2026-11-10 against the packaged Python 3.11 application using immutable
image `sha256:363f797bb98e1ca90f549892b28802d6589000e776505a6f21cefdc7e61c41df`.
The exact versions, source hashes, commands, status checks and cleanup receipts
are in [operator-exercise.json](operator-exercise.json). All **209 packaged
runtime/source files** independently matched the frozen root. The 210th
source-manifest entry is the generated TypeScript contract used by the static
frontend build; its source hash also matched the root and browser build manifest.
The same immutable image is used by the separately recorded final UI proof.

This was an agent executing the published [operator runbook](../../../infra-automation/operations.md)
against disposable local resources. It is not independent human adoption or live
production custody/receiver qualification. No source changes were made during
the final exercise.

## Isolation and actual procedure

Four new named Docker volumes separated application data, outside control ledger,
backups and private operator credential files. All directories were mode 0700;
database/files were private and owned by the runtime app user. Offline CLI
containers used `--network none`. The web app published only
`127.0.0.1:18080:8080`, using `local-development` identity with the exact origin
`http://127.0.0.1:18080`. Port 8080 and the user's original application/stores were
not used. All passwords, setup/recovery evidence, sessions and CSRF values were
generated for this exercise, passed through private files/stdin, and omitted
from the evidence.

The actual command sequence used the packaged CLI:

```text
python -m cli.automation_operations --control /control/ledger initialize --database /domain/app.db --root artifacts=/domain/artifacts --root custody=/domain/custody
python -m cli.identity setup --output /operator/setup
python -m cli.identity bootstrap --username operator-exercise --credential-file /operator/setup --password-file /operator/password
python -m cli.identity recovery-issue --username operator-exercise --output /operator/account-recovery
python -m cli.identity recover --credential-file /operator/account-recovery --password-file /operator/rotated-password
python -m cli.automation_operations --control /control/ledger backup --output /backups/snapshot
python -m cli.automation_operations --control /control/ledger restore --backup /backups/snapshot
python -m cli.automation_operations --control /control/ledger recovery-complete --token-file /operator/session --csrf-file /operator/csrf --reason-file /operator/reason
python -m cli.automation_operations --control /control/ledger restore --backup /backups/snapshot
```

Initialization followed real migrations to head 042. The app then served actual
HTTP login, explicit project membership bootstrap and a complete typed settings
save with execution disabled. Global administrator status alone correctly
returned an empty project list before membership; the bootstrap used the actual
default project ID/key from that disposable database. Account recovery rotated
the synthetic password through the one-use CLI procedure.

Before backup, the app's shared lifecycle lock caused the offline backup command
to exit 1. After stopping the app, the coordinated backup succeeded and published
five manifest entries. The app was restarted for fresh login and then stopped
for restore. The outside control volume remained intact throughout.

## Observed results

| Check | Actual outcome |
| --- | --- |
| CLI account recovery while the participating app served requests | Account authentication version 2 → 3; old sessions revoked; the old HTTP session returned 401 and the rotated password logged in successfully. |
| App's live SQLite WAL identity after recovery | Open WAL/SHM descriptors still referred to live files, without deleted-file aliases. |
| Backup while the app held its shared lifecycle lock | Refused with CLI exit 1. |
| Offline coordinated backup | Succeeded; manifest digest retained in JSON. |
| First restore | New generation 4, phase `reconciliation_required`. |
| Pre-restore session | `/api/v1/auth/session` returned 401. |
| Fresh authentication in recovery mode | Login succeeded; authorized run-history and audit reads returned 200. |
| Retained history | One actual settings audit event survived with the identical digest. Run history was empty. |
| Attempt to re-enable policy before completion | Actual settings PATCH returned 503. |
| Offline completion with the fresh session/CSRF and current full admin authority | Succeeded, phase `ready`; it did not enable policy. |
| Ready restart | Policy remained disabled; the fresh post-restore session remained valid. |
| Restoring the identical snapshot again with the same outside ledger | Reserved generation 5, strictly greater than 4. |
| Prior ready session after the second restore | Returned 401; a new login succeeded. |
| Final storage checks | Schema 042, integrity `ok`, zero foreign-key violations, exact synthetic custody content digest. |

Every created app container and all four named volumes were removed. A final
Docker listing found no `dw1618-operator-` containers or volumes. Private
credential files existed only in those removed volumes. The final exercise
finished with outcome `passed`. The database had zero receiver-recovery sidecars;
this normal operator flow makes no claim of transferring or using a newly issued
receiver credential. The actual restored-operation HTTPS integration belongs to
the separate receiver recovery proof.

## Defect discovered and corrected before final proof

An earlier image exposed a real concurrency failure: after CLI account recovery,
SQL showed authentication version 3 and revoked sessions while some existing web
connections still authenticated version 2. Process descriptors showed deleted
WAL/SHM files. The recovery guard's metadata validation opened and closed a raw
descriptor for the live database. Such a close can clear other SQLite
connections' process-wide POSIX advisory locks, as described by
[SQLite's corruption guide §2.2](https://www.sqlite.org/howtocorrupt.html#_posix_advisory_locks_canceled_by_a_separate_thread_doing_close_).

An independent kernel byte-range probe confirmed that the old helper changed an
existing WAL connection's lock from held to released. The corrected helper holds
the protected parent directory, checks file metadata with `lstat`, and opens the
existing database using SQLite's `mode=rw` connection. SQLite exclusively owns
the database descriptors. It brackets device/inode/type/owner/mode/link identity
without rejecting legitimate concurrent changes to database size or mtime.

The corrective source adds a real cross-process WAL-lock and credential-revocation
regression, plus symlink/public-file/missing-file checks. At that corrective
stage, the scoped operator suite passed **24 tests**; Ruff lint, repository-wide
formatting (602 files) and scoped Bandit passed. Final head-042 image 363f797
repeated the full CLI/API procedure above successfully. Earlier failed
orchestration assumptions and the defective-image negative control are not
counted as successful qualification. Current-head broad validation is recorded
separately by the integration owner.

## Interrupted completion journal supplements

The final image also executed the actual credential-free CLI `resume` command
against two protected fault states in the same disposable domain. These
supplements are separate from the 28 normal CLI/API checks above. Marker and
expiry manipulation below was **test-only fault injection**, not an operator
procedure or a recommendation to edit a deployed control ledger.

| Retained database state and injected outside marker | Actual CLI result |
| --- | --- |
| Generation 4, database `reconciliation_required`, genuine original restored event, no completed event; injected ledger `completing` | `resume` without human credential arguments returned `reconciliation_required`; a fresh human completion was still required. |
| Generation 5 after a genuine fresh-admin `recovery-complete` committed its completed event; injected ledger `completing` and expired every human session | `resume` without human credential arguments returned `ready`, finishing the already authorized commit. |

For each actual resume invocation, SQLite `iterdump` content digests matched
exactly before and after. Restore-event, session, grant and receiver-recovery
credential counts were unchanged. No database mutation, new session, grant,
approval or policy enablement came from resume. It only repaired the outside
journal using retained installation/generation/manifest/event proof. The common
content digests and counts are retained in the JSON supplement records.

This verifies recovery after session expiry without recreating credentials or
lowering a generation. It does not simulate host power loss or qualify physical
storage durability. The final database retained generation 5 in `ready` state,
execution remained disabled, and all disposable resources were removed.

## Acceptance limits

The custody files were explicitly synthetic local text, not real saved plans or
production key material. The exercise created no external operation and proves
no receiver reconciliation or uncertainty-break journey. Same-operation races
remain covered by their separate deterministic tests and browser records.

This proof covers local-development HTTP identity and one local participating
storage domain. HTTPS identity, remote/unmanaged writer quiescence, real
receiver/custody restore and rotation, host-power-loss durability, control-ledger
loss/cross-host restore, restricted egress and an independent human self-service
pilot remain separate gates. The run does not close the original ACs of Stories
12.7 or 12.8.
