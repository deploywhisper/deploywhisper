# Story16.4 workflow lifecycle contract v1

This additive HTTP/in-process contract consumes workflow major2 and leaves every
frozen-v1 artifact unchanged. It owns drafts, immutable revisions, scoped policy,
audit and consumer ports only. It creates no run, runner, grant or outbox tables.

## Scope and authority

Use existing numeric project/workspace IDs; their exact decimal strings fill
workflow-v2 `project_id` / `workspace_id`. No alias guessing. The embedded scope
must equal the workflow row's actual scope. Scope cannot change on draft update.
Null workspace is project-wide authoring, not a runner scope. Snapshot requests
must bind a concrete existing authorized workspace; scoped revisions require the
same workspace. Use `authorized_session` / `guard_project` for every operation,
with SQLite writer reservation before reading authority and no nested commits.
Persist actual object scope, not the membership restriction returned by the guard.

Capabilities: `automation.draft` for create/save/validate (admin/maintainer),
`automation.publish` for publication (admin), `automation.read` for workflow and
revision reads (all human project roles), `automation.admin` for archive/restore,
settings writes, epoch revocation/restore and audit export (admin). Settings reads
use `automation.draft` with read-only credential checking, matching the frozen
admin/maintainer matrix. Live session/membership and mutation CSRF checks apply;
global identity administrator status alone is insufficient. Synthetic service,
agent, runner and receiver claims cannot enter human publication/admin routes.
No machine credential issuer is added.

## HTTP operations

All routes use `/api/v1/infra-automation`, ApiRoute/ApiError/build_meta and typed
closed request/response models. Transport JSON and embedded raw/canonical workflow
bytes each have a 128-KiB ceiling; transport depth <=16. Reject duplicate keys,
nonfinite numbers, unknown fields and invalid constructor types.
The response ceiling measures the complete `data`/`meta` envelope, including
configured application metadata and the correlation ID, before committing a mutation.
Canonical definitions that fit alone but exceed this ceiling with response metadata
receive429 without persisting a draft, revision or audit change. Diagnostics
never reflect input/exception text. Human reasons are nonempty bounded strings
<=256 characters; workflow labels <=120; keys/opaque IDs use identifier bounds.

| Method/path | Payload / purpose |
| --- | --- |
| POST `/workflows` | project_id, workspace_id(null allowed), name, definition(text), reason; create valid nonexecutable draft |
| GET `/workflows` | project_id, optional workspace_id filter, limit(default25,max100), cursor; scoped list |
| GET `/workflows/{id}` | current canonical draft/version/archive state; published history has dedicated revision reads |
| PUT `/workflows/{id}/draft` | expected_version, definition, reason; optimistic update |
| POST `/workflows/validate` | project_id, workspace_id, definition; validate unsaved candidate with draft capability |
| POST `/workflows/{id}/validate` | expected_version, optional candidate definition; validated result, no draft rewrite |
| POST `/workflows/{id}/revisions` | expected_version, idempotency_key, reason; atomically publish |
| GET `/workflows/{id}/revisions` | limit/cursor; immutable history |
| GET `/workflows/{id}/revisions/{revision_id}` | immutable definition/digest |
| POST `/workflows/{id}/archive` | expected_version, reason; stop editing/publication/new snapshot requests |
| POST `/workflows/{id}/restore` | expected_version, optional revision_id, reason; copy revision/current draft into a new draft version, clear archive |
| GET `/settings` | project_id; project-wide settings/version/epochs |
| PATCH `/settings` | project_id, expected_version, complete settings object, reason |
| POST `/settings/revoke` | project_id, expected_version, reason; advance authorization epoch |
| POST `/settings/restore-epoch` | project_id, expected_version, reason; advance authorization and restore epochs; no backup procedure |
| GET `/audit` | project_id, optional workspace_id filter, limit/cursor; scoped screened JSON export |

Validation endpoints return `data.valid`, bounded sanitized `data.errors` and
`data.truncated`, with digest on success. Closed error-v1 is not extended with
validator errors. Invalid create/save/publish uses fixed422 error; missing or
inaccessible scope/object is generic403; stale versions, changed key reuse and
invalid/stale/tampered cursors are409; quotas429; unavailable live authority503.
No run-start HTTP endpoint is introduced; a draft identifier cannot satisfy the
published-revision snapshot port.

