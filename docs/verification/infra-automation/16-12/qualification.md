# Story 16.12 qualification record

## Scope

Protocol/enrollment/attempt qualification uses synthetic projects, identities and collection profiles. No real infrastructure credentials or plan/state enter fixtures. UI validation is not applicable to these backend/client changes.

## Reference workload

The canonical [PRD](../../../../_bmad-output/planning-artifacts/prd-infra-automation.md) specifies Linux, 4 vCPU, 8 GiB RAM, local SSD, singleton SQLite; 20 compatible runner processes; 10 active workflows; 50-step definitions; at most 2 deterministic analysis jobs; 100 warmups then 1,000 measured claims with timestamps, p50/p95/p99 and failures. The wider capacity qualification additionally requires 30 minutes including saturation.

Initial environment inspection (2026-11-04): `docker info --format '{{.OSType}} {{.NCPU}} {{.MemTotal}}'` reported `linux 12 8217165824`. This is below 8 GiB and local-SSD characteristics have not been established. Docker CPU restriction can provide 4 vCPU but cannot establish missing memory/storage evidence.

**Reference capacity is not qualified.** A local diagnostic run may exercise the actual authenticated SQLite service path; its result must retain environment mismatches, transport limitations and failures. It cannot replace the named-profile acceptance gate or advertise 20-runner capacity. Production isolation remains unqualified by this story.

## Commands and results

The reproducible diagnostic harness is [`scripts/benchmark_runner_protocol.py`](../../../../scripts/benchmark_runner_protocol.py). It enrolls 20 separate synthetic runner clients, starts 20 OS processes, publishes a 50-independent-collection-step definition, maintains batches of 10 durable runs, and executes actual queue selection, authenticated polling, frozen message parsing, claim, screened upload and completion against SQLite. Samples time durable pending-attempt enqueue through claim commit. Claims are serially dispatched round-robin; this is not a concurrent saturation workload. Process IPC substitutes for HTTPS; no real infrastructure collection occurs. Warmups and measured rows retain individual UTC enqueue/claim timestamps.

| Run | Warmups / measured | Failures | p50 | p95 | p99 | Reference qualified |
| --- | --- | --- | --- | --- | --- | --- |
| [Local macOS diagnostic](benchmark-local.json) | 100 / 1,000 | 0 | 25.61 ms | 39.84 ms | 54.24 ms | no |
| [Final Linux Docker diagnostic](benchmark-linux.json) | 100 / 1,000 | 0 | 54.82 ms | 99.63 ms | 150.39 ms | no |

Executed commands:

```sh
./.venv/bin/python scripts/benchmark_runner_protocol.py --output docs/verification/infra-automation/16-12/benchmark-local.json

docker run --rm --cpus=4 --memory=7g --user=0 \
  -v /Users/psaho01/deploywhisper:/workspace -w /workspace \
  --entrypoint python deploywhisper-deploywhisper:latest \
  scripts/benchmark_runner_protocol.py \
  --output docs/verification/infra-automation/16-12/benchmark-linux.json
```

Both exited 0 for diagnostic sample completion. **AC6 reference-workload qualification reports failure**, irrespective of these low diagnostic latencies. No runner capacity is advertised. Linux used kernel `6.12.54-linuxkit` ARM64, Python `3.11.17`, SQLite `3.46.1`, container image `sha256:3d5c2573d35a79b86a21d882769a3833852b9ffc840a3ad29fcc0a761b3aed8b`, and an explicit 4-CPU/7-GiB container limit. Host physical CPU enumeration reports 12; it does not represent the cgroup allowance. The host Docker memory total is 8,217,165,824 bytes, insufficient for the required 8 GiB. Local SSD characteristics, HTTPS latency and 30-minute saturation remain unverified.

The Linux diagnostic was rerun after the R1–R4 review repairs (including encoded audit reasons and final fractional credential-deadline checks), from `2026-11-04T05:37:51.495261+00:00` through `2026-11-04T05:41:16.848974+00:00`. Its report captures source hashes and confirms `source_hashes_unchanged: true`; actual cgroup values were `cpu.max: 400000 100000` and `memory.max: 7516192768`. All 100 warmups and 1,000 measured claims completed with zero failures. Concurrent repository validation may affect diagnostic timings.

The macOS result remains an earlier developmental diagnostic without source-hash/cgroup capture. Neither run certifies the PRD reference workload. The harness always emits `reference_qualified: false` to prevent accidental capacity claims.

