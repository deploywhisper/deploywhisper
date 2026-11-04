# Runner enrollment and attempt protocol v1

Story 16.12 supplies the outbound control protocol. It does not qualify a production collection sandbox, execute an IaC command, or certify collected evidence. Those obligations remain in Stories 16.13–16.14 and integrated release qualification.

## Authority and transport

Administrators create bounded one-use enrollment credentials for one concrete project/workspace and a server-selected runner profile. Redemption returns an expiring runner bearer exactly once. Storage retains verifiers; responses containing credentials are transient and must not be cached. Rotation invalidates the previous credential. Revocation, expired credentials, changed authorization/restore epochs and disabled collection deny further work. Authorized retained history remains readable.

Enrollment uses `runner-enrollment-v1`; attempt operations use `runner-task-v1`. Neither grants a human session or receiver authority. Use supported HTTPS and a trusted certificate chain. A configured HTTPS origin does not itself demonstrate execution isolation.

The closed wire contracts remain [enrollment-v1](../../schemas/infra-automation/enrollment-v1.json) and [runner-v1](../../schemas/infra-automation/runner-v1.json). Workflow major 2 does not change these independent protocol majors. Unknown fields/capabilities/versions deny. Messages are at most 128 KiB UTF-8; log chunks at most 16 KiB UTF-8. UTC dates must be real dates in the frozen `YYYY-MM-DDTHH:MM:SSZ` form.

## Task ownership

Selection compares server-owned tags, tool, profile digest and compatible version. The closed workflow never carries arbitrary executable commands or credentials. An eligible runner receives a transient attempt grant; every claim, heartbeat, log, upload and completion independently revalidates runner, project, workspace, run, step, attempt, fence, coordinator generation, authorization/restore epochs, live lease, profile, capability registry and monotonic sequence.

The server binds this grant to the existing durable engine attempt. It never accepts a caller-created coordinator handle. Restart loses transient delivery authority; durable fencing/recovery must issue fresh ownership. A connected runner cannot complete another runner's work. Missing compatible runners produce explicit bounded failure/wait evidence, never a fallback to an unrelated runner or local execution.

Uploads are screened bounded transport bytes, not binary plans or state. Digest and atomic-upload identity must bind the current attempt before success can consume the reference. Partial uploads do not qualify evidence. Exact raw-plan custody remains outside the app.

## Verification and operating limits

See [qualification evidence](../verification/infra-automation/16-12/qualification.md) and [authorization matrix](../verification/infra-automation/16-12/authorization-matrix.md). Tests with synthetic profiles establish protocol behavior only. No production runner throughput or isolation capacity is advertised by these fixtures.

## API and operator entry points

All paths below are under `/api/v1/infra-automation/runners`:

| Method/path | Credential | Result |
| --- | --- | --- |
| `POST /enrollments` | HTTPS human admin session and CSRF | Frozen enrollment envelope and one-use token |
| `POST /enrollments/{id}/redeem` | Enrollment Bearer token | Expiring runner credential; replay denies |
| `POST /{id}/rotate`, `POST /{id}/revoke` | HTTPS human admin session and CSRF | Rotate once or revoke current authority |
| `GET ?project_id=…&workspace_id=…&limit=25&cursor=…` | Scoped admin/maintainer human session | Paginated screened health/history |
| `GET /{id}/tasks` | Runner Bearer token | One-time task assignment or null |
| `POST /claim`, `/heartbeat`, `/logs`, `/complete` | Runner Bearer and `X-Runner-Task-Token` | Frozen operation envelope with current scope |
| `POST /uploads` | Runner Bearer and `X-Runner-Task-Token` | Closed `{message, screened_content}` transport wrapper |

`screened_content` is strict base64 of canonical UTF-8 JSON containing an array of `{name, content}` objects. Both the HTTP envelope and decoded data are bounded; the transport wrapper's 120,000-character base64 maximum is stricter than the general 128 KiB message limit. The server rejects sensitive or unsupported content and recomputes the digest before committing the reference. The frozen completion contract requires a current finalized upload reference for either completion state. A failure before upload is resolved by coordinator cleanup or bounded lease recovery; it does not create a fictitious evidence reference.

Save the enrollment envelope and one-use token into separate operator-owned files. Use the CLI's private-file input rather than putting bearer values into command arguments:

```sh
python -m cli.runner enroll --url https://your-deploywhisper-host \
  --enrollment-file /private/enrollment.json \
  --credential-file /private/enrollment-token \
  --output /private/runner-credential.token
```

The enrollment file contains the JSON envelope; credential files contain only the bearer text. Consult `python -m cli.runner --help` for commands. The output path must be new; it is reserved with owner-only access before redemption. Lost issuance replies cannot be replayed to recover the same secret. Revoke the uncertain enrollment/runner and issue new authority.

The host integrates trusted `RunnerRequirements` through the coordinator's profile mapping and `queue_assignment`; requests cannot supply that mapping. It defaults empty, and the standard collection handler remains unavailable. `RunnerClient.run` accepts only a locally installed trusted handler after a successful claim acknowledgement. The CLI's default `run` fails before consuming an assignment until that qualified handler is supplied by the later collection work. Do not use task polling as a connectivity probe: it consumes one-time delivery authority.

Audit events are append-only application evidence with screened metadata; a database administrator can still alter storage outside the application trust boundary. Revocation and history access remain available while collection is disabled. Connectivity and protocol compatibility never certify sandbox isolation.

## Retained history and current capacity

The project limit is 100 current runner slots: unexpired active credentials and unexpired, unconsumed pending enrollments. Revoked runners and expired enrollment/credential history remain retained without consuming a current slot. Rotating an expired credential must reserve capacity again; concurrent enrollment and rotation cannot exceed the limit. No retained history or audit record is deleted to free capacity.

Health returns `data.items` and `data.cursor`. The default page has 25 items; `limit` accepts 1–100. Pass `data.cursor.next_cursor` with the same project, workspace and limit to continue. Cursors bind the authenticated principal and live authentication/membership versions and expire within 15 minutes. Invalid, stale or tampered cursors return 409; lost permission still denies access. Restart invalidates process-local cursors, so start a fresh first page.

The immutable creation-audit sequence fixes each traversal's insertion snapshot. Ordering remains descending creation time and runner ID; records inserted later, including backdated records, are excluded until a new first page. Live health fields may change as runners operate; pagination grants no execution authority.

Credential screening applies the shared bounded URL-decoding rules to current task/runner values and bearer prefixes, including accumulated logs and decoded upload fields. Every operation refreshes authority after parsing/screening, around mutations and before returning. If a deadline is crossed while processing or constructing its result, the transaction rolls back its sequence, evidence and audit changes.
