# Formal BMad code review — Story 16.18

**Follow-up: all seven findings resolved.** See the final section and [repair evidence](review-fixes.md).

**Original recommendation: REQUEST CHANGES.** Reviewed `262f47b..0716460` on
`feature/16-18-automation-settings-ui`: 164 files, including 74 source/test/config
files and 9,824 source-diff lines. All three fresh-context review layers completed:
Blind Hunter (diff only), Edge Case Hunter and Acceptance Auditor.

The bulk telemetry and screenshots were assessed through their structured
provenance rather than included in the blind source diff. The auditor verified
364 final-source hashes, 210 UI runtime/schema hashes and both 338-file capacity
witnesses against the current tree. Those matching records and passing suites do
not cover the newly reproduced failure paths below.

## Findings

### R1 — HIGH: Make initial recovery binding recoverable after ledger-publication failure

Location: `infra_automation/operator_recovery.py:574`. Source: blind+edge+primary.

initialize commits the recovery-state binding before publishing ledger.json. Injecting OSError from _save leaves one committed binding and no ledger; normal startup, initialize retry, status and resume cannot recover through supported tooling.

Evidence: `{"binding_rows": 1, "ledger_exists": false, "initialize_retry": "denied", "resume": "denied"}`.

Required follow-up: Journal initialization intent before the database binding, then support bounded idempotent recovery of that same intent; do not silently reset a genuinely lost deployed ledger.

### R2 — HIGH: Reject the reserved database root role before binding or restore reservation

Location: `infra_automation/operator_recovery.py:532`. Source: blind+edge+primary.

The role validator accepts database alongside artifacts/custody. In _stage, the expanded root maps overwrite the reserved database source/target entry. Initialization and backup succeed; restore reserves a new generation then fails, and resume repeats the invalid mapping.

Evidence: `{"initialize_and_backup": "accepted", "restore": "denied", "phase": "restore_reserved"}`.

Required follow-up: Reject reserved role names at layout validation or keep the database mapping structurally separate from caller-supplied root roles.

### R3 — MEDIUM: Validate the complete generated backup against restore limits before publication

Location: `infra_automation/operator_recovery.py:678`. Source: blind+edge+primary.

Creation counts content before adding manifest.json and measures depth from each source root; restore walks the entire package including manifest and its role prefix. A successful package at MAX_FILES or the accepted source depth can therefore be rejected by restore.

Evidence: `{"default_max_files": 4096, "source_files": 4093, "backup_returned_files": 4096, "manifest_bytes": 561138, "restore": "denied before reservation", "depth_case": "32 actual nested directories; backup files35; restore denied"}`.

Required follow-up: Apply a single package-aware budget including manifest bytes/count/depth and MAX_METADATA; run package verification on staging before exclusive publication.

### R4 — MEDIUM: Preserve committed retention tombstones when restoring an older snapshot

Location: `infra_automation/operator_recovery.py:800`. Source: blind+auditor.

_preserve_external_history excludes retention tombstones/removal audits, and nonexternal terminal runs bypass the run preservation check. A backup before purge restores the payload and removes the tombstone/removal audit from active history. Old private database copies remain, so this is not a claim that every historical copy is destroyed.

Evidence: `{"purge_http": 200, "payload_bytes_before_restore": 2, "payload_bytes_after_restore": 6390, "active_tombstones_before": 1, "active_tombstones_after": 0, "active_removal_audits_before": 1, "active_removal_audits_after": 0, "restore_phase": "reconciliation_required"}`.

Required follow-up: Refuse snapshots missing current protected deletion receipts, or carry forward validated tombstones and keep their payloads removed before publication. Preserve associated active deletion audit history.

### R5 — MEDIUM: Clean up or durably track failed upgrade-copy staging databases

Location: `infra_automation/operator_recovery.py:1374`. Source: blind+auditor.

Copy/migration/validation/publication failures have no enclosing cleanup or resumable upgrade mapping. Three injected Alembic failures left three full .upgrade-* copies while source stayed unchanged and output absent; every retry allocates another copy.

Evidence: `{"source_unchanged": true, "output_published": false, "failed_attempts": 3, "orphan_staging_files": 3, "orphan_bytes": 24576, "fixture": "tiny private SQLite input carrying schema028 marker; failure injected before migration"}`.

Required follow-up: Remove only positively owned unpublished staging files on ordinary failure, or retain one durable resumable attempt with explicit bounded cleanup; add interrupted upgrade-copy regressions.

### R6 — LOW: Preserve or explicitly warn before discarding same-scope settings drafts

Location: `frontend/src/screens/AutomationSettingsSection.tsx:38`. Source: blind+primary.

The form key includes policy version/authorization epoch, so a background refetch seeing an external update remounts it and silently resets values/reason. The query is immediately stale and the installed QueryClient retains focus-refetch defaults. A transient refetch error also removes the existing form through !policy.isError.

Evidence: `{"verification": "source path + installed TanStack Query defaults; no fresh browser reproduction"}`.

Required follow-up: Keep scope/session remount isolation, but retain dirty same-scope drafts or request an explicit reload acknowledgement when fresh policy data differs.

### R7 — LOW: Update the operator upgrade runbook to the verified schema042 result

Location: `docs/infra-automation/operations.md:423`. Source: auditor+primary.

The final runbook states destination schema041 while the linked final upgrade-results.json and current migration head are042.

Evidence: `{"runbook_destination": "041", "verified_destination": "042"}`.

Required follow-up: Reconcile the runbook statement with the linked final evidence and current supported upgrade target.

## Triage and limits

Seven patch action items: two high, three medium and two low. No decision-needed
or pre-existing deferred findings. Six concerns were dismissed after checking
project policy or documented limits; the full dispositions are in
[formal-code-review.json](formal-code-review.json). Similar observations across
layers were deduplicated. No review layer failed.

Reproductions used temporary synthetic stores and actual Alembic042 guards. The
file-count failure was independently reproduced at the real default4096 limit;
the depth case used the actual32-level boundary. Initialization and reserved-role
failures were reproduced by the primary reviewer and Edge Case Hunter. Retention
used a real valid HTTP purge and coordinated restore. Upgrade failure used a tiny
schema028-labelled SQLite input and injected Alembic errors; no complete live
customer upgrade or hostile archive test is claimed. UI draft loss is a verified
source/default-options path, not a fresh browser journey. No implementation or
production data was changed.

The human pilot remains an acknowledged unexecuted acceptance gate. Target
selection/details match the explicit approved UI packet; this review does not
invent a target-editing flow from broader canonical wording. Neither that scope
boundary nor later production support qualification excuses the functional
findings above.

## Review disposition

Findings are recorded as unchecked action items in the story. Packet18.2 is
reopened because backup, initialization and interrupted upgrade contracts have
reproducible gaps. Story and sprint status remain **in-progress**. Code was not
patched by this review-only request. Remote push was not performed because review
follow-up work remains open.

BMad Help handoff: address these recorded findings through `bmad-dev-story`, add
regressions for the reproduced paths, refresh affected validation/provenance,
then rerun `bmad-code-review`. Preserve the human and release/profile gates.

## Review-fix follow-up — 2026-11-11

All seven patch findings are resolved and independently checked. The request-changes
report above describes the original `0716460` source; its reproductions and six
dismissals remain historical. [Repair details](review-fixes.md) and
[final validation](review-fixes-validation-summary.json) identify the frozen repaired
source, repeated composed-browser/operator checks and full CI/capacity evidence.
Packet18.2 is closed again; the independent human pilot keeps Packet18.5 and the
story in progress. No public GitHub write or production support claim was made.
