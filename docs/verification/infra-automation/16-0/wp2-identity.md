# WP2 — Disposable identity and route-scope qualification

Executed 2026-10-09 by Codex, backend/security qualification contributor. This
packet supplies executable inputs for architecture §25.4 and Story 16.0 AC3.
It does not implement accounts or automation permissions in DeployWhisper,
deliver Stories 16.1/16.2, accept RFC 0001, or independently close IR-02.
WP1's threat-model inputs were read; public acceptance is not a prerequisite
for this disposable experiment. Independent maintainer/security review remains
required before adopting the selection for production.

## Reproduce and evidence

Run from the repository root with the existing environment:

```sh
./.venv/bin/python -m unittest tests.test_infra.test_infra_automation_identity_qualification -v
./.venv/bin/python tests/fixtures/infra_automation/qualification/16_0/identity/measure.py
./.venv/bin/ruff check tests/fixtures/infra_automation/qualification/16_0/identity tests/test_infra/test_infra_automation_identity_qualification.py
./.venv/bin/ruff format --check tests/fixtures/infra_automation/qualification/16_0/identity tests/test_infra/test_infra_automation_identity_qualification.py
./.venv/bin/bandit -q -r tests/fixtures/infra_automation/qualification/16_0/identity tests/test_infra/test_infra_automation_identity_qualification.py
```

The registered `tests/test_infra` lane discovers 18 tests. The first run was red:
the targeted unittest command returned 1 because the disposable prototype did
not yet exist. The implemented run passes all 18 tests, including 2,000 matrix
outcomes. Owned-file Ruff lint/format and Bandit pass without suppressions.
The measurement script reruns unittest in process and regenerates
[the sanitized result](wp2-identity-results.json); it never saves credentials,
raw request/response logs, test logs or the temporary database. Accounts,
bootstrap/session/CSRF material and SQLite files are generated inside private
`TemporaryDirectory` instances and discarded. No production app/database module
is imported. HTTP routes exist only in a fresh FastAPI test application.
No runtime dependency was installed. A failed test run or failed measured crypto verification prints failed/unverified
status, exits 1 and refuses to overwrite accepted evidence. Test totals come from
the runner and matrix totals come from completed matrix assertions; failure is
never published as passing qualification.

## Crypto selection and comparison

The selected experiment uses existing Python/OpenSSL PBKDF2-HMAC-SHA256 with
600,000 iterations, a fresh 128-bit random salt and a 256-bit derived key.
The parser accepts only that exact algorithm/cost/salt/digest shape. Unknown,
legacy, corrupt, weakened or attacker-inflated parameters deny before derivation.
Password creation accepts 15–1,024 UTF-8 bytes; login rejects input above
1,024 bytes. Input cost bounds are checked before derivation. Unencodable UTF-8 credentials
(including a JSON lone surrogate) deny without derivation or consuming bootstrap
authority; unsupported reset verifiers likewise deny. No default
password or remotely exposed bootstrap route exists: trusted local harness
code creates a hashed, one-use bootstrap secret valid for 300 seconds, and
an atomic transaction consumes it and creates the first account.

Inspection of `services/report_service.py` found the same 600,000-iteration
PBKDF2-HMAC-SHA256 primitive and bounded modern verifier parser. That report
sharing helper also accepts legacy SHA-256 solely for its existing compatibility
upgrade. **The account experiment accepts no legacy format and imports none of
that service**, avoiding application DB side effects and accidental share-route
authority. Its explicit versioned verifier permits separate account storage
instead of inheriting the report column encoding constraint.

Seven real salt/derivation samples and one successful verification are measured
on Darwin arm64, Python 3.14.3, OpenSSL 3.6.2 and SQLite 3.53.1. Exact elapsed
milliseconds and installed FastAPI/Starlette/httpx/cryptography/Ruff/Bandit
versions are in the result JSON. This is local latency evidence, not capacity
or cross-hardware benchmarking. Tests keep the real work factor even for
unknown-account dummy verification and password-spraying probes.