Focused authorization evidence: `./.venv/bin/python -m pytest tests/test_infra_automation/test_runner_authorization_matrix.py -q --tb=short` passed 2 tests and 64 subtests. The [matrix](authorization-matrix.md) identifies each role/scope/action obligation. Repo-wide Ruff format check passed at 513 files during packet verification; final whole-story checks belong to the parent completion record.

Combined protocol/client/enrollment/attempt/matrix/API packet check:

```sh
./.venv/bin/python -m pytest \
  tests/test_infra_automation/test_runner_authorization_matrix.py \
  tests/test_infra_automation/test_runner_enrollment.py \
  tests/test_infra_automation/test_runner_protocol.py \
  tests/test_infra_automation/test_runner_client.py \
  tests/test_infra_automation/test_runner_attempts.py \
  tests/test_api/test_infra_automation_runner.py -q --tb=short
```

Result: **40 passed, 158 subtests passed in 5.70 seconds**. This includes the complete role matrix and updated per-operation scope/profile/capability/audience denials. Whole-repository CI and subsequent review repairs are recorded separately by the story owner.

## Independent review and repair checks

The independent `gate_review` reviewer reported no unresolved high-severity findings after the final security and clock repairs. Reported focused checks passed **35 tests / 95 subtests** and **16 tests / 21 subtests**. The review checked live credential and epoch enforcement, retained task authority, closed machine interfaces and the distinction between diagnostic timing and reference qualification. These results are scoped review evidence; the parent story's complete CI run remains the source of truth for repository-wide acceptance.

A subsequent deadline review found that whole-second UTC expiry advertised on the wire could precede a fractional SQLite timestamp. The former comparison could therefore accept authority briefly after the advertised deadline. The final repair treats the advertised second as an exclusive boundary for enrollment, both runner authentication paths, task operations and grant polling. Polling rechecks that boundary before revealing a task grant; screening cannot extend authority across it. Regression cases include legacy fractional enrollment/credential expiry, exact advertised task expiry, polling at expiry, and screening that crosses the deadline. The Linux diagnostic reported above is rerun after this repair; it remains a diagnostic, not reference capacity qualification.

Executed `./.venv/bin/python -m pytest tests/test_infra_automation/test_runner_attempts.py tests/test_infra_automation/test_runner_enrollment.py -q --tb=short` after the deadline repair: **36 passed, 96 subtests passed in 5.62 seconds**.

## Final development verification

- Root `./.venv/bin/python -m unittest discover -q`: 1,612 tests, three skips, successful.
- Exact `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: 732 passed, one skipped, 2,353 subtests.
- `bash scripts/ci-local.sh`: lint, repo formatting, dependency check, Bandit, compile, skill tests and analysis/API/CLI/docs/infra groups passed. The automation group encountered one receiver concurrency temporary lock-file failure. The individual test and full 11-test receiver runtime suite passed immediately on rerun. After the wire-deadline repair, `./.venv/bin/python -m unittest discover -s tests/test_infra_automation -q` passed 837 tests with one skip.
- Remaining local CI coverage was completed explicitly with `PYTHON_BIN=./.venv/bin/python bash scripts/run-test-targets.sh tests/test_llm tests/test_models tests/test_parsers tests/test_services`: 76/22/43/1,232 tests passed respectively (one LLM skip). All ten local CI directories therefore completed successfully across the original run and continuation; the original script exit was nonzero and is not relabeled a clean first pass.
- Final administration matrix: two tests and 300 subtests passed. Post-deadline task/coordinator and enrollment/API suites passed 42/18 tests respectively.
- Final `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .` (515 files), touched-code Bandit, compile checks and `git diff --check` passed.
- Fresh temporary-database `python app.py` smoke: health200; plaintext runner operation403. UI validation not applicable.

The intermittent receiver temporary-file failure is retained as a follow-up risk; receiver runtime code was not changed or its test weakened. Production collection/isolation, named-reference capacity and signed distribution remain unqualified. Story status is review, not released or Git Flow review closure.

## Review repair verification

R1–R4 are repaired and independently verified. The latest full `bash scripts/ci-local.sh` exited 0 without retries, covering all ten test directories (3,083 test executions). Root unittest passed 1,636 tests with 3 skips; exact API/CLI/infra pytest passed 734 with 1 skip and 2,353 subtests; final focused runner suite passed 82 tests / 617 subtests. See [review repair record](review-fixes.md) for commands, cases and limits. The earlier transient receiver test failure above is historical; no such failure occurred in this clean full CI run.
