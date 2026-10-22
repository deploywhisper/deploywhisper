# Story 16.5 qualification results — 2026-10-22

All owned engine acceptance criteria passed on frozen source `cc27c6f`.
The production runtime code is `1661a94`; the later commit changes the synthetic
qualification harness and its documentation only. The original checkout and PR
#159 were left untouched. The story is ready for BMad code review, not release.

## Reference measurements

| Proof | Result |
| --- | --- |
| Actual monotonic capacity interval | **1,800.102835 seconds**, 2026-10-22 04:47:58.968469–05:17:58.877595 UTC |
| Capacity occupancy | **10 active runs in all 6,502 samples**, five per workflow; maximum two local workers and two analysis jobs; 20 exercised synthetic slots |
| Capacity progress | 316 completed attempts; zero engine errors; explicit queue 429; 120 private-owner denials; 178 legitimate human-session read refreshes |
| Ready-step overhead | **1,000 actual newly submitted attempts**, p95 **0.014543958 seconds** (14.54 ms), below one second; 767.121588 seconds total |
| Process exits | **128 cases**, exit immediately before/after each declared transaction boundary and every legal state edge; exact state/audit recovery; 232.403528 seconds |
| Durability | Actual Alembic upgrade to 032, immutable triggers, foreign keys, WAL/FULL, integrity and FK checks |
| Frozen sources | 129 source/fixture hashes identical before and after each phase |
| Capacity storage/resources | Peak sampled cgroup memory 237,535,232 bytes; DB 8,597,504 bytes; WAL 4,165,352 bytes |

Qualification duration is measured by the monotonic clock. The UTC labels are
recorded separately after the setup probe; their approximately 0.194-second
offset does not shorten the measured 1,800.102835-second horizon.

Reference platform: Linux aarch64, Python 3.11, Docker runtime image
`sha256:0131bdec008681265fbcc406e5c6f3a8af6c08e2b76735606beaf97bd93f50fe`.
Each isolated container had two CPUs, 1 GiB memory, PID limit 128, no network,
a read-only root filesystem and source mount, and a synthetic SQLite database in
a 512 MiB temporary filesystem. Qualification commands had health checks disabled.
The three phases ran concurrently in separate containers. Hardware, CPU quota,
RSS/memory, samples, raw timings and database sizes are preserved in the artifacts;
these are allocated CPU and sampled memory measurements, not CPU utilization claims.
No existing application container was stopped or changed.

[reference-results.json](reference-results.json) contains the readable summary,
platform details, source commit and SHA-256 checksums. Complete raw evidence is
compressed losslessly in [capacity.json.gz](capacity.json.gz),
[benchmark.json.gz](benchmark.json.gz) and [faults.json.gz](faults.json.gz).
Use Python `gzip.open` or `gzip -dc` to read them. Each artifact retains its own
source hashes, UTC/monotonic timestamps and qualification flag. The process-fault
artifact includes every individual case and exact-recovery assertion.

The initial capacity attempt was unqualified: its synthetic human session idled
for more than five minutes before replenishment. The harness now performs actual
authorized run reads every ten seconds. A regression verifies idle rejection,
activity beyond the original idle boundary, and rejection after activity stops.
Runtime identity policy and stored timestamps are not bypassed. All three final
reference phases above were rerun using the corrected harness.

## Validation and review

| Command / check | Result |
| --- | --- |
| `./.venv/bin/python -m unittest discover -q` | 1,002 tests; OK, five optional skips |
| `bash scripts/ci-local.sh` | All ten test directories passed, including 1,232 service tests; dependency check, lint, formatting, compilation and security gates passed |
| `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` | 660 passed, one skipped, 2,200 subtests |
| `./.venv/bin/python -m pytest tests/test_services tests/test_infra_automation -v --tb=short` | 1,524 passed, three skipped, 3,017 subtests |
| `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .` | Passed; 401 Python files formatted |
| Mypy, matching CI scope | 313 existing diagnostics versus 314 at baseline `3af659e`; no new diagnostics after normalizing line numbers; scoped engine and repository clean |
| Bandit | No new findings; high-severity gate passed. Existing B104 medium finding compares a sample IP literal in unchanged `services/sample_incident_pack.py`; it is not a socket bind |
| Production Docker build/start/restart | Passed; healthy API, persistent migration 032, integrity OK, zero coordinator leases/audit identity for empty registry |
| `git diff --check` | Passed |

Independent reviewers approved each packet before the next. Confirmed defects
were corrected and reverified: SQLite implicit savepoint commit, missing byte
accounting/corrupt counters, retry after a known permanent outcome, worker-slot
coupling of run admission, changed cancellation replay, exited process-group
cleanup, and the synthetic idle-session fixture. Layered trust-boundary review
covered authorization/CSRF, private capabilities, audit identity, immutable state,
handler registry, process ownership and storage limits. No dependency was added.

UI validation not applicable: no rendered surface changed. The production handler
registry remains empty until Story 16.6 supplies the adapter. Synthetic slot,
external-uncertainty and process doubles do not qualify real runners, receivers,
transport, credentials, infrastructure execution or host power-loss durability.
