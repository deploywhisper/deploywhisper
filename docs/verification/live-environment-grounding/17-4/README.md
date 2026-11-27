# Story 17.4 verification

Story 17.4 compares one recorded Terraform or OpenTofu plan with a selected
observation already retained for the same project. The comparison uses
qualified facts from that observation and keeps the existing advisory
report contract. Production AWS collection, snapshot import, and UI
presentation remain separate stories.

## Acceptance evidence

| Criterion | Proof |
| --- | --- |
| AC1 and AC6 | `tests/test_analysis/test_divergence.py` uses the recorded plan and observation under `tests/fixtures/live_environment_divergence/`. It covers matching, modification, explicit deletion and recreation, tag-only changes, insufficient observation and denied reads. |
| AC2 | `test_verified_divergence_is_persisted_without_calling_the_narrative_provider` verifies exact recorded, live and planned values in the persisted finding. The finding references deterministic evidence minted from the retained observation under the same transaction. |
| AC3 | The comparison tests compute age against the observation start time, verify the exact threshold boundary and distinguish a missing timestamp or an observation taken before the plan. |
| AC4 | `test_divergence_floor.py` covers minimum medium severity, a score of at least 42, caution and preservation of stronger verdicts. Integration tests verify the deterministic briefing bypasses the narrative provider and reviewer feedback with a reason and acknowledgement leaves the floor intact. |
| AC5 | The real CLI walkthrough produces exit 3 and a normal advisory report. The real HTTP walkthrough returns 409 with exit code 3 and retrieves the persisted evidence-linked report. Surface suites verify exit 2 for inconclusive comparison and the opt-out shape. |

## Walkthrough

The named integration test prepares a temporary project and a retained,
synthetic observation. The recorded plan has EC2 termination protection
disabled. The recorded provider observation has it enabled. The test calls
the normal `analyze` CLI parser with `--snapshot-digest` and
`--fail-on-divergence`, checks exit 3, and verifies the JSON report retains
`advisory.should_block=false`.

```sh
LLM_API_BASE=http://127.0.0.1:1 ./.venv/bin/python -m pytest -q \
  tests/test_services/test_plan_reality_divergence.py \
  -k real_cli_gate_returns_distinct_code_and_keeps_advisory_report
```

For an already retained observation, the equivalent operator command is:

```sh
./.venv/bin/python cli.py analyze --project-id PROJECT_ID \
  --snapshot-digest RETAINED_DIGEST --fail-on-divergence plan.json
```

The exit codes and multipart API fields are documented in the
[operator guide](../../../live-environment-grounding/README.md).

## Reproduce verification

```sh
export LLM_API_BASE=http://127.0.0.1:1
./.venv/bin/python -m pytest -q tests/test_analysis/test_divergence.py \
  tests/test_analysis/test_divergence_floor.py tests/test_services/test_plan_reality_divergence.py \
  tests/test_services/test_divergence_plan_intake.py \
  tests/test_services/test_divergence_observation_freshness.py \
  tests/test_cli/test_divergence_gate.py tests/test_api/test_divergence_gate.py
./.venv/bin/python -m unittest discover -q
bash scripts/ci-local.sh
./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short
./.venv/bin/ruff check .
./.venv/bin/ruff format --check .
./.venv/bin/bandit -ll -ii analysis/divergence.py services/divergence_service.py \
  services/analysis_service.py services/cloud_context_service.py services/report_service.py \
  api/routes/analyses.py api/schemas.py cli/analyze.py
git diff --check
docker build -t deploywhisper:story17-4-rereview-fixes .
docker run --rm --network none --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -e LLM_API_BASE=http://127.0.0.1:1 \
  --mount "type=bind,source=$PWD/tests,target=/app/tests,readonly" \
  deploywhisper:story17-4-rereview-fixes sh -ec '
python --version
python -m unittest -q tests.test_analysis.test_divergence tests.test_analysis.test_divergence_floor tests.test_services.test_plan_reality_divergence tests.test_services.test_divergence_plan_intake tests.test_services.test_divergence_observation_freshness
python -c "from importlib.util import find_spec; import os, shutil; from fastapi.testclient import TestClient; from app import create_app; assert os.getuid() != 0 and find_spec(\"botocore\") is None and shutil.which(\"node\") is None; response = TestClient(create_app()).get(\"/api/v1/health\"); assert response.status_code == 200; print(\"Offline runtime health HTTP 200\")"
'
```

UI validation is not applicable to this backend story. Verification uses
checked-in fixtures and a temporary local database.

