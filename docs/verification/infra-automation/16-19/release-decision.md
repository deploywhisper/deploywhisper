# v1.5.0 release decision

Current decision: **BLOCKED — local technical qualification passed; external trust and publication gates remain open.**

## Passed or implemented

- Bounded v1.5.0 scope and Epic17 cut-back to independent v1.6.0.
- Source SBOM/checksum generation and deterministic application/runner archives.
- Real isolated OpenTofu collection, actual TLS runner/report/browser paths and
  bounded runner fault corpus.
- Co-located signed material authority, live protected-custody probe, two-human
  decision and durable non-destructive handoff preparation.
- Clean source-freeze blind/security reviews of the material authority, runner
  distribution, waiver boundary, benchmarks and release tooling.
- Source-freeze workflow validation and runner service latency thresholds.
- An uninterrupted 1,800.138-second capacity run at the declared 10 active
  runs, 2 analysis workers and 20 authenticated runner ports, with zero errors,
  zero OOM events and identical start/end hashes for 357 source files.
- Fresh final-source validation: 2,117 root tests; 3,592 tests across all ten
  local-CI directories; the exact API/CLI/infra and automation shards; frontend
  unit/type/build; Ruff and high-severity Bandit.
- Exact source commit `1adf00fd9de4223186da4976dd8caad9882e26cd`, local
  deterministic application/runner archives, SPDX SBOM and checksums, and
  production image `sha256:7a6afd6fd7b3ce74a672fa6fedda0e2c6d146813bcb3f1009930529e1c5f2323`.
- Extracted runner entrypoint and externally reachable exact-image health/OpenAPI
  smoke at version 1.5.0; the image runs as non-root and contains no Node runtime.
- Accountable-maintainer self-service waiver recorded as `NOT EXECUTED`, with
  residual risk and durable approval requirement explicit.

## Mandatory gates still open

- Durable repository approval evidence for the maintainer waiver.
- Story 16.14 Packet 14.8 accepted/unknown external receiver-effect and
  reconciliation qualification.
- Hosted GitHub attestations for application archive, bounded runner archive,
  manifests, SBOM and checksums; signed OCI candidate verification.
- Final CODEOWNERS/code/security review on the immutable commit.
- Explicit public tag/release/alias publication authorization.

The local artifacts are unsigned preview evidence only. No tag, GitHub release,
registry alias or public support claim may be created while this decision is
blocked.
