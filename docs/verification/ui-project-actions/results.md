# Project actions, navigation and local account settings — 2026-11-03–04

## User-visible changes

- Dashboard, History and shared-shell project menus now open one real native
  creation dialog. The existing project API owns validation and authorization.
  A confirmed refreshed project is selected and persists across reload/routes.
- Automation is always discoverable immediately **before Settings** on all three
  sidebars. Existing account, scope, policy and execution checks remain enforced.
- Settings includes Local account profile/origin/authorization/decision status,
  reused sign-in/sign-out and deliberate protected-host setup instructions.
  `/settings/account` remains compatible. The read-only configuration endpoint
  exposes no accounts, tokens, secrets or mutation authority.
- The normal image packages the existing protected identity CLI and passes through
  explicitly supplied nonsecret identity settings. Defaults remain disabled /
  legacy-evaluation; no account, membership or execution policy is auto-created.
- `docker-compose.approval-ui.yml` is a separately selected disposable Story16.9
  test profile. The normal Compose command never loads it. README/identity/UI
  docs now explain the distinction and the local opt-in procedure.

## Verification

- `npm run ui:typecheck` — passed.
- `npm run ui:test` — 314 tests and 2 adapter/OpenAPI checks passed.
- `npm run ui:build` — passed. Existing bundle-size advisory remains nonblocking.
- `./.venv/bin/python -m unittest discover -q` — final 1,555 tests,
  3 expected skips, passed (678.527 seconds).
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`
  — 724 passed, 1 skipped, 2,348 subtests (292.22 seconds).
- Focused existing project/authorization/container contracts:19 passed.
- New configuration and existing auth tests:22 passed. Strict closed response,
  invalid-origin/secret redaction, no-store, no DB/account inspection and unchanged
  login/setup boundaries are covered. Constructor/consumer search completed and
  generated frontend OpenAPI types refreshed.
- Repository Ruff lint and formatting: passed,495 files. Focused Bandit auth
  route medium/high gate and diff checks passed.
- `BASE_URL=http://localhost:8080 npm run test:ui-review -- project-actions.spec.ts local-account.spec.ts`
  — **9 passed**,10.7 seconds, against a fresh nonroot Compose/tmpfs app with
  identity disabled and normal legacy-evaluation defaults. Includes real mobile
  project creation at760px, desktop/mobile CTA visibility, all3 switchers, duplicate
  correction, uncertainty/remount recovery, pending close, empty project list,
  bounded GET timeout, actual navigation order and inline Settings configuration.
  The separate isolated no-project sign-in wiring case uses explicit synthetic
  intercepted responses; it is not the real credential proof below.
- `BASE_URL=http://localhost:8080 LOCAL_ACCOUNT_UI_FIXTURE=/tmp/local-account-ui.json npm run test:ui-review -- local-account-live.spec.ts`
  — **1 passed**,1.8 seconds, using the same image recreated with local-development
  identity/origin in fresh tmpfs. The packaged CLI issued setup and bootstrapped
  one random synthetic account using private0600 files under a guard that rejects
  non-Docker, root, wrong profile/origin, non-tmpfs and nonempty account stores.
  Real server configuration, login, password clearing, logout and compatible account
  route were exercised. No request interception or credential recording was used.
- Keyboard/focus and axe checks passed in the checked dialog/settings journeys.
  Six [screenshots](screenshots/) cover1440/760. Final visual verdict:95/pass;
  see [visual-verdict.json](visual-verdict.json).

The temporary Compose definition lived outside the checkout; no additional root
Compose file was added for this proof. Real operator data was never mounted in
the test stack. Test account/password material stayed in the isolated container
and a private host fixture, both removed after proof.

## Review corrections

Independent blind, edge and acceptance review completed. Fixed and rechecked:

- Uncertain creation/list refresh state now survives same-identity route remounts.
  Resolving a matching read or explicitly acknowledging a confirmed-but-invisible
  result permits a new creation; no permanent lock remains.
- Identity changes clear checking/form state and fence late responses.
- POST and recovery GET are bounded15seconds. Timeout retains uncertainty and
  permits manual reread; no automatic POST retry occurs. Pending close never
  claims the server request was cancelled.
- Empty shared-shell project lists offer a real menu placeholder without demo data.
- Noncanonical project keys reject before POST; unrelated accepted identities are
  ambiguous, not selected.
- Wrapped switchers retain the exact existing topbar sizing rules. Mobile toolbar
  hiding now affects only the direct toolbar button, preserving the dialog's
  Create project action. Actual760px submission is browser-tested.
- Copied identity configuration preserves the operator's authorization mode until
  memberships are configured. First administrator/recovery remains host-only.

No unresolved introduced finding remains. The final default browser and actual
credential profile both passed after the last mobile CSS correction.

## Normal app restoration

The disposable stack was removed and normal
`docker compose up -d --build --force-recreate` completed. The original named
volume identity was compared before/after and is unchanged. Health returned200.
A fresh read-only browser checked actual localhost8080 sidebar ordering, inline
Local account and New project opening/cancellation with **zero POST requests**.
The running normal profile remains `disabled`; real operator account setup and
execution enablement are deliberate separate actions, guided from Settings.

Scratch logs: `/tmp/project-actions-complete-default-browser.log`,
`/tmp/local-account-complete-live-browser.log`, `/tmp/local-account-final-unittest.log`,
`/tmp/local-account-final-ci-shard.log`, `/tmp/project-actions-normal-rebuild.log`.
The retained records and screenshots above are portable proof; scratch paths are
local only. No operator account or project was created during the final normal-app check.

Completion and normal-app restoration recorded on2026-11-04 (Asia/Kolkata).
