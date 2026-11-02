# Story 16.10 registered targets and durable handoff contract

This is the owning story's additive production interface refinement under
architecture §25.9. Frozen receiver-v1, workflow-v2, decision-v1, error, state and
cursor artifacts remain unchanged. Story 16.0 governance and Stories 16.8/16.9 are
accepted; the latter merged as
`501d789460adccdb1765313f996df42583dc96a1`. This backend slice uses scoped
receiver, material and delivery doubles. Real receiver/GitHub delivery and custody
qualification remain with 16.11/16.14/16.19. No settings screen changes here.

## Registry and precollection admission

`POST /api/v1/infra-automation/targets` creates/updates a registered target using
strict closed integer-v1 DTOs. Fields: audit `project_id`, concrete `workspace_id`,
`canonical_target`, `aliases`, `allowed_scopes` (project/workspace pairs),
`environment`, `receiver_id`, `pipeline_repository_id`, `pipeline_workflow_id`,
`pipeline_workflow_revision` (immutable 40-hex SHA), `github_owner`,
`github_repository`, `github_workflow`, `workflow_ref`, `api_origin`,
`allowed_private_addresses`, `credential_ref`, `receiver_credential_ref`,
`expected_version` (zero for create), `enabled` and bounded screened `reason`.
Credential fields are references, never values. GET collection/detail uses the
same authorized selected scope and existing bounded cursor/read envelopes.

Concrete request: `{version:1, project_id, workspace_id, expected_version,
definition:TargetDefinition, reason}`; the definition contains the registry
fields above except audit scope/expected_version/reason, and has its own strict
`version:1`. `allowed_scopes` is a nonempty bounded tuple of closed
`{project_id,workspace_id}` objects. Receiver audit identity is server-derived,
never a registration field. Responses identify `id`, row `version`, `epoch`,
definition/digest, actor identity and timestamps, with no credential value.

Canonical IDs/aliases normalize ASCII case, are globally unique and cannot be
reassigned to another canonical identity. Retiring an alias never frees its name
for another target. Changes increment the target version/epoch and audit in the
same transaction. Registry administration additionally requires the existing
verified global configuration administrator boundary, unrestricted scoped
`automation.admin`, and authority over every assigned scope. Project admins
cannot redefine global collision identity through an alias.

Only assigned concrete scopes and the exact registered environment may use a
target. Resolve every handoff alias before creating a queued run. One transaction
creates the run/request/snapshot, immutable relational target-resolution sidecars
and unique held canonical locks. All targets are acquired together in stable
order; any collision rolls back admission before collection can be claimed.
Identical run replay returns its retained run without acquiring another lock.
Workflow bytes/digests and closed SnapshotDocument are never rewritten. Resolve
aliases through the retained sidecar when checking canonical decision lineage;
the original alias remains in the immutable workflow definition.

Each sidecar retains target configuration bytes/digest, epoch, scope, alias and
lock identity. Default unqualified collection/handler ports remain unavailable.
Missing legacy sidecars cannot authorize a new handoff; authorized history reads
remain available. A target change cannot revive an old run or grant after a later
re-enable.

## Operator configuration and limits

Configuration is read centrally through `config.py`; registering a reference
never selects an arbitrary environment variable or persists its value.

| Environment variable | Meaning and default |
| --- | --- |
| `DEPLOYWHISPER_INFRA_ALLOWED_ORIGINS` | JSON array of 1–16 unique canonical HTTPS origins; defaults to `["https://api.github.com"]`. Registration cannot broaden this operator policy. |
| `DEPLOYWHISPER_INFRA_DISPATCH_CREDENTIALS` | JSON object mapping `credential_ref` to dedicated dispatch secrets; defaults to `{}`. |
| `DEPLOYWHISPER_INFRA_RECEIVER_CREDENTIALS` | Separate JSON object mapping `receiver_credential_ref` to receiver-operation secrets; defaults to `{}`. Human sessions and dispatch secrets do not replace this audience. |
| `DEPLOYWHISPER_INFRA_GRANT_KEY` | Dedicated stable HMAC key for the fixed `handoff-v1` reference; no usable default. Missing or changed key denies outstanding grant derivation. |
| `DEPLOYWHISPER_ENGINE_PROJECT_BYTES` | Retained run-byte ceiling per project; default/maximum 67,108,864 bytes. |
| `DEPLOYWHISPER_ENGINE_GLOBAL_BYTES` | Retained run-byte ceiling across projects; default/maximum 268,435,456 bytes. |
| `DEPLOYWHISPER_ENGINE_DISK_RESERVE_BYTES` | Required free-disk reserve in addition to new retained bytes; default/maximum 67,108,864 bytes. |

