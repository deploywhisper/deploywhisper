# Story 16.18 formal review fixes

This work addresses R1–R7 from [the formal review](formal-code-review.md).
The original request-changes report remains historical; final resolution and
verification are appended here rather than rewriting its reproduced failures.
Qualification gates outside these fixes remain explicit.

## Backend repairs: R1–R5

- R1: a private initializing control directory, permanent lifecycle lock and
  durable intent are exclusively published before binding the database. Resume
  checks schema, generation, layout and database device/inode, then finishes only
  that intent. A genuinely lost deployed ledger is never reconstructed.
- R2: the reserved `database` root role is rejected before control publication or
  restore reservation; it cannot overwrite the internal staging map.
- R3: backup verifies the complete staged package against restore's file, byte,
  metadata and depth limits before publishing a successful snapshot. Tests cover
  the real 4096-entry boundary, source depth32, metadata size and manifest bytes.
- R4: restore refuses an input that lacks or changes current retention receipts,
  removal audits or the removed manifest's marker/digest identity. Refusal occurs
  before a new restore generation is reserved. Existing external-work checks
  continue to protect consumed operations and unknown locks.
- R5: ordinary failed upgrades remove only the attempt's positively owned,
  unpublished staging inode and private SQLite sidecars. Source files, foreign
  replacement inodes and possibly published outputs remain untouched.

The backend owner recorded baseline failures using the original HEAD module in
an isolated subprocess, without swapping workspace source. Final focused checks:
26 review tests and12 subtests passed; an independent reviewer ran53 review/backup
tests plus12 subtests and tested foreign-inode replacement during failed upgrade.
Initialization crash tests use actual subprocess exit boundaries, beyond normal
exception cleanup. All26 new recovery tests also passed inside the final nonroot,
network-none, read-only Linux production image on Python3.11.17 (31.799s).

SIGKILL and host power loss cannot execute `finally` cleanup. Unpublished private
`.initialize-*` or `.upgrade-*` remnants may require operator inspection; no
automatic startup scavenger or cold-host/power-loss qualification is claimed.

## UI repair: R6

Same-scope drafts retain their original base policy/version and reason across
background changes and transient policy/membership reads. A newer server policy
blocks saving until explicit successful reload; it does not silently change the
version used with the older draft. True project/session changes and definite
authorization rejection discard the protected form. Explicit reload requires
fresh successful membership and policy reads before replacing the draft.

Browser verification uses real composed APIs, native Chromium visibility changes
and guarded failure-only HTTP503 injection. Successful API responses and
authorization are not mocked. Final counts, source/image identity, screenshots
and combined validation are recorded after the frozen-source checks complete.

## Runbook repair: R7

The operator guide now states the schema042 destination recorded by its linked
released-v1.4.0-copy evidence. A drift check compares that statement to the actual
evidence rather than maintaining a second hard-coded schema expectation.
The new test failed on041 before correction. All60 documentation tests passed.

The runbook also describes initialization resume, complete-package validation,
retention-aware restore refusal and the exact failed-upgrade cleanup limits.

## Final combined verification

All seven findings are resolved. Independent reviewers cleared R1–R5 and R6;
R7 has a red-to-green evidence drift regression. The source remained frozen
through the final production-image measurement.

| Validation | Result |
| --- | --- |
| Root `unittest discover -q` | 2079 tests,3 skips; exit0 |
| Full `bash scripts/ci-local.sh` | 3554 tests across all10 directories; exit0 |
| Exact API/CLI/infra pytest shard | 816 passed,1 skipped,2442 subtests |
| Frontend test/typecheck/build | 512 tests plus2 compatibility checks; passed |
| Composed browser validation | 3 journeys,36 screenshots,axe0 serious/critical,visual97 |
| Final-image operator exercise | 31 named CLI/API checks;209 source hashes matched |
| Collection qualification | 49 checks passed |
| Ruff and security gates | Repository check/format614 files; required Bandit high/high gate passed |

[Structured commands, log digests and source witnesses](review-fixes-validation-summary.json)
retain exact evidence. [Capacity result](review-fixes-capacity/operator-capacity.json)
records the full1800-second bounded configured-recovery run; the [reproduction
command](review-fixes-capacity-command.md) states the synthetic/local scope.
[UI results](review-fixes-ui-results.md) and [operator results](review-fixes-operator-results.md)
record final image identity, real request behavior and cleanup.

The required independent human self-service pilot remains open; Story16.18 stays
**in-progress**. Remote HTTPS fleets, production receiver transfer, cold OS/Docker
installation, host power loss and original12.7/12.8 acceptance remain unclaimed.
