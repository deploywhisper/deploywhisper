# Online receiver and reconciliation contract — Story 16.11

The unchanged frozen receiver-v1 message is carried inside additive closed HTTP
requests. The operator reference receiver supports protected synthetic saved
bytes and a harmless local marker only. It does not apply infrastructure.
See [local receiver and custody](receiver-v1.md) and the
[registered handoff contract](handoff-contract-v1.md).

## Authenticated transport

Receiver routes use their own router, HTTPS, no query parameters, exactly one
`Authorization: Bearer ...` and `X-Receiver-Id` header, bounded strict JSON and
no-store responses. Credentials resolve only from the registered captured target
receiver reference; human sessions, dispatch tokens and caller role headers
supply no receiver authority. The service checks its live enabled machine
principal and original authentication generation. Error responses reuse screened
API envelopes and correlation IDs.

| Method and path under `/api/v1/infra-automation` | Contract |
| --- | --- |
| POST `/handoffs/{id}/receipt` | `{version:1,binding_digest}` retrieves exact frozen consume message, semantic payload, original derived one-use grant and run ID for an authenticated receiver. The grant is ephemeral, never a normal human response or stored bearer. Current admission must pass. |
| POST `/handoffs/{id}/consume` | `{version:1,message,grant_token}` atomically consumes the existing grant into its immutable receipt before receiver action. |
| GET `/handoffs/{id}/status` | Returns original receipt and exact retained callback acknowledgement for crash/response-loss recovery; never mints another grant. |
| POST `/handoffs/{id}/authorize-action` | `{version:1}` performs current admission after custody verification, immediately before a new action fence. Uncertainty/cancellation history permanently denies fresh action. |
| POST `/handoffs/{id}/outcome` | Signed callback envelope described below; monotonic sequence/nonce replay protection. |
| GET `/runs/{run_id}/handoffs` | Human scoped read with selected `project_id` and `workspace_id`; at most 50 operations and independent acceptance, observation, receiver outcome, lock and cancellation facts. |
| POST `/handoffs/{id}/reconcile` | Human mutation `{version:1,project_id,workspace_id,expected_version,reason}` performs one bounded registered carrier read and returns the updated projection; never dispatches or manually declares success. |

Bootstrap supplies material only after authenticating the receiver, exact
operation binding and live decision graph. Grant derivation and consumption use
the original operation; no grant values enter GitHub workflow inputs, persistence
or audit. Status/reconciliation remain available for already-started work after
feature disable or evidence expiry, subject to current read/machine identity.
They do not provide new action authority.

## Recorded facts and transitions

Migration `036_add_receiver_reconciliation` adds immutable external-fact
sidecars with per-operation kind/sequence and nonce uniqueness. Exact payload
bytes are charged to existing quotas. No new fields are inserted into frozen
receiver-v1 bindings or workflow-v2 snapshots. Brownfield initialization checks
schema, constraints and immutable guards before adopting revision036; repeated
startup preserves the revision and rejects partial histories.

A correlated HTTP200 `DispatchAcceptance` is persisted separately from verified
receiver outcomes, even if a concurrent callback already advanced the operation.
A missing/dropped response remains `delivery_unknown`, retains its lock and is
never redispatched. GitHub observations validate accepted run, repository,
workflow, protected reviewed revision/ref and event identity. GitHub success
alone cannot complete a deployment.

Callbacks bind version, operation ID, automation run ID, receiver binding digest,
source identity digest, nonce, monotonic envelope sequence and exact frozen
receiver message. Signature is `sha256:` plus HMAC-SHA256 of
`deploywhisper-receiver-callback-v1` plus a zero byte plus canonical envelope bytes
excluding signature. The registered receiver secret authenticates the envelope.
Every accepted nonce/sequence persists before its state is exposed. Replays deny;
a lost response recovers through an exact authenticated `callback_ack` digest,
nonce and sequence instead of a replacement callback or action.

Uncertain/cancellation callbacks create a permanent fresh-action barrier in the
retained history. Later accepted/running progress cannot erase it, and running
cannot regress to accepted. Authenticated terminal evidence can still resolve
already-started work. Only that narrow path may reconcile an external parent to
terminal after every external sibling has verified terminal proof and every local
prerequisite has its durable typed success. A sibling's uncertain or broken lock
cannot be hidden by another success. Operation and parent persisted clock floors
are rechecked, including cancellation, before guarded terminal CAS writes.

Cancellation remains a request and never claims external work was undone.
Unknown outcomes hold the canonical target lock until verified resolution or an
explicit audited operator lock-break, which creates no new authority.

## Trusted composition and limits

`services.infra_automation_receiver_composition.create_github_handoff_service`
connects one actual pinned GitHub adapter to a server-owned DecisionService,
captured snapshot resolver, current credential lookup and bounded poll port.
This is an explicit application composition boundary; an HTTP body cannot select
ports, material providers, credentials or origin policy. The caller supplies an
already qualified material/lease witness. Constructing the carrier does not
qualify a collected source. Unconfigured application material authority stays
unavailable by default, as required by the later collector/integration stories.

The composed browser fixture installs deterministic scoped synthetic ports only
inside its guarded nonroot tmpfs profile. Local HTTPS/TestClient integration and
Linux UID/process-crash tests qualify this slice, not arbitrary provider actions,
host power loss, a compromised receiver UID, network filesystems or universal
production support. Live GitHub transport evidence is retained separately in the
Story16.11 verification directory.

## Run UI

The existing run screen reads the scoped handoff relation. It presents dispatch
acceptance, GitHub observations, verified receiver completion, unknown delivery,
lock status and cancellation request as independent facts. Reconciliation is an
explicit authenticated manual POST with CAS; no retry dispatch control exists.
A submitted ambiguous request remains blocked at the same operation version,
including control unmount/remount, until advancing retained evidence resolves it.
Recognized definite server HTTP4xx rejection allows correction. Identity/scope
loss clears protected facts. Existing shell, cards and buttons are reused.
