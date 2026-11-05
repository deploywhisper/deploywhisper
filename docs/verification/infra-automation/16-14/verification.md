# Story 16.14 verification

This is the original development verification record. The subsequent formal-review repairs and current passing root/full-CI/qualification results are in [review-fixes.md](review-fixes.md).

## Acceptance evidence

| AC | Evidence |
| --- | --- |
| 1 | Fixed pinned version/init/plan/show commands; actual OpenTofu no-change0/change2/error cases. Same task goes through production `CollectionHandler`, authenticated runner intake and existing shared analysis; report stays v2 and `should_block=False`. |
| 2 | Actual original saved plan finalized into owner-restricted local custody; receiver digest receipt verifies those same bytes and restart does not repeat the receipt. Raw and screened digests remain separate. |
| 3 | Actual overwrite/symlink/expiry/source-change rejections plus stale scope/fence/digest and legacy staged-completion contract tests. No replacement grant or replan occurs. |
| 4 | Sensitive-mask and known-credential rejection in actual tool cases; Unicode/quote/backslash/newline escape regressions, whole bounded output screening and corpus assertions over retained proof. Failed/missing/stale evidence remains ineligible and exposes limitations. |
| 5 | Refreshed real isolation CPU/memory/PID/disk/output/network/descendant/controller-death corpus; atomic custody fault cleanup and staged upload cleanup on failure/cancel/expiry/revoke/rotation. Bounded callback/kill-race regressions prevent false successful cleanup. |
| 6 | Passing current-source collection44-check and isolation172-check records. Same-task local authenticated service path and real receiver digest receipt. Explicitly scoped to offline ARM64/OpenTofu1.13.1; no Terraform/cloud/IAM/HTTPS/release claim. |

## Commands and results

- `./.venv/bin/python scripts/qualify_collection.py --build` and subsequent current-source reruns: **44 checks, seven real cases pass**. Final [record](results.json) is authoritative.
- `./.venv/bin/python scripts/qualify_runner_isolation.py`: **172 checks pass**, refreshed [record](../16-13/results.json).
- Combined collection/isolation integrity tests: **9 tests, 62 subtests pass**. Combined integrity plus engine qualification subset: **15 tests, 62 subtests pass**.
- Client/collector/sandbox/execution-boundary repair suite: **37 tests, 91 subtests pass**.
- Service focused suite: **88 tests, 282 subtests pass**; final legacy staged-byte regression included in additional collection suite.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: **734 passed, one skipped, 2353 subtests**, final run460.33s.
- `./.venv/bin/python -m unittest discover -q`: 1755 tests executed, three skipped; one process-recovery timing assertion failed under concurrent suite load. That same test passed in the complete automation CI lane, then `./.venv/bin/python -m pytest tests/test_infra_automation/test_engine_parent_recovery.py -q --tb=short` passed all three tests in73.51s in isolation. The root command itself is not reported as exit0.
- `bash scripts/ci-local.sh`: static/security/compile/skill checks and analysis/API/CLI/docs/infra directories passed; its automation stage initially observed a qualification hash while that record was being refreshed. After the final record, `PYTHON_BIN=./.venv/bin/python bash scripts/run-test-targets.sh tests/test_infra_automation tests/test_llm tests/test_models tests/test_parsers tests/test_services` exited0. Combined final coverage: all10 directories passed, 3201 test executions, three skips. No failed test was excluded from the resumed targets.
- `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `git diff --check`: pass; **546 Python files** formatted.
- Repository nonblocking mypy command:318 errors outside changed files; no changed-file errors were reported. This is not claimed as a clean repository typecheck.
- Scoped new-code Bandit passes. Full medium/high scan reports one unchanged `services/sample_incident_pack.py` B104 finding for the sample `0.0.0.0` literal; the configured high-severity CI gate passes.
- Isolated temporary-database FastAPI lifespan and `/api/v1/health` smoke: **HTTP200**.
- **UI validation not applicable**: no rendered UI or browser interaction changed.

Initial broad runs overlapped implementation/qualification updates and detected stale qualification records, a future-clock HTTP receiver fixture, and the revision032 local engine querying the later runner-staging table. All were repaired and checked independently; settled results above supersede the initial failures, without claiming those initial runs passed. Root logs remain at `/tmp/story16-14-*.log` for this session.

## Scope and remaining limits

No new dependency, database migration, production credential, apply/destroy operation or public artifact/release was introduced. Existing shared analysis, credential/fence transactions and custody primitives are reused. The optional saved-plan receipt is harmless and reports no deployment. Terraform and cloud-backed/remote-state profiles are unqualified; Story12.5 and later release/pilot gates remain separate. A timed-out local custody broker can leave a finalized unreferenced local bundle, which conveys no authority and remains subject to operator retention cleanup.
