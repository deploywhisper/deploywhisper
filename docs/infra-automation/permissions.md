# Trusted project permissions — v1.5.0 / Story 16.2

Protected operations resolve a verified human session, a live server-owned
membership, a named capability, and the object's project/workspace in the same
SQLite transaction. Caller role, actor and scope headers cannot establish this
authority. A global identity administrator is not automatically a project member.
The shared authorization service protects API and direct service entry points.

This slice delivers memberships, authorization audit, protection markers and a
seeded decision-context port. Workflow/run/decision persistence, machine credential
issuance, browser account entry and production automation delivery remain later
story work. See [the identity contract](identity.md) for account/session setup and
[the frozen automation contract](contract-v1.md) for the wider release boundary.

## Role and capability contract

Membership roles are exact server-validated values. The following table lists
every current `PROJECT_ROLE_CAPABILITIES` capability. A check means the role has
the capability; live identity, scope, ownership and mutation checks still apply.
Maintainers do not implicitly receive publication authority.

| Capability | admin | maintainer | reviewer | contributor | read-only |
| --- | --- | --- | --- | --- | --- |
| `project.read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `project.manage` | ✓ | — | — | — | — |
| `workspace.read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `workspace.manage` | ✓ | ✓ | — | — | — |
| `analysis.submit` | ✓ | ✓ | — | ✓ | — |
| `report.read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `report.review` | ✓ | ✓ | ✓ | — | — |
| `report.share.manage` | ✓ | ✓ | — | — | — |
| `feedback.create` | ✓ | ✓ | ✓ | ✓ | — |
| `outcome.read` | ✓ | ✓ | ✓ | — | — |
| `outcome.manage` | ✓ | ✓ | — | — | — |
| `incident.manage` | ✓ | ✓ | — | — | — |
| `topology.read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `topology.manage` | ✓ | ✓ | — | — | — |
| `scanner.manage` | ✓ | ✓ | — | — | — |
| `settings.manage` | ✓ | — | — | — | — |
| `role.manage` | ✓ | — | — | — | — |
| `automation.read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `automation.request` | ✓ | ✓ | — | ✓ | — |
| `automation.draft` | ✓ | ✓ | — | — | — |
| `automation.publish` | ✓ | — | — | — | — |
| `automation.cancel` | ✓ | ✓ | — | ✓ | — |
| `automation.decision` | ✓ | ✓ | ✓ | — | — |
| `automation.admin` | ✓ | — | — | — | — |

An enabled membership with `workspace_id: null` covers the whole project,
including its workspaces. A non-null workspace restricts the membership to that
one workspace. There is one membership per principal/project, not a union of
multiple workspace roles. The workspace must belong to the project. Missing,
disabled, unknown-role, cross-project and stale-version authority denies.

A workspace member may see their parent project's metadata in project listings.
That does not authorize a project-wide operation whose workspace is null.
Workspace-restricted administrators therefore cannot manage project memberships,
project-wide settings, or global settings through that membership.

Cancellation requires `automation.cancel` and the authenticated requester as
owner; a scoped administrator can cancel another owner's work. Shared decisions
require both `automation.decision` and `report.review`, matching report and
decision-context scope, and a different authenticated reviewer from the requester.
The seeded `DecisionContext` is an internal server-owned integration port, never
an HTTP claim or a persisted approval record.

## Principal and audience separation

| Principal | Executable human-session boundary | Pure typed policy port |
| --- | --- | --- |
| human | Matching `human` audience, enabled account/session and live membership | Role capabilities above |
| service | Denied | Only role-permitted read/request with `service-request-v1` audience |
| agent | Denied | Only role-permitted read/request with `service-request-v1` audience |
| runner | Denied | Denied |
| receiver | Denied | Denied |

The pure `trusted_capability_allowed` function evaluates an already verified
principal; it does not verify credentials. Its service/agent rules are synthetic
contract qualification for future issuance. No real machine credential issuer or
resolver is enabled by this story. Nonhuman accounts cannot use a human session
even when a synthetic database session claims the human audience. Wrong audiences,
disabled principals, forged roles and caller-provided membership objects confer
no authority. Legacy `authorize_project_action` never grants `automation.*`.

## Operator profiles and initial membership

`DEPLOYWHISPER_AUTHORIZATION_PROFILE` is server configuration:

| Value | Behavior |
| --- | --- |
| `legacy-evaluation` (default) | Existing unprotected advisory analysis remains available; marked project/report data always requires verified membership. |
| `verified` | All project data requires verified membership. |
| Any other value | Authorization fails closed. |

Configure identity transport/origin and establish a named administrator using
[Story 16.1 setup](identity.md#first-administrator). Identity profile `disabled`
does not grant protected access. Existing projects are not assigned an implicit
administrator during upgrade.

Log in as a verified global identity administrator, then explicitly call the
membership bootstrap route for the existing project. It creates only that
administrator's own unrestricted `admin` membership and protects the project.
Bootstrap is permitted only if the project has no membership or authorization
audit history, including disabled memberships. Revoking the last administrator
does not reopen bootstrap. A fresh login is required after bootstrap because it
invalidates the caller's old sessions.

Subsequent assignment, reassignment and revocation require live unrestricted
`role.manage` in that project. Each successful change records audit, maintains a
monotonically increasing membership authorization version, increments the target
account's authentication version and revokes its sessions atomically. Revocation
disables the membership instead of deleting its history. The target must log in
again before using an updated grant. Global administrator status alone cannot
change an established project's membership.

`DEPLOYWHISPER_IDENTITY_DECISION_MODE` defaults to `shared`, which rejects requester
self-review and records `independent-approval` only for a distinct eligible human.
Server-selected `single-operator` requires exactly one enabled human account and
records `acknowledgement`. It never claims independent/four-eyes approval. Unknown
modes deny. A request body cannot select this mode.

## Membership API

Paths below are relative to `/api/v1/projects/{project_key}/memberships`.

| Method and suffix | Request | Successful `data` |
| --- | --- | --- |
| `POST /bootstrap` | Verified global administrator session, Origin and CSRF | Caller's first unrestricted admin membership |
| `GET` | Verified project administrator session | Membership list, including disabled memberships |
| `PUT /{principal_id}` | Session, Origin, CSRF; JSON `{role, workspace_id?: null}` | Created or updated membership |
| `DELETE /{principal_id}` | Session, Origin and CSRF | Disabled membership with incremented version |

Membership fields are `principal_id`, `project_id`, `workspace_id`, `role`,
`enabled` and `authorization_version`; successful envelopes include `data` and
`meta` with app/version/correlation metadata. PUT accepts only strict JSON with
the two documented fields, a recognized role and null or positive integer
workspace ID. Duplicate/unknown fields, wrong types, non-JSON content, malformed
encoding and bodies above 4,096 streamed bytes are rejected.

The [identity Origin, cookie and CSRF contract](identity.md#api-contract) also
applies to protected operations: mutations require exact configured Origin plus
`X-CSRF-Token` from the login/rotation response. Protected reads validate effective
transport and any presented Origin. Bearer/service credentials and duplicate
security headers/cookies do not substitute for the human cookie. Forged actor,
role and project headers cannot widen the persisted scope.

Protected-operation authorization failures return generic HTTP 403:
`{error: {code: "operation_unavailable", message: "Operation unavailable.",
details: {retryable: false, correlation_id}}}` with `Cache-Control: no-store`.
This includes missing/invalid authority and inaccessible objects, avoiding an
object-existence oracle. Identity endpoints retain their separate 401/403/503
contract. Invalid membership bodies use HTTP 400 `invalid_membership_request`.
Database failures never become grants; clients must re-read live state after
authority is restored rather than replaying an assumed permission.

## Protected-path inventory

A server-controlled `authorization_required` marker on a project or any report
protects the parent project's context and sibling reports. Deleting a marked
report promotes protection to the parent project's persisted flag in the same
transaction, so deleting the last marked report cannot reopen legacy access.
Request provenance, headers and share tokens cannot clear protection.

| Surface / alternate path | Enforcement |
| --- | --- |
| Analysis submission / persistence | Live `analysis.submit` before protected work and persistence; caller's legacy role cannot replace membership. |
| Report detail, exports, history, stats, toolchains, comparison | `report.read`; visibility filters run before pagination/counts/aggregation; comparison checks every report. Outcome-derived history fields, filters and trend aggregates additionally retain `outcome.read`. |
| Report single/batch deletion | `report.review` plus mutation credentials; batch checks all targets atomically before deletion. |
| Share creation / management | `report.share.manage` plus mutation credentials. |
| Shared report / legacy share URL | Live report membership; existing token/password requirements remain additional constraints, never authentication. |
| Artifact snapshots and exports | Live report database row is required even when a file exists; read uses `report.read`, save `analysis.submit`, delete `report.review`. |
| Finding feedback | Read visibility and `feedback.create` for mutation; protected actor/role derive from live identity/membership. |
| Deployment outcomes | `outcome.read` / `outcome.manage`; linked report and incident visibility are checked. |
| Project context / policy and inherited policy reads | Scoped `report.read`; project-wide writes require unrestricted `settings.manage`. |
| Global settings / provider administration | Global identity administrator plus unrestricted `settings.manage` in every protected project; in `verified` mode this includes every project, even without a marker. |
| Custom skill administration and installer / admin CLI | Same global guard for custom/installed status reads; mutation authority for save/install/update/remove. Installer checks before source fetch and again before file replacement; no CLI role or shell access establishes a session grant. |
| Incident reads, status, imports and mutations | Scope visibility plus existing `incident.manage` for management; linked report authority checked before exposing links. |
| Backtesting cached/uncached summaries and invalidation | Live `outcome.read` for outcome-derived calibration/aggregates, with linked evidence checks before cached results; explicit invalidation needs `outcome.manage`. |
| Scanner ingestion / evidence reads | `scanner.manage` for ingestion and `report.read` for reads in live scope. |
| Topology snapshots, graph/context and mutations | Live `topology.read` / `topology.manage` in scope. Protected drift reads return matching cached status or unavailable; explicit refresh requires `topology.manage` plus mutation credentials. |
| Project/workspace metadata, creation, membership administration | Live metadata visibility and relevant project/workspace capabilities; verified project creation requires global administrator. |
| Direct CLI/service and background entry points | Same service guards; absent credentials only allow unrelated unprotected legacy evaluation; background jobs skip protected context. |

Global configuration reads are also guarded when protected projects exist (and
in verified mode). In `verified`, every project participates in the global
membership check, including unmarked projects; a global administrator with no
membership in any one of them cannot administer shared settings or custom skills.
An internal provider configuration helper and runtime skill resolution remain
available for already authorized analysis orchestration. Global defaults must not
mutate protected projects through an unrelated namespace.

Outcome permission is independent of ordinary report permission. Contributors
and read-only members may read authorized reports, but report history, filters,
trends and calibration must not reveal outcome labels, counts or other
outcome-derived metadata without `outcome.read`. Aggregation and cache reuse
retain the same permission as direct outcome reads.

Reading protected topology drift does not fetch a remote source or persist a
fresh check. It returns a source-matching cached status when present, otherwise
an unavailable status explaining that an authorized refresh is required. Explicit
refresh is a mutation; background refresh excludes protected projects.

Custom-skill administration covers `get_custom_skill_statuses`,
`list_installed_skills`, `save_custom_skill` and installer install/update/remove
entry points. The direct `skills`, `skill list`, `skill install`, `skill update`
and `skill remove` CLI commands use those same guards and report generic denial
without a trusted session context. This story introduces no CLI login or
credential-forwarding mechanism for these commands. Unprotected legacy
evaluation remains available. Public registry catalog browsing, built-in skill
tests and linting an operator-supplied file do not grant custom-skill
administration or protected project authority.

## Persistence, audit and transaction behavior

Migration `030_add_project_memberships` follows `029_add_identity_lifecycle`.
It adds `authorization_required` booleans to `projects` and `analysis_reports`
(default false), `project_memberships`, and `project_authorization_audit`.
Memberships have opaque IDs, account/project foreign keys, a unique
principal/project pair, optional workspace, fixed role, enabled flag, positive
authorization version and UTC timestamps. A composite project/workspace foreign
key prevents a workspace from another project. Audit stores actor/optional target,
project/workspace, action, optional object reference, before/after JSON and UTC
creation time. It stores no raw credentials, tokens or infrastructure payloads.

SQLite `BEGIN IMMEDIATE` reserves the operation before reading identity,
membership and objects. Nested service operations reuse the transaction;
repositories flush rather than commit. A concurrent revocation either precedes
the operation (and denies it) or follows the completed authorized operation.
Mid-operation commit/replacement of the transaction is rejected. Reusable
credential contexts and response caches do not preserve stale grants.

Protected report provenance records the verified principal ID as its actor;
caller actor labels remain compatibility metadata only for unprotected legacy
reports. New report artifact writes register compensation with the outer
operation, so commit failure or a later enclosing rollback removes snapshots
before releasing the SQLite reservation. New report IDs also clear orphaned
snapshot directories before writing, including submissions without snapshots.

Topology collection authorizes and captures source state in a short transaction,
collects outside the database writer reservation, then rechecks authority and
source state before saving. Revocation or a concurrent source change rejects the
result. Nested topology reads use cached status; an external collection cannot
silently release a transaction owned by its caller.


Preserve a protected database backup before upgrade or an intentional rollback.
Incomplete authority schemas fail closed for repair. Downgrading to revision 029
removes membership/audit tables and protection markers: older code cannot preserve
these enforcement guarantees. Stop protected use before rollback, and do not
resume it without restoring and verifying authority. Restoring a database can
restore sessions and old permissions; it is not a revocation mechanism. Host and
database administrators remain inside the local trust boundary; tamper-evident
audit retention and restore qualification belong to later release work.

## Acceptance evidence and remaining qualification

`tests/test_services/test_project_permission_matrix.py` specifies expectations
independently of production capability constants. Its live matrix uses persisted
accounts, sessions and memberships in temporary SQLite, with one restricted
membership in project 1/workspace 1 and two workspaces in each of two projects.
Cancellation cells use the authenticated requester as owner; ownership and
decision separation are exercised independently in `test_project_authorization.py`.

| Matrix | Cases | Allowed | Denied |
| --- | ---: | ---: | ---: |
| Live principal × role × project × workspace × action (`5 × 5 × 2 × 2 × 7`) | 700 | 18 | 682 |
| Pure typed principal × role × action (`5 × 5 × 7`) | 175 | 34 | 141 |
| Wrong audience for every typed-policy cell | 175 | 0 | 175 |
| Unknown audience for every typed-policy cell | 175 | 0 | 175 |
| Disabled principal for every typed-policy cell | 175 | 0 | 175 |

Focused verification on 2026-10-13:
`./.venv/bin/python -m pytest tests/test_services/test_project_permission_matrix.py -q`
passed **3 tests and 1,400 subtests**, with zero unexpected authorizations or denials.
The seven actions are read/request/draft/publish/cancel/decision/admin. All five
existing roles and human/service/agent/runner/receiver principals are explicit.
The 700 live cells validate the authorization boundary; they do not claim an
implemented workflow publish/cancel/decision API or real machine enrollment.

Complementary regression files cover membership/bootstrap/audit and race orderings
(`test_project_authorization.py`), protected report/share/artifact behavior
(`test_report_authorization.py`), global/project policy and provider/skill settings
(`test_settings_authorization.py`), linked context/feedback/outcomes/scanner/topology
(`test_linked_authorization.py`), API credential propagation
(`tests/test_api/test_project_authorization_context.py`), and migration contracts.
The Story 16.2 Dev Agent Record owns final aggregate CI and independent review
evidence; this focused run does not substitute for those checks.

**UI validation not applicable:** this slice changes backend/contracts without
rendered UI changes. Production TLS/browser deployment, actual workflow/report
linkage, persisted approval delivery, machine issuance, audit retention and
restore qualification remain separate integration evidence.
