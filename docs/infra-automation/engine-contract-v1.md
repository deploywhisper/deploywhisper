# Story 16.5 durable engine contract v1

This additive in-process/HTTP engine contract consumes workflow v2 and the 16.4
immutable snapshot port. Frozen state/error/cursor/runner/receiver schemas remain
unchanged. It owns no receiver, runner enrollment, grant, outbox, approval or
artifact custody implementation. Test doubles never qualify those later slices.

## Authority and admission

Human request/read/cancel routes reuse the existing authenticated router and
project operation transaction. Request requires `automation.request` with mutation
credentials; cancel requires `automation.cancel` with requester ownership or scoped
admin. Read requires current `automation.read`. Machine request issuance remains
unavailable until its owning story supplies an independently authenticated audience.
Never persist sessions, CSRF tokens, raw artifacts or provider credentials.

POST `/runs` accepts workflow_id, revision_id, concrete workspace_id, bounded typed
inputs, idempotency_key, reason and total_timeout_seconds (60–3600, default3600).
IDs/scalars/reasons use existing strict closed lifecycle types. Bind the key to
verified principal + project + workspace + operation; bind request digest to exact
revision, validated/defaulted inputs, source, scope, timeout and reason. Identical
retries return the original run after live scope authorization, without recapturing
policy/time or creating another snapshot/audit. Changed reuse is409. A new request
calls export_run_snapshot in that SAME transaction and stores its authoritative
bytes/digest plus the requester, request digest and created/deadline timestamps.
Never execute a draft. Feature disabled, stale membership, missing immutable source,
corrupt snapshot or unadmitted collection fail closed before persistence.

GET `/runs`, `/runs/{id}`, `/runs/{id}/steps`, `/runs/{id}/logs` and POST
`/runs/{id}/cancel` provide the owned HTTP surface. Lists filter scope before query
limits and use existing signed principal/scope/filter-bound snapshot cursors,
default25/max100. Run detail reports immutable snapshot identity and summaries,
not complete512KiB snapshot bytes. Logs are independently paginated with monotonic
per-attempt sequence and explicit gap/truncated/last_sequence. All response envelopes
are <=128KiB inside the operation transaction. Existing401/403/409/422/429/503,
no-store and fixed diagnostics apply. No handler/plugin/command comes from HTTP.

## Persisted families and transitions

Migration032 follows031 after checking Alembic head. Only engine-owned families:
run (including immutable snapshot/request binding), attempt, coordinator lease and
request idempotency. Log chunks and screened upload/output references may be
bounded attempt records rather than future raw-artifact tables. Scope foreign
keys bind project/workspace/workflow/revision. Enforce unique(run,step,attempt),
(run,step,fence) and scoped requester/key. Immutable run identity/snapshot/request
and already-committed outputs cannot be rewritten/deleted through ordinary SQL.
Use the existing append-only audit in the same transaction as every state change.
Mutable run/attempt transitions compare a positive monotonically increasing version.

Run and attempt enums match frozen state-v1 exactly. Unknown states/edges deny.
Run queued->running|cancelled|expired|timed_out|failed; running may enter waiting_approval, ready_handoff, handing_off,
external_running or a declared terminal. waiting_approval may enter ready_handoff,
rejected or a pre-external terminal; ready_handoff may enter handing_off or a
pre-external terminal; handing_off may enter external_running or delivery_unknown;
external_running may enter delivery_unknown. Pre-external terminal states are
succeeded,failed,stopped_by_gate,rejected,expired,timed_out,cancelled. Succeeded from
running requires every step to have a successful committed attempt and every
output-producing step to have its required committed typed output. A no-output
handoff cannot become local success; possible external acceptance forbids local
success. When a run stops, unfinished pending/claimed/running descendants become
cancelled (or timed_out on timeout), without inventing a skipped wire state. Terminal runs
never reopen. delivery_unknown is reconciliation-only; no automatic claim/retry
or local terminal-success transition exists. Only a later authenticated receiver
integration can supply an observed external terminal outcome.

Attempt pending->claimed->running->succeeded|failed|timed_out|cancelled; pending or
claimed can also fail/time out/cancel before execution. Retry inserts a new row,
never reopens any old attempt/output. Every DAG prerequisite must have a successful
committed output before a dependent step becomes claimable. Gate stop, rejection,
expiry, timeout, cancellation, failure and external uncertainty remain distinct.