Credential maps have at most 32 entries and at most 65,536 JSON characters. Keys
use the closed reference syntax; secrets and the grant key require 32–4,096
printable non-whitespace ASCII characters. Keep values in the operator's
protected environment, never registration bodies, examples, logs or persistent
settings. All configured handoff credentials join content screening. Engine
bounds accept only positive decimal integers at or below their shipped ceilings;
invalid configuration fails closed. Quota exhaustion returns 429; unavailable
configuration/storage returns 503 through the existing error envelope.

Registration admits at most 1,000 canonical targets, 32 aliases per definition,
50 concrete project/workspace assignments, 16 exact private-address exceptions,
and 32,768 canonical definition bytes. Scope assignments do not imply permission:
the caller still needs live authority for every assigned scope. Alias names
remain reserved even after retirement. Private exceptions also require the exact
operator-allowlisted internal HTTPS origin; metadata and forbidden ranges remain
denied.

Run admission charges each retained target snapshot copy, its canonical sidecar
metadata and each canonical lock's bookkeeping. Preparation charges both decision
and receiver binding copies, exact semantic payload, retained target snapshot,
and canonical nonsecret operation/outbox/grant bookkeeping. Preparation reserves future mutable scalar bookkeeping at its bounded maximum:
operation/outbox longest states, signed 64-bit version widths, attempted/consumed
UTC timestamps, invalidated grant status and receipt digest. The persisted
initial states remain unchanged. Consumption therefore charges only the retained
raw receipt bytes before committing it; its timestamp/digest growth was already
reserved. Canonical locks similarly reserve terminal status/version and the
maximum 256-character printable reason (up to 1,024 UTF8 bytes) at admission, so
later verified resolution or uncertainty break needs no unaccounted growth. These additions use the existing
run `retained_bytes` counter, project/global ceilings and physical disk reserve
in the same transaction; rollback leaves neither authority nor a partial charge.
Standalone registry writes check physical capacity for definition/alias/scope
bytes and the registry count/definition bounds; they are not charged as a run.
These logical quotas are not an exact SQLite file-size estimate.

Semantic payload and each retained binding/snapshot are bounded to 131,072 bytes.
The fixed transport independently defaults to a 10-second overall deadline and
65,536-byte wire-request/response ceilings (constructor ceilings: 30 seconds and
1,048,576 bytes). Larger semantic payload eligibility never overrides the wire
limit. These bounds do not install production ports: default decision material,
workflow-ref, delivery and collection handlers remain unavailable. Environment
configuration alone cannot qualify a real receiver or trusted collector.

## Atomic operation, outbox and one-use grant

The closed prepare request identifies `approval_id`, `handoff_step_id`,
`idempotency_key` and `reason`; it never selects a destination URL or supplies a
replacement binding. Preparation requires current human mutation authority in
the actual run scope and `DecisionService.recheck_approved` in the SAME reserved
operation transaction. Verify captured target/lock/current epoch, immutable
decision/report/action bytes, all requester/reviewer generations, policy,
feature/restore epochs, custody/source availability, current workflow ref pin and
the earliest run/evidence/approval/source/custody deadline. Recheck the clock
after callbacks. No stale authority becomes a credential.

Owned public resources (historical frozen route fixtures are not edited):

| Method/path | Closed request / result |
| --- | --- |
| POST `/targets` | Registration request above; target view |
| GET `/targets`, `/targets/{target_id}` | Required project/workspace scope; bounded current target views |
| POST `/handoffs/prepare` | `{version:1,project_id,workspace_id,approval_id,handoff_step_id,idempotency_key,reason}`; operation view |
| GET `/handoffs/{operation_id}` | Required selected project/workspace; retained operation view |
| POST `/handoffs/{operation_id}/dispatch` | `{version:1,project_id,workspace_id,expected_version,reason}`; persisted operation view, never claimed remote success |
| POST `/targets/{target_id}/break-lock` | `{version:1,project_id,workspace_id,expected_lock_id,expected_version,acknowledge_uncertainty:true,reason}`; broken lock view |

