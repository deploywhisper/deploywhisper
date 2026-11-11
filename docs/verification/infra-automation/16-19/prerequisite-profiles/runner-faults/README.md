# Actual HTTPS runner fault proof

Three fault cases and three browser journeys passed against immutable application image `sha256:a0155abf874bd29a798a19e794dd9d2928d17ed701011e655ecc6920cc65d447` (runtime source `675f127`). All 243 packaged Python source hashes match the qualified positive image. This supplement changes only qualification drivers/configuration and preserves the earlier positive proof.

| Case | Actual behavior | Browser proof |
| --- | --- | --- |
| Published wire lease expires | An actual HTTPS-issued/claimed task reaches its published 30-second lease deadline. After the deadline plus clock margin, the production runner rejects local admission with `IsolationError` before creating a container or invoking credentials/authority/finalization callbacks. The late heartbeat returns409; the application records failed and retains no report/custody. | Correct failed run; no permanent briefing; no invented independent termination or external-acceptance claim |
| Authority revoked while a tool runs | The actual Docker process listing observes an OpenTofu process during the real isolated collector. A genuine administrator HTTPS revoke follows. Live runner authorization becomes unavailable; the production runner terminates/removes its owned process/container, does not finalize custody/output, and the application records failed with no report. | Failed collection and honest cancellation/termination copy |
| Chunk and retention caps | Operator-supported configuration lowers the chunk ceiling to128 bytes and total attempt-log ceiling to8192 bytes. A129-byte chunk returns429.65 valid chunks retain8107 bytes; the next chunk would exceed8192 and returns429 without advancing the committed sequence. A real isolated collection then completes through the same authenticated assignment and produces one report. | First log page is truncated, gap=false; keyboard pagination changes the last sequence and preserves focus. No false sequence-gap warning |

The expired-before-start and running-revocation cases are distinct. The former does not claim a process was running when the wire lease expired; the latter proves cleanup of an actual running OpenTofu process after live authority loss. The published lease and process observations are retained in [runner-faults.json](runner-faults.json).

No run or attempt terminal state is seeded. All workflows, revisions, runner enrollment/redemption, task claims, heartbeat/log operations, revocations and run/report reads use the real HTTPS application and production protocol. Transport observation records only method/path/status/time and returns the real transport result unchanged. The expiry callbacks are failure sentinels which must never run after admission is denied. No clock or production guard is patched.

The lower log ceilings are legitimate operator configuration, not a claim of testing every permitted ceiling. Full retained-log retrieval independently confirms the byte bound, contiguous sequences and rejected-next-chunk calculation. A read cursor's truncation flag describes its incomplete page; no missing log sequence is fabricated.

## Verification and cleanup

- Driver: all three cases passed.
- Browser: **3 passed in6.2 seconds**, six viewport captures at1440/760, zero critical/serious axe violations; [visual95/pass](visual-verdict.json).
- Typecheck, targeted Ruff/Bandit high-severity checks and repository-wide formatting passed.
- The exact owned project `deploywhisper-s1619-runner-faults`, its container and certificate volume were removed and independently inspected absent. Its private credential export and certificate directory were removed. The original8080 application remains healthy with HTTP200. The separate receiver19443 lane was untouched.

[Structured results](results.json) contain source/screenshot/log hashes, commands and cleanup identities. The positive profile records remain separate. `development/invalid-hcl-attempt.json` is an explicitly historical driver error from malformed synthetic HCL, corrected before the successful full corpus; it is not a final product failure.

This local technical proof does not qualify remote GitHub delivery, production cloud effects, an independent human pilot or the full release performance profile. Accepted/unknown external delivery is owned by the separate actual ReferenceReceiver supplement.

Final causal assertion recheck: the running-revocation driver requires exactly `authority_unavailable`, empty output, no output digest, no collection/custody and no report, in addition to observed running OpenTofu, successful revocation and cleanup. All three actual fault cases and three browser journeys were repeated with this strengthened driver; source and log hashes are refreshed in results.json.