## Ownership, time and recovery

Use short SQLite BEGIN IMMEDIATE operation transactions. Retain earlier authority
semantics; do not issue a cached credential from a snapshot. Request/check/claim
and worker writes validate captured principal/membership and live policy epochs
under the same operation session via the 16.4 deny check. Internal worker ports
are local process-owned capabilities, not exposed runner endpoints. Bind every
heartbeat/log/upload/output/complete to exact project/workspace/requester/run/step/
attempt, owner, monotonic fence, coordinator generation, captured policy epochs and
unexpired persisted coordinator AND attempt leases. Exact owner identity is mandatory;
lease expiry alone never grants authority. A caller cannot synthesize a current
owner by selecting the public comparison fields. Mint256-bit process-held coordinator
owner secrets; persist only their hash, compare with constant-time equality, and
rotate on takeover. Each attempt has an independently minted256-bit secret and
its own persisted hash. A worker receives only its attempt secret; it cannot mint
coordinator authority or forge a sibling attempt by changing public binding fields. Local claim handles carry that secret privately and never
serialize it into responses/logs. This authenticates the internal operation separately
from the public stamp; do not fabricate a human session. After live authority denial,
internal safety-only invalidation/cancellation/expiry may still stop local work and
append audit, but cannot persist a new result or start an effect.

A global coordinator lease has persisted generation and owner; takeover advances
generation atomically. Healthy unexpired ownership excludes competitors. Only its current authenticated owner may release; release
invalidates its generation before another owner can claim. Startup never invalidates
a healthy competing lease; acquire only an empty/released or expired lease by CAS. Fences and attempt
numbers only increase across reclamation/retry. Reclaimed safe work receives a new
attempt; a successor may adopt the same prior immutable output reference without
rewriting the old attempt/output or rerunning its handler. Stale handles still deny.
Stale generations cannot heartbeat, append logs, upload or complete.
Persist claims before invoking a handler and commit output reference/digest before
completion. A trusted external-capable double must additionally commit handing_off
before invocation; only then can its uncertain result become delivery_unknown.
Ordinary running local work cannot return an external outcome. Same output/completion replay is idempotent only for its original exact
binding; changed replay conflicts. A worker has a fresh DB session for every write.

Background audit uses a dedicated non-login service account, not a fabricated human
actor. Lazily create it after verified human run admission, never on migration or
empty-app startup (human bootstrap rejects any prior account). Use fixed engine ID,
reserved username "infra-engine-coordinator " (trailing ASCII space, already
rejected by existing human username validation),
principal_type=service, enabled=false,
is_admin=false and inert invalid password verifier; no membership, session or token
is issued. Existing or conflicting identity mismatches fail closed. Record audit
actor_type=service and role=coordinator; original requester remains immutable run
metadata. Tests prove this account cannot log in/recover and fresh bootstrap stays
available before the first run.

UTC deadlines are finite and expire at now>=deadline. Default coordinator lease30s,
attempt lease30s, heartbeat<=10s, attempt timeout300s(max600), max3 attempts; the
attempt deadline never exceeds the immutable run/evidence deadline. Effective run
deadline=min(request total deadline,snapshot capture+policy evidence TTL). Persist
last observed UTC and deny time moving backwards; monotonic process time additionally
bounds cancellation/worker timeouts. Fail closed on corrupt counters/unavailable
policy. A leap forward can expire work but never extends authority. Crash probes
cover both sides of each owned commit and recover exactly committed audit/state;
no host-power-loss/distributed-clock guarantee is made.

Only trusted registered local handlers explicitly marked retry_safe may retry an
unsuccessful local attempt within both remaining run deadline and max attempts.
Persist handler identity/classification so restart cannot reinterpret unsafe work.
Unsupported handlers do not execute and cannot return success. Production registry
starts empty;16.6 integrates real analysis. No generalized commands, shell or
request-defined plugin registration is introduced. Typed external doubles can model
accepted/dropped-response results: possible external acceptance permanently prevents
blind resend and requires reconciliation, including after cancel/epoch changes.

