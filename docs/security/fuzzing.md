# Production credential-screening fuzzing

DeployWhisper runs ClusterFuzzLite with Atheris against the actual
`services.content_security` functions. The pinned workflow builds a standalone
Python executable, then fuzzes it for 300 seconds on pull requests and pushes to
`main` and `develop`. Unexpected exceptions and invariant failures fail the job.
There is no dry-run setting or allowed broken-target allowance.

The harness feeds arbitrary bounded bytes through text redaction and artifact
credential extraction. It also derives synthetic credentials from the fuzz
input and checks sibling echoes, JSON credentials, Kubernetes `stringData` and
base64 `data`, Terraform sensitive masks, CloudFormation `NoEcho`, percent
encoding, input immutability, and repeated structured redaction. The checked-in
corpus contains only synthetic data, including malformed UTF-8, aliases and
cycles, intrinsic tags, heredocs, block scalars, and unsafe Python object tags.
Deterministic regressions prove a broken or mutating redactor fails these checks
and prove Python object tags never invoke `os.system`.

Inputs are limited to 4096 bytes, with a ten-second per-input timeout. These
limits provide a practical CI budget; they do not establish correctness for
unbounded artifacts. Retain minimized reproductions as synthetic regression
fixtures when repairing a genuine finding. Avoid uploading real infrastructure,
credentials, or production incident data as corpus inputs.

## Build inputs

The fuzz builder uses an immutable official `base-builder-python` image and
ClusterFuzzLite action commit. Its Python is 3.11.13. Only the existing application
PyYAML and Pydantic dependencies and their complete hashed dependency closure
are installed. The official image supplies Atheris and PyInstaller; no fuzzing
packages are added to application runtime requirements or the runtime image.

Regenerate the minimal lock using **uv 0.11.2**:

```bash
uv pip compile .clusterfuzzlite/requirements-source.txt --universal \
  --python-version 3.10 --generate-hashes \
  --output-file .clusterfuzzlite/requirements.txt
```

Update the source versions alongside application dependency updates, review the
lock, and rebuild the packaged target. The Docker install enforces
`--require-hashes`. PyInstaller bundles the production modules and dependencies.
The execution wrapper uses Atheris's internal engine without `LD_PRELOAD`, as
recommended for Python fuzzing without instrumented native extensions. This
control exercises Python behavior; it does not claim sanitizer coverage of
prebuilt Pydantic/PyYAML native wheels.

## Local verification

Run the deterministic checks without installing Atheris:

```bash
./.venv/bin/python -m unittest discover -s tests/test_infra \
  -p test_fuzzing_contract.py -v
```

Build and run the **packaged** target, including on an ARM Docker host:

```bash
docker build --platform linux/amd64 -f .clusterfuzzlite/Dockerfile \
  -t deploywhisper-fuzz-local .
mkdir -p /tmp/deploywhisper-fuzz-out /tmp/deploywhisper-fuzz-work
docker run --rm --platform linux/amd64 \
  -e FUZZING_LANGUAGE=python -e SANITIZER=address \
  -e FUZZING_ENGINE=libfuzzer -e ARCHITECTURE=x86_64 \
  -v /tmp/deploywhisper-fuzz-out:/out \
  -v /tmp/deploywhisper-fuzz-work:/work \
  deploywhisper-fuzz-local compile
docker run --rm --platform linux/amd64 --network none \
  -v /tmp/deploywhisper-fuzz-out:/out \
  deploywhisper-fuzz-local \
  /out/content_security_fuzzer /src/deploywhisper/.clusterfuzzlite/corpus \
  -max_total_time=60 -max_len=4096 -timeout=10
```

For the stronger standalone-execution check, mount the output in the official
OSS-Fuzz `base-runner` image; it has neither the project source tree nor installed
project dependencies:

```bash
mkdir -p /tmp/deploywhisper-fuzz-corpus
cp .clusterfuzzlite/corpus/* /tmp/deploywhisper-fuzz-corpus/
docker run --rm --platform linux/amd64 --network none \
  -v /tmp/deploywhisper-fuzz-out:/out \
  -v /tmp/deploywhisper-fuzz-corpus:/tmp/fuzz-corpus \
  gcr.io/oss-fuzz-base/base-runner@sha256:dc7b5c23c5c818bdbeaf3f136fb6da639b85ef78cf585f5726554d4cf194d300 \
  /out/content_security_fuzzer /tmp/fuzz-corpus \
  -max_total_time=60 -max_len=4096 -timeout=10
```

A successful run must show nonzero Atheris coverage and actual mutation
executions, not just a successful Docker build. Never treat Scorecard detection
as executable proof.

The runner's build checks can also verify target discovery, architecture,
instrumentation, and startup:

```bash
docker run --rm --platform linux/amd64 --network none \
  -e FUZZING_LANGUAGE=python -e SANITIZER=address \
  -e FUZZING_ENGINE=libfuzzer -e ARCHITECTURE=x86_64 \
  -v /tmp/deploywhisper-fuzz-out:/out \
  gcr.io/oss-fuzz-base/base-runner@sha256:dc7b5c23c5c818bdbeaf3f136fb6da639b85ef78cf585f5726554d4cf194d300 \
  test_all.py
```

## Initial verification

On 2026-10-07 the hash-enforced Docker install and packaged build succeeded.
The first packaged run completed **12,976 executions in 61 seconds**, increasing
coverage from **757 to 1,054**. The independent, network-disabled runner completed
**15,116 executions in 61 seconds**, increasing coverage from **757 to 1,038**
and features from **1,714 to 3,535**. Both runs exited successfully and logged
production redaction and CloudFormation-loader instrumentation. The official
runner's `test_all.py` build checks passed.

The five fuzz-invariant regressions and 31 existing content-security tests
passed. Ruff lint/format, shell syntax validation, and actionlint passed for the
new files. UI validation is not applicable: this control changes no UI surface.
These bounded local runs establish executable behavior; the GitHub workflow's
results and published Scorecard assessment remain separate evidence.

Official references:

- [ClusterFuzzLite Python build integration](https://google.github.io/clusterfuzzlite/build-integration/python-lang/)
- [ClusterFuzzLite GitHub Actions](https://google.github.io/clusterfuzzlite/running-clusterfuzzlite/github-actions/)
- [Atheris instrumentation and coverage](https://github.com/google/atheris)
- [Scorecard v5.5.0 fuzzing detection](https://github.com/ossf/scorecard/blob/v5.5.0/checks/raw/fuzzing.go)

### Hosted helper-image limitation

The official ClusterFuzzLite action definitions are pinned to a verified commit.
Those definitions currently delegate execution to upstream CIFuzz Docker images
with a `v1` tag. The local standalone verification uses an explicitly pinned
runner image, but the action commit alone does not freeze those upstream helper
image tags. The hosted job holds only repository-read privileges. Keep this
transitive tooling limit distinct from the pinned project builder and hash-locked
fuzzer dependencies; no claim of fully immutable upstream helper execution is made.

### Hosted validation

[The first hosted run](https://github.com/deploywhisper/deploywhisper/actions/runs/37590005754) completed build checks and300seconds of production fuzzing successfully on `5318488`:47,634 executions, coverage1,090, features4,739, no crashes. These are actual libFuzzer/Atheris log statistics, separate from Scorecard's configuration detection.
