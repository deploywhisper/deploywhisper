# Completed receiver recovery and private CLI adapter

Implemented after independent design clearance of
`receiver-recovery-design.md` SHA-256
`1d9394e5132db18e8d36b2eabd518c0bb33770fbd6e9430bd651a47a98839430`.
This packet owns `infra_automation/receiver_runtime.py`, the issuance adapter in
`cli/automation_operations.py`, and their new receiver/CLI tests. Backend issuance,
sidecar authorization, migration 042 and actual coordinated-restore composition
are verified by their separate integration packet.

## Behavior

`ReferenceReceiver.recover_completed(operation_id, binding_digest)` requires an
existing protected local row in phase `complete`, exact original consume/payload/
receipt/binding bytes, the original terminal callback and the matching durable
synthetic marker or saved-plan digest receipt. It never enters `run`,
`flush_callbacks`, bootstrap, consume, action admission or custody verification.
An unfinished or uncertain phase remains unresolved even if a marker exists.

The helper first reads authenticated server status. Terminal server state permits
only recognition of an exact original or previously retained callback
acknowledgement; conflicting/missing proof never produces a new callback. For an
eligible unresolved server state, it re-signs the same immutable event using the
new private secret while preserving message, source, nonce and sequence. It
durably commits the complete envelope and digest before transmission, retains
the original callback unchanged, and stores no plaintext new bearer.

The local outbox has at most 100 candidates per operation. A full outbox denies a
new signature but still permits recognition of an exact retained acknowledgement.
Lost responses and later credential rotation recognize the existing envelope
digest rather than replaying an action or changing the event identity. The
server's separately enforced `status_only`/`status_terminal` authority is not
represented by a caller-selected wire flag.

The private operator command is:

```text
python -m cli.automation_operations --control /private/control receiver-recovery-issue --operation ORIGINAL_OPERATION --token-file /private/human-session --csrf-file /private/csrf --reason-file /private/reason --output /private/new-receiver-token
```

It binds fresh human mutation credentials and delegates to
`services.infra_automation_receiver_recovery.issue_credential`. The existing
private writer reserves a new owner-only output inode before issuance. Existing
files and symlinks deny without issuing; failed publication removes only the
reserved output. An explicit new issue rotates a lost credential. Standard
output is only `{"credential_written": true}`; credentials are never command
arguments or printed output. CLI adapter tests inject an issuer: they prove
custody/publication behavior, not backend administrator authorization.

## Verification

The regression-first run failed because `recover_completed` did not exist.
After implementation, the following final scoped run passed:

```text
./.venv/bin/python -m pytest tests/test_cli/test_receiver_recovery.py tests/test_cli/test_identity.py tests/test_infra_automation/test_receiver_completed_recovery.py tests/test_infra_automation/test_receiver_runtime.py tests/test_infra_automation/test_collection_receiver.py tests/test_infra_automation/test_receiver_protocol.py tests/test_infra_automation/test_receiver_custody.py -q --tb=short
66 passed, 1 skipped, 146 subtests passed in 11.39s
```

The skip requires Linux root to exercise separate receiver UIDs. Ten new
completed-recovery tests cover unchanged event identity, original accepted
acknowledgement, lost recovery replies followed by rotation, unfinished phases,
terminal conflicting acknowledgement, binding/receipt/marker mismatch, outbox
limits, unavailable status and saved-plan receipt mode. An actual subprocess
exits at checkpoint `recovery_callback` after server acceptance and before local
delivery acknowledgement. A second process with a rotated key recognizes the
durable prior candidate, sends zero callbacks, and retains exactly one action.

Four private CLI tests cover reserved-inode permissions, existing/symlink output,
issuer/publication failure with explicit retry, secret-free output and public
human-input rejection. Existing normal receiver/identity/collection receipt
tests remain in the same command.

Scoped Ruff lint and Bandit passed. Repository-wide
`./.venv/bin/ruff format --check .` passed with **610 files already formatted**.

## Boundary

The server port and action material in these tests are explicitly synthetic.
The actual process/SQLite/outbox behavior is exercised; these tests do not prove
production credential transfer, HTTPS receiver admission, a real infrastructure
outcome, host-power-loss durability or independent human adoption. The separate
backend packet must prove actual restore, new credential issuance, old-token
denial and signed terminal reconciliation through its real service boundary.
No deployment, apply, replacement grant or fresh approval is introduced.
