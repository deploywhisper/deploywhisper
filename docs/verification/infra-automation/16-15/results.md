# Story 16.15 implementation and verification

**Status: implementation verified within the available lanes; story remains in-progress.** Positive HTTPS enrollment and authenticated isolated-runner-to-report browser acceptance are not yet qualified. The supplemental HTTPS validation-lane question is pending; existing transport and identity gates are unchanged.

## Implementation

- Separate backend-for-UI branch: `feature/16-15-runner-health-backend-for-ui`, commit `db73571`. Scoped health/capabilities, typed administration responses, durable collection/readiness observations and generated API types are additive. No protocol or application migration changed.
- UI branch: `feature/16-15-runner-health-and-collection-ux`, based on that backend commit. Adds the runner route, transient enrollment/rotation/revocation, collected run entry, recorded stages, guarded cancellation and recovery. Existing primitives, styles, analysis and APIs are reused; no dependency or Dashboard addition.
- Connectivity uses server-evaluated60/180-second thresholds; credentials, registration and configured profiles remain separate. Health never attests isolation.
- Source/upload/analysis stages use retained facts, with explicit unobserved stages and unavailable event timestamps. Cancellation never implies owned or external work stopped.

## Validation performed

| Check | Result |
| --- | --- |
| `./.venv/bin/python -m unittest discover -q` | **1794 tests passed**, three skips, 751.993s |
| `bash scripts/ci-local.sh` | **exit 0; 3240 test executions**, all ten directories, three skips |
| Exact API/CLI/infra pytest shard | **745 passed**, one skip,2356 subtests |
| `npm run ui:gen-api` | Generated from current FastAPI OpenAPI;96 paths |
| `npm run ui:typecheck` | Pass |
| `npm run ui:test` | **377 tests pass**, plus two OpenAPI compatibility checks |
| `npm run ui:build` and Compose production image build | Pass; static Vite assets served by FastAPI, Node remains outside runtime |
| New composed HTTP and component browser lane | **19 passed**,2.0m: three actual API-backed HTTP denial/access scenarios and16 explicitly synthetic component fault models |
| Existing composed uploaded workflow/run/report lane | **14 passed**,1.3m, including keyboard publication, actual analysis, permanent report, CSRF/origin, revoked/expired/denied and recovery paths |
| Axe/keyboard/screenshots | No critical/serious violations in captured tested states at 1440/760; no horizontal document overflow; focus/draft fault regressions pass |
| Visual verdict | **93/100**, pass for captured HTTP/compatibility states; see `visual-verdict.json` |
| Refreshed Story 16.14 real collection qualification | **49 checks pass**, current source hashes; this is collector regression proof, not Story 16.15 HTTPS browser acceptance |
| Ruff/repository-wide formatting/whitespace | Pass;555 Python files formatted |
| Type/security baseline | Mypy reports320 diagnostics outside changed files (includes missing PyYAML stubs); no changed-file errors. Configured security gate passes; unchanged sample-IP medium Bandit finding remains disclosed. |

The exact browser commands used `BASE_URL=http://localhost:8080`, the named disposable Compose profiles and private fixture variables. The new lane ran `npm run test:ui-review -- infra-automation-runners.spec.ts infra-automation-runner-component.spec.ts`; compatibility ran `npm run test:ui-review -- infra-automation.spec.ts`. Synthetic component scenarios are labelled as such in the tests and cannot satisfy positive real enrollment/AC6.

Docker29 reports the fixture tmpfs through `HostConfig.Tmpfs`; the host guard accepts that explicit mapping only without a conflicting data mount, and the in-container guard still checks actual `/proc/self/mountinfo`. Browser sign-ins are paced to respect the unchanged20-per-minute authentication limit. Credential flows disable traces, video, automatic screenshots and automatic failure ARIA snapshots. Only safe states are deliberately captured.

## Review and repair evidence

Independent backend review passed31 tests/20subtests plus existing runner API/enrollment21tests/22subtests with no findings. Integrated Blind Hunter, Edge Case Hunter and Acceptance Auditor completed. Reproduced UI issues were repaired:

- The account return allow-list now includes the exact runner read route and bounded scope query; credential/action selectors and foreign destinations remain rejected.
- Secret lifetime uses a server-time anchor and monotonic read-start; backwards browser clocks cannot extend it.
- Pending runner issuance is nonsecret bounded memory, established before POST, retained across same-session remount/membership changes, never silently evicted unresolved. Late verified outcomes retain only safe metadata; fresh GETs do not resolve unknown effects.
- Collection validation precedes transport markers; late success/definite rejection settles shared tickets before mounted-only React updates. Cancellation rejects stale ticket settlements and retains protection after ambiguous responses.
- Late collection snapshots correct once per bounded version pair; persistent mismatch becomes explicit unavailable evidence.
- Non-auth read failures retain authorized same-scope run/collection/step/report/handoff/log panels and local drafts. Consequential actions disable;401/403 clears protected content. Lease/deadline and evidence-expiry corrections are distinct.

Independent targeted repair verification reported no residual findings;71 unit tests and six direct late-handler probes passed. Actual browser fault models cover clock/context/authorization clearing, late responses, invalid local reasons,503 retention/focus and403 clearing. Earlier browser failures were retained in session logs; final runs above supersede them. The older account-browser expectations were aligned to the already-merged Settings fallback and collapsed operator guidance rather than changing those production flows.

## Screenshots and cleanup

New runner captures are `screenshots/runners-*-1440.png` and `screenshots/runners-*-760.png`. Current uploaded-flow compatibility captures use `screenshots/upload-*.png`; older Story 16.7 reference captures were restored rather than overwritten. Initial HTTP visual captures are retained separately as `http-initial-*.png`.

The existing repository app container was temporarily stopped only for exclusive port 8080 use. Every disposable lane used a nonroot image and tmpfs database, then ran Compose down. The original exact container was restored with its data volume unchanged and verified healthy. No real state, provider credentials, binary plans or browser credential exports were committed.

## Remaining acceptance gate

[AGENTS.md](../../../../AGENTS.md) requires all browser verification at HTTP localhost:8080. Runner administration requires actual HTTPS and production-eligible origin-bound sessions. A separate same-origin HTTPS Compose lane is the safe proposed supplement; cross-origin requests, fake forwarded headers, or weakening local-development identity would not qualify it. The user decision remains pending.

After approval, implement and execute that lane with real enrollment/redemption and the qualified isolated runner, capture populated health/enrollment/recovery states at 1440/760, and complete the remaining AC3/AC4/AC6 proof. No public PR or release was created; backend and UI publication must remain separate.