## Verified results

- Focused pytest passed 204 tests and 376 subtests across comparison, reporting, cloud, evidence, and both gate surfaces. The four retained-report integration tests also passed with the reviewer feedback assertion.
- Independent scoped review identified cross-artifact screening as a gap. A failing regression reproduced it and passed after the comparison began screening over the whole submission and configured provider credentials. The independent follow-up confirmed screening and the deterministic caution briefing.
- The network-disabled Python 3.11.17 image passed 16 tests and returned HTTP 200 for `/api/v1/health`. Its digest is `sha256:2fbbd1f943e2be7565b29e21ad61491694f250c2380f2717eba1e98f5ddb1af6`.

- Full local CI passed all 12 shards with 3,894 tests run and 3 skips, plus 195 isolation tests, skill scenarios and prompt-injection tests. Root unittest discovery ran 2,342 tests with 3 skips. The exact API/CLI/infra pytest command passed 850 tests and 2,494 subtests with one skip.
- Ruff lint and formatting, scoped Bandit, Python 3.10 syntax parsing for all nine changed runtime files, and `git diff --check` passed. The nine comparison tests also passed with execution-epic imports blocked. All nine runtime files matched the tested Docker image by SHA-256.

## Review follow-up verification

| Finding | Regression coverage |
| --- | --- |
| Unobserved planned changes | The comparator tests require evidence for changed scalar fields, tag paths, and unknown planned values before a match. Verified drift remains visible when other fields are incomplete. |
| Scope-local identities | The comparator tests reject name-only AWS identity matches and retain exact scoped matches without weakening account screening. |
| Snapshot age and chronology | The observation freshness suite covers the one-hour boundary, future observations, undated plans, stale partial snapshots, and gate precedence. The CLI asserts exit 2 for otherwise matching stale or unordered input. The retained-report suite verifies rollback when a snapshot ages out during publication. |
| Incomplete plan input | The comparator suite rejects explicit errored, incomplete, and deferred plans. A deliberate no-op remains valid. |
| Mixed confirmed drift and missing facts | The retained-report suite starts with a complete baseline and verifies the saved report still signals insufficient context when some live facts are missing. |
| Read denial under temporal checks | The comparator and freshness suites preserve unreadable status and the corresponding missing permission even when other comparison facts cannot be used. |
| Discarded narrative | The retained-report suite asserts that confirmed security-relevant divergence uses the deterministic briefing without a narrative provider call. Reviewer feedback still leaves the floor intact. |

The comparator regressions exposed 11 failing baseline assertions. The service freshness suite exposed six. Two additional report regressions failed on the previous implementation. After the fixes, 216 focused tests and 391 subtests passed. Independent verification passed 37 targeted tests and 35 subtests. Scoped Bandit, repo-wide Ruff lint and formatting, and diff whitespace checks passed.

- Full local CI ran 3,906 tests across 12 shards with 3 skips. The API/CLI/infra pytest shard passed 851 tests and 2,496 subtests with one skip. Root discovery ran 2,342 tests with three skips on the full retry. The initial run's infrastructure process-tree recovery timeout passed in isolation and in local CI.
- The rebuilt Python 3.11.17 image ran 27 tests with networking disabled and returned HTTP 200. Image `sha256:54c59fc3a50bc220c24a1229da0a882bcab49bbf2ae344c9fe106b2f85e61244` matched all nine runtime source hashes. Python 3.10 grammar checks passed, and all 14 comparison tests passed with execution-epic imports blocked.

## Re-review follow-up verification

| Finding | Regression coverage |
| --- | --- |
| Analysis and gate select different plans | The intake suite rejects excluded and ambiguous plans, including a qualified plan beside another Terraform JSON plan whose format is unqualified. The real retained-analysis test verifies that comparison and report generation share one parse pass. |
| Conflicting recorded evidence | The comparator suite verifies that conflicting recorded values or selectors are unresolved. Ordinary moves, deposed resources and omitted fields retain their existing semantics. |
| Denial identity | The comparator tests verify account and region binding before attributing a denial. A verified denial still carries its exact permission when the plan chronology is unknown. |
| Finalization freshness | Retained-analysis tests age the observation during report writing, evidence verification and the owning unit of work's exit. Each test checks that publication rolls back. |
| Persistence errors | Real HTTP and CLI tests inject a filesystem permission failure after writing a report and verify HTTP 500, CLI exit 1 and rollback. A database commit fault also remains a persistence error. |
| Malformed UTC offsets | Comparator tests reject out-of-range UTC offsets and keep chronology unverified. |

