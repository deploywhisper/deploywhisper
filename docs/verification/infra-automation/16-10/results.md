# Story16.10 registered targets, outbox, grants and locks

Latest review: **accepted scoped implementation**. R4/R5 and the validated
supervision correction are complete. Final [resolution and qualification](r4-r5-resolution.md)
records the final source, all passing gates and retained historical limitations.

Date: 2026-10-30. Baseline: merged Story16.9, `501d789460adccdb1765313f996df42583dc96a1`.
Implementation branch: `feature/16-10-targets-outbox-grants`.

This record qualifies the registered-target and handoff authorization slice.
The [owning contract](../../../infra-automation/handoff-contract-v1.md) and
[entry reassessment](../../../../_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-30-story-16-10.md)
record the interface and dependency decisions. Frozen receiver/prototype/schema
artifacts remain unchanged. Formal BMad code review follows this dev-story.

## Acceptance evidence

| AC | Implemented boundary | Executable evidence |
| --- | --- | --- |
| AC1 | Admission atomically captures immutable target snapshots and canonical locks before collection; aliases across projects share the unique held lock | `test_target_admission`, `test_target_persistence`, `test_target_references`, `test_handoff_alias_references`; cross-project and multi-target collisions roll back the whole run admission; original input/revision/snapshot bytes remain unchanged |
| AC2 | One reserved transaction refreshes live authority, exact material/custody/ref, selected required ancestry and deadlines before exact immutable intent, grant verifier and outbox commit | `test_handoff_service`, `test_target_capacity`, API target/handoff tests; callback mutation, raw-SQL stale identity-map, audit/storage failure and final clock tests; network port is called after committed sending intent |
| AC3 | Scoped request identity and one operation per approval AND run/handoff prevent replacement; exact receiver mapping and one-use grant CAS bind both digests, payload, epochs, identity and expiry | `test_receiver_protocol`, `test_handoff_service`, `test_target_persistence`; frozen vectors, altered wire even with recomputed digest, duplicate/concurrent consume, key rotation and lost-response status recovery |
| AC4 | Only operator-allowed registered HTTPS origins and fixed dispatch paths; validate every DNS answer, pin TCP address, verify peer before/after verified TLS; no redirects/proxies | `test_target_transport` IPv4/IPv6, mapped/transition forms, metadata/private/loopback/mixed DNS, rebinding, peer mismatch, exact internal exception, bounds and timeout corpus; fixed GitHub API version `2026-03-10` asserted in emitted request |
| AC5 | Start/claim/prepare/dispatch/consume/action checks retain live feature/member/receiver/target/restore generations and exact selected proof | `test_target_admission`, `test_handoff_service`, `test_handoff_report_context`; disable/re-enable, reviewer/requester revocation, restore, custody/ref changes, callback races and late caller revocation; durable history/receipts remain readable under current read authorization |
| AC6 | Sending marks parent run external-possible before delivery; unknown/cancel/lease retain lock; exact consumed sequenced terminal proof or privileged audited uncertainty break resolves it | `test_handoff_service`, `test_target_admission`, `test_target_persistence`; no resend after possible delivery, no replacement grant, retired old claim cannot reacquire, before/after audit and read-without-event tests |

## Persisted-boundary crash and concurrency corpus

`test_handoff_process_recovery` uses actual subprocess `os._exit` and reopens the
same private SQLite database. Credentials and transient grant values are not
written to argv, logs or exported fixture files. These are controlled process
crashes, not host-power-loss qualification.

| Fault boundary | Verified recovery |
| --- | --- |
| Prepare before commit | No partial operation/outbox/grant/audit survives |
| Prepare after commit | Same immutable operation, payload and grant verifier recover; no replacement |
| Delivery after sending claim commit | Possible-delivery intent survives; no second send; lock retained |
| Consume before commit | Grant remains available with no partial receipt/consumed state |
| Consume after commit | Original durable receipt recovers; repeat consume denied |
| Concurrent consumption | One transactional CAS winner |
| Lost consume response / concurrent action checks / receiver restart | Durable receiver-double ledger counts at most one action per operation; online admission itself is a repeatable deny check, not the action fence |
| Audit or capacity failure | Intent/receipt and logical storage charge roll back together |
| Slow material/ref/disk callback | Refreshed deadlines and monotonic floors deny stale authority |

The receiver ledger is an independent SQL test double. Production receiver
storage, HTTP receipt/outcome/reconcile routes, dispatch credential carrier,
collector custody and real GitHub effects remain Story16.11/later ownership.
Material/ref/delivery ports default unavailable. No production apply or end-to-end
remote exactly-once guarantee is claimed. Verified operation terminal resolution
can release its lock; parent-run terminal reconciliation remains Story16.11.

## Secret and transport corpus

