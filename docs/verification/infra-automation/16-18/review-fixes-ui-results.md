# Story 16.18 R6 — settings draft preservation

The final UI fix preserves same-project/session drafts through policy changes and
temporary membership/policy read failures. The form stores its original policy
version and authorization/restore epochs. A newer server policy pauses saves;
the existing explicit refresh replaces values, reason and base policy only after
fresh administrator membership and policy reads both succeed.

Project/session changes and definite GET or PATCH 401/403 discard the draft.
A PATCH denial also latches the parent section closed despite cached successful
GET data; explicit fresh membership **and** policy checks are required to reopen
it. Save-side 409/422/503 retain the draft and existing manual-refresh behavior.
No save is automatically repeated. Existing fields, theme classes and registered
target inspection remain the approved scope; no dependencies or production
Python code changed in this UI fix.

## Final verification

All browser URLs used the production-built FastAPI app at
`http://localhost:8080/`, using root SPA routes. Final image:
`sha256:2c652ba689e6c6d6e02d7be7dc054ea4cbc093c46bb87341846824acc1a5c3e8`.

| Command | Final result |
| --- | --- |
| `npm run ui:test` | 512 tests in 30 files; 2 compatibility checks passed. Includes 20 settings component cases. |
| `npm run ui:typecheck` | Passed. |
| `npm run ui:build` | Passed; existing large-chunk advisory remains. |
| `./.venv/bin/python -m pytest tests/test_infra/test_settings_ui_fixture_guard.py -q` | 4 passed. |
| Ruff check/format for the fixture and guard tests | Passed. |
| `./.venv/bin/python -m bandit scripts/settings_ui_fixture.py -ll -ii -q` | Passed; existing harmless unused-nosec warning. |
| `docker compose -f scripts/compose-story16-18.yaml build` | Final image built with the frontend production stage. |
| `BASE_URL=http://localhost:8080 SETTINGS_UI_FIXTURE=<private export> SETTINGS_UI_CONTAINER=<verified disposable container> npm run test:ui-review -- infra-automation-settings.spec.ts` | 2 passed in 24.1s; journeys 10.8s and 12.0s. |
| `BASE_URL=http://localhost:8080 SETTINGS_OUTCOME_UI_FIXTURE=<private export> SETTINGS_OUTCOME_UI_CONTAINER=<verified disposable container> npm run test:ui-review -- infra-automation-settings-outcomes.spec.ts` | 1 passed in 4.7s; journey 3.6s. |
| `git diff --check` | Passed. |

The new browser journey uses a fresh private Chromium profile attached through
loopback CDP with `noDefaults: true`. Normal Playwright focus emulation keeps all
tabs visible, so it cannot prove TanStack's native visibility-refetch behavior.
Actual tab activation now proves `hidden` → `visible`, followed by actual policy
and membership HTTP requests. It does not dispatch synthetic app events. The
browser targets only the local composed app and `about:blank`; background
networking is disabled, and its temporary profile is removed afterward.

The source-controlled, nonroot/tmpfs-guarded fixture can return only HTTP 503 for
selected synthetic project policy/membership GETs. Its operator-only failure
file is owner-0600, bounded, single-link and opened without following symlinks;
there is no HTTP fixture-control endpoint. The PATCH 403 regression changes only
the outgoing CSRF header and reaches the real server guard. Successful responses
and authority are never mocked. The original approved/accepted-operation fixture
still uses explicitly synthetic material/receiver ports, so that journey does
not qualify a real external action or production receiver.

The journeys cover retained values/reason during native focus refetch, server
version changes, separate policy/membership 503s and recovery; blocked saves;
explicit replacement with the latest policy; a real save using that reviewed
base version; stale-CAS 409 and unsafe-limit 409; 422 validation; denied-save
draft clearing and fresh-check recovery; dirty project switching; actual logout
401; nonadministrator absence/403; retained removed-content guidance; and
feature-off accepted-operation reconciliation.

## Regression and visual evidence

Before implementation, 7 of the first 11 component tests failed, including the
unsafe stale-values/new-version submission and stale explicit-refresh closure.
The later independent PATCH-denial check reproduced 2 failures with the other
15 cases passing. The final 20 component cases all pass in the 512-test suite.

The final 36 screenshots cover 1440px and 760px viewports; 12 new captures show
the retained draft during server changes and temporary policy/membership
unavailability. Keyboard journeys pass, with zero critical/serious axe findings.
The pre-edit persisted references were inspected at commit
`0716460356571aa6c5267238c910cb2adbdf3337`. Final composed captures retain the
existing shell, typography, grid, field spacing and controls. Required status
paragraphs add vertical space without layout overlap. [Visual verdict: 97/pass](review-fixes-ui-visual-verdict.json).

Representative final images: [changed server policy, 1440px](screenshots/settings-draft-changed-1440.png),
[changed server policy, 760px](screenshots/settings-draft-changed-760.png),
[unavailable membership, 1440px](screenshots/settings-draft-membership-unavailable-1440.png),
and [unavailable membership, 760px](screenshots/settings-draft-membership-unavailable-760.png).
Source/artifact digests and exact final results are in
[the structured record](review-fixes-ui-results.json).

Earlier browser attempts exposed a sibling-401 cancellation race in the test's
response waiter and an unnecessary final login exhausting the real authentication
attempt budget. Those test issues were repaired. Image `0016a092…` then passed
three journeys, but preceded the independent PATCH403 finding and is not final
proof of that repair. All three journeys were repeated on the final image above.

Both disposable Compose projects and their exported private host fixtures were
removed. The original container
`5970d092f40105574b40ba43996b4af1b770a85697f085318d1fb4360c83b31f`
was preserved intact and restored running/healthy with HTTP 200 after each lane.
This bounded UI repair does not close the independent human pilot or broader
production qualification gates in the story.