## Bounded coordinator and cancellation

FastAPI lifespan owns start/stop of one coordinator loop; tick claims/transitions
bounded work and never executes synchronous analysis/network work on the event loop.
Use at most2 global off-loop worker slots and no unbounded executor queue. A slow
handler cannot block another claim or coordinator heartbeat. Startup respects any healthy competing lease. Shutdown may release/invalidate only
this process's authenticated owned generation; unknown external work stays protected. Every worker
completion routes through the original claim capability and its own DB transaction.
No fake successful default handlers are installed by app startup.

Cancel commits the request and invalidates local attempt authority before signaling.
A local owned process/descendant double must terminate within5s (TERM then KILL with
bounded join); verify the whole owned tree, not only the parent. No arbitrary process
ID or executable is supplied by HTTP. Completion racing the committed cancellation
loses its CAS/fence. If external acceptance is possible, cancellation records request
and delivery_unknown, never claims the remote pipeline stopped or frees its lock.
Actual runner isolation/process lifecycle remains16.12–16.14.

## Quotas and qualification

Quota active states are running/waiting_approval/ready_handoff/handing_off/
external_running/delivery_unknown; queued is counted separately. Terminal states
retain their byte accounting, and unknown remains active/protected. A workflow's
five-active cap therefore needs at least two workflows for the ten-active benchmark.
Reject lower-than-usage quota changes; do not delete evidence or silently release
unknown capacity. Project active/queue caps reuse 16.4 settings(default10/100). Add server-owned strict
engine bounds: workflow active<=5(default5), workflow queued<=25(default25), global
workers<=2(default2), per-project retained engine bytes64MiB(default), global retained
engine bytes256MiB(default), per-attempt log<=1MiB and per-chunk UTF8<=16KiB. Config
values may reduce bounds; invalid/nonpositive/excess values fail closed. Bound JSON
parsing and canonical bytes before DB writes. The retained payload budget counts exact snapshot bytes plus UTF8 logs/upload/output
JSON (including initial empty arrays); fixed ORM metadata and audit rows are excluded
from that payload measure and physical disk availability is checked separately. These
payload bytes count atomically before admission/writes; terminal/unknown evidence stays counted.
No retention janitor is added and quota reduction does not delete evidence. Saturation
returns429 or leaves durable queued work with explicit backpressure. Disk errors
roll back state and audit and return503, never acknowledge an uncommitted admission.

Record 1000 ready transitions with p95<1s excluding handler time. Run a real elapsed
30-minute bounded capacity test with10 active runs,<=2 analysis doubles and20
synthetic online runner slots; report actual hardware, Python/SQLite, bytes, CPU/RSS,
queue/disk faults, sample count, errors and timing. Qualify only the local engine and
synthetic slots. Later full runner/receiver/release integration remains its owners.

## Packet order and evidence

A state/persistence/migration -> independent review -> B claims/recovery -> independent
review -> C coordinator/off-loop workers -> review -> D retry/output -> review ->
E cancellation/HTTP -> review -> F fault/capacity/docs. Integrate each packet into
this story branch with its own tests and decision commit before widening scope.
No checkboxes are completed by this design document. Root owns integration,
service/HTTP and qualification; bounded native implementation owners are recorded
in the story before their packet starts. No new dependency or UI work is authorized.

## Concrete DTOs and internal port shapes

Strict engine DTOs live in infra_automation/state.py; schema engine-v1.json is new
and does not replace frozen-v1. RunRequest has the POST fields above; CancelRunRequest
has expected_version and reason; RetryAttemptRequest has expected_version and reason
(service-only). No client field selects state, actor, lease, fence or handler. Inputs
reuse SnapshotDocument's bounded scalar mapping. RunView has id/workflow_id/revision_id/
project_id/workspace_id/requested_by/state/version/snapshot_digest/definition_digest/
input_digest/created_at/deadline_at/cancel_requested/cancellation_requested_at. Step
views expose attempt identity/number/state/version/fence/generation/deadlines and
committed typed output/upload references, never owner secret. List envelopes reuse
items/cursor. Cancel is idempotent for a repeated already-recorded cancellation but
stale changed requests conflict. Retry is internal, not an HTTP or machine issuer.

