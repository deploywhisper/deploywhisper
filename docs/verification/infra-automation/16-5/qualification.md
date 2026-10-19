# Story 16.5 engine qualification

The executable harness is `tests/fixtures/infra_automation/engine_v1/qualification.py`.
It uses Python's standard library and the application's installed runtime dependencies,
including SQLAlchemy, Alembic and Pydantic. Pytest is not required by the harness.
All identity, workflow, input, report and runner-slot data is synthetic. Databases
are temporary and separate from the application database. The actual Alembic
upgrade to revision `032_add_infra_automation_engine` runs before fixture seeding;
its foreign keys and immutable-state triggers remain enabled throughout testing.

Run from the repository root, or set `PYTHONPATH` to the read-only mounted source:

```sh
python -m tests.fixtures.infra_automation.engine_v1.qualification --mode fault --output /evidence
python -m tests.fixtures.infra_automation.engine_v1.qualification --mode benchmark --output /evidence
python -m tests.fixtures.infra_automation.engine_v1.qualification --mode capacity --output /evidence
```

For a short, explicitly unqualified harness check, append `--smoke`; a capacity
smoke can also use `--capacity-seconds 3`. Acceptance runs require at least 1,800
actual monotonic seconds and exactly 1,000 benchmark transitions. No accelerated
clock is used for these measurements. The root task owns the Docker command and
records the allocated CPU/memory, source mount and output location alongside the
JSON artifacts. Use a unique container and an ephemeral database, with network
access disabled; do not attach existing databases, credentials or `.env` files.

`faults.json` covers both sides of each fixture boundary and every declared
run/attempt edge. A spawned child executes the actual operation and calls
`os._exit(79)` immediately before or after its outer transaction commit. It first
fsyncs an expected-state manifest to a temporary sidecar. A fresh connection
compares every persisted table row, immutable snapshot byte and audit row with
exact pre-commit or expected post-commit state. Foreign-key and integrity checks
run after each restart. Additional attempt preparation, committed-output adoption
and external-intent operations are included. Cancellation request and completion
labels both exercise the actual `service.cancel_run` transaction: this engine
commits its flag, cancellation decision, request idempotency and audit together.
Process signaling follows that transaction and is independently covered by the
cancellation regressions; it is not an additional persisted commit boundary.

`benchmark.json` records 1,000 actual coordinator `_schedule` calls which submit
a newly committed attempt to a real spawned worker. Samples include database,
claim and process-start orchestration and exclude handler execution. Raw samples
and nearest-rank p95 are retained; the acceptance threshold is strictly below one
second. This is a ready-step orchestration measurement, not a handler benchmark.

`capacity.json` records 10 active runs across two workflows, each with at most
five active runs; each workflow has an uploaded source followed by 49 analysis
steps. Real spawned analysis handlers delay 10 seconds. At most two worker
processes are admitted. Completed runs are replenished through the authenticated
engine admission API and normal coordinator promotion. The capacity horizon
starts after all 10 runs are active. Twenty typed local heartbeat/read slot
doubles are exercised on every sample; these are not real runner agents.
The loop records progress, queue counts, worker and analysis counts, resources,
database/WAL size, integrity checks, physical capacity checks and forged-owner
rejections. A real bounded queue admission probe must return explicit 429
backpressure. The report preserves every sample and any capacity dip.

All reports preserve UTC start/end timestamps, monotonic elapsed time,
Python/SQLite versions, WAL/FULL pragmas, hardware/cgroup resource details and
source hashes before/after measurement. Source changes invalidate the run.
The hashes include engine, authorization, persistence, migration, configuration,
contract and fixture-helper code. No host power-loss durability, real receiver,
real runner, collection/network integration or production analysis adapter is
qualified by these local doubles. Actual results are recorded in the generated
JSON evidence; this document alone makes no acceptance claim.

UI validation not applicable: no rendered surface is changed.
