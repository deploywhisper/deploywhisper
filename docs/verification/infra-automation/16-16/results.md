# Story 16.16 implementation and verification

Implementation, layered review repairs and required verification are complete.
Story16.16 is done after formal review repairs. The fresh review results are in
[formal code review](formal-code-review.md); the tables below retain development
evidence. Backend and UI remain separate Git Flow branches; release is not claimed.

## Delivered behavior

- Strict human-declared inventory, exact affected/prerequisite coverage, located
  errors, deterministic collection/review waves and versioned canonical digests.
- Migration038 immutable revisions and run associations, exact workflow-step
  coverage, existing shared target aliases/locks and server-derived combined
  evidence. Every collected unit's earliest deadline bounds associated decisions.
- Accessible Inventory editor and confirmation, per-unit uploads/bindings, run
  wave/evidence/lock tables, live invalidation and guarded lost-response recovery.
- Existing shared analysis, advisory report semantics and canonical lock services
  are reused. No dependencies or new execution primitives were introduced.

Uploaded/mixed bundles remain advisory. Actual collected bindings currently
support repository root only. Waves never assert provisioning order or completion;
changed infrastructure/source/map/evidence requires recollection, analysis and a
new decision. No new production authority provider was installed.

## Entry review

Independent readiness review checked16.0 governance/qualification, completed16.3,
16.10 final R4/R5 resolution and16.14 independently repaired collection evidence.
Current source-integrity checks passed before implementation. Final interfaces use
closed declarations, immutable run associations and server-derived evidence with
shared locks. Estimated review units were domain2, integration3–4, UI2–3 and
proof/documentation2; these are planning units, not measured delivery time.

## Validation

| Check | Result |
| --- | --- |
| Domain | 12 tests, 25 subtests pass; independent resource-bound review clear |
| Service | 42 tests, 27 subtests pass; integrated decision/target run 69 tests, 25 subtests pass |
| New API routes | 6 real-session tests pass |
| Migration startup/recovery | 36 tests, 2 subtests pass; broader legacy-head assertions updated and verified |
| `npm run ui:gen-api` | Generated from current `create_app().openapi()` via `OPENAPI_URL=/tmp/story16-16-openapi.json` |
| `npm run ui:typecheck`, `npm run ui:build` | Pass |
| `npm run ui:test` | 432 tests and 2 OpenAPI compatibility checks pass |
| Composed Playwright | 1 real API-backed journey passes, 29.3s; keyboard, two reports, invalidation, zero axe critical/serious violations |
| Screenshots / visual verdict | Ten at 1440/760; 94/100 pass |
| Real `scripts/qualify_collection.py` | Current 49-check run qualified; expanded source hash coverage includes unit integration |
| Collection/isolation integrity | 9 tests, 73 subtests pass; existing isolation qualification hashes remain current |
| Ruff lint / repo-wide format | Pass |
| Security | Touched-code Bandit passes; full CI high-severity gate passes; unchanged sample-IP finding remains outside this change |
| CI mypy command | 318 diagnostics in existing code; zero diagnostics on added/modified lines |
| API/CLI/infra pytest shard | 753 passed, 1 skipped, 2,358 subtests, 413.87s |
| Root unittest discovery | 1,862 tests pass, 3 skips, 798.192s |
| Automation pytest shard | 1,060 passed, 1 skipped, 3,081 subtests, 491.27s |
| Every-directory local CI | All ten targets verified after the documented fixture repairs; initial and resumed outputs retained |

Local Python3.14.3, Node24.7.0, npm11.12.1 and Docker29.1.3. Production Compose
Python3.11.17 and Playwright1.63.0 are recorded in [browser proof](browser-proof.md).
The real collection scope remains offline ARM64/OpenTofu1.13.1; Terraform, cloud
IAM and remote-state profiles are not qualified by this task.

## Review and verification recovery

[Layered review](code-review.md) records independent blind, edge and acceptance
findings and their repairs. The composed test additionally found and repaired the
Inventory account-return allowlist entry; route regression tests pass. Browser
proof preserves initial failures and test-mechanics corrections.

The first `bash scripts/ci-local.sh` passed analysis69, API355, CLI102 and docs51,
then found stale revision037 assertions in the infrastructure suite. All current
head assertions and the migration catalog now expect038. Receiver migration tests
still verify every old guard's exact SQL while allowing new unit guards. The
repeated infrastructure directory passed297 tests with one skip.

The first automation directory run completed1061 tests but hit one unchanged
receiver concurrency fixture failure. A standalone macOS/APFS probe reproduced
concurrent first-lock-file creation returning ENOENT with the directory/file
present (2758/4000 opens); the original test reproduced1/20 failures. The test now
initializes the empty ledger before its four-process contention and always reaps
children before cleanup. Twenty repetitions and the11-test receiver module pass.
Production Linux receiver code is unchanged. The complete automation pytest shard passed after this fixture repair (1,060
passed, one skipped, 3,081 subtests). Root discovery also passed. No failure is
represented as a pass.

The remaining CI directories run through the same `scripts/run-test-targets.sh`
entrypoint. Initial and resumed logs remain separate to preserve the actual
verification history. Root smoke and exact pytest shards use isolated worktrees.

Browser resources and private credentials were removed. The original application
container was restored and health returned HTTP200. No operator database, secrets,
real state or binary plan was committed; no public GitHub write or release occurred.

## Final command evidence

- `./.venv/bin/python -m unittest discover -q`: exit0,1862tests/3skips.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: exit0,753passed/1skip/2358subtests.
- `./.venv/bin/python -m pytest tests/test_infra_automation -v --tb=short`: exit0,1060passed/1skip/3081subtests.
- `bash scripts/ci-local.sh`: initial four targets passed; stale migration expectations repaired. `PYTHON_BIN=./.venv/bin/python bash scripts/run-test-targets.sh tests/test_infra tests/test_infra_automation tests/test_llm tests/test_models tests/test_parsers tests/test_services` repeated infrastructure successfully and exposed the receiver fixture race. The final four targets then passed through the same script; the repaired automation target passed its full pytest shard and root discovery.
- Per-directory counts: analysis69, API355, CLI102, docs51, infra297, automation1061, LLM76, models22, parsers43, services1232 (three expected skips across the directory targets).
- Final `npm run ui:typecheck`, `npm run ui:test`, production UI/Compose builds, `ruff check .`, and repository-wide `ruff format --check .` pass;565Pythonfiles formatted. Final docs discovery51tests passes.

The exact API/CLI/infra shard and root smoke ran from the isolated combined UI
worktree using the repository virtualenv interpreter. Their backend source
matches the main worktree; mutable test data remains isolated. Final log hashes
and runtime versions are in [validation-summary.json](validation-summary.json).

Next BMad handoff: story code-review closure on the separate backend/UI branches.
The internal independent reviews are complete; no public push/PR is represented
as performed. Existing nonblocking mypy diagnostics remain outside changed lines.