A CoordinatorHandle privately holds owner_id,256-bit coordinator secret and generation;
an AttemptHandle carries its distinct per-attempt secret and additionally binds project/workspace/requester/run/step/attempt ID and
number/fence/epochs. Heartbeat, log, upload, output and completion accept that exact
handle and strictly validated operation data. OutputReference is kind (existing
OutputKind), opaque reference and digest; no raw artifact payload. WorkerResult
distinguishes local_success, retryable_local_failure, permanent_local_failure,
stopped_by_gate, rejected and external_unknown. External unknown admits only a
trusted synthetic adapter result here, permanently prohibiting redispatch. Each
handler has trusted stable ID/version, supported fixed step kind, output kind or
none, retry_safe classification and callable. External-capable doubles are never
retry_safe. No client can register a handler or choose that classification.

### Trusted runtime ceilings and physical storage

`config.engine_bounds()` reads `DEPLOYWHISPER_ENGINE_<FIELD>` dynamically, where
`FIELD` is an uppercase EngineBounds field name (for example,
`DEPLOYWHISPER_ENGINE_GLOBAL_QUEUED_RUNS`). Values are ASCII decimal integers from
1 through the published default; malformed values and increases fail closed.
Global queued runs default to 1,000, including every project's queued rows.
Engine payload budgets include immutable snapshot bytes and the exact UTF-8 bytes
of each attempt's logs/upload/output JSON, including JSON delimiters; initial
empty logs and uploads cost four bytes. Fixed ORM metadata and audit are excluded
from this payload budget. Terminal and delivery-unknown evidence still count.

New admission, new local work and growing evidence require known physical free
space on the SQLite database volume. The default reserve is 64 MiB, in addition
to the requested payload growth; `disk_reserve_bytes` can only be reduced within
its published bounds. Unavailable storage measurements fail closed. This check
provides backpressure and does not guarantee a later filesystem write succeeds;
actual SQLite-full failures roll back the operation. Safety cancellation and
unknown-outcome reconciliation remain available without a free-space precheck.

Only explicit installation of a trusted engine handler catalog activates the
file-SQLite durability helper. It sets and verifies WAL journal mode and FULL
synchronous mode, and verifies/configures each checked-out connection. Empty
production catalogs cause no database-profile side effects. This qualifies
controlled process/container restart only; it does not establish host-power-loss
support. Project policy changes cannot reduce active or queued limits below the
actual corresponding project run counts; denial changes no settings, epochs or
audit history.

### Review recovery guarantees

The two analysis slots are global to the canonical SQLite path, including during
coordinator process overlap. Independent supervisors own gated worker groups and
watch creator liveness through private pipes. Coordinator process death triggers
bounded group cleanup; terminal run/attempt state also triggers owned-process
cleanup rather than assuming a persisted cancellation proves process exit.
Only after confirming the entire group stopped may a slot be released.

Stable local file locks and dirty runtime reservation metadata beside SQLite are
execution resource accounting, not an added ORM family or an authorization token.
Successors count dirty/unreadable slots as occupied and never signal uncertain
process identities. Unexpected supervisor failure requires trusted operator
recovery of dirty capacity; automatic recovery from that additional failure is
not qualified. The production handler registry remains empty and unsupported
platforms do not activate workers.

Candidate sweeps advance through at most100 rows per tick with a fixed sequence
ceiling per sweep and project/workflow interleaving. Later arrivals cannot extend
an ongoing sweep indefinitely. Temporary coded SQLite storage/capacity failures
inside wrapper-owned setup/read/write operations preserve declared-safe bounded
retry behavior; handler and authority failures cannot impersonate those internal
operations. Typed committed output adoption remains idempotent.

Creator liveness is finite even while its process remains alive. The coordinator
validates its private current-owner capability on every pulse inside the reserved
operation transaction, including the cached-renewal path. Only after that operation
commits may it send a nonblocking private monotonic expiry, bounded by both three
seconds and the persisted lease end. A guardian stops on EOF, malformed/stale
pulses, or lifetime expiry and never revives overdue execution. This covers stalled
schedulers as well as process death and prevents a successor cancellation from
leaving stale-owner work running. All matching guardians are signaled before any
join and share one 4.5-second shutdown confirmation deadline.
