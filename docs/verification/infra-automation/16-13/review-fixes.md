# Story 16.13 review repairs

Date: 2026-11-04. Scope: R1–R5 from [the formal review](code-review.md). All five repairs are resolved and independently verified. Fresh real qualification and full repository CI passed; Story16.13 is ready for re-review.

| Finding | Repair | Regression evidence |
| --- | --- | --- |
| R1 — timeout reset after setup | Capture the original absolute execution deadline and remaining monotonic budget before preparation/create. The private bootstrap frame carries both and caps them by the original lease. Startup/delivery does not replenish the watchdog. | Original missing-budget/delayed-setup cases failed before the fix. Actual timeout6/create-delay3/lease60/controller-death case now observes stop at 6.092 seconds, within the original budget plus declared 0.75-second observation tolerance. |
| R2 — OpenTofu format bypass | One shared configuration selection path covers `.tf`, `.tf.json`, `.tofu` and `.tofu.json`, including the per-file byte bound and module validation. | Escaping/remote/expression and oversized configuration cases deny before credential resolution; real admitted vendored OpenTofu configuration runs successfully. |
| R3 — publicly readable snapshots | Require current-operator-owned 0700 staging. Create a private internal envelope around the container-readable tree. Hold parent/envelope descriptors and inode identities across creation, publication, verification and cleanup. | Public/group-readable staging denies; permission relaxation and parent replacement cannot publish private source or redirect cleanup. Legitimate non-root container readability remains qualified. |
| R4 — early cleanup confirmation | Persist the immutable container acknowledgement separately from the ownership nonce. Unacknowledged creation remains pending through empty or foreign-name observations; known-ID absence can be reconciled. | Controlled late-create model proves pending state survives the initial empty lookup and a fresh host instance recovers/removes the late owned object. Foreign containers remain untouched. This is modeled transport evidence, not a reproduced late-commit Docker-daemon race. |
| R5 — broken standalone command | Remove `provider_probe` from the advertised command registry. Keep the internal external-provider helper, which receives the provider protocol's JSON input. | The removed command is rejected before execution; both remaining advertised commands (`qualification_probe`, `tool_version`) execute through the real launcher. |

Existing model, redaction, process, filesystem and ownership primitives were reused. No dependency or app database migration was added. The private journal receives a nullable acknowledgement column without discarding existing records or declaring legacy uncertainty clean.

## Additional failures caught by qualification

The full corpus kept its failure evidence and assertions:

1. The improved watchdog could terminate a timed-out container before the host issued a kill. The observer now requires durable timeout/cancellation before host removal in that autonomous-exit case; explicit cancellation and authority-loss cases still require persistence before host kill.
2. A container could exit naturally between inspection and a kill request. Failed kill now permits cleanup only after fresh proof that the exact immutable owned ID is stopped or absent. Running, unavailable or foreign identity remains unresolved. Unit failures were reproduced before repair.
3. `_call` conflated execution-budget expiry with lease loss. Pre/wait/post checks now preserve `timed_out`, `lease_lost` and callback-only `authority_unavailable` separately. Three regression cases failed before the fix; the actual timeout probe now reports the correct state.

The separate inherited-module-cache hypothesis did not reproduce an admission/execution bypass: the no-cache control succeeded, while both local/outside cached-module variants failed without finalizable output and cleaned up. No speculative production change was made for that hypothesis.

Historical review counterexamples in `review-deadline-repro.json` remain untouched. The original 130-assertion record and intermediate failed repair-run JSONs were preserved in session temporary evidence; the current `results.json` contains the new accepted result.

## Current verification

- Fresh real qualification: **172/172 assertions**, 19 task cases, three controller-death cases and 17 admission cases. All image/source pins and source-stability checks passed; no owned containers remain.
- Independent final repair verification: **68 tests passed, 135 subtests passed**. No residual actionable R1–R5 finding was identified.
- Root `./.venv/bin/python -m unittest discover -q`: **1,701 tests, three skips**, OK in 831.172 seconds.
- Exact `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: **734 passed, one skipped, 2,353 subtests**, 523.49 seconds.
- Scoped six-module mypy, repo-wide Ruff check/format (532 files), configured Bandit medium/high gate and `git diff --check` passed.
- `bash scripts/ci-local.sh` completed with **exit 0, no retries**: all ten directories passed (69 analysis, 343 API, 102 CLI, 51 docs, 290 infra, 923 automation, 76 LLM, 22 models, 43 parsers, 1,232 services; 3,151 test executions with three existing skips). Dependency, compilation, skill/prompt-injection and configured security gates passed.

Changed runtime files: `infra_automation/runner/{bootstrap,execution,sandbox,source,catalog}.py`. Related regression tests, the real qualification harness/evidence and operator documentation were updated. UI validation is not applicable.

Support remains the declared offline Linux ARM64 / Docker29.1.3 / LinuxKit6.12.54 profile. Production collector/custody integration, additional networks and alternate profiles remain separate qualification work.

All five story action items are checked off and story/sprint status is review. Changes remain uncommitted on `feature/16-13-isolated-runner-execution-profile`; formal BMad re-review/Git Flow closeout is the next workflow.
