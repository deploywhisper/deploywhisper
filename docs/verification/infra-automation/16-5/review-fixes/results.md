# Story 16.5 review-fix verification

The five findings from the 2026-10-22 review are fixed in `7bf930a` and `fbb638c`.
The qualified production runtime is frozen at **`fbb638c`**. Corrected runtime-test
fixtures are committed separately at **`570e7ec`**. No production dependency,
public DTO, migration, rendered UI, or real runner/receiver integration was added.

## Finding-to-proof map

| Finding | Fix | Regression proof |
| --- | --- | --- |
| CR16.5-01: coordinator loss leaves old workers running | Independent gated supervisors, two global file slots, and finite lease-bounded creator pulses; signal all groups before a shared 4.5-second join deadline | Real coordinator death; live stalled creator with open pipe; both worker/descendant trees stop within five seconds; real 31-second lease takeover and cancellation; stale/rollback pulses rejected |
| CR16.5-02: terminal siblings retain execution | Stop owned terminal/missing attempts and runs after heartbeat/scheduling; keep capacity until exit is confirmed | Real blocking handler PID disappears after sibling failure; controlled refusal retains slot beyond deadlines; confirmed cleanup permits reuse |
| CR16.5-03: oldest-100 starvation | Bounded advancing pages, project/workflow interleaving, fixed sweep ceiling | Eligible/expired rows beyond 100; independent project quota; continuous new arrivals cannot extend a sweep forever |
| CR16.5-04: temporary storage failures become permanent | Classify only wrapper-owned setup/read/write failures; allow safe bounded retries for capacity429 and coded SQLite BUSY/LOCKED/FULL | Actual wrapper failures, real configuration error propagation, three-attempt exhaustion, committed-output adoption, handler/authority failures remain permanent, external uncertainty never resends |
| CR16.5-05: lease documentation contradicts API | Document public lease/fence/generation metadata separately from private capabilities | Typed StepView contract and corrected operator guide agree |

Each ownership pulse follows current private-capability validation in a committed
reserved transaction, including the cached renewal path. The monotonic pulse is
bounded by three seconds and the persisted coordinator lease; stale or late pulses
cannot revive expired work. A supervisor retains its actual worker leader until
all owned group execution stops, so a reused PID cannot become a signal target.
An abnormal supervisor exit leaves dirty capacity unavailable for trusted operator
recovery. Stable lock files must never be unlinked during operation.

## Fresh qualification of the repaired runtime

| Measurement | Result |
| --- | --- |
| Process/transaction exits | **128 actual exit cases**, exact recovered state/audit; 253.306 seconds |
| Scoped scheduler dispatch | **1,000 submissions**, nearest-rank p95 **19.121 ms**, max 139.908 ms; zero run errors |
| Real capacity horizon | **1,800.124686 monotonic seconds**, 2026-10-23 06:57:59.251401–07:27:59.297793 UTC labels |
| Capacity observations | **6,362 samples**, ten active runs in every sample, at most two analysis workers, 20 exercised synthetic slots, zero errors |
| Capacity progress/backpressure | 270 completed attempts, 272 submissions, explicit queue 429, 119 private-owner denials, 178 legitimate read refreshes |
| Capacity resources | Peak sampled cgroup memory 351,412,224 bytes; DB 8,232,960 bytes; WAL 4,148,872 bytes |
| Durability | Actual migration032, immutable guards, foreign keys, WAL/FULL, integrity/FK checks |
| Corrected Linux automation | **354 tests run**, zero failures/errors, three optional JSON Schema validator skips; 329.510 seconds |

Each reference container had two CPUs, 1 GiB memory, PID limit 128, no network,
a read-only root/source mount, and a 512 MiB temporary filesystem. Platform:
Linux aarch64, Python 3.11.17, SQLite versions/PRAGMAs and hardware/cgroup details
are in the raw reports. Image:
`sha256:889caacc284c32de31ab4e0058c375a8e0ce2bb9aa279f5045ec9ad445a1f6fa`.
No existing application container was stopped or modified. An owned temporary
host sleep assertion prevented suspension during the measured runs.

The dispatch measurement is the declared scoped `_schedule` claim/process-start
submission measurement, excluding asynchronous worker bootstrap and handler time.
It is not an end-to-end cold-start latency claim. Total benchmark time 1675.388 s
and capacity throughput include actual spawned process initialization overhead.

