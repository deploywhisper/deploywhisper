# Story 16.4 lifecycle qualification

This packet qualifies scoped authoring/publication, immutable snapshot export,
live policy/epoch checks, screened audit and configuration. It does not qualify a
run engine, collector, receiver, real grant or integrated release workload.

[Source evidence](source-evidence.json) identifies the baseline, branch, runtime
image and all 15 changed runtime Python files. Those files were byte-checked
against the running Docker image. Tests use isolated checkouts, synthetic SQLite
databases and synthetic identity sessions; no local `.env` or application data
was copied into validation or Docker build contexts.

## Evidence

| Boundary | Proof |
| --- | --- |
| Persistence | 56 packet tests cover synthetic v1.4.0 migration 028 database-copy upgrade, 030 upgrade, downgrade/reupgrade, unversioned recognition, partial-schema refusal and existing-data preservation. |
| Immutability | Database guards reject revision/audit update/delete/replacement, scope movement and epoch reset; repositories flush within caller-owned transactions. |
| Publication | Different keys racing one expected draft version produce one revision. Identical retry after later edits returns its original publication; changed reuse/stale versions conflict. Audit failure rolls back revision and draft-version changes. |
| Scope/identity | All relevant operations recheck real human sessions and live memberships. Cross-project/workspace, synthetic machine publication, missing CSRF and read-only mutation credentials deny. |
| Snapshots | Immutable bytes preserve published definition, validated inputs, source per step and policy. Tests cover uploaded null Git identity, collected immutable commits/catalogs, mixed sources, later edits, wrong scopes/IDs, corruption and oversized-export rollback. |
| Epoch/retention | Tests exercise disable/re-enable, membership/authentication changes, explicit revocation/restore, advisory save/delete and change-and-restore. Both consume/revoke lock orderings pass. Accepted/unknown work remains protected; expired pending evidence needs known invalidation. |
| Transport/cursors | Bounded JSON rejects duplicates, excessive depth/bytes, nonfinite numbers and extra fields; errors remain closed and nonreflective. Signed cursors bind principal/scope/filter/snapshot/limit and cover tampering, expiry, eviction, restart and equal/backward timestamp inserts. |
| Screening | Recognizable/configured secrets are rejected before canonical persistence or snapshot export; audit contains verified metadata and digests rather than raw definitions or inputs. |

Fresh repository checks:

- `bash scripts/ci-local.sh`: **2,270 tests across all ten directories passed**,
  two expected skips, plus eight prompt-injection tests / 96 subtests, skill tests,
  dependency consistency, compilation, Ruff and configured Bandit.
- API/CLI/infrastructure pytest shard: **647 passed, one skipped, 2,176 subtests**.
- Final-source root discovery: **824 tests, OK (two skips)**.
- Pre-review services/workflow pytest shard: **1,362 passed, 2,692 subtests**;
  all those service/automation tests also pass in the post-fix full local CI run.
- Production Python3.11 lifecycle/migration suite: **86 tests, OK (one optional
  external-JSON-Schema-validator skip)**; the corresponding check passes locally.
- Root lint, repository-wide format and diff checks pass. Scoped mypy for the new
  domain/service/route/repository modules passes. Whole-repository mypy is an
  existing nonblocking gate: baseline 314 errors, current 312, no new diagnostic.
  Existing missing PyYAML stubs and legacy typing debt remain.
- Docker production image builds, starts and restarts with migration 031. The
  default disabled-identity profile rejects automation settings access with the
  frozen 403 envelope and `no-store`. Enabled-profile401/CSRF/role behavior is
  covered by the actual FastAPI tests. Dynamic Docker ports are rediscovered
  after restart; startup probes tolerate transient connection resets.

The first broad test pass exposed stale authorization exception imports after
legacy module reloads and an outdated container migration list. Regression tests
reproduced the issue; new lifecycle modules now resolve authorization symbols
through the module, and the list includes 031. Subsequent checks pass. The final
snapshot JSON Schema also rejects keys outside the bounded input-name pattern;
an independent JSON Schema validator proves this alongside runtime validation.

The final BMad review used three fresh independent layers. It found one medium
response-size discrepancy: an arbitrary metadata allowance rejected a valid
workflow whose complete response fit the declared ceiling. The correction measures
the exact shared response envelope before commit. Its regression first failed, then
passed create/save/publish/read, exact 131,072-byte success and one-byte-over rejection
with audit/workflow rollback. Independent re-review found no remaining acceptance gap.

Earlier contract, persistence and service/security reviewers found no remaining
blocking issue. The policy review confirms that stamps are comparison data,
not credentials: future consumers authenticate their operation first and retain
the same reserved transaction through live checking and local mutation.

Application append-only guards are not tamper-proof against a host/database
administrator. Actual machine authentication, runtime quota enforcement, deletion
workers and coordinated restore remain later-story responsibilities. UI validation
is not applicable; no React surface or browser interaction changed.
