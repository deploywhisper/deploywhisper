# Durable engine v1 (Story 16.5)

The engine persists immutable workflow-v2 run snapshots, fenced local attempts,
coordinator ownership, cancellation evidence, and human request idempotency in
SQLite migration 032. It uses the existing project/workspace authorization,
policy epochs, audit, and signed read cursors. The exact state and storage
contracts are in [engine-contract-v1.md](engine-contract-v1.md).

## Availability and scope

The production local-handler registry is intentionally empty. Requesting a new
run without all required trusted handlers returns the fixed 503 response. Empty
registry startup does not install a coordinator or create its audit identity.
Story 16.6 supplies the analysis adapter; receiver, outbox, credentials, runner
execution and reconciliation integrations belong to later stories. This engine
does not send infrastructure changes or accept client-provided code, commands,
process IDs, handler registrations, or worker capabilities.

With a trusted server-owned registry installed, one singleton coordinator uses
short transactions and at most two spawned local worker processes. Handlers get
immutable snapshot bytes and typed prerequisite references, with no database
session, coordinator secret, or sibling-attempt capability. Each worker wrapper
opens its own database sessions. Production uses the qualified SQLite WAL/FULL
profile; it does not require Node, a broker, or another database.

## Human API

All resources are under `/api/v1/infra-automation` and use human authentication,
current project/workspace roles, fixed bounded error envelopes, and `no-store`.
Mutations require the existing trusted origin and CSRF protections.

| Resource | Meaning |
| --- | --- |
| `POST /runs` | Capture a published revision and validated inputs under a scoped idempotency key. |
| `GET /runs?project_id=…&workspace_id=…` | List scoped run summaries. |
| `GET /runs/{run_id}` | Read current state and immutable snapshot/input/definition digests. |
| `GET /runs/{run_id}/steps` | List attempt summaries and typed output references. |
| `GET /runs/{run_id}/logs?attempt_id=…` | Read bounded log chunks with explicit gap/truncation metadata. |
| `POST /runs/{run_id}/cancel` | Request cancellation as the current requester or scoped administrator. |

List routes accept `limit` (default 25, maximum 100) and an opaque signed
snapshot cursor. Every page rechecks current authority. Attempts and logs are
ordered newest first; entries added after the first page do not enter its
snapshot. Worker nonces, hashes, leases and private ownership handles never
appear in public responses.

Admission keys bind the original typed body and its authoritative resolution.
An identical retry returns the existing run without recapturing policy, inputs
or time. Reusing the key for a changed body returns 409. Existing runs remain
readable after the feature is disabled, subject to current read authority.

Cancellation takes `expected_version` and `reason`. The first successful request
atomically records its flag, human audit, and terminal local state before any
process signal. Identical retries are audit-free and reattempt signaling. A
signal error may return 503 while the cancellation remains durably recorded.
Local cleanup also observes the flag on coordinator ticks, including after a
lost callback or ownership change. Cancellation cannot undo accepted external
work: possible delivery remains `delivery_unknown` and requires reconciliation.
Terminal success cannot be relabeled as cancellation.

## Recovery and limits

All worker mutations verify the full private attempt binding, current generation,
monotonic fence, live lease/deadlines, scope and current authorization epochs.
A retry creates a fresh attempt; it never reopens a completed attempt or rewrites
an immutable output. Retry-safe local work has at most three attempts within the
original run deadline. Already committed matching output can be adopted without
executing the handler again. External uncertainty is never automatically resent.

Project defaults admit 10 active and 100 queued runs; workflow defaults are five
active and 25 queued runs. Unknown delivery retains an active slot. Active-run
promotion is independent of the two-worker execution limit. Payload retention
includes terminal and unknown runs, canonical snapshots, log JSON and typed
upload/output references. Default retained payload ceilings are 64 MiB per
project and 256 MiB globally; these do not represent the physical size of SQLite
indexes, rows or audit history. Physical disk reserve is checked separately.
Each attempt retains at most 1 MiB of log JSON and each UTF-8 chunk is at most
16 KiB. Safety cleanup remains possible when admission is blocked.

UTC deadlines are immutable and bounded by captured evidence expiry. A backward
clock denies new authority. Cancellation measures local termination using a
monotonic clock: signal the owned process group, allow TERM, then KILL, within
five seconds. A failed kill retains the worker slot until cleanup is confirmed;
it never silently admits an unmanaged third worker.

## Verification scope

Synthetic process, HTTP, migration, fault-injection, overhead and capacity proofs
are recorded in `docs/verification/infra-automation/16-5/`. Capacity qualification
uses 10 active runs across two workflows, at most two real local worker processes
and 20 exercised synthetic online slot ports for a real 30-minute interval.
Those synthetic ports do not qualify real runners, receivers, transport,
credentials, or infrastructure execution. No browser surface changes in this
story: UI validation is not applicable.

## Trusted server configuration

`DEPLOYWHISPER_ENGINE_` followed by the uppercase `EngineBounds` field name
configures a ceiling, for example `DEPLOYWHISPER_ENGINE_ANALYSIS_WORKERS=1` or
`DEPLOYWHISPER_ENGINE_GLOBAL_QUEUED_RUNS=500`. Fields are
`WORKFLOW_ACTIVE_RUNS`, `WORKFLOW_QUEUED_RUNS`, `GLOBAL_QUEUED_RUNS`,
`ANALYSIS_WORKERS`, `PROJECT_BYTES`, `GLOBAL_BYTES`, `ATTEMPT_LOG_BYTES`,
`LOG_CHUNK_UTF8_BYTES`, and `DISK_RESERVE_BYTES`. Defaults and maximum permitted
values are frozen in the engine schema. Values must be nonempty positive ASCII
decimal integers no greater than their defaults; invalid configuration fails
closed with 503. These are server settings and are never accepted from a human
run request. Restart an installed coordinator to capture changed server bounds.
The default global backlog is 1,000 queued runs and disk reserve is 64 MiB.
Project policy changes cannot reduce active/backlog quotas below retained usage.