Preparation/dispatch requires scoped `automation.request` and human mutation
credentials; lock-break requires global configuration/scoped admin. Operation
reads require current `automation.read`. Target configuration reads also require the global administration boundary and
filter selected assigned scope before pagination; full definitions never leak
other project associations to a restricted reader.
Idempotency is scoped to project/workspace/verified principal/prepare-handoff/key;
one retained approval/handoff cannot mint another operation through another key.
Operation views expose protocol_version 1, id, row version/state, scope/run/step/
approval/target/receiver identities, authorization kind, both binding digests,
payload digest, deadline and recorded consumption/outcome metadata. No grant or
credential values are returned. Internal prepared/sending/outbox states are not
new receiver-v1 wire states.

The approved semantic action payload is deterministic typed canonical JSON
derived from the decision and captured registry configuration. Its digest must
equal the approved payload digest; callers cannot attach arbitrary inputs.

Exact semantic payload shape: `{version:1,kind:"registered_github_handoff",
decision:<DecisionBinding JSON excluding payload_digest>,destination:{api_origin,
github_owner,github_repository,github_workflow,workflow_ref,target_version,
target_epoch,target_snapshot_digest}}`. Canonicalize with tuple-json-utf8-v1.
The payload excludes its own digest, operation IDs generated after approval,
grants and transport credentials. Decision material captures these identical
bytes/digest before approval; preparation regenerates only for exact comparison
and persists those exact bytes. Routing/ref/current-pin checks use the captured
configuration and live registered version, not caller body fields.
Persist its exact bytes, both binding identities, stable operation, scoped key
and request digest, immutable grant verifier/expiry and outbox before delivery.
One operation per approval AND per run/handoff step, plus scoped key uniqueness,
prevent replay or replacement through a later decision generation.
Same key/same exact request returns the retained operation; changed reuse is 409.

The grant is an operation-scoped HMAC-derived bearer using a dedicated
environment-backed server key and immutable operation/binding/epoch/expiry facts.
Only its SHA-256 verifier and key reference persist. The same key/facts reproduce
the same bearer after crash; key removal/rotation fails closed rather than
replacing an outstanding grant. All configured handoff secrets join the existing
screening corpus. No plaintext grant enters DB, audit, logs or public responses.
Transport authentication is separate from the approved semantic payload and
the closed receiver JSON. The delivery port receives ephemeral credentials
separately; this slice does not invent a GitHub workflow credential carrier.

HMAC inputs are canonical closed JSON with domain `handoff-grant-v1`, operation,
receiver, both binding digests, payload digest, expiry, captured target epoch and
authorization/restore epochs. Immutable key reference and SHA-256 verifier must
still match derivation using the current configured key; rotation cannot cause
the same operation to acquire replacement authority.

Preparing/reading/dispatching operations uses typed service/API boundaries with
the existing 401/403/409/422/429/503 envelopes. Public human preparation/read/
dispatch resources are owned here and fixture-tested before consumers. Frozen
receiver HTTP consume/receipt/outcome/reconcile routes remain 16.11 ownership.

## Consistent material graph admission (server-owned port)

`DecisionService.recheck_approved` requires a qualified, read-only
`material_witness_port(session, MaterialReadScope) -> MaterialWitness`, in
addition to the existing per-step material resolver. The default is unavailable
(503); installing only a material resolver cannot authorize a handoff. These are
internal server-composition contracts, not HTTP credentials or frozen wire DTOs.

`MaterialReadScope` binds the exact run, project/workspace and sorted tuple of
`(approval_id, step_id, binding_digest)` for the selected decision and every
mandatory human ancestor of its matching handoff graph (at most 50 steps).
`MaterialWitness` carries `source_id`, `scope_digest` (canonical scope SHA-256)
and one strict positive monotonic generation per scoped tuple in that order.
The provider atomically reads those generations in the caller's reserved
operation transaction. Its fact/custody lifecycle must serialize with admission
or retain the corresponding leases through the operation; a remote observation
without that guarantee is not a qualified implementation.

The provider must advance the relevant generation on EVERY custody, evidence or
binding change, including a revoke-and-restore ABA change, and change its domain
`source_id` whenever counters reset or their source is replaced. Do not infer
generations from occasional content hashes or return constant counters for
mutable material. A matching digest of final booleans cannot prove no intervening
revocation. A constant witness is valid only for genuinely immutable scoped
fixtures, such as the controlled crash child.

Consumer admission reads the witness before and after the complete decision-graph
material traversal, denies a changed domain/generation vector or changed receipt
scope with 409, and denies missing/malformed/wrong-scope/count/unavailable witness
values with 503. All material callbacks finish between these two reads; there is
no arbitrary repeated-pass loop. Time and the existing final handoff target,
receiver, reviewer, policy and authority floors are refreshed after the final
read. Deadline expiry during that read still denies. This witness is an
additional consistency fence, never a new approval, grant or replacement for the
existing exact-binding/epoch/custody checks. Preliminary human readiness checks
remain advisory until guarded consumer admission succeeds.

