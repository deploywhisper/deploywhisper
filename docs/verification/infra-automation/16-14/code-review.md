# Story16.14 independent development review

2026-11-04. BMad layered review covered the full working change against `develop` baseline4ff2c2d and the story/project context. Blind Hunter received only the4425-line diff; Edge Case Hunter received diff/project access; Acceptance Auditor received diff/story/context. All three returned findings. An earlier independent boundary review supplemented these layers. No human approval is claimed.

## Findings and repair evidence

| Finding | Disposition | Evidence |
| --- | --- | --- |
| P1: JSON-escaped known collector credentials bypass serialized-text screening | Fixed | Reproduced failing Unicode-escape regression, then rejected decoded document through existing `redact_value(..., sensitive_values=...)`; original serialized text checks retained |
| P1: legacy artifact arrays accepted for admitted collection without provenance/manifest | Fixed | Independent authenticated claim/upload/complete reproduction succeeded without a manifest; upload and successful completion now both require the typed envelope, including prior-version staged bytes. Final independent intake/runner recheck: 36 tests passed. |
| P2: fixed3600-second handler TTL rejects valid shorter workflow policy | Fixed | Explicit bounded operator-bound evidence TTL; client test verifies actual300-second provenance interval |
| P2: synchronous custody finalizer can hang beyond deadline | Fixed | Existing bounded callback supervisor; hanging-finalizer regression returns without output/metadata, even if an unreferenced late local bundle is published |
| P2: abandoned upload staging survives terminal recovery | Fixed | Shared transactional cleanup on engine safety/terminal transitions and runner revoke/rotate, preserving committed output/manifests |
| AC6: disconnected real-plan/service/receiver fixtures cannot prove continuous lineage | Fixed and qualified | Fixture-first actual enrolled task, production CollectionHandler and authenticated service path added; receiver binds original retained custody. Final stable qualification passed: 44 collection checks and 172 isolation checks; integrity suite 9 tests/62 subtests |

Dismissed: missing source `version` is normalized by `Collected.model_validate` before custody persistence. Generic true sensitivity masks already reject through shared artifact screening. The mutable-lease equality hypothesis was not an immediate upload-renewal defect; intake nevertheless distinguishes stable task scope from lease validity and adds advancing-clock checks.

No new dependency or architecture decision requires user input. Repairs remain within the authorized story. This review does not waive real-tool or repository validation gates; the final Dev Agent Record records those results. Git Flow branch is `feature/16-14-opentofu-terraform-collection-provenance`; public publication is not part of this development review.

A final focused run exposed a macOS process-group permission race during natural exit. The cleanup helper now performs its existing bounded wait/poll after PermissionError, succeeding only after observed exit and returning failure if still running. Regression plus client/collector/sandbox/boundary suite: 37 tests, 91 subtests passed.

Full automation regression found an older revision032 engine fixture lacking the later runner-task table. Cleanup now returns before querying runner staging for non-collection attempts. Fresh engine qualification/intake suite: 18 tests, 11 subtests passed; collection44-check qualification regenerated with current repository hash, isolation172-check record remains current.
