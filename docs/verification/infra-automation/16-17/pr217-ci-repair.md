# PR217 conflict and CI repair

## Base refresh

Backend PR216 was squash-merged into `develop` as
`48a9a9a51a0a6caaa2d7ee037b47275fd5ef1451`. PR217 still retained the original
backend feature history, so the completed UI story/sprint records conflicted
with the backend slice's earlier `in-progress` records. Merge `4ad80de` refreshes
the UI branch from develop, retains its completed evidence/status and preserves
the previous UI tree exactly. No production source changed in this merge.

## Failed CI and cause

Push run [42604812134](https://github.com/deploywhisper/deploywhisper/actions/runs/42604812134),
infra-automation job129118577528, failed two subcases of
`TriggerPrivilegeTests.test_real_decision_entrypoint_denies_each_machine_kind_and_role`.
The same-head pull-request run passed; the failing push run reported service /
contributor and agent / read-only failures at `reserve_nonce`, before the actual
human-decision privilege check.

Real handoff setup rechecks live machine authority and advances the durable
clock. Under slower coverage-enabled CI execution, that observation can pass the
fixture's previously captured next-second `case.now`. Sleeping until that old
instant does not refresh it. Signing with the stale injected clock correctly
triggers the production rollback fence and returns503 before the test can
exercise the intended403 denial.

## Repair and regression

Refresh only this new decision-matrix request with
`case.now = max(case.now, datetime.now(timezone.utc))`. Remove the sleep-only
block. Keep the shared signer, negative clock tests, signatures, scope/version
checks and all production guards unchanged. No larger sleep or relaxed assertion
is introduced.

The deterministic regression constructs actual signed handoffs, advances the
real durable machine-clock floor while retaining stale fixture request time,
and supplies the later wall clock at the request boundary. Before the repair,
all four principal/role combinations fail at nonce admission. After it, all four
reach the real decision service, verify their actual membership roles, and are
denied403 as required.

- Red regression: all four combinations reproduce reserve_nonce503 before decide.
- Focused green:2tests/8subtests passed.
- Entire privilege module:10tests/72subtests passed in25.04s.
- Ruff lint, repo-wide formatting584files and whitespace checks passed.
- All seven recorded critical runtime/contract/evidence hashes and collection
  qualification source hashes remain unchanged.

The full affected pytest shard is rerun with CI's coverage flags in an isolated
verification worktree. Root unittest is also rerun. Final acceptance requires
GitHub's new exact-head push and pull-request checks to finish successfully and
PR217 to be mergeable; a same-head PR pass alone does not clear a failed push.

UI validation not applicable: production UI, API, CLI, renderer and browser-test
source are unchanged. The prior fresh Compose/runtime proof remains applicable.
No merge of PR217, deployment or release is authorized by this repair.
