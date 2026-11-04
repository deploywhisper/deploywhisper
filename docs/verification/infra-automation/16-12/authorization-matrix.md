# Story16.12 authorization matrix

The matrix covers control protocol authority. A permitted operation still requires live credentials, feature policy, exact object binding and unexpired leases. `allow` never means unrestricted collection authority.

## Human role × project/workspace × operation

`test_runner_authorization_matrix.py::test_every_human_role_and_scope_for_administration_and_health` exercises all 60 cells below: five roles × three scope cases × four operations. Scope cases are matching project/workspace, same project/wrong workspace and other project/workspace. Mutations resolve the retained runner's scope; creation/read resolve the requested scope. The actor has a workspace-specific grant, so a sibling workspace is inaccessible.

| Principal and role | Matching scope enroll | Matching scope rotate | Matching scope revoke | Matching scope health | Wrong workspace, all four | Wrong project, all four |
| --- | --- | --- | --- | --- | --- | --- |
| Human admin | allow | allow | allow | allow | deny | deny |
| Human maintainer | deny | deny | deny | allow | deny | deny |
| Human reviewer | deny | deny | deny | deny | deny | deny |
| Human contributor | deny | deny | deny | deny | deny | deny |
| Human read-only | deny | deny | deny | deny | deny | deny |

`test_nonhuman_sessions_never_grant_runner_administration` adds 240 machine-principal cases: service, agent, runner and receiver × five roles × three scope cases × enrollment/health/rotation/revocation. Each has a synthetic human-audience session; all operations are denied. This tests that membership/audience labels cannot transform a machine into a human administrator.

Executed: `./.venv/bin/python -m pytest tests/test_infra_automation/test_runner_authorization_matrix.py -q --tb=short` → **2 passed, 300 subtests passed**.

## Runner task dimensions × operations

The task owner supplies `test_runner_attempts.py::test_scope_matrix_denies_every_operation_before_mutation`, covering claim, heartbeat, log, upload and complete with changed runner/project/workspace/run/step/attempt/fence/coordinator generation/authorization epoch/restore epoch/lease/audience/profile. The test checks retained attempt/task state after denials; protocol parsing handles invalid audiences and strict types before mutation.

| Authority condition | Claim | Heartbeat | Log | Upload | Complete |
| --- | --- | --- | --- | --- | --- |
| Exact current runner, credential generation, grant and scope | allow in valid state | allow in valid state | allow in valid state | allow with screened bytes/digest | allow with finalized matching upload |
| Any changed scope, profile or audience | deny | deny | deny | deny | deny |
| Wrong task token or expired lease | deny | deny | deny | deny | deny |
| Rotated/revoked/expired runner credential | deny | deny | deny | deny | deny |
| Disabled policy or changed restore/authorization epoch | deny | deny | deny | deny | deny |
| Human cookie without runner bearer | deny | deny | deny | deny | deny |
| Replayed sequence or stale fenced owner | deny | deny | deny | deny | deny |

Supporting tests: `test_expired_lease_wrong_token_and_rotation_deny`, `test_sequence_race_allows_one_effect`, `test_complete_requires_atomic_upload_and_rejects_replay`; existing engine stale-binding/concurrent-claim tests remain part of the inherited engine boundary.

## Enrollment and transport

`test_runner_enrollment.py` covers one-use replay, concurrent redemption, credential hashes, expiration, rotation, revocation, disabled-policy retained health, changed issuer membership, envelope/version binding and secret rejection in persistent reason fields. `test_runner_protocol.py` covers strict closed schemas, UTF-8 byte limits, duplicate fields and separate enrollment/task audiences. `test_infra_automation_runner.py` covers HTTP/query rejection, human cookie denial, duplicate Authorization headers and screened error responses. `test_runner_client.py` covers HTTPS origin validation, protected credential files, bounded polling and absence of blind mutation retries.

These test mappings document executable obligations. The final qualification record supplies the executed combined test result; mappings alone are not a passing release or production collection claim.
