# Story 16.18 acceptance audit

Read-only acceptance audit on 2026-11-10. This document maps the canonical story
and approved packets to delivered contracts and actual evidence. It changes no
runtime, test, story status or checkbox. It is not an independent rerun of the
commands described by the evidence owners.

## Evidence boundary at audit time

- Final packaged product image:
  `sha256:363f797bb98e1ca90f549892b28802d6589000e776505a6f21cefdc7e61c41df`;
  migration head `042_add_receiver_recovery`. The operator and UI records identify
  that same image and matching frozen runtime sources.
- Actual packaged operator exercise: 28 CLI/API checks plus two interrupted
  completion-resume supplements, with private disposable stores and cleanup.
  [Operator evidence](operator-exercise.md) distinguishes real commands from
  synthetic custody and test-only interruption markers.
- The `ui-results.md` UI evidence is currently in the separate UI worktree
  `/tmp/deploywhisper-story16-18-ui`. The canonical location after branch
  integration is `docs/verification/infra-automation/16-18/ui-results.md` on
  `feature/16-18-automation-settings-ui`; the integration owner must preserve it
  and its screenshot/source manifests when preparing the separate UI PR.
  Its final results are 493 frontend tests, two compatibility checks, two composed
  browser journeys, 24 screenshots, zero serious/critical axe findings and visual
  verdict 94. These are browser proofs against the production-built image, not a
  Vite server.
- Root reports the final exact API/CLI/infra shard passed: 812 tests, one skip,
  2442 subtests. Final root smoke passed 2048 tests with three skips. Full local
  CI subsequently passed all ten targets: 3,523 tests. Repository formatting
  passed for 611 files. The final [validation summary](validation-summary.json)
  records commands and log digests.
- A subsequent actual offline-installation exercise closes the earlier bounded
  Packet 18.4 installation-proof gap. The current product image was saved,
  stream-verified and loaded locally, then bootstrapped and recovered in fresh
  private state under network `none`; the complete details are in the owning
  `offline-install-results.json` and `offline-install-results.md` records.
- The final Linux Python 3.11, two-CPU/two-GiB configured-recovery capacity
  run subsequently passed 1800.767 actual seconds, 3600 samples, 72,000 authenticated
  polls and 40 credential rotations with zero errors and unchanged source witnesses.
  See [capacity results](capacity-results.md). The committed
  `linux-smoke/operator-capacity.json` is a 15.5-second diagnostic with
  `acceptance_qualified: false`. Earlier interrupted directories are negative or
  incomplete evidence. None can substitute for the final JSON and resource/error
  report from the full interval.

The earlier Story 16.0 gate and the completed 16.16/16.17 dependencies are cleared
for this bounded implementation; [entry review](readiness.md) records the actual
prerequisites and reviewed final interfaces. Later Story 16.19 production support
qualification is not an earlier-code prerequisite. Conversely, this story's
explicit operational proof cannot be declared passed merely because 16.19 will
also perform release qualification.

## Offline installation supplement

The owning exercise reports a saved **229,869,568-byte** image archive with
stream verification of its configuration and **21 layer diff IDs**, followed by
`docker load` recognition of the exact current `363f797…` image ID without a
registry pull. A fresh UID-999 schema-042 domain initially contained zero
accounts, sessions and memberships, with execution policy disabled. Twenty-eight
actual CLI/API bootstrap, account rotation, backup/restore, barrier, completion
and repeat-restore checks ran inside network `none`; loopback HTTP was reached
through Docker exec, with no published host port. Restore generations advanced
4 to 5. Real DNS and external IPv4/IPv6 attempts denied, with external network
error 101, no UP non-loopback interface/routes and no provider credentials. All
209 packaged runtime/source hashes matched root; disposable resources were
removed.

This is actual installation from a verified local image artifact and actual
fresh-state recovery on an already installed Docker host. It is stronger than
the earlier prepared-cache inspection, and sufficient to close that bounded
18.4 gap. It is not a cold-machine OS/Docker/dependency installation, an
independent human pilot, remote receiver transfer, host-power-loss durability or
full original Story 12.8 qualification.

## Acceptance criteria

