# Story 16.13 development review

Date: 2026-11-04. Scope: the operator-only source/catalog, container launcher, bootstrap and execution lifetime. This review supports development verification; formal BMad code review and Git Flow closure remain the next workflow.

## Readiness

PR209 merged Story16.12 into develop as `e2690a7` after successful CI and independent repair verification. Its stale tracker state was reconciled; no GitHub approval review is invented. Story16.0 accepted governance and qualification remain authoritative historical evidence. The new16.13 image/results do not overwrite frozen16.0 fixtures.

## Findings repaired during implementation

- Finalization initially allowed cancellation or expiry during inspection/redaction/cleanup to produce successful output. Final checks and a reserved journal transition now let durable cancellation/deadlines win, with no finalizable output.
- A failed create could treat a caller-supplied name as ownership and remove an unrelated container. Cleanup now requires a successful immutable container ID or matching per-operation ownership nonce and task label; ambiguous ownership remains unresolved.
- Task journal identity included the renewable lease deadline. It now binds immutable attempt/fence/generation/epoch scope, so renewal cannot start duplicate work or make cancellation miss the original execution.
- Final journal lock acquisition could cross a lease/time deadline. Those bounds are rechecked inside the reserved transaction before success.
- Recovery could treat uncertain owned state as cleaned up. Matching nonces with unexpected image/configuration and unavailable daemons now retain pending cleanup; only proven absence or foreign ownership can clear without removal.
- Host supervision alone could leave execution alive after controller death. Fixed in-container PID1 now enforces the original lease/time bound independently and tears down its entire PID namespace. Non-dumpability plus a stacked restrictive seccomp filter prevents descendants from manipulating its memory, priority, scheduler or affinity.
- The first bootstrap run exposed a source-digest prefix mismatch. The comparison was corrected without bypassing pin verification. Real LinuxKit networking also required measuring actual dormant namespace interfaces rather than assuming the interface list contained only loopback. The accepted profile is now pinned to the observed kernel and requires explicit down/addressless/routeless checks; active or unknown interfaces deny before credentials.

Independent regressions use harmless real subprocesses and private SQLite to exercise cancellation/expiry, ownership collisions, lease renewal, final-transaction contention and uncertain recovery. These unit tests do not claim container isolation. Credential-echo tests cover raw, URL/nested URL and split output; they reject output without retaining values in journal files. Screening is a measured corpus and is not a universal guarantee against arbitrary encoding or malicious-provider data disclosure.

## Evidence

The accepted real record at `results.json` passed 17 task cases, two actual host-controller SIGKILL/recovery cases, nine source/catalog admission cases and all130 named assertions. It covers the actual OpenTofu/external provider, namespace/privilege/mount/network controls, resource bounds, separate-session descendants, watchdog attacks, finalization cancellation and cleanup. A second unchanged-source run passed the same corpus. All image/source pins match and no owned containers remain.

The six-module source-drift guard prevents changed isolation code from silently inheriting this record. It validates evidence integrity in ordinary CI; it does not itself run or qualify a live host.

Final focused isolation/source/catalog/lifetime/evidence suite and broader regression results are recorded in the story Dev Agent Record. Scoped mypy covers the new runtime modules. A broader imported-module mypy invocation also reports pre-existing PyYAML-stub/content_security typing issues; no new dependency or unrelated typing rewrite was introduced. Bandit's configured medium/high gate passed; low subprocess warnings remain bounded by fixed/protected argv and explicit operator trust.

## Limits

Qualification is only for the recorded offline Linux ARM64 / Docker29.1.3 / LinuxKit6.12.54 profile and pinned image. The macOS control process is not a native macOS sandbox. Actual cloud credentials, collector/custody integration, additional networks and alternate host/tool profiles remain separately qualified later-story work. The default application and outbound client still do not launch production collection.

## Final development validation

- Real qualification: 17 task cases, two host-controller death/recovery cases, nine admission cases, **130/130 assertions passed**. An unchanged-source repeat also passed. All image/source pins match, core hashes are current and no owned containers remain.
- Focused new isolation/source/catalog/lifetime/evidence suite: **43 passed, 83 subtests**.
- `./.venv/bin/python -m unittest discover -q`: **1,677 tests, three skips**, OK.
- Exact `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: **734 passed, one skipped, 2,353 subtests**.
- `bash scripts/ci-local.sh`: **exit0, no retries**; all ten directories passed, 3,125 test executions with three existing skips.
- Final repository Ruff check/format (532 files), scoped six-module mypy, configured Bandit medium/high gate and `git diff --check` passed.

Story status is review. Source-level review repairs are complete; formal BMad review and Git Flow publication are separate next steps.
