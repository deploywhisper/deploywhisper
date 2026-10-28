# Scoped automation capabilities for the React UI

This read-only backend-for-UI prerequisite supports Story 16.7. It adds permission
and feature-state discovery to the existing automation APIs; it does not implement
the workflow editor or grant authority to execute a workflow.

## Request and response

`GET /api/v1/infra-automation/capabilities?project_id=1&workspace_id=1` uses the
existing verified human session cookie. Reads do not require CSRF; transport and
Origin checks remain the identity contract's responsibility. Responses use the
existing `data`/`meta` envelope and `Cache-Control: no-store`.

Example for a contributor in an unconfigured project:

```json
{
  "data": {
    "version": 1,
    "project_id": 1,
    "workspace_id": 1,
    "membership_version": 1,
    "policy_version": 0,
    "execution_enabled": false,
    "capabilities": ["automation.read", "automation.request"]
  },
  "meta": {
    "app": "DeployWhisper",
    "version": "1.4.0",
    "correlation_id": "synthetic-example"
  }
}
```

The strict closed projection version is independent of workflow v2, report v2 and
the earlier frozen protocol schemas. `project_id` is required; `workspace_id` is
optional. Both IDs are positive JavaScript-safe integers. A workspace-limited
membership must supply its exact workspace; omitting it does not broaden access.
A project-wide member may query the whole project (`workspace_id: null`) or one of
its workspaces. Missing/inaccessible projects and mismatched/missing workspaces
return the same generic 403 without disclosing existence.

Only four existing role permissions are projected, in this order:

| Project membership | Capabilities |
| --- | --- |
| admin | read, draft, publish, request |
| maintainer | read, draft, request |
| reviewer | read |
| contributor | read, request |
| read-only | read |

Each value has the `automation.` prefix. Global account-admin status and legacy
role/actor headers do not establish these permissions. The response does not expose
other members, session/CSRF material, settings administration, approval eligibility
or conditional run-cancellation authority.

## Freshness and mutation boundary

The service reads the live verified principal, exact scope membership and policy
under one existing `authorized_session` transaction. `membership_version` describes
that membership; `policy_version` is zero for an unconfigured policy and advances
on persisted policy changes. These are descriptive change indicators, not tokens
that may be presented instead of credentials. Every request rechecks live state.

`execution_enabled` comes from the actual automation policy; an unconfigured
project defaults off. Feature-off leaves permitted draft/save/publish and
historical reads available. A role can still possess `automation.request` while
execution is disabled. That permission alone cannot establish run eligibility.

The UI must discard prior-scope eligibility and forms on project/workspace or
identity changes. A failed refresh, network loss or unknown response must disable
consequential controls until fresh state is loaded. A successful read also does
not prove CSRF possession: login/rotation supplies transient CSRF and a full page
reload needs fresh login before mutations under the current identity contract.

Starting a preflight still requires a permitted immutable published revision,
concrete authorized workspace, validated inputs, enabled policy, live mutation
credentials/CSRF, `automation.request`, `analysis.submit`, supported artifacts and
available quotas. Existing server-side mutation checks remain authoritative even
if permissions, membership or policy change after this response.

The existing fixed automation errors apply: 401 for missing/invalid human identity,
403 for transport/scope/permission denial, 422 for invalid query parameters,
429 for bounds and 503 for unavailable/corrupt authority or policy. Duplicate and
unknown query parameters are rejected. Errors do not reflect submitted values.

## Story 16.6 continuity and validation boundary

Story 16.6 already supplies `/preflights`, `/runs`, run steps/logs and
`/runs/{id}/reports` with relational provenance and durable `evidence_status`.
Step output/upload references expose screened artifact digests. Those responses,
immutable manifests/report links, shared analysis, admission guards and canonical
advisory reports are unchanged. This projection fills only the discovery gap;
static `/projects/roles`, admin-only memberships and draft-only settings reads
remain under their existing contracts.

No migration, dependency, authentication mechanism, role capability, report field
or frozen schema is changed. New API/service tests use synthetic temporary
databases; workflow and preflight regression suites cover existing behavior.
UI validation not applicable: no React screen, route, interaction or accessibility
semantics changes in this backend workstream. Actual browser qualification remains
part of Story 16.7.

See the [prerequisite specification](../../_bmad-output/implementation-artifacts/spec-16-7-backend-for-ui-capabilities.md)
for executed verification and review results, and [identity](identity.md),
[permissions](permissions.md), [workflows](workflows.md) and [preflight](preflight.md)
for the underlying contracts. Ship this support in a separate PR labeled
`backend-for-ui` before integrating the UI workstream.