`test_handoff_secret_screening` submits actual derived synthetic grants through
registry identifiers and lock-break reasons and checks the database dump for
absence. Raw, upper-case, embedded, URL-encoded and four bounded base64 layers
are screened without requiring a configured grant key. Existing safe logging
screens access URLs and exceptions. The operation API/audit expose digests and
recorded metadata, never plaintext grant or credentials. Only verifier/key-ref
persist; a key change cannot mint replacement authority.

DNS/TCP/TLS/HTTP doubles qualify the transport policy without external sends.
The API-version assertion qualifies request construction only; GitHub run-ID
interpretation and authenticated terminal outcomes are not supplied here.

## Verification results

Final command results are recorded below. Host uses Python 3.14;
the multi-stage production image uses Python 3.11, nonroot `appuser`, no Node
runtime, schema035 and no seeded identity accounts. The backend runtime smoke
uses an isolated Compose project with disposable data tmpfs and a random
localhost port. The existing operator container and port8080 are preserved.

UI validation not applicable. No React rendered route, interaction, keyboard or
accessibility surface changed; only generated OpenAPI TypeScript declarations
were refreshed from the current source app and typechecked. Target settings UI
remains the later owning story.

| Command / check | Result |
| --- | --- |
| `docker build -t deploywhisper-story16-10:qualification .` | Passed; Linux ARM64 multi-stage image `sha256:aeab7d605fabbba2d0f19712eb818932334596b36e3929d39fbc136886edf8b1` |
| Isolated Compose health/OpenAPI/runtime smoke | Passed; Python 3.11.17, schema035, nonroot, noNode, zero seeded identity accounts; registry/human handoff routes present and no receiver consume HTTP route |
| Production image `python -m unittest` focused target/handoff/API modules listed below | 156 tests run, OK, one optional JSON-schema-validator skip; 80.855s |
| Fresh-process migration regressions | 57 existing focused migration tests and 5 new handoff migration tests passed |
| `./.venv/bin/python -m unittest discover -s tests/test_infra -q` | 284 tests run, OK, one existing opt-in skip |
| `npm run ui:test` | 256 passed in16 files |
| `npm run ui:typecheck` | Passed |
| Current-source OpenAPI export + `OPENAPI_URL=/tmp/story16-10-openapi.json npm run ui:gen-api` | Passed; generated declarations refreshed |
| `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .` | Passed; all 474 Python files formatted |
| Scoped mypy on 10 new source modules | Passed; no issues |
| `git diff --check` | Passed |

<!-- final-broad-results -->

### Review-fix validation — 2026-11-02

R1/R2 fixes are in `services/infra_automation_handoffs.py`; eight regression
methods in `test_handoff_service.ReviewBoundaryRegressionTests` cover all four
ref callbacks × custody/evidence/binding changes, both disk-probe custody-loss
boundaries, restarted clock rollback, same-instant repeatability and audit
rollback/chaining. The first six methods reproduced 14 failures before code
changes. The complete handoff service suite is now green: 60 tests, 30 subtests,
26.20s. An independent read-only re-review found no remaining R1/R2 defect.

| Check after review fixes | Actual result |
| --- | --- |
| `docker build -t deploywhisper-story16-10:review-fixes .` | Passed; image `sha256:558b8c95bb2d52cef8a5b4b940dccbac12a834f5829227291063f828c3e27eea` |
| Isolated production-image startup smoke with `TestClient(create_app())` | Passed: health200, target/handoff OpenAPI, schema035, zero seeded identities, nonroot/no Node; Python 3.11.17; disposable tmpfs, network disabled |
| Production-image `python -m unittest -q` on all 15 focused modules | 164 tests run, OK, one optional JSON-schema-validator skip; 88.371s; read-only test/schema mounts, disposable tmpfs and no network |
| Scoped mypy on 10 story source modules | Passed; no issues |
| `./.venv/bin/python -m unittest discover -q` | 1,447 tests run, OK (2 existing skips), 690.308s |
| `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` | 709 passed, 1 skipped; 2,316 subtests, 516.76s |

Final root discovery, exact API/CLI/infra shard and full local CI all completed
against the same frozen source. `bash scripts/ci-local.sh` exited 0 on the fresh
serial run: **2,893 tests across all 10 directories, OK (2 existing skips)**.
It also passed Ruff lint/format, pip consistency, the configured Bandit gate,
compileall, the skill test matrix and the prompt-injection check.

| Local CI directory | Tests run | Result |
| --- | --- | --- |
| `tests/test_analysis` | 69 | OK |
| `tests/test_api` | 324 | OK |
| `tests/test_cli` | 102 | OK |
| `tests/test_docs` | 51 | OK |
| `tests/test_infra` | 284 | OK (1 skipped) |
| `tests/test_infra_automation` | 690 | OK |
| `tests/test_llm` | 76 | OK (1 skipped) |
| `tests/test_models` | 22 | OK |
| `tests/test_parsers` | 43 | OK |
| `tests/test_services` | 1232 | OK |

