# Story 16.12 — BMad code review

Date: 2026-11-04. Initial outcome: **Changes requested**.

Current repair disposition: **R1–R4 resolved and verified; story ready for re-review**. See [repair details and fresh full test results](review-fixes.md). The original findings and reproductions below are retained as review history.

## Scope and method

Reviewed the 44 uncommitted story files on `feature/16-12-runner-enrollment-attempt-protocol` against HEAD, including new files. The full diff contains 27,591 lines (26,941 additions / 53 removals); excluding repetitive benchmark JSON samples leaves 5,464 diff lines. Frozen runner/enrollment v1, project context and Story 16.12 supplied acceptance authority. The review did not rely on the earlier development review's clean conclusion.

All three independent layers completed: Blind Hunter (diff only), Edge Case Hunter (diff and project), Acceptance Auditor (diff, story and contracts). Parent review reproduced the timing and encoded-secret failures. No layer failed. Triage: **0 decision-needed, 4 patch, 0 defer, 1 dismissed candidate**. Duplicate quota findings were merged.

## Findings

### R1 — P1: Encoded live task credentials survive log screening

**Resolved:** Shared bounded redaction now screens current credentials and bearer prefixes in logs, upload fields and administrative audit reasons; encoded and chunk-join regressions pass.

Location: `infra_automation/runner/claims.py:191–196`. Sources: edge + parent verification. Violates AC1 and the secret-free retained log/audit boundary.

`_secret_free` only searches for literal token strings and literal enrollment/runner prefixes. A valid runner can submit a percent-encoded current task token as a log chunk; the operation succeeds and the recoverable credential is persisted in `InfraAutomationAttempt.logs_json`. This concerns a standard encoding already supported by the repository's credential redactor, not arbitrary encrypted exfiltration.

Isolated reproduction: initialize `RunnerAttemptTests`, claim sequence 1, encode the current task token as `''.join('%%%02x' % ord(c) for c in task_token)`, and submit it as sequence-2 diagnostic log through `tasks.operate`. The stored log contains the token after `urllib.parse.unquote`. The existing `redact_text(encoded, sensitive_values=(task_token,))` detects the same value. No bearer values were printed or retained in this report.

Required repair: apply the existing bounded sensitive-value encoding handling to current runner/task credentials and known bearer prefixes before retention, including accumulated chunks and decoded upload fields. Add URL-encoded and supported encoded-variant regressions that assert no sequence or byte persistence on denial.

### R2 — P1: Message parsing can carry expired lease authority into mutation

**Resolved:** Fresh authority checks bracket parsing, each effect, audit and projection; savepoint rollback protects all retained state. Fractional credential expiry uses the advertised floor. All-five-operation delay regressions pass.

Location: `infra_automation/runner/claims.py:211–216`, `:247–251`, and non-upload operation branches. Source: parent verification. Violates AC2/AC4.

`operate` captures `now` before `parse_message`, then checks scope/lease and performs claim/heartbeat/log/complete using that captured timestamp. Only upload refreshes authority after its expensive screening. A processing delay or scheduler pause can cross the lease deadline before the actual check while still advancing the attempt with stale time.

Isolated reproduction: claim sequence 1; use the production `now=None` path; wrap the real `parse_message` so the controlled wall clock advances by 31 seconds after parsing; submit heartbeat sequence 2. The operation returns success and the durable runner-task sequence becomes 2 after the lease expired. This uses the real SQLite service path and existing engine checks, not a mocked mutation.

Required repair: refresh the operation clock and revalidate runner credential, coordinator/attempt and advertised lease after parsing/screening and immediately before each effect. Include claim/heartbeat/log/complete and credential expiry, not only upload and lock acquisition. Add regressions proving rejected operations leave sequence/state/bytes unchanged.

### R3 — P2: Historical enrollment rows permanently consume all runner slots

**Resolved:** Only live active credentials and unexpired pending enrollments consume capacity. Expired rotation and concurrent last-slot allocation are guarded; retained history remains readable.

Location: `services/infra_automation_runners.py:212–220`. Sources: blind + edge. Violates enrollment lifecycle/recovery intent in AC1/AC4.

The 100-runner project cap counts all rows, including revoked runners and expired pending enrollments. Revocation retains the row; expired enrollments cannot be redeemed; revoked/pending runners cannot rotate. The supported API has no path to reclaim these slots while retaining audit history.

Isolated reproduction: create and revoke 100 enrollments in a temporary project. The database has zero active runners and 100 revoked runners; the next enrollment returns 429. Ordinary replacements or documented lost-issuance recovery can therefore permanently disable enrollment for that project.

Required repair: separate live runner/pending-enrollment capacity from retained history, or provide a bounded replacement mechanism that preserves history. Test repeated expired/revoked enrollment recovery and active-cap enforcement. Coordinate history pagination with R4.

### R4 — P2: Runner health omits frozen list pagination

**Resolved:** Typed default25/max100 health pagination reuses scoped CursorStore and the immutable creation-audit insertion watermark; cursor authorization, expiry, tamper and insertion-isolation tests pass.

Location: `api/routes/infra_automation_runner_admin.py:61–63`, `services/infra_automation_runners.py:420–456`. Source: acceptance auditor. Violates AC5's frozen API list contract (`docs/infra-automation/contract-v1.md`, States/proposed resources/envelopes).

The route accepts only project/workspace and returns all retained runners, with no `limit`, snapshot cursor or continuation metadata. The frozen contract requires default 25, maximum 100, principal/scope/filter/snapshot-bound cursors with finite lifetime, and invalid-cursor 409.

Isolated API reproduction: 26 enrolled rows produce HTTP200 with all 26. Adding `limit=25` or `cursor=synthetic` returns 422. This is a contract mismatch, not a claimed cross-scope leak.

Required repair: reuse existing scoped snapshot pagination patterns; test the default/max page size, inserts between pages, cursor tampering/expiry, authorization changes, and retained history beyond the active enrollment cap.

## Dismissed and retained boundaries

- Tentative remote capacity-check bypass: dismissed as a separate defect because the authenticated claim reaches `engine.start_attempt`, which checks physical capacity before execution. No concurrency bypass was established.
- AC6 explicitly permits failed qualification without advertising capacity. The named-reference failure and diagnostic-only measurements are honestly reported and are not an approval blocker by themselves.
- Production isolation/real collection/signed distribution remain later-story gates; their absence was not reported as missing Story 16.12 implementation.
- The previously recorded receiver temporary lock-file test failure remains historical evidence; this review did not reproduce or newly classify it.

## Verification and disposition

Fresh focused runner/protocol/client/enrollment/attempt/authorization/sensitive-default/API/migration suite: **62 passed, 433 subtests passed**, in 15.49 seconds. Independent acceptance subset: 48 passed / 408 subtests. Repo-wide Ruff check and Ruff formatting (515 files), plus `git diff --check`, passed. Passing tests do not cover the reproduced findings above.

At the original review, only artifacts/tracking changed and four runtime fixes remained open; story/sprint status was in-progress. The repair follow-up now resolves all four with fresh verification (linked above). The existing branch complies with Git Flow. No commit or remote push was performed during the original review. The repair task also leaves git closure for the subsequent review workflow. Formal story closure still requires re-review; the implementation repair action items are now complete. BMad help routes the next step to `bmad-dev-story` for these action items, then `bmad-code-review` again.
