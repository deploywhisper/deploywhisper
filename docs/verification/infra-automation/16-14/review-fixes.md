# Story 16.14 formal review repairs

**R1–R4 resolved and independently verified.** The four findings in [the formal review](formal-code-review.md) are repaired with regressions, refreshed real qualification and completed repository validation. Story16.14 is ready for re-review. No dependency or infrastructure action was added.

## R1 and R2 — decoded credential boundaries

A bounded helper in `infra_automation/artifact_intake.py` checks every decoded JSON key and string value with the existing redaction primitives. It caps bytes, depth and node count and uses fixed nonreflective errors. The host invokes it before custody/output; authenticated intake invokes it with the current task/runner/enrollment credential corpus before staging and again before successful completion. The shared redactor's general field semantics remain unchanged.

Twelve initial regression failures reproduced the leaks before the implementation. Escaped keys cover quotes, backslashes, newlines and Unicode. Authenticated tests use actual issued fixture task/runner bearers, assert rollback/no new staging/manifests/reports, and reject previously staged malicious completion. Existing contaminated staging can only await its normal terminal cleanup; it cannot become an immutable report.

Independent verification:42 tests/580 subtests passed, plus nine direct rejected credential/boundary probes and a safe-input positive check.

## R3 — production payload compatibility

The receiver now accepts the canonical `registered_github_handoff` payload only when its embedded exact-plan decision maps to the approved receiver binding. Explicit operator-local `saved_plan_receipt` mode still performs only a digest receipt. Existing canonical target/payload bytes and digests are unchanged; malformed decisions, altered bindings and restart mode changes reject. Earlier explicit receipt payloads retain their bounded compatibility path.

The red regression reproduced rejection of the actual production payload before the fix. The revised real qualification uses `semantic_payload()` and carries the actual report ID/digest, scope/run and original custody through the receiver. It no longer proves this boundary using a custom selector payload.

## R4 — bounded, sealed transport

The local handler requires `execution_timeout_seconds` from its protected execution profile. The original lease and profile budget bound every send. Lock acquisition is nonblocking, sends use a bounded worker pool, and only a timely waiting caller can advance scope/sequence. A timeout or ambiguous response seals the channel. Late transport results cannot revive it, and no new completion is queued behind an uncertain heartbeat/upload.

Regressions cover stalled heartbeat, upload and completion, original deadline expiry, invalid budgets and late response release. Independent verification observed a blocked heartbeat return in0.405s with no later sequence advance or completion. Receiver/client/runtime verification passed31 tests/32 subtests; the broader implementer client/execution group passed47 tests/46 subtests.

## Qualification and validation

- Combined repair regressions:43 tests/63 subtests passed.
- Real collection qualification:49 checks across eight cases pass with matching source hashes, including actual credential-key reflection rejection and canonical production receiver payload admission.
- Refreshed isolation qualification: **172 checks pass** with current hashes. The first run failed only the three-second descendant-observation assertion; it recorded exit124, completed cleanup and stable hashes. The unchanged corpus then passed alone; the first result is retained at `/tmp/story16-14-fixes-isolation-first.json`.
- Qualification integrity tests: **9 tests, 66 subtests pass**.
- Full automation directory: **984 tests passed**, one skip.
- `./.venv/bin/python -m unittest discover -q`: **exit0, 1766 tests, three skips**, 757.537s. Started after CI automation passed to avoid competing process-recovery workloads.
- Full `bash scripts/ci-local.sh`: **exit0**, all ten directories pass, **3212 test executions** (three skips), plus static/security/compile/skill checks. This was one complete run on frozen repair code.
- Exact API/CLI/infra pytest shard: **734 passed, one skipped, 2353 subtests**, 492.06s.
- Ruff check and repo-wide formatting: **pass, 546 files**. Touched-code Bandit and the configured full-CI high-severity gate pass; the full medium scan retains one unchanged sample-IP B104 finding outside repair scope.
- Nonblocking mypy continues to report318 errors outside changed files; no changed-file errors reported.

Source artifacts remain local. Terraform, cloud IAM, remote-state and alternate-platform profiles remain unqualified. UI validation not applicable. Public commit/push/PR/release actions are outside this repair task.

## Changed repair files

Runtime repairs: `infra_automation/artifact_intake.py`, `infra_automation/runner/collection_output.py`, `infra_automation/runner/claims.py`, `infra_automation/runner/collection_client.py`, `infra_automation/receiver_runtime.py`. Existing decoding, authentication, custody and canonical binding primitives are reused; no alternate analysis engine or target-schema migration was introduced. Regressions and qualification changes are recorded in the story File List.

Local verification logs: `/tmp/story16-14-fixes-{focused,ci,root,api-cli-infra,qualification,isolation-final,mypy}.log`. No commit, push, PR or release was performed. UI validation not applicable.