## Publication and immutable storage

Workflow rows hold a current canonical draft, digest, positive optimistic version,
archive flag and actual scope. Published rows retain exact canonical bytes/digest,
revision number, verified publisher, request digest and hash of idempotency key.
Uniqueness is `(workflow_id, revision_number)` and publisher/key for publication.
A request digest binds workflow, expected draft version, definition digest and
reason; replay of the same key/request returns the same revision after live auth,
while altered payload conflicts. Key identity remains bound to the original
request, so subsequent draft edits cannot be published under that key. Publish
revalidates schema, scope, screening and admitted profiles inside its transaction.
Successful publication advances the optimistic draft version in the same transaction, so two different keys using one expected version cannot both publish. Replay looks up the original publisher/key first after scope authorization and computes the incoming request digest using that stored revision’s definition digest, not today’s draft; identical retries after edits still return the original revision. No update/delete API for published rows; database guards reject revision mutation
and audit update/delete through ordinary application SQL. DB/host administrators
remain outside tamper-proof guarantees. Parent deletion cannot erase history.
Publication checks both the returned revision and the updated draft envelope before
commit: a version gaining a digit must not leave a previously readable draft over
the transport ceiling. Such publication rejects atomically with 429.

Archive and restore require expected draft version and append audit in the same
transaction. Restoring any old revision copies it to a new draft version; it does
not modify revision bytes or snapshots. Archiving blocks new starts/publications,
without claiming existing accepted external work stopped. Draft save/publication
and authorized history remain available while execution feature is disabled.

## Project policy and numeric limits

There is one policy row per project, no workspace override in this slice. Changing
it requires project-wide admin authority; a workspace-only admin cannot change
other workspaces' limits. Missing policy is disabled with version0. First explicit
update inserts version1; later updates compare/increment version. Authorization
and restore epochs start positive and never decrease. Every effective settings
change increments authorization epoch; disable/re-enable never revives old stamps.
Explicit revocation increments authorization epoch; restore invalidation increments
both. Revoked/changed memberships and disabled/changed principals independently
invalidate previously captured authority even without a settings edit.

Defaults/floors below are conservative configuration policy, not measured runtime
capacity. Collection TTL<=3600 and artifact<=8MiB reuse frozen limits; active-run
cap10 follows the architecture reference workload. Other ceilings bound storage
and authoring, not production throughput. Retention defaults to seven days and
never below one day; this exceeds maximum evidence/credential TTL and preserves
minimal operational headroom. Accepted/unknown work has independent protection.

| Setting | Default | Allowed range |
| --- | ---: | --- |
| enabled | false | strict boolean |
| max_workflows | 100 | 1–1000 |
| max_revisions_per_workflow | 100 | 1–1000 |
| max_active_runs | 10 | 1–10 |
| max_queued_runs | 100 | 1–1000 |
| max_artifact_bytes | 8388608 | 1–8388608 |
| retention_seconds | 604800 | 86400–31536000 |
| evidence_ttl_seconds | 3600 | 60–3600 |
| approval_ttl_seconds | 900 | 60–3600; <= evidence TTL |
| credential_ttl_seconds | 900 | 60–3600; <= evidence TTL |

Credential TTL is for future automation authority, not human-session lifetimes.
Central config may supply validated defaults for newly configured projects; it
never silently rewrites persisted live policy. Collection profiles are immutable
server-supplied RegistryContract data; default catalog stays empty. HTTP cannot
admit a profile. Qualified synthetic catalogs exercise collected snapshots only.
Reject ceilings below already retained workflow/revision counts. Remaining runtime
quota enforcement is owned by later consumers; bounded doubles prove the policy.

## Snapshot, live policy and retention ports

Export accepts only a published revision, typed input values and a concrete
workspace under live `automation.request` authority with feature enabled. Export
revalidates the revision and resolves values using Story16.3; collected sources
require immutable commit SHA and admitted profile. Uploaded sources explicitly
retain null repository/commit and the fixed advisory limitation. Each source step
is represented separately, including mixed-source workflows.

