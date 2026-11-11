# Restored receiver reconciliation results

Story 16.18 packets 18.2/18.3, 2026-11-10. The independently reviewed
[design](receiver-recovery-design.md) was implemented using migration 042,
private operator issuance and the existing receiver wire. No old receiver
credential or action grant is restored.

## Delivered contract

- One current hashed, 256-bit reconciliation credential per retained consumed
  operation, bound to installation/global restore generation, project restore
  epoch, original binding/receipt, current receiver and human issuer versions.
  Issuance requires a fresh verified global human configuration owner and current
  operation-scope administration during `reconciliation_required`.
- Server-derived `status_terminal` and `status_only` modes distinguish unresolved
  consumed operations from already verified terminal outcomes with lost replies.
  Rotation is CAS protected, bounded to 100 issues per operation/generation, and
  charged to existing retained-storage quotas. Only the private CLI file writer
  receives plaintext; the database and audit retain no bearer.
- Recovery credentials permit exact retained status and signed terminal callback
  admission only. Bootstrap, consume, action authorization, progress callbacks
  and the public unsigned `resolve_terminal` service method deny them. Signed
  callback admission invokes a private terminal transition helper after existing
  source/binding/signature/sequence/nonce checks and durable fact retention.
- Live authorization/time is rechecked before mutation and after terminal audit.
  Expiry observations persist only a monotonic credential clock under the same
  outer SQLite reservation after business-savepoint rollback. An expired token
  cannot regain authority when the server clock moves backward. Wrong verifiers
  cannot advance that clock.
- The global content redactor now screens literal reconciliation credentials and
  four bounded base64 layers plus existing URL-decoding variants. The decoded
  JSON screening helper rejects reflection in ordinary keys and string values.

## Actual local proof

The new recovery tests execute actual Alembic migrations through 042. Shared
synthetic collected-material fixtures directly seed intermediate engine states;
guards are temporarily absent only during that seeding. The exact SQL emitted by
the actual migrations is restored before any tested service admission, receiver
operation, backup or restore. This is not a model-metadata-only restore fixture.

The integrated case executes the real protected `ReferenceReceiver` against the
actual HTTPS FastAPI receiver routes and counts one synthetic local marker
action. Its terminal callback is deliberately interrupted. It then performs a
coordinated database/custody backup and restore, rejects the old receiver
credential, runs actual one-use human account recovery and fresh login, issues a
new reconciliation credential, and restarts the reference receiver. Only
`status`/`outcome` HTTP calls occur during recovery. The original consumed
operation reconciles; repeating recovery leaves the action count at one.

Other cases verify terminal lost-acknowledgement `status_only`, rotation,
concurrent issuers, receiver/issuer revocation, another global/project restore,
expiry and clock rollback, expiry during HMAC/audit, wrong receiver/audience,
quota rejection and audit rollback. The entire action privilege ceiling is
checked separately from successful status/outcome use.

## Commands and results

Existing local Python: 3.14.3. Existing dependencies were reused.

| Command | Result |
| --- | --- |
| `./.venv/bin/python -m pytest tests/test_infra_automation/test_receiver_recovery.py tests/test_infra_automation/test_receiver_recovery_redaction.py -q --tb=short` | 17 passed, 68 subtests passed, 24.43s; existing Alembic path-separator deprecation warnings. |
| `./.venv/bin/python -m pytest tests/test_infra_automation/test_handoff_service.py tests/test_infra_automation/test_handoff_process_recovery.py tests/test_api/test_infra_automation_receiver.py -q --tb=short` | 83 passed, 124 subtests passed, 49.21s. |
| `./.venv/bin/python -m pytest tests/test_infra_automation/test_receiver_recovery_redaction.py tests/test_infra_automation/test_handoff_secret_screening.py tests/test_infra_automation/test_artifact_intake.py -q --tb=short` | 15 passed, 435 subtests passed, 2.11s. |
| `./.venv/bin/python -m ruff check services/content_security.py services/infra_automation_receiver_recovery.py services/infra_automation_handoffs.py models/receiver_recovery.py infra_automation/receiver_recovery.py migrations/versions/042_add_receiver_recovery.py tests/test_infra_automation/test_receiver_recovery.py tests/test_infra_automation/test_receiver_recovery_redaction.py` | Passed. |
| `./.venv/bin/python -m bandit -r services/infra_automation_receiver_recovery.py services/infra_automation_handoffs.py infra_automation/receiver_recovery.py models/receiver_recovery.py -ll -ii -q` | Passed. |
| `./.venv/bin/ruff format --check .` | Passed; 611 Python files formatted. |
| `git diff --check` | Passed. |

Red-phase evidence: the first new test failed importing the missing recovery
service. Redaction tests subsequently reproduced 55 reflection subtest failures
before adding the known credential family. Actual restore testing also exposed
the existing inert engine audit identity's fixed authentication-version check;
root corrected that separate audit-only validation without exempting any
credential from restore invalidation.

Independent review reproduced an expired-token clock-rollback revival, then
independently verified denial after the observation fix. The same reviewer ran
28 backend/reference-receiver/CLI tests and 17 subtests successfully in 23.71s
against service hash `e1e9350938961a3170ef6b4719f44694ea18fb94cce488bb80f8811298a5e4ec`.

Final reviewed service/source SHA-256 values:

| Path | SHA-256 |
| --- | --- |
| `services/infra_automation_receiver_recovery.py` | `e1e9350938961a3170ef6b4719f44694ea18fb94cce488bb80f8811298a5e4ec` |
| `services/infra_automation_handoffs.py` | `2a29c719856e2b68c9a2cb309eb65dfec065e7c28910f72bf937b08d6e25bee6` |
| `models/receiver_recovery.py` | `1f0a991b72be22baac38e576ffa4649d883015eace1c135a6ac56bcdc1a3941f` |
| `infra_automation/receiver_recovery.py` | `7573fc1bcfd75bbeb5927e26f6e554d9d1969617f5821e50b5d8dc981a4c571e` |
| `migrations/versions/042_add_receiver_recovery.py` | `aa45e46856a5f3b8e5e50007537f3ec357b47e57b41b4d83c63feaacf438f840` |
| `services/content_security.py` | `722885fea5af32cce11bf31d440b04b7392371013c87aa0c9c3afd89a0db715b` |

## Qualification boundary

This proves a synthetic effect and an in-process HTTPS adapter, not a live TLS
deployment, protected token transfer to a production receiver, infrastructure
deployment, host power-loss durability, or operator pilot. Actual tool/profile
requalification and source-drift checks belong to root's final current-source
verification. Broad CI, capacity, UI and story status remain root-owned. UI
validation is not applicable to these backend/CLI/receiver contract changes.
