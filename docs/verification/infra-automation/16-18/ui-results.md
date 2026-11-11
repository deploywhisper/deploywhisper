# Story 16.18 automation settings UI

> Historical pre-fix record at `0716460`. Review-fix evidence is recorded in
> [review-fixes.md](review-fixes.md) and [review-fixes-validation-summary.json](review-fixes-validation-summary.json).
> Original results below remain scoped to their recorded image/source; current screenshots are identified by [screenshots.json](screenshots.json).

The independent UI branch `feature/16-18-automation-settings-ui` implements the
Packet 18.6 form against existing 16.4 policy and 16.10 target APIs. Its baseline is
`262f47b`. Final composed verification temporarily overlaid the owning backend's
210 frozen runtime/generated-schema files, including migration 042, the corrected
040 retention debit guard, SQLite-managed operator connection safety fix,
protected receiver recovery contracts and reviewed completion-resume handling.
Those exact files were backed up and restored afterward, keeping this UI branch
separate from backend product changes. This record does not close
all Story 16.18 acceptance or production qualification.

## Delivered behavior

- `/settings` resolves whole-project administrator membership through the existing
  protected API. Session, identity-epoch and selected-project changes remount the
  section. Denied policy/membership reads hide stale controls.
- Strict generated types and bounded adapters carry enablement, workflow/run/
  artifact limits, retention, evidence/approval/credential lifetimes, CAS version
  and a server-validated reason. Server authorization remains authoritative.
- Validation, definite conflicts, forbidden reductions, success receipts and
  ambiguous responses use bounded messages. Saves never automatically repeat.
  Controls require explicit refresh after a response before another save.
- Scoped paginated target selection shows canonical identity, environment,
  receiver, pinned workflow revision, enabled state and retained lock status.
  Denied list reads hide cached target details. No infrastructure credentials or
  credential-reference editing is introduced; target registration remains an
  operator mechanism.
- Existing Settings card/field/button/grid and20px section spacing are reused.
  No dependencies, fonts, icons, design tokens or production backend were changed
  by this UI branch.

## Executed validation

Commands ran in `/tmp/deploywhisper-story16-18-ui` using existing installed
frontend dependencies and `/Users/psaho01/deploywhisper/.venv/bin/python`.

| Command | Actual result |
| --- | --- |
| `npm run ui:typecheck` | Passed, including final overlaid generated API types |
| `npm run ui:test` | 493 tests in30 files passed;2 OpenAPI compatibility checks passed |
| `npm run ui:build` | Passed; existing large-chunk advisory retained |
| `python -m pytest tests/test_infra/test_settings_ui_fixture_guard.py -q` | 3 passed; host/root/persistent-volume seeding denied before loading fixture code |
| `python -m ruff check .` | Passed |
| `python -m ruff format --check .` | Passed: 586 original-worktree files; 598 files during final head 042 backend overlay |
| `python -m bandit scripts/settings_ui_fixture.py -ll -ii -q` | Passed; harmless unused-nosec annotation warning only |
| `git diff --check` | Passed |

The first boundary test failed because the new adapter did not exist, then passed
against implementation. Early browser runs exposed label names and incomplete
synthetic global-admin membership. A real migrated-DB purge then returned503:
the prior032 immutable-run guard rejected reclaimed-byte debits, which the
metadata-only retention fixture had missed. The owning backend corrected040's
exact tombstone-bound debit proof and added migrated-DB coverage. Only the final
passing runs below qualify the final backend.

## Final composed settings and post-purge proof

The preserved application container `5970d092f401` was stopped intact. Separate
nonroot Compose projects used disposable tmpfs SQLite data, explicit
local-development identity, synthetic named accounts and actual authenticated
APIs. Original application health200 was restored between lanes and at completion.

```sh
docker compose -f scripts/compose-story16-18.yaml up -d --build
# Wait for http://localhost:8080/api/v1/health ->200.
# Copy /tmp/settings-ui-browser-fixture.json from this disposable container
# to a new private0600 host file.
BASE_URL=http://localhost:8080 \
SETTINGS_UI_FIXTURE=/tmp/story16-18-ui-fixture.json \
SETTINGS_UI_CONTAINER=<verified-disposable-container-id> \
npm run test:ui-review -- infra-automation-settings.spec.ts
docker compose -f scripts/compose-story16-18.yaml down
```

Final result: **1 passed in 10.0s**, 9.1s inside the journey. It proved actual target
registration/list/details, keyboard access, local numeric validation, typed save,
stale-version409, unsafe workflow-limit reduction409, credential-lifetime422,
disabling with authorized history readable, selected-project cache clearing,
nonadministrator control absence and actual PATCH403.