The immutable in-process snapshot carries exact revision/definition, validated
inputs and input digest, actual scope/environment, per-step resolved sources,
current automation/advisory policy and a live-authority stamp. Authoritative bytes
are immutable; returned typed views are fresh copies. Bound the combined export
at512KiB (definition + independently bounded inputs + policy/source metadata); it
is not a new wire message. Future v1 operation protocols carry bound digests.
No run is persisted. Later draft, policy or caller-object edits cannot alter bytes.

The stamp binds workflow/revision IDs, principal ID/authentication version, membership authorization
version, actual project/workspace and current policy authorization/restore epochs.
The `start` check also rereads the workflow archive flag, so archiving after export
blocks an unstarted snapshot; restoring later creates a new draft and does not
rewrite the exported revision. Existing accepted work retains reconciliation.
Existing policy_adapter_settings save/delete operations advance this project’s
automation authorization epoch and append a screened audit event in the same
transaction whenever they change a stored policy (including integration overrides).
A change-and-restore cannot revive old stamps. The snapshot retains exact prior
advisory-policy content; live checks additionally compare current effective policy
digest and deny corruption/out-of-band mismatch. This linkage changes no scoring
semantics and is inactive when no automation policy has been configured.
A shared policy consumer re-reads current principal/membership/project/epochs under
one authorized SQLite transaction for `start`, `claim`, `dispatch` and `consume`.
The consumer holds `authorized_session` through both the live check and its local
mutation, preventing check-then-act races. The policy checker requires that same
operation transaction and is an additional deny check; callers must authenticate
their own operation before invoking it. Human snapshot creation does this itself. Later machine owners must
also authenticate their own audiences and check their operation/attempt state;
the stamp is a deny-policy snapshot, not a credential or executable grant.

`read`/`reconcile` of accepted or unknown work remain available under current read
permission despite disabled feature or stale epochs. Revoked callers do not gain
reads; other authorized operators may reconcile. No API claims to stop a begun
external action. Retention policy doubles reject deletion while evidence protects
current pending authority, or any accepted/unknown external work. A permitted
retention reduction advances authorization epoch before any deletion can occur;
unsafe floors are rejected. No deletion worker, target registry or real grant is
implemented in this slice.

## Screening, audit and cursor contract

Before persistence/export, use existing content_security helpers on already
bounded typed structures, including metadata-context screening of keys/numbers
and configured credential literals. Reject changed/redacted definitions/inputs
rather than silently editing canonical meaning. Screen names/reasons before any
persistence or echo. Audit records contain verified principal/type/role, actual
scope, target/event, reason/time and before/after digests only; no raw definition,
input values, credentials or artifacts. Append audit and mutation atomically.
Application append-only is not host/DB-admin tamper resistance.

Lists use frozen cursor-v1 response fields and opaque tokens<=128 identifier
characters, stable descending `(created_at,id)` order, default25/max100 and live
authority on every page. Use monotonic internal row sequences for a fixed insert
snapshot even under equal timestamps/clock rollback. Tokens are HMAC-signed,
bound to principal/membership version, scope, route/filters, page size, snapshot
and last row, and expire within15minutes. A bounded per-process cursor store is
permitted for the singleton profile; restart/eviction makes cursors stale409,
never broadens scope. Maximum1024 retained cursor states. No new persistence table
is needed solely for pagination. Query filters apply before pagination/counts.

## Persistence and qualification ownership

Only four entity families: workflow/current draft, published revision, project
policy, append-only automation audit. Use opaque public IDs and internal monotonic
sequences; uniqueness/composite scope FKs and immutable-row guards are migrated.
Allocate the next Alembic revision after030; models/database bootstrap recognition
must fail closed on partial automation schema. Prove synthetic028(v1.4.0) copied-DB
upgrade through031, prior-head upgrade, interrupted/partial schema rejection,
rollback/reupgrade and existing-data preservation. Never touch the local app DB.

Packet owners: persistence agent (tables/repository/migration/bootstrap/tests),
root (contracts/service/snapshots/HTTP integration), bounded policy owner after
service packet (policy consumer/settings/retention proofs), independent reviewers
and qualification owner (scope/concurrency/secret/API audit/docs). Dependencies
remain packet-ordered; freeze this interface and fixtures before implementation.