OWASP recommends 600,000 iterations for
[PBKDF2-HMAC-SHA256](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#pbkdf2),
while favoring Argon2id for new password storage generally. Reusing the already
available supported PBKDF2 primitive with explicit parameters, bounded work and
constant-time digest comparison is adequate for this local feasibility packet;
this is not a FIPS-certified implementation claim or proof of resistance to all
offline attacks. A production reviewer must reassess cost on deployment hardware
and password policy before Story 16.1 ships. No new hashing library is needed to
run this experiment; any later Argon2id preference is a separate reviewed
dependency decision.

Bootstrap, sessions and CSRF material each use 32 CSPRNG bytes (256 bits).
Only SHA-256 hashes persist; plaintext is returned once to the private client.
This exceeds OWASP's minimum custom-token
[entropy guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#session-id-entropy).
High-entropy tokens use a fast hash because they are not guessable passwords.
A nonblocking single derivation slot avoids an authentication queue, with five
attempts/account and twenty global attempts/60 seconds. Unknown accounts use a
valid dummy verifier, and spraying does not create more than twenty limiter rows
per window. Tests exercise saturation and lock refusal. These limits can deny
legitimate logins during an attack; they bound work rather than promise availability.
The single-process global limiter resets on restart, so persistent abuse control,
proxy/IP policy and production concurrency remain downstream work.

## Tested lifecycle and browser boundary

Tests verify bootstrap wrong-secret/one-use/replay/exact-expiry/no-default-account
behavior and that bootstrap secrets do not appear in a SQLite dump. Password
verifiers differ for identical passwords; wrong passwords and corrupt parameters
deny. Session and CSRF plaintext likewise never appears in the dump.

Every successful login creates new session/CSRF material and retires existing
human sessions, ignoring a presented fixation cookie. Explicit rotation retires
the old token. Tokens expire at five idle minutes or one absolute hour even when
refreshed or repeatedly rotated; rotation retains the original authentication
creation time instead of extending that deadline; logout, password reset, account revocation and membership/privilege
changes invalidate old sessions. Privilege changes require fresh authentication
and never upgrade an old token. Wrong audiences, revoked tokens, unknown tokens,
unknown roles/capabilities/scope types and revoked membership deny.

An actual FastAPI `TestClient` at `https://qualify.invalid` checks `__Host-session`
with `HttpOnly`, `Secure`, `SameSite=strict`, `Path=/` and no Domain attribute.
Login and cookie mutations require the fixed trusted Origin; mutations also
require the session-bound CSRF verifier. Missing/wrong CSRF, missing/foreign/null
Origin and unsupported HTTP login deny. Identity comes from the stored session,
not actor/role headers, request bodies or legacy Authorization/share material.
The [Origin/CSRF policy](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
is defense in depth alongside SameSite, not a claim that SameSite alone is enough.
Five tests-first review regressions also cover absolute expiry through repeated
rotations, malformed UTF-8 credentials, failed measurement publication, false measured-crypto verification, and
malformed/non-object/oversized JSON plus non-scalar scoped IDs. Both test routes
parse at most 4,096 streamed request-body bytes and accept only JSON objects;
invalid bodies deny with 400, and invalid scope IDs deny with 403 before SQLite
binding. TLS termination, browser cookie enforcement, reverse proxies and XSS prevention
are not qualified by an in-process HTTP client.

## Exhaustive generic route-capability matrix

Both project and workspace checks require the exact server-owned
`(principal, project, workspace, role)` membership. Each of five audiences × five
roles × two scopes × ten capabilities is exercised for matching scope, a foreign
project, a foreign workspace and absent membership: 500 matching cases plus
1,500 cross/absent denials. Of the matching cases, 54 allow and 446 deny; total
unauthorized expected denials are 1,946 with zero failed assertions.

| Human role | Allowed generic capability operations |
| --- | --- |
| admin | workflow, publish, run, decision, target, enrollment, report, artifact, policy, settings |
| maintainer | workflow, run, decision, report, artifact, policy |
| reviewer | decision, report, artifact, policy |
| contributor | run, report, artifact, policy |
| read-only | report, artifact, policy |

Here report/artifact/policy represent scoped reads; workflow means drafting,
run means requesting an admitted run, target/enrollment/settings mean management,
and publication is admin-only. Cancellation ownership, granular policy mutation
and operation-specific API routes are not silently assigned by these coarse
capabilities; WP6 and Story 16.2 must freeze them. Service, agent, runner and
receiver credentials all deny these **human routes**, even if their synthetic
principal has an admin membership. Their dedicated protocol capabilities remain
separate contracts, not permissions inferred from a human role. Each audience's
credential resolves only within its own audience and expires/revokes independently.

Shared-mode requester self-decision denies; another authorized human can approve.
The authenticated sole account may record `acknowledgement` only in explicitly
selected single-operator mode. A second account prevents that exception; unknown
mode denies. This makes no claim about a physical click or four-eyes review.
Forged headers, missing roles and a legacy share URL do not grant authority in
the disposable app. Protecting actual production linked reports/artifacts and
legacy routes remains Story 16.2 integration evidence, not this packet's credit.

## Remaining limits and handoff

UI validation is not applicable: no React surface is touched. Independent human
security review, full TLS/browser/proxy integration, production lifecycle HTTP
endpoints, reset delivery and abuse/load/restart controls remain unproved.
Enrollment one-use/attempt/lease binding and runner/receiver protocol capabilities
belong to WP3/WP5/WP6 and downstream stories. Root/DB administrators remain trusted;
no secret memory erasure or malicious-host resistance is claimed. Installed
Starlette emits an httpx TestClient deprecation warning; it did not fail the tests
and was recorded without installing the suggested replacement.

WP2 provides bounded executable evidence for the selected design. RFC acceptance,
other mandatory spikes, contract freeze, independent review and readiness rerun
are still required before downstream implementation or overall gate closure.