The guarded fixture additionally performs **original INSERTs** of an explicitly
synthetic terminal historical run/manifest with8-day-old timestamps and a typed,
recomputed snapshot. No immutable row is backdated by UPDATE; no product/API clock
bypass or retention-floor reduction exists. The browser calls the real purge
endpoint, verifies its removed-content receipt/original digest, reads reports200
and renders the removed-content limitation plus new-preflight recovery guidance
after execution is disabled. The actual database retained exactly one tombstone,
one removed-content marker and one removal audit. This original-insert fixture
is not evidence of an8-day execution or old-version upgrade. It contains no
successful report; the browser proves explicit stale/removed evidence and report
absence rather than successful-analysis retention.

## Final approval-disable and reconciliation proof

```sh
docker compose -f scripts/compose-story16-18-outcomes.yaml up -d
# Wait for health200; export via the existing protected helper:
# docker compose -f scripts/compose-story16-18-outcomes.yaml exec -T \
#   deploywhisper python /tmp/outcome_fixture.py --export-fixture
# Copy the exported fixture to a private0600 host file.
BASE_URL=http://localhost:8080 \
SETTINGS_OUTCOME_UI_FIXTURE=/tmp/story16-18-outcome-fixture.json \
SETTINGS_OUTCOME_UI_CONTAINER=<verified-disposable-container-id> \
npm run test:ui-review -- infra-automation-settings-outcomes.spec.ts
docker compose -f scripts/compose-story16-18-outcomes.yaml down
```

Final result: **1 passed in 7.0s**, 5.9s inside the journey. Existing 16.11 protected
fixtures create an actual persisted reviewer approval, prepared handoff, consumed
grant and accepted receiver operation through real application services. Their
material/witness/carrier/receiver ports are explicitly synthetic. The browser
then disables through the settings form, follows SPA history and the explicit
run-workspace control, and executes real reconciliation POST200 while the feature
remains off. The operation version advances with the same dispatch acceptance;
receiver state remains accepted, verified completion remains unknown and the
canonical lock remains held. This does not prove an external action stopped or
qualify a live receiver.

## Images, source identity and cleanup

Both final lanes used production image:
`sha256:363f797bb98e1ca90f549892b28802d6589000e776505a6f21cefdc7e61c41df`.
Migration 042 and 040's `reclaimed_bytes` column were verified in the actual fresh
SQLite database. The [source manifest](ui-integrated-sources.json) records the 210
frozen runtime/schema hashes, UI/fixture hashes, exact image and results. Runtime
source drift during final proof was zero.

Twenty-four [screenshots](screenshots.json) cover1440×1000 and760×1000 with zero
critical/serious axe findings, keyboard journeys, focused receipts, post-purge
history and feature-off reconciliation. The [visual verdict](visual-verdict.json)
passed at94 against the existing Settings reference. Credential-entry traces,
videos and automatic failure screenshots were disabled. Private fixture files
were removed; all original UI-worktree backend/schema files were restored and
the preserved application was running with health200 after both projects were down.

Build/runtime: Node24.7.0/npm11.12.1 on the build host, Docker29.1.3, and
Python3.11.17/no Node executable in the application runtime.

## Changed files

Production UI: `frontend/src/screens/Settings.tsx`,
`frontend/src/screens/AutomationSettingsSection.tsx`, and
`frontend/src/api/infraAutomationSettings.ts`. Coverage: their two new frontend
unit files, `frontend/e2e/infra-automation-settings.spec.ts`,
`frontend/e2e/infra-automation-settings-outcomes.spec.ts`, and
`tests/test_infra/test_settings_ui_fixture_guard.py`. Disposable harness:
`scripts/settings_ui_fixture.py`, `scripts/compose-story16-18.yaml`, and
`scripts/compose-story16-18-outcomes.yaml`. This directory contains the results,
source manifest, visual verdict, screenshot manifest and 24 captures.

Receiver recovery credentials remain issued only by the protected operator CLI;
this work adds no browser credential form or HTTP issuance endpoint.

## Qualification limits

No live runner/receiver, production HTTPS, actual infrastructure credentials,
30-minute capacity run, self-service operator pilot, restored database or wider
network profile is qualified by these browser tests. The post-purge fixture uses
uploaded evidence and does not qualify a collected-provenance upload timeline,
raw custody erasure or an existing successful report-link purge. Keep those
owning acceptance/production gates explicit. No public write, commit, PR, merge,
production deployment or release was performed by this UI workstream.
