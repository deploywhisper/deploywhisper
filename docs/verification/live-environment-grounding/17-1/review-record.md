# Story 17.1 implementation review and repairs

Scope: the provider-neutral, SDK-free foundation. Three independent read-only reviewers checked contracts/redaction, storage/admission and acceptance. The interface plan and storage-isolation correction were separately reviewed before implementation.

| Finding | Repair and meaningful regression |
| --- | --- |
| Numeric secret echoes | Collect private numeric values before dropping fields; scrub numeric/string/key/identity echoes while preserving trusted protocol authority. Integer8675309 and float12.34 reproductions now disappear from persisted SQL payloads. |
| Prefixed raw content | Normalize explicit provider prefixes and encoded raw-state/plan/response aliases; block them and their sibling echoes, recording incomplete reads. |
| SQLite replacement | Same-key INSERT/REPLACE refusal and WITHOUT ROWID remove live overwrite, tombstone resurrection and rowid/oid/_rowid_ conflict paths under recursive triggers0/1. Ordinary idempotence and lawful purge remain valid. |
| Report workspace scope | Refresh actual report/workspace rows after flush and enforce ownership independently of optional evidence metadata. Foreign and missing workspace cases roll back. |
| Publication set | Validate every new live-state row and admitted-report reference against the private minted set, including zero-minted writes and forged additional rows. Artifact evidence remains supported. |
| Retained collection result | Re-read the retained row before returning successful collection; expired unreferenced or purged duplicates cannot return success or reset age. |
| Shared qualification coupling | Replace the rejected global043/shared-metadata design with cloud-owned metadata/schema initialization. Core source bytes and migration history remain unchanged; no old qualification hashes or execution code are altered. |

Each concrete failure had a failing regression before repair. Independent reviewers reran original reproductions and the corrected suites, including persisted SQLite secret cases and raw SQL replacement. The storage reviewer found no remaining concrete high/medium issue; the contract reviewer closed both redaction findings. The corrected schema lifecycle was reviewed for atomic savepoints, strict absence/version/object checks, default-off zeroDDL and separate metadata/FK behavior.

## Qualified profile

- No provider SDK, credentials or network required; reference provider is injected only by trusted server/test code.
- SQLite with foreign keys and a physical checked writer transaction. Cloud schema initialization uses a Connection savepoint; partial state is never adopted or repaired automatically.
- Report publication reserves the same authorization transaction until durable fact/evidence binding is checked. An admission reserved before TTL expiry commits its report reference atomically; an already-expired unreferenced snapshot is unavailable.
- Production authorization adapters, provider IAM/transport/deadline qualification and user-facing live-context surfaces remain with later stories. Admission currently scans live-evidence IDs and retained column values to guard publication; production-scale optimization must preserve these checks.

## Evidence and commands

Final focused result:120tests +121subtests pass. Import/network-isolated cloud/evidence/storage profile:84tests pass. Scoped mypy passes, with one informational note about untyped bodies; Ruff and the configured Bandit gate pass. Runtime Docker proof is in docker-runtime-result.json. Final root/full-CI and exact GitHub shard summaries are recorded in README.md/final-verification.json after completion.

Recorded red/green logs include `/tmp/story17-1-numeric-raw-alias-red.log`, `/tmp/story17-1-numeric-raw-alias-green.log`, `/tmp/dw17-1-replace-red.log`, `/tmp/dw17-1-rowid-replace-red.log`, and the per-packet owner logs. Publication-set regression and rollback-mutation outcomes were independently verified and are covered by the focused test command. The failed shared-head approach is preserved in `/tmp/story17-1-shared-head-approach-ci.log`; final success must not be inferred from that run.

## Story 17.1 code-review repairs — 2026-11-16

- P1 early commit: guard Session.before_commit, Connection.commit and explicit SQL COMMIT/END, including SQLite comments, empty statements and BOM prefixes. An attempted early commit invalidates admission even if the caller catches its exception. Regression assertions inspect a fresh session and verify no report or fabricated evidence is durable.
- P1 retained evidence mutation: capture complete live-state rows before admission and compare stored column values after flush. ORM edits, bulk SQL edits, relabeling, deletion and cross-project mutation now reject and roll back. No shared model/migration change was needed.
- P2 numeric account disclosure: normalize integral float/int account values for masking; preserve nonintegral values, booleans, disabled masking and redaction idempotence. Unit and actual persisted-payload regressions failed before the fix and pass afterward.
- Independent follow-up reviewer reran commit reproductions; COMMIT, semicolon, BOM and mixed comment prefixes now leave zero reports. Admission suite:28tests,30subtests passed. Focused foundation:125tests,137subtests passed.

The raw driver/database-owner boundary and production provider qualification remain unchanged. No new dependency or UI surface was introduced; UI validation not applicable. Full validation for this follow-up is recorded in review-fixes-2026-11-16.json separately from the original implementation qualification.
