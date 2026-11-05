# Story 16.16 formal-review composed browser proof

**Four actual Compose tests passed in 45.4 seconds.** All browser/API operations target
`http://localhost:8080`; the production static build is served by FastAPI. The
nonroot fixture requires disposable tmpfs storage and synthetic identities.
No success or evidence response was fabricated. One explicitly simulated gateway
rejection is described below; no external infrastructure action ran.

## Review regressions proved

1. The original keyboard create/validate/confirm/two-unit-analysis/review journey
   passes. An unknown prerequisite marks the actual prerequisites input invalid,
   associates its diagnostic, leaves the valid ID unmarked, and lets the keyboard
   operator activate a summary link to focus that exact control.
2. A client-only fetch wrapper fully receives a successful real start response,
   then discards it by throwing. After an actual later inventory revision is
   saved, explicit retry submits the identical payload/idempotency key, returns
   the original run and leaves exactly one run for that workflow. Before the
   successful replay, one client-side gateway fault returns a synthetic 429
   `quota_exceeded` response without sending that retry. The original pending
   payload/key and retry action remain available; new admission and artifact edits
   remain disabled. The next retry reaches the real API with the same payload.
   A rejected retry therefore cannot erase uncertainty about the earlier commit.
3. The same controlled response-loss technique hides a committed second inventory
   revision. After a real third revision is saved, the browser reads bounded
   history, opens revision 2 and explicitly adopts its verified matching effect.
   No additional browser save POST occurs during recovery.
4. Fifty-one real workflows and 51 real revisions exercise middle pages under the
   existing 100-item authoring bounds and 25-item page size. With real selected
   inputs and a gated browser `File.text()`, all four First/Next workflow/revision
   controls remain disabled. Releasing reads submits the still-selected exact
   workflow/revision through the real API.

Keyboard journeys use Tab/Shift+Tab, native select typeahead, text entry and button
activation. File contents are synthetic fixture injection after proving keyboard
reachability. Delayed file reads and discarded client responses are deliberate
fault models around real server operations, not claims of physical network loss.

Axe found zero critical/serious violations at each captured 1440/760 viewport.
Eighteen screenshots and their hashes/dimensions are in
[review-screenshots.json](review-screenshots.json). Visual comparison against the
retained original Inventory/run screenshots scores 94/100, pass; see
[review-visual-verdict.json](review-visual-verdict.json). Exact image/source hashes
are retained in [review-browser-source.json](review-browser-source.json).

## Commands and preserved history

```sh
docker compose -f scripts/compose-story16-16.yaml build
docker compose -f scripts/compose-story16-16.yaml up -d --build
# Wait for health 200; copy the protected fixture to an owner-only temporary file.
BASE_URL=http://localhost:8080 UNIT_UI_CONTAINER=deploywhisper-story16-16-deploywhisper-1 UNIT_UI_FIXTURE=<private-file> npm run test:ui-review -- infra-automation-units.spec.ts
docker compose -f scripts/compose-story16-16.yaml down
```

[Final output](review-browser-verified.txt) preserves the four passing tests.
The first new fault test was interrupted after its test observer waited on the
intentionally discarded response body. The real server had committed the run.
The fixture now consumes a clone before discarding, and verification reads durable
state through a separate real GET. [Interrupted output](review-browser-interrupted.txt)
is retained; it is not a product failure or a passing run. Retained text logs
normalize trailing whitespace only.

Credential traces/video/automatic failure screenshots remain disabled. The
pre-existing application container was restored to its exact recorded identity
and health returned 200 after each attempt. Disposable Compose resources and the
private host fixture directory were removed. No operator data was mounted into
the proof lane. State is recorded in
`.omx/state/story-16-16-ui/review-browser-proof.json`.

The earlier four-test 43.7-second pass is retained in [review-browser-before-retry-hardening.txt](review-browser-before-retry-hardening.txt). The final 45.4-second pass supersedes it and additionally proves that a simulated gateway 429 cannot settle the original ambiguous start. This 429 is a client/gateway fault model, not a claim that the real server exhausted its quota.
