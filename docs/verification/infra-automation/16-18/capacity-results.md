# Final bounded capacity result

> Historical pre-fix record at `0716460`. Review-fix evidence is recorded in
> [review-fixes.md](review-fixes.md) and [review-fixes-validation-summary.json](review-fixes-validation-summary.json).
> Original results below remain scoped to their recorded image/source; current screenshots are identified by [screenshots.json](screenshots.json).

Passed on the production image recorded in [container-profile.json](capacity/container-profile.json):
Python 3.11.17, Linux ARM64, two CPU cores, 2 GiB memory, UID/GID 999, network none,
read-only root and 256 MiB private temporary storage. Operator recovery controls were
configured and inherited by spawned workers.

| Measurement | Observed |
| --- | --- |
| Actual monotonic horizon | 1800.767 seconds |
| Samples | 3600 |
| Active runs in every post-warmup sample | 10 |
| Maximum spawned workers / analysis in flight | 2 / 2 |
| Authenticated persisted online runners | 20 |
| Successful runner poll authentications |72000 |
| Credential rotations |40 |
| Transition errors |0 |
| Queue backpressure | Explicit 429 verified |
| Committed attempts during workload |241 |
| Ready-orchestration p95 |31.076 ms |
| Maximum DB / WAL bytes |5906432 /4148872 |
| Maximum sampled cgroup memory |447709184 bytes (426.97MiB) |
| Before/after source witnesses |Identical; all 338 recorded inputs match final tree |
| Integrity / foreign keys / memory-limit events |No corruption/violations/OOM observed |

The [full operator report](capacity/operator-capacity.json) retains every sample,
versions, limits and witnesses; [the underlying workload report](capacity/capacity.json)
is retained separately. [Exact reproducible commands](capacity-command.md) state
all source mounts and resource settings. The measured container, evidence volume
and private fixture state were removed after copying the nonsecret evidence.

This qualifies the declared control-plane workload: real spawned **synthetic**
analysis workers plus authenticated local runner service ports. It does not
qualify twenty remote HTTPS runner processes, collector/provider workloads,
production receivers, human usability or host-power-loss durability. The broader
production profile and independent human pilot remain open.

Earlier interrupted measurements and the15-second smoke remain explicitly
unqualified adjacent artifacts. They were stopped before required code or fixture
corrections; none supplies acceptance evidence for the final horizon.
