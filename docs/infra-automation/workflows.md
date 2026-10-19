# Scoped workflows and immutable revisions

Story 16.4 adds authenticated workflow authoring, immutable publication, project
settings and screened audit export. Use [local identity](identity.md) and
[project permissions](permissions.md) first. Caller role headers, share links and
synthetic machine identities do not authorize these operations. Browser mutations
require the existing session cookie, allowed origin and CSRF token.

The [lifecycle contract](workflow-lifecycle-contract-v1.md),
[request/snapshot schema](../../schemas/infra-automation/workflow-lifecycle-v1.json)
and application OpenAPI describe the exact fields. Definitions use
[workflow major 2](workflow-schema.md); historical frozen-v1 artifacts stay unchanged.
The application still has no workflow run engine or collector in this slice.

## Create, validate and publish

All paths below begin `/api/v1/infra-automation`. Use real project/workspace IDs
from the existing project APIs. Their exact decimal strings belong inside a
workflow-v2 definition; quote them in YAML. Scope is fixed when the workflow is
created. A null workspace creates a project-wide draft and requires whole-project
membership; it cannot bypass a workspace restriction.

An admin or maintainer can create a valid, nonexecutable draft:

```json
{
  "project_id": 100,
  "workspace_id": 100,
  "name": "Reviewed preflight",
  "definition": "workflow_version: 2\nproject_id: '100'\nworkspace_id: '100'\nenvironment: production\nsteps:\n- id: intake\n  kind: uploaded_intake\n  depends_on: []\n  source: {kind: uploaded}\n",
  "reason": "Create preflight draft"
}
```

Send it to `POST /workflows`. `GET /workflows/{id}` returns the canonical draft,
digest, `draft_version` and archive state. `PUT /workflows/{id}/draft` accepts
`expected_version`, replacement `definition` text and a reason. Scope changes and
unsupported definitions reject; stale versions return 409.

`POST /workflows/validate` accepts project/workspace and candidate definition
without storing it. `POST /workflows/{id}/validate` accepts `expected_version` and
an optional candidate definition; omission validates the stored draft. Validation
does not rewrite the draft. Its success envelope contains `valid`, `digest`,
sanitized field diagnostics and `truncated`; an invalid definition has
`valid:false`. Syntax values and submitted secrets never appear in diagnostics.

Only a project admin may publish:

```json
{
  "expected_version": 1,
  "idempotency_key": "reviewed-release-001",
  "reason": "Publish reviewed preflight"
}
```

Send this to `POST /workflows/{id}/revisions`. Publication revalidates the current
draft, inserts one numbered immutable revision, advances the draft version and
appends audit within one SQLite transaction. Concurrent requests using one
expected version cannot both publish under different keys. An identical key and
request returns its original revision even after later draft edits; changing the
workflow, expected version or reason under that publisher/key returns409.
Refresh the workflow before the next edit to obtain its current version.

Read published content through `GET /workflows/{id}/revisions` or
`GET /workflows/{id}/revisions/{revision_id}`. Ordinary application SQL and APIs
cannot update, delete or replace published revision rows. A draft ID never
satisfies the published-revision snapshot port. No `/runs` start endpoint is
installed by this story.

## Archive and restore

Admins archive with `POST /workflows/{id}/archive`, supplying `expected_version`
and a reason. Archived workflows cannot be edited, published or exported for a
new start. They and their published history remain readable to authorized members.

`POST /workflows/{id}/restore` accepts the current `expected_version`, a reason
and optional `revision_id`. It copies that workflow's revision—or its current
draft when omitted—into a new draft version and clears archive state. It never
rewrites a published revision or an existing exported snapshot. The live start
check rejects a snapshot exported before an intervening archive while the
workflow remains archived. Archiving does not claim that an accepted external
action stopped, and is not evidence that pending artifacts can be deleted.

## Configure execution policy

Feature execution defaults off. Authoring, publication and permitted history
remain available while off. Settings are project-wide in this slice; a
workspace-restricted administrator cannot change another workspace's policy.
`GET /settings?project_id=100` requires an admin or maintainer. All settings
mutations and audit export require a scoped admin.

Read settings, retain all returned `settings` fields, modify the desired values,
then send `PATCH /settings` with `project_id`, `expected_version`, the **complete**
settings object and a reason. Partial replacements reject to avoid accidentally
resetting safety values. A new project's version is 0; its first explicit update
creates version 1. Merely changing environment defaults does not enable execution
or overwrite an existing persisted policy.

The configuration contract has bounded workflow/revision counts, future run/queue
quotas, artifact bytes, retention and evidence/approval/credential TTLs. Retention
is at least one day; evidence TTL is at most one hour; approval/credential TTLs
cannot outlive evidence. The reference active-run cap is 10, not a throughput
promise. Runtime queue and execution enforcement remain with later consumers.
Credential TTL concerns future automation credentials, not human login sessions.

