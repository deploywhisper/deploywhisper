# Story 17.1 verification packet

Status: **done; ready for PR integration** after implementation, independent review, review repairs and final validation. Scope: provider-neutral contracts, registry, immutable screened snapshots and evidence admission using a network-free reference provider. AWS/Azure/GCP remain registered as explicitly unimplemented. No provider SDK or dependency was added.

## Implemented packets and acceptance proof

| Packet | Implementation | Proof |
| --- | --- | --- |
| 1.1 Contract/registry | Deeply frozen resource identities, scalar facts, read states and connector Protocol; explicit unknown/unimplemented errors. | Contract/registry tests and injected provider extension. |
| 1.2 Snapshot/redaction | Canonical digest over normalized UTC observation, provider/project/opaque scope and screened metadata. Account display masking, raw-content rejection, numeric/string secret echo removal and partial causes. | Immutable/tampered/reordered observation tests plus hostile raw/credential corpus. |
| 1.3 Evidence/freshness | Append live_state to the two existing source Literals only; reuse existing determinism/freshness models and Evidence Law. | Exact legacy serialization fixtures, freshness matrix and retained-fact publication tests. |
| 1.4 Service/storage | Constructor-only current-authorization UOW, default-off configuration, own snapshot metadata/schema namespace, immutable retention/tombstones and atomic evidence publication. | Scope/revocation/early-commit/duplicate/REPLACE/rowid/workspace/publication-set regressions; report-reference retention and history after disable/rotation. |
| 1.5 Reference/conformance | Pure pre-seeded reference observations; no default fake provider registration. | Actual configure/collect/persist/admit/report/read workflow with SDK/execution-module imports and networking blocked. |
| 1.6 Compatibility/CI | Explicit cloud/evidence/storage targets, isolation runner, package/runtime COPY, scoped static checks and unchanged core metadata/history. | Full baseline suites, exact GitHub API/CLI/infra pytest shard, real runtime image and qualified source hash comparison. |

All AC1–7 are evidenced. An unconfigured or disabled project returns before connector construction. Missing server authorization is unavailable rather than default-allow. Snapshot absence, corruption, unreadable/partial resources, invalid scope, missing publication and unvalidated live-state rows cannot mint or commit a grounded claim. Artifact evidence can coexist. Existing report/API/CLI/agent payloads gain no default fields; source enum domains expand additively as required.

## Executed results

- Focused foundation: **120 tests and 121 subtests passed**.
- SDK/network/execution-module isolation: **84 tests passed**.
- Root smoke: **2,224 tests, 3 skipped**, passed.
- Full local CI: **3,723 tests across 12 targets, 3 skipped**, passed, plus isolation, skill and prompt-injection checks.
- Exact API/CLI/infra pytest shard: **834 passed, 1 skipped, 2,456 subtests passed**.
- Ruff lint/format, scoped mypy, compilation/syntax and configured Bandit gate passed.
- Real non-root Python3.11.17 Docker reference workflow, default-off zeroDDL, no Node/provider SDK and core restart checks passed.

Exact commands, versions and critical source hashes are in [final-verification.json](final-verification.json). Independent findings, red/green repairs and profile boundaries are recorded in [review-record.md](review-record.md). Schema isolation decisions are in [the course correction](../../../../_bmad-output/planning-artifacts/sprint-change-proposal-2026-11-13-cloud-storage-isolation.md).

## Storage boundary

The rejected global043/shared-model approach broke released qualification/recovery assumptions; its failed run is preserved in `/tmp/story17-1-shared-head-approach-ci.log`. The final design keeps models/database.py and models/tables.py byte-identical and core Alembic history unchanged. models/cloud_snapshots.py owns separate metadata; cloud/schema.py owns strict version1 marker/table/guard validation. Only explicit enabled configuration initializes it atomically under checked SQLite/FK-enabled physical transactions. Partial or unknown namespaces are never adopted automatically.

Payload lifetime is seven days unreferenced from observation, extended by retained report/evidence references. Duplicate observations do not reset age; purged data cannot resurrect. Disabling or rotating a connector preserves authorized historical inspection. Project lifecycle cleanup prevents inherited opt-in. A valid admission reserves its source before expiry and publishes a durable reference in the same transaction.

## Reproduce

```sh
./.venv/bin/python scripts/verify_cloud_isolation.py
./.venv/bin/python -m pytest tests/test_cloud tests/test_evidence tests/test_services/test_cloud_context_service.py tests/test_models/test_cloud_snapshot_storage.py tests/test_infra/test_cloud_snapshot_migration.py -q --tb=short
./.venv/bin/python -m unittest discover -q
bash scripts/ci-local.sh
./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short
./.venv/bin/ruff check .
./.venv/bin/ruff format --check .
./.venv/bin/mypy cloud/ services/cloud_context_service.py models/cloud_snapshots.py models/repositories/cloud_snapshots.py --ignore-missing-imports --follow-imports=silent --no-error-summary
./.venv/bin/bandit -r cloud/ services/cloud_context_service.py models/cloud_snapshots.py models/repositories/cloud_snapshots.py scripts/verify_cloud_isolation.py --severity-level medium --confidence-level medium
```

The reference-profile runner currently covers the foundation and new storage tests; future optional provider-SDK qualification needs a separate profile while preserving these isolation checks. UI validation not applicable.

## Runtime proof and limits

[Docker result](docker-runtime-result.json) verifies a non-root Python3.11 runtime with no Node/provider SDK, default-off zero cloud DDL, reference collection/persistence/retrieval, historical access after disablement and a successful core restart without changing the core head. The disposable container used no network or host data mounts and was removed. The build context included source files only, with local environment files excluded. Host dependency installation was unnecessary. The wheel package manifest includes cloud; a standalone wheel build was not run because the build backend was absent from the environment and this story authorizes no installation.

This slice exposes an internal server integration boundary. Production authorization adapters, real provider reads/IAM/transport and user-facing settings/report routes remain with later stories. The current single-snapshot admission uses live-evidence ID scans for publication integrity; production-scale optimization must preserve the same guards. Database-owner DDL tampering is outside application admission and detected namespace damage fails closed. No live provider or combined production release profile is claimed.

## Git Flow closeout — 2026-11-16

All three review findings are resolved. Refreshed focused checks (125 tests and 137 subtests), repo-wide Ruff, source-only Docker build and offline built-image smoke passed. See [review repair validation](review-fixes-2026-11-16.json) for full local CI/root/exact-shard results and [closeout evidence](git-flow-closeout-2026-11-16.json) for refreshed packaging proof. The feature branch targets `develop`; provider and production adapter qualification remain outside this foundation.
