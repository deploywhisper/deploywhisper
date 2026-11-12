# Prerequisite profile qualification

The bounded Story 16.13/16.14 profile and the previously missing positive Story 16.15 HTTPS/browser lane initially passed against source commit `675f127a0c4ad7c3630d3c59cb7412818afd1db8`. The OpenTofu collection profile was rerun after the final production-composition changes and its current 65-file witness passes. The React production source used by the browser lane is byte-identical between that commit and final implementation commit `1adf00fd9de4223186da4976dd8caad9882e26cd`; the final exact image also passed external health/OpenAPI smoke. This is agent-executed technical qualification, not the independent human self-service pilot, external carrier-effect proof or blanket production approval.

## Final evidence

| Proof | Result | Record |
| --- | --- | --- |
| Actual isolated Linux runner corpus | 172 checks; all 23 source hashes match | [isolation-final/results.json](isolation-final/results.json) |
| Actual pinned OpenTofu collection/custody/receiver corpus | 49 checks; all 65 source hashes match | [collection-final/results.json](collection-final/results.json) |
| Same-task collector through actual HTTPS application | 49 checks; real collector, authenticated intake, spawned shared analysis and one retained report | [https-final/results.json](https-final/results.json), [same run](https-final/https-run.json) |
| Production image identity and source witness | 243 packaged Python files match; one successful analysis completion, no crash; one report and one link | [runtime-witness.json](https-final/runtime-witness.json) |
| Actual composed TLS browser | 3 journeys passed in 1.2 minutes; 8 captures at 1440/760; zero critical/serious axe violations | [results.json](results.json), [screenshots](https/screenshots) |
| Frontend unit/type/build | 513 tests plus 2 compatibility checks; typecheck and production build passed | Log hashes in [results.json](results.json) |

The composed TLS/browser application's recorded image is `sha256:a0155abf874bd29a798a19e794dd9d2928d17ed701011e655ecc6920cc65d447`. The final exact local release image is `sha256:7a6afd6fd7b3ce74a672fa6fedda0e2c6d146813bcb3f1009930529e1c5f2323`; it is not relabelled as the earlier browser image. The collector uses the recorded Linux ARM64/OpenTofu 1.13.1 image and operator-owned immutable source/catalog/custody. No cloud/provider credentials or external infrastructure action were used.

The real HTTP path publishes a collected workflow, admits a run, enrolls and redeems a runner, establishes its online heartbeat, receives and claims an actual task, executes the real isolated collector, uploads and completes through the normal `RunnerClient` transport, and waits for the application's coordinator and spawned analysis worker. The browser then opens that same run and its permanent briefing. There is no synthetic success-response adapter in this path. The original direct-service collector corpus remains separately identified.

## Browser boundaries

The supplemental origin is `https://localhost:18443`, with SPA and APIs served by the same TLS-enabled FastAPI application. Uvicorn uses actual TLS and disables forwarded-header trust. The application uses the actual HTTPS identity profile and current administrator memberships. The browser accepts a disposable self-signed certificate; the production `RunnerClient` uses its normal verified TLS transport with the explicit temporary CA. No global trust-store change was made.

The three journeys cover:

1. Keyboard enrollment, real redemption and task polling; transient browser network loss disables actions while retaining last-known rows; explicit refresh recovers; rotation rejects the old credential and admits the new one; revocation rejects the rotated credential. One-time secrets are closed and absent from DOM, URLs and browser storage before capture.
2. Navigation from the same real isolated collection run to its permanent report, with keyboard activation and collected-provenance assertions.
3. A fresh unredeemed enrollment uses a configured 60-second credential lifetime. The reveal clears, then the test waits beyond the actual published server deadline before proving redemption returns401. No product clock was patched. The UI intentionally clears conservatively slightly before the server deadline.

These journeys do not establish the complete AC4 final-image
create/run/review/decision/runner/unit/recovery flow or the accepted/unknown
delivery screenshots. NFR-009 and Packet19.4 remain open until that exact
candidate journey is executed.

Trace, video, automatic screenshots and credential exports from browser storage are disabled. Deliberate captures occur after secret clearing. The required earlier HTTP-denial lane remains valid; this explicit supplemental TLS lane supplies its missing positive proof.

## Defects found and repaired

- The production sessionmaker expires ORM objects on commit. `queue_assignment` used the selected runner object after the transaction closed, causing `DetachedInstanceError` and cancelling a real collection run. It now captures the immutable runner ID/generation inside the transaction and publishes the mailbox only after successful commit. The regression uses `expire_on_commit=True`, verifies a failed commit publishes nothing, then checks one-time polling and restart fencing. It reproduced red before the repair; 29 focused tests and 102 subtests passed after it. Independent edge review confirmed live generation/authority/lease checks remain intact.
- The report context hardcoded uploaded provenance even for a real collected result. It now derives the title and advisory explanation from the existing validated provenance kind. Uploaded evidence retains its explicit approval restriction; collected provenance grants no authority. A fully typed component regression reproduced red; all 513 frontend tests, typecheck/build and the actual browser assertion passed.

The final visual assessment is [94/pass](https/visual-verdict.json). Existing styles and controls remain; the collected title now matches its source.

## Historical attempts and limits

Preliminary evidence directories are snapshots of earlier source or test-driver iterations. `https-before-network-assertion/observation.json` records one undetermined failed analysis attempt followed by a bounded successful retry, with exactly one retained report/link. Production safe diagnostics did not retain its raw cause; none is invented. Final read-only observation reports one `local_success`, `crashed=false`, and only one analysis attempt. `https-before-copy-fix` retains the mislabelled report and prior successful mechanics before the semantic assertion.

The administration fixture was first exercised on8443. An unowned concurrent helper was observed targeting that lane, so authoritative proof moved to the uniquely owned18443 project. Both exact disposable projects and certificate volumes were subsequently removed after their IDs, labels, nonroot identity and tmpfs database were verified. Private fixture exports and the owned certificate directory were deleted. Unowned qualifier directories were untouched. The original8080 application remained running/healthy with HTTP200; cleanup identities are in [results.json](results.json).

This closes the named isolation/collection and positive HTTPS/browser proof. Packet15.3 also names real-runner lease-loss, log-limit and accepted/unknown-dispatch browser cases; those are not established by these three positive journeys or by relabelling earlier component tests. Terraform, production cloud IAM/remote state, remote fleets, cold-host installation, host power-loss durability and the independent human pilot remain outside this proof. Story16.19's full reference-hardware/performance/release gates require their own evidence.

## Reproduction

Use `scripts/compose-story16-19-https.yaml` with a uniquely owned TLS volume, actual localhost certificate, explicit qualified profile digest, nonroot user and disposable tmpfs domain. Set `RUNNER_HTTPS_ORIGIN=https://localhost:18443`, `RUNNER_HTTPS_HOST_PORT=18443` and a unique Compose project. Keep the private browser fixture mode0600; never print its credentials. The exact qualification/browser command forms and log hashes are in [results.json](results.json). Generate a fresh certificate/fixture for a rerun, then remove only that run's recorded containers, volumes and exports.


## Subsequent real lease/log supplement

[runner-faults/README.md](runner-faults/README.md) closes the actual wire-expiry,
running OpenTofu revocation and bounded-log browser cases with three fault cases,
three browser journeys and six captures. It preserves the675f127 runtime.
The remaining accepted/unknown production path is explicitly blocked by the
[composition gap](receiver-faults/README.md); component receiver tests do not
supply the missing production material authority or handlers.

Source-witness matches in this record refer to the isolated675f127 snapshot and its identified image. Later concurrent working-copy authority/version/benchmark edits are not qualified by this record.