Final logs: `/tmp/story16-10-fixes-ci-final.log`,
`/tmp/story16-10-fixes-unittest.log`,
`/tmp/story16-10-fixes-api-cli-infra.log`,
`/tmp/story16-10-fixes-runtime.log` and
`/tmp/story16-10-fixes-runtime-smoke.log`.
Scoped mypy passed all 10 story modules. The final repo-wide Ruff format check
covered 474 Python files; Ruff lint and `git diff --check` also passed.
Bandit's high/high gate passed. Its medium report retains one existing B104
warning for the synthetic `0.0.0.0` sample in `services/sample_incident_pack.py`;
changed handoff code has no medium/high findings. No suppression was added.

All three review findings are resolved. No new dependency, schema change or
rendered UI change was needed for these fixes. UI validation not applicable.
The registered-target/receiver qualification remains scoped to the declared
doubles and controlled process recovery; real receiver/custody integration and
host-power-loss durability remain the later owning stories.



The15 focused modules are `test_target_contracts`, `test_target_persistence`,
`test_target_service`, `test_target_admission`, `test_target_capacity`,
`test_target_references`, `test_target_transport`, `test_receiver_protocol`,
`test_handoff_service`, `test_handoff_process_recovery`,
`test_handoff_alias_references`, `test_handoff_report_context`,
`test_handoff_secret_screening` under `tests.test_infra_automation`, and
`test_infra_automation_targets`/`test_infra_automation_handoffs` under
`tests.test_api`. They run in the real runtime image with read-only test/schema
binds and disposable data, without live delivery ports.

Constructor searches used repository-wide `rg` for every new ORM/DTO/credential/
wire/response model; consumers are the typed services/repositories, API schemas,
generated declarations and synthetic fixtures. Existing required constructor
fields were not changed. The root fixture and exact GitHub API/CLI/infra shard
were rechecked; final results are in the review-fix table above. Both CI discovery configurations already include
`tests/test_infra_automation`; no discovery script change was needed.

## Corrections made during qualification

Independent contract/security checks led to explicit separate decision/receiver
hashes, final required-ancestor deadline checks, exact reviewer mode/human count,
narrow receiver report context, fresh ORM state after raw-SQL callbacks, retained
unknown state before late caller denial, parent-run external-possible marking,
whole-second published grant deadlines and a durable test-double action fence.
Quota charges now include retained target/intent/receipt copies exactly once and
roll back on denial. Uppercase workflow aliases resolve canonically without
changing stored workflow bytes. Generated grants join shared content/log
screening. The legacy external-effect fixture now registers/captures its target
instead of bypassing the new admission guard.

Production-image execution caught older SQLite evaluating `json_extract` on
invalid bytes despite an adjacent `json_valid` conjunction. A lazy `CASE` now
denies malformed, truncated and invalid-UTF8 snapshots with the intended
integrity error on both SQLite versions. No validation was weakened. The first broad discovery overlapped that migration
file correction, so its long-lived imported guard map differed from fresh child
Alembic processes. That mixed-source run is not final verification. Fresh-process
exact guards match without a production verifier change. The broad run also
found stale034 head assertions, the old no-handoff-route assertion and two legacy
external-effect fixtures lacking real registry capture. Tests now assert035,
the exact new human handoff routes with no receiver transport, and genuine
registered-target admission; all broad commands are rerun against frozen source.

No dependencies or generic webhook adapter were added. This slice reuses the
existing authorization/session, quota, audit, clock, canonicalization and error
boundaries. Database/host administrators remain trusted. Controlled crash tests
do not establish storage durability under power failure.


The first post-fix local CI attempt passed analysis 69, API 324, CLI 102, docs 51
and infra 284 (one skip), then directory discovery of infra-automation ran 690
methods in 349.296s and reported three errors from one inherited
`test_blocking_handler_does_not_block_tick_or_second_claim` and its cleanup:
local worker termination could not be confirmed. Root discovery had passed that
coverage, and the exact directory-import isolated case passed in 3.240s. No
handoff assertion failed. The parent traceback does not establish the supervisor
exit cause. The direct isolated test and five further instrumented isolated runs
all passed; no diagnostic failure triggered. The subsequent full local CI run
alone passed all 690 infra-automation methods and all remaining directories.
Supervision code, termination confirmation and dirty-slot protections were
unchanged. Original output is retained in `/tmp/story16-10-fixes-ci.log`;
repetitions are in `/tmp/story16-10-fixes-worker-repeat.log`. The observed
shutdown-test failure is retained as a validation limitation rather than hidden
or treated as a handoff defect.