Regression tests reproduced the previous behavior before implementation. The ordinary drift fixture was corrected so it agrees with its declared prior values. A separate test covers conflicting input. The independent targeted review verified the commit-time freshness and storage-error cases.

- Focused pytest passed 257 tests and 405 subtests. Full local CI passed all 12 shards with 3,922 tests and 3 skips, plus 195 isolation tests, skill scenarios and prompt-injection tests. Root discovery passed with 2,342 tests and three skips. The exact API/CLI/infra shard passed 851 tests and 2,496 subtests with one skip.
- The network-disabled Python 3.11.17 image ran 43 tests and returned HTTP 200. Image `sha256:3e1ae14fbee6e932eae0fd813827ccb9643dc8963bfd73db3943c16b38aa40e8` matched all nine runtime source files. Python 3.10 grammar, repo-wide Ruff lint and formatting, scoped Bandit, comparison without execution-epic imports, and diff whitespace checks passed.

## 2026-11-27 review follow-up verification

| Finding | Regression coverage |
| --- | --- |
| Unobserved security group rules | The real HTTP gate uses two retained snapshots collected through the same SDK projection. A synthetic out-of-band CIDR rule edit leaves identical facts, and the otherwise matching tag edit returns HTTP 409 with exit code 2. The comparator also verifies egress, positive tag-only coverage when no rules are recorded, and exit 3 for independently confirmed tag drift. |
| Contradictory no-ops and duplicate changes | The comparator rejects inconsistent no-op values, unknown planned values, and duplicate change identities regardless of row order. A consistent no-op still clears the gate. A pure create cannot borrow a prior-state identity. |
| Post-write database failures | Operational faults during evidence verification and the retained-snapshot recheck return HTTP 500 and CLI exit 1 with `report_persistence_failed`. Both surfaces verify rollback and keep exception details out of their responses. |
| Sub-microsecond chronology | Nonzero digits beyond microseconds leave chronology unverified for UTC and offset timestamps. Extra zero digits preserve the exact represented time. |

The six added regression tests reproduced all four findings against the saved pre-fix Python sources. The focused run passed 268 tests and 422 subtests on the fixed sources.

```sh
export LLM_API_BASE=http://127.0.0.1:1
./.venv/bin/python -m pytest -q tests/test_analysis/test_divergence.py \
  tests/test_analysis/test_divergence_floor.py tests/test_api/test_divergence_gate.py \
  tests/test_cli/test_divergence_gate.py tests/test_services/test_divergence_observation_freshness.py \
  tests/test_services/test_divergence_plan_intake.py tests/test_services/test_plan_reality_divergence.py \
  tests/test_services/test_analysis_cloud_grounding.py tests/test_services/test_cloud_context_service.py \
  tests/test_cloud tests/test_evidence
```

The rebuilt network-disabled Python 3.11.17 image passed 62 story tests and returned HTTP 200 from `/api/v1/health`. Image `sha256:84562b8c0c1a35b7bb3c9a5c744148fa5ffc5fb3744c7962f831799772a6be55` matched all nine story runtime source hashes. The runtime test included the API and CLI suites, ran as a non-root user, and verified that Node and the AWS SDK were absent.

```sh
docker build -t deploywhisper:story17-4-review-2026-11-27 .
docker run --rm --network none --tmpfs /tmp --tmpfs /app/data:mode=1777 \
  -e PYTHONDONTWRITEBYTECODE=1 -e LLM_API_BASE=http://127.0.0.1:1 \
  --mount "type=bind,source=$PWD/tests,target=/app/tests,readonly" \
  deploywhisper:story17-4-review-2026-11-27 sh -ec '
python --version
python -m unittest -q tests.test_analysis.test_divergence tests.test_analysis.test_divergence_floor tests.test_services.test_plan_reality_divergence tests.test_services.test_divergence_plan_intake tests.test_services.test_divergence_observation_freshness tests.test_api.test_divergence_gate tests.test_cli.test_divergence_gate
python -c "from importlib.util import find_spec; import os, shutil; from fastapi.testclient import TestClient; from app import create_app; assert os.getuid() != 0 and find_spec(\"botocore\") is None and shutil.which(\"node\") is None; response = TestClient(create_app()).get(\"/api/v1/health\"); assert response.status_code == 200; print(\"Offline runtime health HTTP 200\")"
'
```