Synthetic material-store fixtures increment generations on every immutable
material replacement, including ABA, and qualify both callback orders. Real
provider/receiver/collector generation and lease qualification remains with the
owning integration stories; no production source is enabled by this refinement.

## Receiver identity and exact wire mapping

DecisionBinding contains integer project/workspace IDs and revision_id. Frozen
receiver-v1 Binding uses string scope IDs and omits revision_id. An explicit
validated mapper retains every receiver field, converts only canonical scope
IDs, and excludes only the decision-only revision_id. Keep the decision digest
and relational revision linkage alongside the independently canonicalized receiver
binding/digest. Never label a decision digest as a receiver digest or regenerate
the frozen schema. Validate vectors against the actual frozen prototype/schema.

Online consume is qualified through a distinct operation-bound receiver
credential and consumer double, never a human cookie, caller role header,
service-request credential or general machine issuer. Registration binds a
nonhuman audit identity and environment-backed receiver credential reference.
Actual credentials, live account/target versions, receiver, scope, operation,
grant verifier, payload and both immutable binding identities are rechecked in
the reserved consumption transaction. `recheck_approved(... phase="consume")`
and the refreshed clock remain additional deny checks. Workflow-ref lookup must
finish before final material/custody admission; preparation also completes the
capacity probe before that admission. Final target/receiver/policy/clock checks
follow material callbacks. Consumption CAS writes
one durable receipt before the double counts any action. Repeated consume is 409;
authenticated status recovers the original receipt without another consume or
replacement grant. Revocation/disable/restore cannot authorize a new/resumed
action; already accepted work remains readable to currently authorized actors.
Successful action admission durably advances the operation observation floor
when time advances, using a same-state CAS and `handoff_action_checked` audit
in the same transaction. A regressed clock denies even after service restart;
a same-clock recheck does not mutate state. This never creates another grant,
receipt or action-fencing identity.
Status returns the same recorded operation and durable consumption receipt after
a lost consume response. It never increments consumption or resumes action by
itself. The double must separately recheck admission before counted action.

## Connection and uncertainty boundary

The fixed GitHub-compatible transport constructs its own bounded dispatch path
from registry fields and pins `X-GitHub-Api-Version: 2026-03-10`. Origins must also satisfy operator-owned configured host
policy (default only `https://api.github.com`). HTTPS with an explicit TLS1.2 minimum, verified certificates and hostnames; no URL credentials,
query/fragment, workflow URL, redirects, or TLS verification bypass. Resolve all
addresses at connection time, reject mixed/forbidden results, pin the numerical
connection address, verify peer address and retain TLS hostname verification.
Metadata/link-local/unspecified/multicast/reserved destinations always deny.
Private/loopback addresses require exact audited administrator-owned origin and
explicit address exceptions; an exception cannot authorize metadata access.
Timeouts, response bytes and wire bodies stay bounded. This transport's tests
prove the connection policy, not live GitHub delivery/receiver durability.

Outbox claim marks possible delivery and retains the lock before network work,
which occurs outside SQLite. Crash/response loss after that boundary becomes
`delivery_unknown`; no blind resend or replacement grant. Feature, target,
membership or restore changes deny new dispatch/consume; history/status remains
readable. Cancellation/lease expiry is not proof external work stopped.

Only a verified terminal resolution, provably pre-external local terminal state,
or privileged audited break can release a lock. Break requires expected holder/
version, explicit uncertainty acknowledgement and reason, permanently invalidates
that operation's remaining authorization, and never creates an approval/grant.
Breaking a precollection lock also permanently retires its retained run/target
claim even when no operation exists yet; the old run/decision cannot reacquire
authority through a new lock, alias or later re-enable.
Retained operation/outbox/grant/snapshot/audit identity is append-only; DB/host
administrators remain trusted.

A verified sequence 2 succeeded/failed outcome in this slice updates the retained
operation. A shared canonical lock resolves only after every captured handoff
using that lock has a verified terminal operation; one terminal sibling cannot
release another's uncertainty. This service-level terminal proof is not a new
public outcome endpoint and does not terminalize the parent run. Story 16.11 owns
signed/sequenced HTTP callbacks, receiver durability, observed outcomes and
parent-run terminal reconciliation. Until that reconciliation exists, a parent
run may remain `external_running` after its retained handoff is terminal; do not
infer run completion or retry authority from a resolved lock.
