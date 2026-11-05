# Story 16.16 composed browser proof

The final real Compose journey passed: **1 test, 29.3s**, with zero axe critical/serious violations at 1440 px and 760 px. Ten screenshots cover invalid inventory, editor, explicit confirmation, available unit evidence and review-required evidence. Visual inspection against the established 16.7 workflow/run screens scored **94/100, pass**; see [the verdict](visual-verdict.json) and [screenshot manifest](screenshots.json).

## Executed boundary

The production Docker frontend build is served by FastAPI at `http://localhost:8080`. A guarded nonroot fixture seeds synthetic human identities into disposable tmpfs SQLite. The browser logs in using keyboard input, then real authenticated APIs publish a four-step uploaded workflow. The browser edits network/app inventory, receives located unknown-ID/cycle errors, confirms exact affected/prerequisite scope, saves a revision, supplies exact intake/analysis mappings and uploaded files, and starts the actual worker workflow. Both analyses succeed and persist separate advisory reports. Server responses prove deterministic two-wave order, retained map identity and combined evidence digest. The browser opens a briefing using Tab/Enter and reviews report tabs using arrow keys.

A subsequent real API inventory revision changes downstream source/path. The mounted run view observes `changed` and displays “Review required again” without a reload or run-version change. This is uploaded advisory proof: lock observations are `not_requested`; no collector, external receiver, approval provider or infrastructure action is claimed.

Keyboard traversal uses native Tab/Shift+Tab, keyboard text/checkbox/button input and native select typeahead. Chromium on this macOS host does not commit synthetic arrow-key native-menu selection; isolated native-control probes established typeahead works. No programmatic focus, selectOption, route mocks or DOM value mutation is used. File input content is synthetic fixture injection after proving Tab reachability. Credential traces, video and automatic failure screenshots remain disabled.

## Commands and runtime

```sh
docker compose -f scripts/compose-story16-16.yaml build
docker compose -f scripts/compose-story16-16.yaml up -d --build
# Wait for GET http://localhost:8080/api/v1/health -> 200.
# Copy /tmp/unit-ui-browser-fixture.json to a private temporary host directory;
# chmod 0600; never print fixture credentials.
BASE_URL=http://localhost:8080 UNIT_UI_CONTAINER=deploywhisper-story16-16-deploywhisper-1 UNIT_UI_FIXTURE=<protected-local-file> npm run test:ui-review -- infra-automation-units.spec.ts
docker compose -f scripts/compose-story16-16.yaml down
```

Docker 29.1.3; production Python 3.11.17; Node 24.7.0; Playwright 1.63.0. Verified image: `sha256:da75af8a43d94328089e507f809c6b7ee315395a1ed2371d7ac7c2a6a7350f18`. Backend base 82732d2 plus the reviewed uncommitted UI workstream at verification time. [Final command output](browser-verified.txt) is retained. Fixture Python lint/compile and repo-wide Ruff formatting passed before browser execution.

## Failure preservation and cleanup

The first real run found a product defect: inventory was missing from the account return-route allowlist, redirecting successful login to Settings. The UI owner repaired it with three red/green regressions and reran identity tests, typecheck and build. [Initial failure](browser-initial-navigation-failure.txt) is preserved. Later test-only corrections removed an unnecessary reload that intentionally lost in-memory CSRF, selected native controls by accessible role rather than nested-label text, and used working native keyboard typeahead. Their logs are retained beside this record. Earlier successful journeys were repeated solely to frame the lower evidence tables after viewport reflow; no further product change was made.

The pre-existing `deploywhisper-deploywhisper-1` container was recorded before testing, stopped only after image build and restored after each attempt. Final original container health returned HTTP 200. The disposable Compose project was removed; private credentials and their temporary directory were deleted. No operator database or infrastructure data was modified.

Retained text logs normalize trailing whitespace only; diagnostic content and outcomes are preserved.
