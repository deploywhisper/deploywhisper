# Story17.0 BMad code review — 2026-11-12

Current verdict: **APPROVED after fixes**. All eight patch findings are resolved; no blocking findings remain. See [resolution verification](review-fix-verification.md). Original findings below are retained as review history.

Initial verdict: **Changes requested**.8patch findings (7P2,1P3);0decision-needed;0defer;2dismissed. All three review layers completed. Story remains in-progress; no final story closure or remote push.

## Scope and method

Reviewed53changed/new files (5,676added lines,13removed) against Story17.0, project context, RFC0002, architecture§26 and the canonical feature PRD. Independent blind, edge-case and acceptance layers ran without inherited conversation. The1,504,372-byte generated large-plan fixture was excluded from the blind diff payload and remained available to project-aware reviewers. Existing43focused checks pass; passing tests do not cover the failures below. Production AWS qualification is not demanded by this review.

## Patch findings

### R1 [P2] Validate mandatory response postfilters
- Location: `measurement/benchmark.py:206`.
- Source: blind+edge.
- Deleting a Lambda mapping postfilter still passes validate_contract_calls(); matches_postfilter() defaults to an empty dict and accepts an unrelated UUID. Validate required UUID/function/event-source filters and reject missing filters for operations that require them.

### R2 [P2] Match Route53 routing variants by SetIdentifier
- Location: `measurement/benchmark.py:197`.
- Source: blind.
- The frozen contract requires exact name/type/set-identifier matching, but build_calls() records only Name and Type. A different weighted/failover/latency variant is accepted. Carry the recorded SetIdentifier, including the absent/simple-record case, into the comparison.

### R3 [P2] Restrict benchmark SDK model loading to installed package data
- Location: `measurement/benchmark.py:236`.
- Source: blind.
- validate_sdk_models() uses a default botocore Session. A temporary AWS_DATA_PATH EC2 model with a forged request member makes an otherwise invalid ForgedInput parameter pass validation. Apply the same trusted loader used by SDK and coverage probes and test both environment and home model injection.

### R4 [P2] Drain completed results during throttle backoff
- Location: `measurement/benchmark.py:305`.
- Source: edge.
- The cooldown branch skips processing pending futures. If the deadline arrives during cooldown, already-finished results are cancelled/abandoned without counting them. Deterministic wait ordering reproduced four issued and finished throttled reads but only one reported throttle. Drain completed futures independently of dispatch cooldown before finalizing counts.

### R5 [P2] Provide a provider-based request-cost estimate for AC6
- Location: `measurement/benchmark.py:413`.
- Source: auditor.
- The uniform USD0.005/1000-call input is explicitly an arbitrary sensitivity rate and excludes service/region tariffs. That arithmetic does not establish the provider-cost estimate required by AC6, despite the readiness report marking AC6 satisfied. Retain the useful sensitivity scenario separately; add dated official per-operation pricing/free-operation classifications for the chosen region and derive the manifest estimate without live AWS calls.

### R6 [P2] Detect or explicitly label benchmark hardware identity
- Location: `measurement/benchmark.py:382`.
- Source: blind.
- CPU and model are always Apple M3 Pro and Mac15,7 while other platform fields are detected dynamically. Reproducing the command on another host falsely attributes its timings to this hardware. Detect hardware where supported or require an explicit labelled host description and refuse/mark unknown when unavailable.

### R7 [P2] Validate the frozen family set and operation references
- Location: `coverage/validate_contract.py:60`.
- Source: blind.
- The freeze validator checks only that there are25 families. Renaming aws_security_group to aws_unapproved_family and pointing its operations at missing_template still returns success. Assert the approved versioned family membership and nonempty valid operation references before validating operation definitions.

### R8 [P3] Reject fractional and non-finite measurement bounds
- Location: `measurement/benchmark.py:264`.
- Source: edge.
- A budget of0.5 passes the bounds check and dispatches one call, exceeding the supplied cap. Require nonboolean integer attempt/concurrency counts and finite valid durations/rates; add boundary tests. Current recorded defaults are integers, so this is harness hardening rather than a production-path regression.

## Reproduced results

- Empty supplied manifest passes the per-call validator; dismissed as a separate finding because its per-call role is intentional and existing fixture tests assert900unique requests.
- Removing required mapping postfilter: validator accepts it; unrelated UUID matches.
- Route53 record with matching name/type but different SetIdentifier matches.
- Four futures completed as throttled before backoff; only one throttle counted at deadline.
- Fractional attempt budget0.5 dispatches one request.
- Injected AWS_DATA_PATH EC2 model accepts ForgedInput; no network or real credentials used.
- Renamed approved family plus nonexistent operation reference still passes the25-family freeze validator.

## Dismissed findings

1. Demand to benchmark every frozen secondary request: AC6 permits a scoped measurement spike, and code explicitly chooses primary requests; this is not proof of a complete collector workload and is already qualified accordingly.
2. Demand that validate_contract_calls reject every partial manifest: it is used as a per-request contract checker; fixture count/unique-address assertions cover the generated primary manifest. The separate missing-postfilter issue remains valid.

## Validation and follow-up

All43existing focused checks pass independently. Root2128tests/fullCI3603tests recorded by the development packet remain valid baseline results; no implementation was edited during this review. No new product test suite was run unnecessarily.
Resolve R1–R8, regenerate affected measurement/coverage/final verification evidence and independently re-review before restoring READY or closing Story17.0. Per BMad help routing, development fixes precede the next code review.
Branch: `feature/17-0-grounding-contract` is compliant. Remote push was not performed because review follow-up work remains open. **Blocked: story still in-progress after review.**

## Fix continuation

The maintainer explicitly requested all eight findings fixed and properly tested. R1–R8 are now repaired and independently re-verified with rollback mutation checks; no blocking findings remain. See [review-fix-verification.md](review-fix-verification.md). Final root/full-CI results are pending before terminal story status and Git Flow closure. Earlier changes-requested prose above is retained as historical review evidence.

## Terminal review result

All R1–R8 fixed and independently verified, with mutation checks demonstrating regression sensitivity. 68 qualification checks passed; fresh root discovery passed 2,128 tests (3 skipped); full local CI passed 3,603 tests across 10 shards (3 skipped), plus skill scenarios and 8 prompt-injection tests with 96 subtests. Repo-wide Ruff lint/format (647 files), Bandit medium/high gate, compilation, Python 3.10 syntax and fixture/link checks passed. Story status: done. Git Flow closeout uses the existing feature/17-0-grounding-contract branch and a PR targeting develop.
