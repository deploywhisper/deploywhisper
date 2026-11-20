# Story 17.3 verification

Story 17.3 covers plan-directed resource selection, bounded AWS reads, fail-safe degradation, and budget reporting. The feature branch is `feature/17-3-plan-directed-reflection`, based on `64ef0fa`. [The first code review](code-review.md) examined `2606d68`. [The independent security review](security-review.md) records the initial implementation and its findings.

## Review follow-up coverage

| Requirement | Regression proof |
| --- | --- |
| AC1 and AC2 | Terraform and OpenTofu fixtures exercise recorded prior state and pure creates. Reflection tests cover ordinary no-ops, moves, imports, deposed objects, unsupported families, recorded tags, and AWS region and SQS identity reconciliation. |
| AC3 and AC4 | The collector rejects a broadened manifest before client construction. One-hop tests assert selected endpoints, recorded limits and reasons, and zero follow-up requests. |
| AC5 | Collector and retained-readback tests cover private-value screening, AWS tag maps, typed SQS redrive metadata, unknown identities and every confirmed IAM denial. Analysis tests cover insufficient context and fail-safe severity and confidence. |
| AC6 | Collector tests verify cross-region concurrency and backoff, frozen dispatch counts and cancellation. Service tests exercise stalled plan preparation, stalled readback, and cancellation during transaction finalization. API and CLI tests verify the existing additive budget contract. |

New deadline regressions failed on the original implementation because the service waited for blocked preparation, readback or commit finalization. A follow-up test established that a stalled provider could also consume the time needed to retain an earlier successful read. The reflection and collection regressions failed before their corresponding fixes. All test data is synthetic or drawn from the checked-in recorded producer fixtures.

## Reproduce the local checks

Run from the repository root with its existing application environment.

```sh
export LLM_API_BASE=http://127.0.0.1:1
./.venv/bin/python -m pytest -q tests/test_cloud \
  tests/test_analysis/test_cloud_grounding.py \
  tests/test_services/test_cloud_plan_collection.py \
  tests/test_services/test_analysis_cloud_grounding.py \
  tests/test_api/test_cloud_collection_budget.py \
  tests/test_cli/test_cloud_collection_budget.py
./.venv/bin/python -m unittest discover -q
bash scripts/ci-local.sh
./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short
./.venv/bin/ruff check .
./.venv/bin/ruff format --check .
./.venv/bin/bandit -r cloud services/cloud_context_service.py -ll -ii
git diff --check
./.venv/bin/python - <<'PY'
import ast
from pathlib import Path

for name in (
    'cloud/aws/client.py', 'cloud/aws/projection.py', 'cloud/aws/session.py',
    'cloud/collection.py', 'cloud/redaction.py', 'cloud/reflection.py',
    'services/cloud_context_service.py',
):
    ast.parse(Path(name).read_text(), filename=name, feature_version=(3, 10))
PY
```

## Reproduce the offline Python 3.11 proof

Build the application image, then run the selected suites with networking disabled and the checked-in tests and fixtures mounted read-only.

```sh
docker build -t deploywhisper:story17-3-closeout-fixes .
docker run --rm --network none --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -e LLM_API_BASE=http://127.0.0.1:1 \
  --mount "type=bind,source=$PWD/tests,target=/app/tests,readonly" \
  --mount "type=bind,source=$PWD/docs,target=/app/docs,readonly" \
  deploywhisper:story17-3-closeout-fixes sh -ec '
python --version
python -m unittest discover -s tests/test_cloud -q
python -m unittest -q tests.test_analysis.test_cloud_grounding tests.test_services.test_cloud_plan_collection tests.test_services.test_analysis_cloud_grounding
'
docker run --rm --network none --tmpfs /tmp -i \
  deploywhisper:story17-3-closeout-fixes python - <<'PY'
from importlib.util import find_spec
import os
import shutil
from fastapi.testclient import TestClient
from app import create_app

assert os.getuid() != 0
assert find_spec("botocore") is None
assert shutil.which("node") is None
with TestClient(create_app()) as client:
    response = client.get("/api/v1/health")
    assert response.status_code == 200, response.status_code
    print(f"SDK-free, Node-free, non-root runtime health HTTP {response.status_code}")
PY
```

## Qualification boundaries

The native SDK proof uses boto3 and botocore 1.44.1. The [approved lock](../17-0/sdk-requirements.lock) pins the wheel hashes. Download and unpack the wheels into a disposable directory, then mount them read-only for the network-disabled Python 3.11 test run. The application image and virtual environment stay SDK-free.