These environment-backed values seed unconfigured defaults only:

| Setting | Default |
| --- | ---: |
| `DEPLOYWHISPER_AUTOMATION_MAX_WORKFLOWS` | 100 |
| `DEPLOYWHISPER_AUTOMATION_MAX_REVISIONS_PER_WORKFLOW` | 100 |
| `DEPLOYWHISPER_AUTOMATION_MAX_ACTIVE_RUNS` | 10 |
| `DEPLOYWHISPER_AUTOMATION_MAX_QUEUED_RUNS` | 100 |
| `DEPLOYWHISPER_AUTOMATION_MAX_ARTIFACT_BYTES` | 8388608 |
| `DEPLOYWHISPER_AUTOMATION_RETENTION_SECONDS` | 604800 |
| `DEPLOYWHISPER_AUTOMATION_EVIDENCE_TTL_SECONDS` | 3600 |
| `DEPLOYWHISPER_AUTOMATION_APPROVAL_TTL_SECONDS` | 900 |
| `DEPLOYWHISPER_AUTOMATION_CREDENTIAL_TTL_SECONDS` | 900 |

Every effective settings change advances the authorization epoch atomically with
audit. `POST /settings/revoke` advances it explicitly. `POST
/settings/restore-epoch` advances both authorization and restore epochs; both take
project ID, expected settings version and reason, and require an existing policy.
The latter is an invalidation port, not a database restore procedure. Restoring
old values cannot revive old stamps. Existing advisory-policy save/delete paths
also advance the configured project's epoch in the same transaction, including
integration overrides, without changing report-scoring semantics.

## Snapshot and consumer boundary

`services.infra_automation_service.export_run_snapshot` is an in-process port for
later run creation. It requires a published revision, validated inputs, an enabled
policy and a concrete authorized workspace. Its canonical bytes bind definition,
inputs, policy, scope, resolved source per step and live-authority versions.
Fresh typed views cannot mutate those authoritative bytes. Uploaded sources retain
explicit null repository/commit and their advisory limitation. Collected sources
need a literal immutable commit after substitution and a trusted admitted profile.
The default profile catalog is empty; no HTTP request can admit one.

The authority stamp is public comparison data, **not a credential**. A future
consumer authenticates its own operation/audience, enters `authorized_session`,
calls `check_live_policy` and performs its local mutation within that same reserved
transaction. The check rereads original principal/membership and current epochs
and policy digests; stale, disabled, revoked or unavailable authority denies new
start/claim/dispatch/consume. Each machine owner must additionally validate its
operation, attempt, fence, credential and deadlines.

Authorized read/reconciliation remains available for accepted or unknown work
despite a stale stamp or disabled feature. Revoked callers still lose access;
another currently authorized operator may reconcile. The retention predicate
always protects accepted/unknown work and current pending authority. Expired
pending evidence requires known invalidation before deletion is allowed. Missing
or corrupt authority cannot justify deletion. There is no deletion worker here.

## Audit, pagination and operational limits

`GET /audit?project_id=100` exports append-only, scoped events: verified actor/type/
role, actual scope, target, reason, time and before/after digests. It contains no
raw definition, input values, artifacts or credentials. Names/reasons and typed
definition/input structures pass the existing configured-literal and structural
secret screening before persistence. Recognizable secrets are rejected rather
than silently changing canonical meaning. Never put credentials in workflow
inputs; screening cannot identify every arbitrary opaque secret.

Workflow/revision/audit collections use default 25/max 100 pages, descending
`(created_at,id)` order and a fixed insertion snapshot. Opaque signed cursors bind
the authenticated principal, scope, filters and limit; membership is checked on
every page. Later inserts are excluded even if timestamps move backwards.
Cursors expire within 15 minutes. Restart or bounded-cache eviction makes them
stale 409; start a new first page. A page may be shorter to keep its response bounded.

HTTP JSON and workflow definitions have a 128-KiB ceiling and depth 16. Unknown
fields, duplicate keys, unsafe quantities and malformed values reject. Errors use
the frozen code/message vocabulary and only retryability/correlation details;
inaccessible and missing objects share a generic 403. Closed validation diagnostics
are returned in validation data, not added to the error envelope. Responses are
`Cache-Control: no-store`.

Migration `031_add_infra_workflows` adds only workflow, revision, policy and audit
families after 030. Startup rejects partial or damaged automation schema instead
of silently recreating authority/history. Parent scope deletion cannot erase that
history. Application guards are not tamper-proof against a host/database
administrator. Downgrade removes the new automation data; production backup,
restore and retention procedures remain Story 16.18 responsibilities. Upgrade and
rollback qualification here uses disposable synthetic database copies.

No React surface changes in this story: UI validation is not applicable.