Raw immutable reports and checksums: [reference-results.json](reference-results.json),
[capacity.json.gz](capacity.json.gz),[benchmark.json.gz](benchmark.json.gz),
[faults.json.gz](faults.json.gz). Full current Linux regression:
[process.json](process.json),[process.log](process.log).

## Explicit source provenance

The three reference phases were run entirely on `fbb638c`, with all 136 hashes
identical at start/end. After those measurements completed, `570e7ec` changed only
three unittest modules that qualification neither imports nor executes:

- `tests/test_infra_automation/test_engine_coordinator.py`
- `tests/test_infra_automation/test_engine_cancellation.py`
- `tests/test_infra_automation/test_engine_recovery.py`

All **133 remaining entries**, including all production runtime, contract, migration,
harness, and actually used fixture dependencies, remain byte-identical. The harness
uses `LifecycleCase`, `EngineClaimsTests`, `EngineRepositoryTests` and
`WorkflowSnapshotTests`; it uses its own handlers and never loads the three changed
test modules. This was independently checked statically and by dynamic import.
[Exact hash differences](source-provenance.json) are retained; the full 136-entry
qualification map is deliberately not claimed to match the later test revision.

The later full Linux run validates `570e7ec` fixtures on the same qualified image;
all 136 of its start/end hashes match the current checkout. Native full CI and
exact shards also passed the production fixes at `fbb638c`; current-fixture host
checks are recorded in the final verification summary.

## Validation environment corrections

The original12/15-second fixture waits ended while five supervised serial stages
were still progressing: earlier steps had succeeded and later steps were claimed.
The 30-second test budget covers the declared startup handshakes. The parallel-run
test now proves both durable runs succeed with committed output and distinct
per-attempt nonces, allowing legitimate bounded retry history. Actual run/attempt
deadlines and the five-second cancellation assertion were not relaxed.

The production image intentionally omits dev-only tools. Its full unittest suite
also exercises a Python 3.10 TOML fallback using the existing locked `tomli==2.5.0`.
The corrected test container mounts that package's pure-Python files read-only,
verified against the installed distribution RECORD and unchanged requirements-dev
pin. [Test dependency provenance](test-dependency-manifest.json). No package or
lock-file change was made. The three remaining skips are optional JSON Schema
validator checks, explicitly listed in `process.log`; runtime Pydantic validation,
schema-fixture parity and API tests remain covered.

Earlier suspended or incomplete attempts are not qualification evidence. Their
failures led to real fixes for cold shutdown, finite owner liveness and test
startup assumptions; fresh passing artifacts above supersede them.

UI validation not applicable. These proofs qualify trusted local analysis doubles
and synthetic heartbeat/read slots, not real receiver/runner transport, credentials,
infrastructure execution or host-power-loss durability. Production handlers remain
empty until Story 16.6 integration.


## Final native verification and handoff

All current-fixture checks passed on `570e7ec`:

| Check | Result |
| --- | --- |
| `bash scripts/ci-local.sh` | All ten directories passed: analysis 69, API 287, CLI 102, docs 51, infra 272, automation 354, LLM 76, models 22, parsers 43, services 1,232; dependency/lint/format/security gates passed |
| Root `unittest discover -q` | 1,062 tests, OK, five skips |
| Exact services/automation pytest shard | 1,583 passed, three skipped, 3,084 subtests passed |
| Exact API/CLI/infra pytest shard | 660 passed, one skipped, 2,200 subtests passed on byte-identical runtime/API/CLI/infra sources; current CI also reran all three directories |
| Linux production runtime automation suite | 354 tests, zero failures/errors, three optional validator skips |
| Ruff lint / repo-wide formatting | Passed; 408 Python files formatted |
| Mypy matching CI scope | 313 existing diagnostics versus 314 baseline; no new diagnostics; changed engine scope clean |
| Bandit | No new findings; high gate passed; only unchanged medium B104 sample-IP comparison |
| Production image build/start/restart | Healthy, migration 032, integrity OK, zero empty-registry engine identities/leases/slot directory |

[Verification summary and log checksums](verification-summary.json).
[Runtime startup/restart result](runtime-smoke.json).
Independent source and artifact audit found no outstanding blocker. Story 16.5
returns to **review** with all five review items resolved. Runtime and test
integration scope remains bounded as described above; this is not a release claim.
The temporary containers created by this task were removed after evidence capture.
The original Epic17 checkout and PR #159 were untouched.
