# Story 16.15 formal review repairs

**R1–R3 resolved and independently verified.** Full integration CI and all repair checks have completed successfully. The separate positive HTTPS/real-runner browser acceptance gate remains open; no HTTP or synthetic test is relabelled as that proof.

## R1 — independent revocation recovery

The nonsecret store now tracks bounded revocations by runner ID. An unknown revoke of A still blocks repeating A, while B remains independently revocable. Unresolved entries are never evicted to free capacity. Operation tickets prevent stale responses from clearing newer requests, and a revoke can settle only the matching issuance ticket captured when it began.

Regression coverage includes two-runner recovery across SPA navigation, capacity protection, same-target deduplication, and an old revoke racing with a later rotation.

## R2 — verified rejection classification

Submitted runner mutations settle as rejected only for an expected application status/code pair. HTML, malformed, uncoded or mismatched 4xx retain uncertainty. Enrollment, rotation and revocation finish local input/header/body validation before their onSubmit callback creates a marker; a local validation error cannot create a fictitious uncertain server effect.

The red suite reproduced 19 failures before repair. Tests cover both issuance operations, unrecognized responses, genuine rejections, pre-send validation and marker continuity. Composed component tests exercise HTML403, unknown422 and recognized409 for enrollment and rotation, with exactly one POST and no automatic retry.

## R3 — one bounded routing candidate set

`models/repositories/infra_automation_runners.py::routing_candidates` is shared by readiness and actual assignment. It ranks current credential windows before retained history, rejects future creation from that priority and uses stable runner ID ordering within a 1000-row ceiling. Callers retain their live scope, credential, policy, version/profile/tag, heartbeat, busy and fencing checks. History is not deleted.

The failing integration reproduction used1000 expired active rows before a valid runner. New tests exercise actual readiness followed by queue_assignment for expired/future-created history, deterministic bounds, busy runners and live rejection cases. The fix remains on the separate backend-for-UI branch (`f5d6c19`, qualification follow-up `86e9825`) and is merged into the UI integration branch.

## Verification

- Independent repair review: no residual R1–R3 finding; UI 38 focused tests plus two OpenAPI checks, backend 18 tests/15subtests.
- UI implementation tests:48 focused tests; **398 full UI tests** plus two OpenAPI checks. TypeScript and production build pass.
- Backend expanded focused suite: **93 tests, 608 subtests** pass.
- Backend worktree root smoke: **1795 tests, three skips**, exit0,805.051s. The unchanged UI-only fixture guard is additionally included in main integration CI.
- Exact backend API/CLI/infra shard: **740 passed, one skipped, 2356 subtests**,418.23s.
- Composed main-branch browser: **26 passed**,2.5m (three real HTTP access/denial scenarios plus23 explicitly synthetic component fault models). Original app container restored healthy; private credential exports destroyed. No production HTTPS administration is claimed.
- Real collection regression: **49 checks pass**. The witness now covers the shared repository query and both routing consumers. All recorded source hashes match.
- Collection/isolation integrity: **9 tests,69 subtests pass**; unchanged isolation qualification remains current.
- Main full `bash scripts/ci-local.sh`: **exit 0; 3246 test executions** across all ten directories, three skips.
- Ruff/formatting and scoped Bandit passed; final whitespace/format checks pass. Nonblocking mypy reports318 existing diagnostics with no new normalized diagnostics against the prior run.

The browser lane uses the built FastAPI static mount at `http://localhost:8080`, not Vite. Sign-ins retain normal throttling. Credential traces/video/automatic screenshots and failure ARIA snapshots are disabled; only safe states are captured. Runtime layouts/styles were not changed by these repairs; the fresh HTTP visual assessment remains93.

No new dependency, migration, retention deletion, transport weakening, public push or PR was introduced. Positive HTTPS enrollment and the actual isolated-runner browser journey still require the previously requested verification-lane decision. Relevant commands/logs are retained at `/tmp/story16-15-{routing-*,repairs-*}.log` for this session.

## Files and completion boundary

R1/R2 update the runner mutation store, screen and API adapter plus unit/browser regressions. R3 replaces duplicated candidate-query ordering in the readiness and dispatcher services with the shared repository query. The real qualification witness now includes those three routing modules. No schema migration or dependency was introduced.

All review repair items are complete. Story 16.15 stays in-progress only for its separately recorded positive HTTPS/real-run browser acceptance and authorized publication gates. No public push/PR or HTTPS-lane execution occurred in this repair task.
