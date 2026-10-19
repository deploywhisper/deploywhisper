# Harness validation — 2026-10-19

These checks validate the harness before the reference Docker measurements.
They do not replace the full 1,000-transition or 1,800-second reference runs.
The host environment was macOS ARM64 with Python 3.14; the intended reference
container uses Linux ARM64, Python 3.11, two CPUs and 1 GiB memory.

Commands used the repository virtual environment's Python/Ruff executables:

```sh
python -m pytest tests/test_infra_automation/test_engine_qualification.py -q
ruff check tests/fixtures/infra_automation/engine_v1/qualification.py tests/test_infra_automation/test_engine_qualification.py
ruff format --check tests/fixtures/infra_automation/engine_v1/qualification.py tests/test_infra_automation/test_engine_qualification.py
python -m tests.fixtures.infra_automation.engine_v1.qualification --mode fault --output /private/tmp/s165-f-final
python -m tests.fixtures.infra_automation.engine_v1.qualification --mode capacity --smoke --capacity-seconds 3 --output /private/tmp/s165-f-final-smoke
python -m tests.fixtures.infra_automation.engine_v1.qualification --mode benchmark --smoke --transitions 20 --output /private/tmp/s165-f-final-smoke
```

Results:

- Five regression tests passed in 3.39 seconds. Ruff lint/format checks passed.
- The complete frozen fault corpus passed all 128 spawned-process exit cases in
  113.222093 seconds. Every exact restart state/audit comparison, foreign-key
  check and integrity check passed. Source hashes were identical before/after.
- The short capacity check ran for 3.135456 actual seconds and retained 12
  samples: ten active runs in every sample after warmup, two actual workers,
  two analysis attempts in flight, twenty exercised online slot doubles,
  successful explicit queue backpressure and a rejected forged private owner.
  Source hashes were identical. This smoke result is explicitly unqualified.
- The short benchmark measured twenty actual ready orchestration transitions
  in 6.968677 seconds, with p95 0.024379 seconds and at most two real workers.
  Source hashes were identical. This smoke result is explicitly unqualified.

Temporary artifacts are `faults.json` in `/private/tmp/s165-f-final`, and
`capacity.json` / `benchmark.json` in `/private/tmp/s165-f-final-smoke`.
The reference container command, complete workload results and permanent JSON
artifacts must be recorded separately before accepting AC7. No real runner,
receiver or host power-loss qualification is claimed. UI validation not applicable.
