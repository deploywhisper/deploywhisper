# Story 16.19 reference performance

Evidence in this directory is generated under the declared Linux container
allocation: four CPU quota and 8 GiB cgroup memory. Each result records the exact
environment, corpus, source hashes, sample counts, percentiles, failures and limits.

The measurements do not authorize publication or broaden the supported tool,
runner, receiver, host or network profile.

Current source-frozen measurements:

- Workflow validation: 100 warmups + 1,000 measured 50-step validations,
  zero failures, p95 1.668459 ms (limit: below 500 ms).
- Runner service path: 100 warmups + 1,000 measured claims across twenty
  processes, zero failures, p95 90.855916 ms (limit: below 2,000 ms).
- Capacity/saturation: the accepted run sustained 10 active runs, 2 spawned
  analysis workers and 20 persisted authenticated local runner ports for
  1,800.138 seconds. It recorded 3,730 samples, zero errors, zero OOM events,
  bounded storage (6,021,120-byte database; 4,165,352-byte WAL), and identical
  start/end hashes for all 357 measured source files. Its 250 actual
  ready-to-spawn transitions had p95 34.046 ms (limit: below 1,000 ms). The
  authoritative record is `capacity-final/operator-capacity.json`; earlier
  stopped attempts are explicitly retained only in invalidated directories.

`runner-claims.json` qualifies the durable server/process service path only.
Actual TLS transport behavior is proved separately, so this result is not by
itself the complete NFR-006 or `reference-performance` release gate. The final
gate must compose both records and retain the absence of sampled HTTPS latency.
