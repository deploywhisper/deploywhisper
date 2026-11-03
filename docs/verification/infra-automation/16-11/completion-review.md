# Story 16.11 completion review — 2026-11-03

Reviewed the follow-up to merged PR207 against `origin/develop` (`d7d8fa1`).
The initial review input contained 5,262 lines of source, tests and workflow
changes, grouped by receiver/custody, server/auth/reconciliation, frontend and
qualification tooling. Generated security reports were excluded.

## Three independent review layers

Blind adversarial review, exhaustive edge-case review and acceptance audit each
completed without inherited conversation context. Their findings deduplicate to:

1. **P1, blind + edge + auditor:** a correctly signed accepted callback after
   delivery_unknown could replace the latest uncertainty fact and reopen action
   admission. Fixed by checking immutable callback history and rejecting progress
   regression after unknown/cancel/running. Regressions exercise unknown→accepted,
   cancel→running, running→accepted and continued terminal reconciliation.
2. **P2, edge:** a reconciliation control could unmount while POST was in flight
   before recording ambiguity, then allow another same-version submission.
   Fixed by persisting the scoped marker immediately before POST and clearing it
   only for a matching version after recognized definite server HTTP4xx rejection.
   A real browser journey holds POST, fails a child read, remounts the control,
   checks it remains blocked, then observes the real advancing operation.

No decisions or deferred findings remain. Independent blind/edge/acceptance
rechecks confirm both corrections. The acceptance recheck independently passed
21 reconciliation unittest cases. Final edge recheck returned an empty array.

## Additional integration corrections

- Lost callback response now recovers only from authenticated exact persisted
  envelope digest/nonce/sequence plus original receipt; duplicate callback 409
  never authorizes another action.
- Final action authorization occurs after bounded custody verification while the
  verified bytes remain held; expiry is checked again before the synthetic effect.
- Terminal reconciliation respects the parent clock floor and guarded CAS,
  including cancellation and sibling uncertainty. It cannot create local evidence.
- Explicit trusted composition connects one actual GitHub adapter to the admitted
  decision service; unqualified material witnesses remain unavailable by default.
- Migration036 schema/guard recognition survives repeated startup and unversioned
  adoption. Prior migration tests retain direct historical targets and immutable
  guard checks while expecting the current head after normal startup.
- Composed child reads exposed one missing `mutation=False` argument; the real
  scoped HTTP relation now has regression coverage. Fixture-only typed output and
  provenance records are normalized before immutable insertion, never rewritten.
- Actual GET-only GitHub preflight exposed premature closure of Connection-close
  response readers. A 262,144-byte regression failed before the lifetime fix;
  host and Linux transport tests pass afterward. The live preflight and one
  harmless dispatch then passed. Deadline/peer/TLS/body limits and no retry remain.
- Browser axe identified existing nested report main landmarks and low-severity
  contrast on the linked permanent report. ReportBody now reuses the shell's main
  and existing accessible neutral EvidenceTag for Low severity. Approved tokens
  and other severities are unchanged. No issue was suppressed.
- Narrow-screen QA identified intrinsic grid width from long retained IDs and
  action labels. Scoped zero-minimum layout and wrapping retain approved visual
  values. Visual verdict rose from 82/84 revise to final 95/pass.

## Skill forward-test

The owner explicitly requested updating the workflow that halted independent
implementation when live configuration was missing. The dev-story skill now
blocks only dependent external effects, preserves default-deny and all live proof
requirements, resolves routine technical choices from repository authority, and
continues independent code/tests/documentation. Completion and sprint status are
conditional on all Step9 gates. The stale Step6 completion reference was fixed.

The skill validator passed. Independent forward-testing verified both scenarios:
continue independent work while a remote proof is not run; halt the remaining
irreversible operation if its required authority/configuration is truly missing.
It never treats fixtures as live proof or closes unfinished acceptance gates.

See [completion evidence](completion-evidence.md),
[live GitHub proof](live-github-proof.json) and [visual verdict](visual-verdict.json).
