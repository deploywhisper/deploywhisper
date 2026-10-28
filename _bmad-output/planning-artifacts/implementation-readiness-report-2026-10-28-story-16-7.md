---
assessmentScope: Story 16.7 only
status: backend-prerequisite-verified-ui-preparation-pending
---

# Story 16.7 scoped implementation readiness

## Subsequent authorized prerequisite work

The maintainer subsequently authorized implementing the necessary support in a
separate backend-for-UI workstream on 2026-10-28, with explicit Story 16.6
cross-verification and regression testing. The original assessment below records
the entry condition; it is superseded for support-contract status by the
[prerequisite specification](../implementation-artifacts/spec-16-7-backend-for-ui-capabilities.md)
and [implemented API contract](../../docs/infra-automation/ui-capabilities.md).
The separate branch is `feature/16-7-backend-for-ui-capabilities`. Full Story 16.7
UI acceptance remains outstanding; no UI task is marked complete by this support.

The prerequisite is implemented and independently reviewed. Final verification
passed: full local CI 2,607 tests, final root smoke 1,161 tests, exact affected shard
685 tests /2,267 subtests, production Python 3.11 new-test suite 20 tests and actual
app smoke. Existing static-analysis debt and the initial smoke-test retry are
disclosed in the [verification record](../../docs/verification/infra-automation/16-7-backend-for-ui/results.md).
Resume full story preparation using the concrete API contract; keep separate
backend/UI delivery and the outstanding UI/browser acceptance boundary.

2026-10-28. The requested `bmad-dev-story` entry assessment inspected the complete
story, project context, sprint tracker, delivered lifecycle/preflight/identity
contracts, feature UX, frozen composition review and current route/service models.
An independent native read-only review reached the same blocker below. No feature
implementation or browser qualification is claimed.

## Earlier gates

The original story preparation predates the accepted dependency implementations.
Stories 16.0–16.6 are now done in `sprint-status.yaml`. RFC 0001 records maintainer
acceptance and qualification; workflow authoring subsequently adopted v2.
Stories 16.4 and 16.6 record independent review and actual verification. Their
original unresolved status is no longer the reason to hold this story.

Current evidence: [RFC](../../docs/rfcs/0001-infra-automation-preflight-and-handoff.md),
[16.4](../implementation-artifacts/16-4-scoped-workflows-and-immutable-revisions.md),
[16.6](../implementation-artifacts/16-6-uploaded-artifact-preflight-and-report-linkage.md),
[tracker](../implementation-artifacts/sprint-status.yaml).

## Blocking API support gap

Packet 1 requires capabilities; AC3/AC4 require actual permitted actions and fresh
authorization after project changes, conflicts or connection loss. No current
resource provides the verified caller's scoped automation capabilities together
with execution feature state:

- `api/routes/projects.py::get_project_roles` returns static role definitions.
- `services/project_service.py::list_project_memberships` requires project-wide
  `role.manage`; it cannot supply ordinary readers' own eligibility.
- `services/infra_automation_policy.py::get_settings` requires `automation.draft`
  at project scope. Authorized read-only and workspace-limited readers cannot
  use it to discover disabled mode.
- Workflow/run reads return resource state, without the caller's publication or
  request capabilities. Successful history reads do not establish mutation authority.

Do not infer authority from global `is_admin`, caller role headers, static role
definitions or successful list reads. The server continues checking every mutation;
the missing projection is needed to render accurate controls and recovery state.

AGENTS.md explicitly says to stop and raise flow/validation/API-contract gaps and
requires backend-for-UI behavior to ship in its own labeled PR. Story 16.7 Packet 5
repeats this delivery boundary. A separate additive support workstream must resolve
and review the contract before the full UI story is promoted. No route name,
response schema or backend implementation is adopted by this assessment.

## Concrete prerequisite acceptance proposal

The separately reviewed read contract should provide only the caller's effective
automation capabilities, actual project/workspace scope and feature state. Resolve
these from the existing live session, membership and policy within one operation;
use the existing generic denial/error and no-store conventions. A response is
descriptive state, never a mutation credential or authorization grant.

Required proof: anonymous/revoked/expired callers deny; inaccessible scopes do not
leak existence; project-wide and workspace-limited memberships remain distinct;
read-only users can discover disabled state while retaining authorized historical
reads; contributor/publisher controls reflect actual capabilities; membership,
policy and project changes invalidate stale eligibility. Existing service mutation
checks remain authoritative. Review the exact API and tests before UI binding.

## Bounded implementation handoff

| Packet | Ownership/output | Relative effort |
| --- | --- | --- |
| Separate prerequisite | Backend-for-UI owner: scoped capability/feature-state read contract, tests and labeled PR | Medium |
| 1 | Integration owner: generated schema, typed adapters, structured errors, cursor/conflict tests | Medium |
| 2 | UI owner: scoped lists, executable upload template, YAML validation/save/publish and revisions | Large |
| 3 | UI owner: ordered attempts, bounded logs, artifact digests and relational briefing links | Medium |
| 4 | Test/documentation owner: real API seed, composed keyboard/axe journeys and 1440/760 screenshots | Large |
| 5 | Identity UI owner: sign-in/logout/expiry/recovery, transient CSRF and safe return routes | Medium |

These are relative planning judgments, not measured delivery commitments. Preserve
the stable story ID, ordered packet dependencies and separate backend/UI branches.
Independent review outcome: earlier dependencies cleared; full readiness remains
conditional on the concrete support contract and delivery boundary above.

Additional binding constraints from implemented APIs:

- Session reads return a principal without CSRF. Keep login/rotation CSRF in
  memory; reload can resume historical reads, while mutations require fresh login
  unless a separately reviewed session-resumption contract is added.
- Use the executable `uploaded_intake` → `shared_analysis` subset: one artifact
  set and one analysis. Create/save reject invalid definitions; keep invalid
  candidates transiently in the editor and use server diagnostics before saving.
- Provenance is relational through `/runs/{id}/reports`; do not invent report-v2
  provenance fields or an unimplemented reverse relation. Step output/upload
  digests identify artifacts; workflow/input/snapshot hashes are different facts.
- Preserve the sanctioned shell, Dashboard budget and permanent report URLs.
  Browser acceptance still requires Compose, actual APIs, keyboard/axe and screenshots.

## Verification and BMad handoff

Read-only source inspection and independent readiness review completed. Application
code/configuration is unchanged; unit, integration, Compose and browser tests were
not run and no implementation checkbox is checked. Documentation validation:
`git diff --check` (record actual result in the story).

BMad Help recommendation: resolve the separate backend-for-UI contract first,
then refresh Story 16.7 through `[CS] bmad-create-story` with current dependencies
and scoped readiness; resume `[DS] bmad-dev-story`, followed by `[CR] bmad-code-review`.
Story 16.7 remains backlog until the blocker is resolved.
