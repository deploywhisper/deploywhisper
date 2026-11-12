# Original12.7/12.8 scope and executed evidence

## Contract interpretation

Story12.7 AC1 requires operational documentation of supported SQLite and PostgreSQL paths; it is not a request to implement a new PostgreSQL runtime. Original architecture sections12.1/12.2 (around lines703–707) identify SQLite as the baseline and PostgreSQL as a target shared-install scale path. ADR14 (line1119) explicitly says PostgreSQL is not a baseline dependency. The v1.5 architecture at line1234 excludes PostgreSQL/HA automation and states that roadmap scale paths are not v1.5 support promises. Accordingly, conditional PostgreSQL operator guidance and an explicit unsupported-current-profile boundary are appropriate; introducing a PostgreSQL engine under16.19 would violate its scope.

Story12.8 AC1 requires installation/core analysis without external services and optional-service limitations. It does not explicitly require installing an operating system/Docker from scratch, an empty daemon cache, or an independent human pilot. Those limitations must be disclosed, but they are not automatically missing12.8 acceptance. The distinct16.18/16.19 independent operator pilot remains a real gate and cannot be substituted by this agent exercise.

The new data-lifecycle and restricted-network guides supply these bounded documentation paths. Do not claim that they qualify the future PostgreSQL application profile. Acceptance should be reviewed against the currently supported Docker/SQLite scope; a decision to advertise PostgreSQL support would require its own driver, migrations and operational qualification.

## Actual proof

- Existing16.18 offline-install-results.md/json records complete image archive/layer verification, docker load, fresh state under network none, and28 real CLI/API recovery checks. It explicitly uses an installed Docker host and cached layers.
- core-offline-results.json records actual CLI analysis under network none on the final2c652 image: report1 persisted, advisory_only true, narrative_degraded explicit, exit0. No provider/analysis success response was mocked.
- core-roundtrip-results.json records a fresh real migrated042 core database, actual CLI report generation, SQLite backup API snapshot and independent restored database. Full report rows match, integrity isok, FK violations0, and source remains unchanged. Disposable container removed; no host data mounted.
- Existing authentic released-v1.4.0 upgrade-results.json records028→042 with37 report columns retained and source unchanged.
- Fresh command `./.venv/bin/python -m pytest tests/test_infra_automation/test_operator_recovery_review.py -k 'failed_migration or real_api_removal or backup_after_removal' -q` passed3 tests in3.74seconds. It exercises repeated failed upgrades followed by actual successful migration, source preservation, real API purge/old-backup refusal and valid post-purge restore.
- Existing documentation suite passed60 tests; `git diff --check` passed. No runtime implementation or dependency changed in this work.

These records support current SQLite/core offline operation. They do not establish future PostgreSQL support, host power-loss durability or independent human self-service qualification. Root integration owns final story/status disposition and links to these guides.

## Nonempty deterministic-analysis follow-up

Independent review requested positive finding/evidence proof beyond the empty-plan baseline. The final core-offline-results.json now records an actual network-none CLI run on one synthetic Terraform security-group change, with an asserted deterministic finding linked to deterministic artifact evidence for that exact modified resource. It also asserts persisted report1, advisory-only true, deployment approval false, human decision required, narrative degradation and full SQLite backup/restore row equality. The exact stdin exercise is retained in core-offline-exercise.txt; command and hashes are in the JSON. The earlier empty case is retained only as historical baseline. No analysis/provider response was mocked.
