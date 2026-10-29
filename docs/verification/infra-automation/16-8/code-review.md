# Story 16.8 BMad code review

Date: 2026-10-29. Reviewed baseline `b2e87ecb41e0bdafc5904586969db396a45ce390`
through `6238a59` on `feature/16-8-evidence-bound-decisions-freshness`.
The initial diff contained 30 files, 4,924 insertions and 63 deletions.
The explicit story/spec and frozen contracts provided full acceptance context.

The review used independent native agents without inherited conversation:
Blind Hunter received only the diff; Edge Case Hunter followed reachable project
references; Acceptance Auditor received the story and mandatory project context.
All three layers completed. The root normalized/deduplicated their findings and
reproduced the applicable defects before assigning fixes. Repository autonomy
instructions authorized applying the unambiguous patches without a permission
checkpoint. No product or architecture decision needed user clarification.

## Triage

0 decision-needed, 6 patch, 0 defer, 3 dismiss; no failed layers.

| ID | Severity | Source | Finding | Disposition |
| --- | --- | --- | --- | --- |
| R1 | P1 | edge | Enforce total run deadlines and monotonic clock floors at every decision/recheck boundary | Fixed; regression and independent re-review passed |
| R2 | P1 | edge+root | Refresh the clock after material resolution before authorizing a decision | Fixed; regression and independent re-review passed |
| R3 | P2 | auditor | Preserve the actual evidence/source/custody expiry reasons | Fixed; regression and independent re-review passed |
| R4 | P2 | blind | Protect the decision sequence primary key from SQLite OR REPLACE | Fixed; regression and independent re-review passed |
| R5 | P2 | blind | Keep a valid run waiting when a later decision is requested before its human prerequisite | Fixed; regression and independent re-review passed |
| R6 | P2 | blind | Preserve transient authority-unavailable responses without inventing binding changes | Fixed; regression and independent re-review passed |

The SQLite replacement regression first demonstrated that an existing sequence
could be overwritten with a new ID, step and generation while recursive triggers
were off. The corrected guard covers every uniqueness conflict key. Storage and
migration checks then passed 20 tests and 27 subtests.

The service matrix reproduced run-total-timeout admission and dispatch, material
callbacks crossing an approval deadline, incorrect component-expiry reasons,
rollback before retained clock floors, premature serial-human requests, and
retryable unavailable material/receipt dependencies. Final independent focused
validation passed 77 tests and 154 subtests, including the original service,
API, graph and immutable-packet cases. No blocking source finding remained.

### Dismissed conditional findings

- A historical successful analysis cannot normally acquire a later replacement
  attempt: `infra_automation_runs.create_attempt` admits retry predecessors only
  after failed/timed-out attempts. No reachable new-change bypass was established.
- Approval list access checks the exact current project/workspace scope and
  `automation.decision`. Every registered role with that capability also has
  `report.read`/`report.review`; `guard_report` applies the same scope check.
  There is no independent per-report deny rule in the current model to bypass.
- Staged human decisions after an external handoff are not executable in the
  qualified profile. Fixed-handler admission rejects unavailable handoff
  execution; later target/receiver owners must integrate those stages. Static
  graph validity alone does not admit a runtime handler. The delivery boundary
  is explicit in `docs/infra-automation/decisions.md`.

## Final verification and closure

Final root smoke passed 1,242 tests (2 skips). The exact API/CLI/infra shard passed 688 tests and 2,274 subtests (1 opt-in skip). Full local CI passed, exit 0: 2,688 directory tests across all ten directories.
Ruff lint and repository-wide formatting (439 files), independent focused tests,
scoped typing/security and API-declaration typecheck have passed.
UI validation not applicable: no rendered surface or browser interaction changed.
No production collector/target/custody/receiver or release qualification is claimed.

Commands ran with `LLM_API_BASE=http://127.0.0.1:1` to exercise optional-narrative fallback deterministically:

- `./.venv/bin/python -m unittest discover -q`: 1,242 tests, 2 skips.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: 688 passed, 1 opt-in skip, 2,274 subtests.
- `bash scripts/ci-local.sh`: exit 0; 69 analysis, 312 API, 102 CLI, 51 docs, 275 infra, 506 automation, 76 LLM, 22 model, 43 parser and 1,232 service tests. The infra/LLM opt-in skips remain explicit.
- Ruff lint and repository-wide formatting: passed (439 files).
- Scoped mypy/Bandit, compilation and generated API typecheck: passed.
- Repo-wide mypy: 312 existing findings versus 314 on the original archived baseline; no introduced file/message findings.

Review-fix commit: `15b8197`. Story/sprint status: **done**. The existing feature
branch is compliant with Git Flow; remote push and PR linkage are being completed.
The prior dev-story worker-teardown retry is retained in results.md; this formal
review's root, affected shard and full local CI runs passed without a retry.

