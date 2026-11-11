# Final review-fix capacity qualification

Passed on 2026-11-11: **1800.440 actual seconds, 3587 samples, 71740 authenticated polls, 40 rotations and zero errors**.
Source remained frozen throughout; both 340-file witnesses
match each other and the final workspace. Schema042, production Python3.11.17/Linux
ARM64, image `sha256:2c652ba689e6c6d6e02d7be7dc054ea4cbc093c46bb87341846824acc1a5c3e8`.

The measured envelope maintained ten active runs, at most two actual spawned
synthetic analysis workers and twenty enrolled/redeemed/polled authenticated local
runner service ports. Assertions covered continuous progress, configured recovery
participation, current authorization, owner-denial checks, backpressure HTTP429,
SQLite integrity/foreign keys, storage bounds and the full1800-second horizon.

Runtime was nonroot999:999, network none, read-only root, two CPUs/two GiB,
pids128 and a256 MiB tmpfs. Existing web-app healthchecks have no HTTP server
under the CLI harness entrypoint; qualification uses the actual workload result.
The independent original application stayed running/healthy with HTTP200.
The owned evidence container and volume were removed and inspected absent.

[Reproduce the command](review-fixes-capacity-command.md), inspect the
[complete quantitative record](review-fixes-capacity/operator-capacity.json) and
[resource/cleanup profile](review-fixes-capacity/container-profile.json).

This qualifies the bounded local control-plane profile. It does not qualify
remote HTTPS runner processes, production collector/receiver/provider workloads,
physical-host power loss, cold OS/Docker installation or the human self-service
pilot. Original12.7/12.8 acceptance remains open.

The earlier [clock-interrupted attempt](review-fixes-capacity-clock-interruption/interruption.json)
is explicitly unqualified. This retry used unchanged source/image and macOS
`caffeinate -dimsu` to prevent idle host sleep; no product guard or clock bypass
was introduced.