Repo-wide Ruff lint and formatting, scoped Bandit, and Python 3.10 syntax checks passed. The CI mypy command still reports existing errors. It reported 345 errors, down from 358 before the fixes, with zero new diagnostics. UI validation not applicable.

| Command | Result |
| --- | --- |
| `bash scripts/ci-local.sh` | All 12 suites passed. 3,928 tests ran with three skips. The script also passed 195 isolation tests, the skill scenarios, and eight prompt-injection tests with 96 subtests. |
| `./.venv/bin/python -m unittest discover -q` | 2,343 tests ran with three skips. |
| `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` | 852 passed, one skipped, and 2,496 subtests passed. |

## EC2 attachment and snapshot storage fix verification

| Finding | Regression coverage |
| --- | --- |
| EC2 security group attachments | The comparator treats recorded and observed group IDs as sets and requires usable attachment evidence. The collector marks a malformed trailing group incomplete. A real HTTP gate test using synthetic AWS replies returns HTTP 409 with exit code 3 and the caution floor. The saved report links its finding to both retained group facts and the snapshot digest. |
| Final retained-snapshot read | Faults at the actual SQLAlchemy snapshot row read and schema marker query return HTTP 500 and CLI exit 1 after the report write. The tests verify rollback, zero committed reports, and redacted public errors. A fault before the write keeps HTTP 404 and CLI exit 2. |

The new API, comparator, collector, and storage assertions reproduced the failures before the fixes. The updated focused run passed 286 tests and 446 subtests. An independent CLI run through the collector and retained snapshot produced exit 0 for reordered matching attachments, exit 3 for confirmed drift, and exit 2 for an incomplete read.

```sh
export LLM_API_BASE=http://127.0.0.1:1
./.venv/bin/python -m pytest -q tests/test_analysis/test_divergence.py \
  tests/test_analysis/test_divergence_floor.py tests/test_api/test_divergence_gate.py \
  tests/test_cli/test_divergence_gate.py tests/test_services/test_divergence_observation_freshness.py \
  tests/test_services/test_divergence_plan_intake.py tests/test_services/test_plan_reality_divergence.py \
  tests/test_services/test_analysis_cloud_grounding.py tests/test_services/test_cloud_context_service.py \
  tests/test_cloud tests/test_evidence tests/test_infra/test_cloud_snapshot_migration.py
```

Repo-wide Ruff lint and formatting, scoped Bandit, and Python 3.10 syntax validation passed. The existing 345 mypy errors were unchanged. The OpenAPI comparison response still exposes the same fields. UI validation not applicable.

Image `sha256:5ab2adfc0155761268a8dca199510880a74638f16ce15854e10de705a3d117f3` matched all 12 story runtime source hashes. The rebuilt Python 3.11.17 container ran 100 tests with networking disabled and returned HTTP 200 from `/api/v1/health`. The process ran as a non-root user and verified that Node and the AWS SDK were absent.

```sh
docker build -t deploywhisper:story17-4-attachment-storage-fixes .
docker run --rm --network none --tmpfs /tmp --tmpfs /app/data:mode=1777 \
  -e PYTHONDONTWRITEBYTECODE=1 -e LLM_API_BASE=http://127.0.0.1:1 \
  --mount "type=bind,source=$PWD/tests,target=/app/tests,readonly" \
  deploywhisper:story17-4-attachment-storage-fixes sh -ec '
python --version
python -m unittest -q tests.test_analysis.test_divergence tests.test_analysis.test_divergence_floor tests.test_services.test_plan_reality_divergence tests.test_services.test_divergence_plan_intake tests.test_services.test_divergence_observation_freshness tests.test_api.test_divergence_gate tests.test_cli.test_divergence_gate tests.test_cloud.test_collection tests.test_infra.test_cloud_snapshot_migration
python -c "from importlib.util import find_spec; import os, shutil; from fastapi.testclient import TestClient; from app import create_app; assert os.getuid() != 0 and find_spec(\"botocore\") is None and shutil.which(\"node\") is None; response = TestClient(create_app()).get(\"/api/v1/health\"); assert response.status_code == 200; print(\"Offline runtime health HTTP 200\")"
'
```

| Command | Result |
| --- | --- |
| `bash scripts/ci-local.sh` | All 12 suites passed. 3,934 tests ran with three skips. The script also passed 196 isolation tests, the skill scenarios, and eight prompt-injection tests with 96 subtests. |
| `./.venv/bin/python -m unittest discover -q` | 2,345 tests ran with three skips. |
| `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` | 853 passed, one skipped, and 2,496 subtests passed. |
