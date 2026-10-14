# Story 16.3 validator qualification

The [machine-readable measurement](validator-benchmark.json) qualifies the
standalone workflow-v2 validator on the declared Linux reference allocation.
Measured after review fixes on 2026-10-14: 100 warmups, 1,000 measured validations of the declared
50-step mixed uploaded/collected AND-DAG; zero warmup or measured correctness
failures. Nearest-rank p50 **1.502083 ms**, p95 **1.714917 ms**, p99
**2.150250 ms**. The acceptance threshold is p95 below 500 ms.

The host is an Apple M3 Pro running Docker Desktop's Linux ARM64 VM. The container
records Linux 6.12.54-linuxkit, Python 3.11.17, Pydantic 2.13.3 and PyYAML 6.0.3.
Its CPU affinity is 0–3 and cgroup CPU quota is 400000/100000 (four CPUs). The
memory cgroup ceiling is 8,589,934,592 bytes (8 GiB); the VM's kernel-visible usable
memory is 8,217,165,824 bytes after virtualization/kernel reservations. The VM
reports 12 logical CPUs; the container's measured allocation is four. This is a
virtualized, resource-capped run, not a claim of dedicated physical hardware.

The production Dockerfile built image
`sha256:c7d357a1a0a23590fc74fe1bac02189b16c898dbe34ef87b1a5a0fb64cee16e6`
from an isolated checkout of baseline `5c32eec` overlaid with Story 16.3 changes.
No local `.env` or application data was copied. Network was disabled for the
benchmark. The artifact records corpus, canonical definition, implementation and
harness hashes, so the uncommitted source snapshot is independently identifiable.
All source/harness hashes were checked against the final implementation.

Reproduce from a checkout with dependencies/build tools installed:

```sh
docker build -t deploywhisper:s163-review .
mkdir -p /tmp/s163-benchmark-evidence
chmod 777 /tmp/s163-benchmark-evidence
docker run --rm --network=none --cpus=4 --cpuset-cpus=0-3 --memory=8g \
  --mount type=bind,src="$PWD/scripts/benchmark_workflow_validation.py",dst=/app/scripts/benchmark_workflow_validation.py,readonly \
  --mount type=bind,src="$PWD/tests/fixtures/infra_automation/workflow_v2/valid.json",dst=/corpus.json,readonly \
  --mount type=bind,src=/tmp/s163-benchmark-evidence,dst=/evidence \
  deploywhisper:s163-review python -m scripts.benchmark_workflow_validation \
  --corpus /corpus.json --output /evidence/validator-benchmark.json
```

Require `qualified: true`, not merely a zero exit code. Only the public pure
`validate_workflow` call is timed; fixture loading and per-iteration correctness
checks happen outside the timer. Collection, persistence, concurrency, real
approval authority and the integrated release workload remain later-story proof,
including Story 16.19. No UI surface changes in this slice.


The [pre-review development measurement](validator-benchmark-dev.json) is retained
as history (2026-10-13, p95 42.562708 ms). Review found that the original YAML-only
intake reinterpreted some valid JSON scalar representations. The corrected
implementation uses bounded JSON decoding for complete JSON documents and the
bounded YAML parser otherwise. Both measurements use the identical JSON corpus,
canonical output digest and harness; the current measurement identifies the fixed
source. These numbers characterize that declared JSON workload, not every YAML
spelling. All eight valid corpus definitions also pass YAML-to-JSON canonical
parity tests. The six fixed step kinds and frozen manifests are unchanged.
