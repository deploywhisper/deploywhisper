---
title: Restore project creation and discoverable automation navigation
type: bugfix
created: '2026-11-03'
status: done
completed: '2026-11-04'
baseline_commit: bcbdc3304d0921e3973566e9621783fb3eb1f2fe
context: []
---

<frozen-after-approval reason="existing UI bug report; prior owner direction authorizes routine implementation choices">

## Intent

**Problem:** The project switcher renders a New project button without a handler
on Dashboard, History or shared-shell screens. Automation is implemented but its
navigation disappears for the default disabled identity profile, making shipped
screens look absent after an ordinary Compose rebuild.

**Approach:** Reuse the existing project-creation API through one shared switcher
wrapper and an accessible native dialog. Place Automation immediately before Settings and link its existing route
even before account/policy readiness. Add an inline Local account section inside
Settings with the existing sign-in/out flow and actual read-only identity
configuration, plus deliberate trusted-host setup instructions. Explain disposable test Compose profiles separately
from normal operator deployment.

## Boundaries & Constraints

**Always:** Preserve real API validation, named admin/CSRF in verified mode,
legacy evaluation semantics, identity-scoped query caches and selected project.
Use fixed safe error copy and the existing visual primitives/tokens. Creating a
project does not invent a workspace or grant project permission. Actual Automation
APIs continue enforcing identity, membership, execution and evidence gates.

**Ask First:** New server authorization, automatic feature enablement or changes
to real operator data beyond the user's explicitly submitted project creation.

**Never:** Auto-enable privileged execution, bootstrap accounts, fabricate roles,
replace the normal data volume with disposable fixtures, or expose credentials.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| --- | --- | --- | --- |
| Project creation | Valid key/name in permitted profile | One POST, refreshed project list and newly selected project | Inline safe errors retain input |
| Search prefill | Search text then New project | Useful display-name/key prefill, editable fields | Empty input cannot submit |
| Verified access | Named admin and current CSRF | Header from identity context; existing API decides authority | Missing/revoked authority denies without role fallback |
| Duplicate/validation | Existing key or invalid request | No fake success or blind POST retry | Fixed correction message |
| Response ambiguity | Lost/malformed response or unmount during POST | No automatic resubmission; reread existing projects before retry | Report uncertainty and retain form state |
| Cancel/keyboard | Escape, Cancel, Tab/ShiftTab | Native modal isolation, focus restoration, no POST | Pending request never presented as undone |
| Automation setup | Signed out, disabled execution or unavailable scope | Existing route stays discoverable, displays current access/setup guidance | No protected data or action authority from menu visibility |

</frozen-after-approval>

## Code Map

- `frontend/src/components/ui/ProjectSwitcher.tsx`: presentational search/action callback.
- `frontend/src/screens/ProjectMenu.tsx`: shared API-bound wrapper/dialog.
- `frontend/src/screens/{Dashboard,History,Phase6Shell}.tsx`: real switcher callers.
- `frontend/src/api/dashboard.ts`: existing project reads plus new typed POST adapter.
- `frontend/src/screens/AutomationNavigation.tsx`: discoverable existing route.
- `api/routes/projects.py` / `services/project_service.py`: unchanged authority and creation contract.
- `docker-compose.approval-ui.yml`: explicitly selected disposable browser fixture.
- `docker-compose.yml`: normal operator image and persistent volume.
- `frontend/src/screens/Settings.tsx` and `AccountAccess.tsx`: inline/reused Local account flow.
- `api/routes/auth.py` and `api/schemas.py`: nonsecret read-only runtime identity configuration.

## Tasks & Acceptance

**Execution:**
- [x] Add typed project POST adapter and shared accessible creation wrapper; wire all3 production switchers.
- [x] Keep Automation visible immediately before Settings in all3 sidebars; retain all real route authorization.
- [x] Add Settings Local account sign-in/status independent of project/settings-summary access; reuse existing credential logic and preserve /settings/account compatibility.
- [x] Add nonsecret read-only identity configuration endpoint; never expose account existence/credentials or add HTTP bootstrap/profile mutation.
- [x] Add meaningful UI/API-adapter regression and composed browser journeys for actual creation, selection, keyboard and setup navigation.
- [x] Document why fixture screenshots differ from default configuration and how operator identity/membership/policy setup works; pass through opt-in nonsecret Compose identity settings and include the existing protected CLI in the runtime image so the documented bootstrap can actually run.
- [x] Run typecheck/unit/build, composed browser/axe/keyboard/screenshots and independent review; record limits.

**Acceptance Criteria:**
- Given normal Compose and disabled identity, New project creates a real selected project via the existing API and Automation opens its existing setup route.
- Given verified authorization, the same UI cannot create a project without current named admin mutation credentials.
- Given any production switcher, its action opens the same working form rather than a no-op.
- Given default deployment, rebuilding does not implicitly seed test accounts or enable execution.

## Spec Change Log

- 2026-11-03 owner steering: place Automation immediately before Settings and put local account login/identity configuration inside Settings. Read-only runtime status plus reused sign-in and operator setup meet this intent without anonymous configuration writes or HTTP bootstrap. Preserve the completed project-creation fix.

## Verification

- `npm run ui:typecheck`, `npm run ui:test`, `npm run ui:build`.
- Existing project API/authorization tests; no Python behavior changes.
- Composed FastAPI app at localhost8080: actual create/select, Automation route, modal keyboard, safe errors and axe; scoped synthetic data only.
- Visual verdict before any additional visual edit. Preserve operator container/volume and restore it after isolated proof.


## Completion Evidence

Read-only status API, normal Compose defaults/opt-in, runtime CLI and UI actions
are implemented. Final verification:314 UI tests+2 checks, root1,555 tests,
API/CLI/infra724 tests+2,348 subtests,9 default composed browser journeys and1
actual configured-account login/logout. Ruff495 and focused Bandit passed.
Normal app rebuilt, original data volume preserved and health200; no real account
or project was created by verification. Detailed results:
[results](../../docs/verification/ui-project-actions/results.md).

## Suggested Review Order

**Entry actions**

- Shared dialog, identity-scoped ambiguity and bounded manual recovery.
  [ProjectMenu.tsx:24](../../frontend/src/screens/ProjectMenu.tsx#L24)

- Retain pending intent across routes and fence identity changes.
  [projectCreationSession.ts:25](../../frontend/src/screens/projectCreationSession.ts#L25)


**Local account and authority**

- Settings remains usable before project or settings-summary access.
  [LocalAccountSection.tsx:54](../../frontend/src/screens/LocalAccountSection.tsx#L54)

- Reuse credential handling without storing passwords or restoring lost CSRF.
  [AccountSessionFields.tsx:6](../../frontend/src/screens/AccountSessionFields.tsx#L6)

- Read only sanitized deployment configuration; never issue setup authority.
  [auth.py:141](../../api/routes/auth.py#L141)


**Bindings and verification**

- Mount Local account independently of protected settings summary.
  [Settings.tsx:356](../../frontend/src/screens/Settings.tsx#L356)

- Preserve disabled defaults and deliberate nonsecret opt-in.
  [docker-compose.yml:17](../../docker-compose.yml#L17)

- Exercise real creation, mobile submission and response-loss recovery.
  [project-actions.spec.ts:28](../../frontend/e2e/project-actions.spec.ts#L28)

- Verify actual protected CLI bootstrap and real backend login/logout.
  [local-account-live.spec.ts:27](../../frontend/e2e/local-account-live.spec.ts#L27)