```sh
dw_sdk_dir="$(mktemp -d /tmp/dw-17-3-sdk.XXXXXX)"
./.venv/bin/python -m pip download --require-hashes --only-binary=:all: --no-deps \
  --dest "$dw_sdk_dir/wheels" -r docs/verification/live-environment-grounding/17-0/sdk-requirements.lock
./.venv/bin/python - "$dw_sdk_dir" <<'PY'
from pathlib import Path
import sys
from zipfile import ZipFile

root = Path(sys.argv[1])
wheels = sorted((root / 'wheels').glob('*.whl'))
assert len(wheels) == 7
for wheel in wheels:
    with ZipFile(wheel) as archive:
        archive.extractall(root / 'packages')
PY
docker build -t deploywhisper:story17-3-closeout-fixes .
docker run --rm --network none --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/opt/story-sdk -e LLM_API_BASE=http://127.0.0.1:1 \
  --mount "type=bind,source=$PWD/docs,target=/app/docs,readonly" \
  --mount "type=bind,source=$dw_sdk_dir/packages,target=/opt/story-sdk,readonly" \
  deploywhisper:story17-3-closeout-fixes sh -ec '
python --version
python -c "import boto3, botocore; assert boto3.__version__ == botocore.__version__ == \"1.44.1\""
python -m unittest discover -s docs/verification/live-environment-grounding/17-2 -q
python -m unittest discover -s docs/verification/live-environment-grounding/17-3 -q
'
```

The fixtures exercise the existing HTTP and CLI serializers with trusted collection outcomes. Production authority composition and live AWS qualification belong to Story 17.9. UI validation is not applicable to this backend slice.

## Follow-up results

- Python 3.14.3 focused pytest passed with 166 tests and 339 subtests. The exact API/CLI/infra pytest shard passed with 838 tests, 1 skip and 2,474 subtests.
- Root unittest discovery passed with 2,331 tests run and 3 skips. The host slept during the initial broad runs and two infrastructure recovery tests failed. Both passed in isolation. The broad retries used `caffeinate -i` to inhibit idle sleep.
- A reviewer who did not implement the authorization service changes independently reran 18 service and analysis tests, including the stalled-provider partial snapshot case.
- Docker built image `sha256:6747fffa18cd1c69ae2a12712565e7b0c847e622a6ad360c4f9a8ab56a804c13`. Python 3.11.17 ran 136 cloud tests and 26 analysis/service tests with networking disabled. The non-root, SDK-free and Node-free image returned HTTP 200 at `/api/v1/health`.
- Repo-wide Ruff lint and formatting, Python 3.10 grammar checks for the five changed runtime files, Bandit at the documented threshold and `git diff --check` passed.
- Local CI passed all 12 shards with 3,859 tests run and 3 skips, plus 189 SDK-free isolation tests, skill scenarios, and prompt-injection tests.

## Closeout-fix verification

- Projection regressions cover RDS instance and cluster tag lists, numeric equivalents in scalar labels and values, and decoded SQS metadata. Six checks failed before the fix. The projection suite then passed 16 tests and 14 subtests.
- Both denial-address regressions failed before the fix and passed afterward. One covers the collector result and one checks account masking and retained readback through the service. Independent review also verified that a screened-address collision fails before publication.
- Dispatch regressions cover cancellation before admission and before transport, plus sibling expiry before scheduler polling. The pinned Botocore test verifies that cancellation during signing blocks socket use. Counting at an exact `before-call` handler initially failed native Stubber tests. Admission moved into the existing operation fence and the native suite then passed.
- The focused suite passed 173 tests and 347 subtests. The SDK-free Python 3.11.17 image ran 169 focused tests and returned HTTP 200 for `/api/v1/health`. The same image ran 17 pinned native SDK tests with the approved wheel files mounted read-only and networking disabled. The image digest is `sha256:237bee53c3151e7d2324b66c37bf933d20a3287b622e133ced7dd5f13df061b1`.
- Repo-wide Ruff lint and formatting, scoped Bandit, and Python 3.10 grammar checks for the seven changed runtime files passed. Those files matched the tested image by SHA-256.
- The exact API/CLI/infra pytest shard passed 838 tests and 2,474 subtests with one skip.
- Root discovery ran 2,336 tests with 3 skips. Full local CI ran 3,866 tests across 12 shards with 3 skips, plus 194 isolation tests, skill scenarios, and prompt-injection tests. Both runs passed.