| AC | Delivered paths and actual proof | Disposition and limits |
| --- | --- | --- |
| 1 — privileged configuration, floors, audit and protected retention | `services/infra_automation_policy.py`, typed lifecycle settings, `services/infra_automation_retention.py`, `infra_automation/retention.py`, manifest repository, migration 040 and effective startup validation. [Retention results](retention-results.md) include actual migrated-head API purge, immutable tombstone/marker, exact one-use debit, integer/accounting floors, exact retry, rollback, admin/CSRF/CAS denial and protected pending/approved/uncertain work. Final composed UI performs actual policy save and purge, then reads removed-evidence guidance. | Owned conservative contract delivered. Protection rather than decision invalidation is explicitly allowed by AC1. All handoffs and held/broken locks remain protected; removal never authorizes execution. Only screened manifest payload is removed. Linked report exports, decision material, artifact snapshots and raw custody are retained separately; do not claim universal erasure. |
| 2 — bounded saturation, backpressure and cleanup | Existing engine/storage/worker limits, `tests/test_infra_automation/test_engine_limits.py` (including actual SQLite FULL), worker-failure/retry and staged-upload regressions, retention cleanup/accounting tests, plus `scripts/qualify_operator_capacity.py` and its adapter tests. | Deterministic quota/disk/cleanup contract delivered; sustained acceptance passed for the exact local control-plane profile in the final full capacity result. Unknown operations keep locks and capacity rather than being discarded. Do not count the short Linux smoke or interrupted capacity runs as the required measurement. |
| 3 — coordinated backup/upgrade/restore and no revived authority | `infra_automation/operator_recovery.py`, `cli/automation_operations.py`, migrations 041/042, recovery state/events, lifecycle participation and startup barrier. [Restore results](restore-results.md), [released v1.4.0 upgrade](upgrade-results.json), [operator exercise](operator-exercise.md), and [receiver recovery](receiver-recovery-results.md). Actual released source `v1.4.0@935f3bb`, schema 028 to 042, source unchanged, 37 report columns preserved, integrity `ok`, zero foreign-key violations. Actual repeated restore advances the outside ledger and invalidates sessions. Real migrated tests exercise interruptions and old-token denial; actual HTTPS FastAPI receiver routes reconcile the original consumed operation through a new, restricted credential without repeating its synthetic action. | Owned participating-local-domain contract delivered. Copied SQLite alone is insufficient. An older backup with missing/different current external history is deliberately refused. Missing/rolled-back outside ledger remains fail-closed. Unmanaged remote writers, host power loss, cross-host/control-ledger-loss recovery and production receiver credential transfer are not qualified. These support limits do not invalidate the tested local contract. |
| 4 — expiry/revocation/unknown work remains readable and reconciliation only | Existing policy/target/runner/handoff services, `tests/test_infra_automation/test_operator_recovery.py`, recovery barrier, `services/infra_automation_receiver_recovery.py`, `infra_automation/receiver_recovery.py` and `ReferenceReceiver.recover_completed`. [Recovery matrix](recovery-results.md), [restored receiver proof](receiver-recovery-results.md), [runtime/CLI proof](receiver-runtime-recovery-results.md), and final feature-off browser reconciliation. | Owned contract delivered. Revocation/expiry never proves remote work stopped. Same-operation terminal/status-only authority does not permit bootstrap, consume, action admission, progress callbacks, unsigned resolution or new grants. Audited break acknowledges uncertainty and does not mint approval. Expired-credential clock rollback and completion interruption findings were repaired and independently retested. A live production transport/effect remains a later support qualification. |
| 5 — pinned caches, restricted DNS/egress and rotation | `infra_automation/runner/cache.py`, [network runbook](../../../infra-automation/network.md), [cache record](cache-results.json), [actual DNS observation](network-results.md), current 16.13/16.14 pinned offline isolation/collection records, and the new [offline installation/recovery exercise](offline-install-results.md) with [structured results](offline-install-results.json). | Owned offline installation/collection/recovery contract delivered for the named installed-Docker profile. The exact current image was saved, independently stream-verified, locally loaded without a pull and started with fresh private schema-042 state. Actual bootstrap/rotation/backup/restore/barrier/completion/repeated-generation checks ran with network `none`, with denied DNS and external IPv4/IPv6. This closes the earlier prepared-cache-only proof gap. Docker and image layers were already locally available; it does not qualify cold OS/Docker/dependency installation, another network profile, Terraform/cloud IAM/remote state or full original 12.8 acceptance. |
| 6 — version-matched exercises, recorded 30-minute limits and contribution boundaries | `docs/infra-automation/operations.md`, `network.md`, docs checks, operator/upgrade/cache/DNS/receiver records, existing scoped run/step/runner/approval/delivery reads and new capacity recorder. Actual operator exercise used packaged commands, exact image and disposable named stores; no secret values are retained. | Runbooks and agent-executed operator exercise delivered. The final 1800-second capacity record passed; an independent human self-service pilot remains mandatory outstanding evidence. This story introduces no new metrics export endpoint; bounded existing read APIs and recorded counts/resources are its observation surfaces. Original 12.7/12.8 acceptance stays open. |
| 7 — administrator settings browser integration | Separate UI branch: `frontend/src/screens/AutomationSettingsSection.tsx`, `Settings.tsx`, strict `frontend/src/api/infraAutomationSettings.ts`, two browser tests and guarded disposable fixtures. Actual composed saves prove typed values, local/server validation, 409 conflict/unsafe reductions, 422 lifetime rejection, 403 nonadmin denial, scope cache clearing, post-approval disable and feature-off history/reconciliation. | Approved Packet 18.6 contract delivered. Registered-target selection/details use existing 16.10 APIs and show canonical identity, environment, receiver, pinned workflow, enabled state and lock. Target registration/mutation remains the existing protected operator mechanism; the form does not introduce target editing or persist a selected target into project policy. Do not advertise a new target-save form. No infrastructure/provider/receiver credentials are entered by this UI. |

## Packet/checklist guidance

| Packet | Completed owned output | Remaining acceptance before an unqualified checkbox/whole-story claim |
| --- | --- | --- |
| 18.1 | Atomic, conservative screened-payload removal, immutable manifests/tombstones, exact replay and quota debit; reuse of existing atomic intake, staged-upload cleanup and bounded storage. | Final combined CI passed. Do not turn this into a claim that all report/custody copies were erased or pending decisions were invalidated: they are protected. Sustained capacity is recorded under 18.5/AC2. |
| 18.2 | Coordinated private local backup/restore, outside monotonic generation, interrupted publication/completion recovery, authentic released-schema upgrade and restricted restored-operation credential mechanism. | Final combined CI passed; exact evidence is integrated. Production token transfer/unmanaged writers/power-loss are support limits, not implemented alternatives to this contract. |
| 18.3 | Expiry/revocation/disable/break matrix plus real migrated restore-to-HTTPS-adapter same-operation terminal reconciliation and no duplicate synthetic effect. | Final combined CI passed; production external effect qualification remains later. No unresolved mandatory restored-receiver software contract was found after the 042 correction. |
| 18.4 | Bound private cache verification, documented per-process network identities, qualified offline task denial, actual DNS observation and the subsequent complete image-archive verification/load plus fresh-state network-none bootstrap/recovery/rotation exercise. | The earlier bounded installation-proof gap is now closed by actual procedure, not by the cache verifier alone. Preserve the preinstalled-Docker/cached-layer limit; original 12.8 cold/core installation and its broader optional-service matrix remain separate. Final combined CI/document checks passed. |
| 18.5 | Versioned runbooks, contribution matrix, existing bounded observation surfaces, actual packaged CLI/API exercise and capacity harness. | Full 30-minute result and final CI passed. Independent human self-service pilot remains open; final docs/provenance are recorded. Leave this packet/whole-story acceptance open until those mandatory proofs are accounted for. |
| 18.6 | Approved settings and target-inspection behavior, composed API-backed browser tests, accessibility/keyboard/screenshot evidence. | Preserve the separate UI branch/PR and copy its proof artifacts into the final review package. Target-selection/details scope matches the explicit approved packet; no new target-mutation flow is required by that packet. |

The canonical AC7 phrase includes “target … settings are saved in `/settings`”,
while the explicit approved packet specifies registered-target selection/details.
This audit does not invent a target-editing flow or treat its absence as an
implementation defect against that approved packet. Final completion prose must
state the delivered inspection/selection boundary plainly; if maintainers intend
AC7 to require target mutation from this screen, that additional requirement
would need an explicit scope decision and proof rather than a silent claim.

## Remaining mandatory evidence and status

At final integration, retain Story 16.18 **in-progress**. Full local CI and the
1800-second capacity artifact/resource summary passed. An independent human
self-service pilot cannot be represented as completed.
Root smoke has passed, and the subsequent bounded offline-installation procedure
closes Packet 18.4's earlier proof gap. The parent may update this disposition
after new concrete evidence arrives; an active process or elapsed wall time is
not a result.

For the capacity result, require exact final source/image/profile identity,
1800-second interval, all numerical assertions, resource/errors/cleanup and
source-drift checks. The declared scope is ten active runs, at most two real local
analysis workers using synthetic analysis, and twenty authenticated persisted
runner-service ports. Even a passing record does not prove twenty remote
independent runner agents, actual provider collection throughput or a production
receiver fleet.

The implemented support envelope is the named offline OpenTofu/Linux ARM64
profile plus local participating storage/control-plane recovery. Host-power-loss,
real production receiver token transfer/effects, unmanaged remote writer
coordination and additional tools/networks remain later release/support gates.
They must not be recast as already-qualified features or as reasons to block
unrelated completed local code.

Stories 12.7 and 12.8 remain open under their original acceptance. The former
includes original backup/upgrade/log/maintenance and supported database-path
obligations beyond this singleton SQLite automation slice; the latter requires
full offline core installation/analysis and its optional-service/network matrix.
The automation contribution table in `operations.md` correctly preserves this
boundary. Earlier handoff runbook sentences that still say all new exercises are
unrun should be reconciled to the newer exact evidence records during final docs
closeout; they do not negate the now-executed agent/operator and restored-receiver
contracts or the subsequent bounded offline installation proof, nor can they
supply the missing independent human proof.
