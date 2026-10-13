# Local human identity — v1.5.0 / Story 16.1

Named local accounts provide verified human identity for later infrastructure
automation. Existing project/report behavior is unchanged. A verified account or
administrator flag alone does not grant project membership, workflow publication,
approval or handoff authority: scoped authorization belongs to Story 16.2 and the
browser account entry to Story 16.7. No bootstrap or recovery HTTP endpoint exists.

## Persistence and upgrade contract

Normal startup upgrades Alembic revision `028_add_narrative_guidance_payload` to
`029_add_identity_lifecycle`. This adds three tables: `identity_accounts`
(unique username, salted password verifier, principal type, enabled/admin flags,
authentication version and creation/revocation timestamps), `identity_sessions`
(unique token hash, CSRF hash, account foreign key, audience, origin/profile,
authentication version and lifecycle timestamps), and `identity_credentials`
(unique token hash, setup/recovery purpose, optional account foreign key and
creation/expiry/consumption timestamps). IDs are opaque; timestamps represent UTC.
The existing `app_settings` table holds one bounded, nonsecret
`identity.login_limits.v1` record. No workflow, membership or runner tables are
created by this migration.

Fresh databases, upgrades, downgrade/reupgrade and complete unversioned-schema
recognition are covered by migration tests. An incomplete identity schema fails
startup for operator repair rather than silently recreating account authority.
Before an intentional rollback, stop the application and preserve a protected
database backup. Downgrading to revision 028 removes all three identity tables
and the limiter record; re-upgrading creates an empty identity store requiring
fresh bootstrap. Never treat a database restore as a session-revocation mechanism:
restoring a snapshot can restore its sessions. Coordinated restore-epoch handling
and integrated restore qualification belong to Story 16.18.

## First administrator

Run the CLI on the trusted application host, as the operating-system account
that owns the application database. It uses `DATABASE_URL` and initializes the
normal schema through `init_db()`. No default account or password is installed.
HTTP identity may remain disabled while using these local commands.

```sh
umask 077
mkdir -m 700 identity-private
./.venv/bin/python -m cli.identity setup --output identity-private/setup
./.venv/bin/python -m cli.identity bootstrap --username operator \
  --credential-file identity-private/setup
```

The second command prompts for a password with terminal echo disabled. Passwords
must contain 15–1,024 UTF-8 bytes. No password or token belongs in command
arguments, shell history, environment variables, URLs, logs or this repository.
Use a private directory outside the checkout for real operator evidence; the
relative directory above is illustrative. Remove consumed credential files using
your local secret-retention procedure.

For unattended local use, `bootstrap` and `recover` also accept
`--password-file /private/path/password`, or `--password-file -` to read a
protected pipe or redirected private file owned by the current operating-system
user. Obtain the pipe from a trusted secret provider; do not construct it with a
literal secret in a shell command. Stdin must expose a real descriptor: anonymous
pipes are accepted, while redirected regular files and named FIFOs require mode
`0600` or `0400`. Terminal stdin, foreign owners, public files/FIFOs, sockets and
other descriptor types are rejected for `-`. The default prompt requires a
terminal and fails if secure no-echo input is unavailable. Input is bounded and
accepts one UTF-8 line with an optional LF/CRLF terminator; password spaces are
preserved.

Named input files must be regular files owned by the current operating-system user,
with exactly mode `0600` or `0400`. Symlinks, directories, FIFOs, foreign owners,
and group/other permissions are rejected using descriptor checks. Generated
credentials go only into a newly created `0600` file: existing files and symlinks
are never overwritten. An unavailable output destination is rejected before
issuing or superseding evidence. The commands print only a generic completion or
failure message, with exit status 0 or 1. `--help` prints command usage. Generic
errors intentionally omit argument values, file paths and database exceptions.

Setup evidence has 256 bits of randomness, expires after 300 seconds, and is
consumed in the same transaction as first-account creation. Concurrent consumers
cannot create two first administrators. Issuing new setup evidence supersedes
earlier unused setup evidence; setup issuance is denied once an account exists.

## Secured recovery

Only an operator with trusted host/database access may issue recovery evidence.
This is break-glass account recovery, not remote password reset or an approval
bypass. Root and database administrators are inside the trust boundary: a host
compromise defeats local account protections.

```sh
./.venv/bin/python -m cli.identity recovery-issue --username operator \
  --output identity-private/recovery
./.venv/bin/python -m cli.identity recover \
  --credential-file identity-private/recovery
```

Recovery requires possession of the generated evidence, which is one-use and
expires after 300 seconds. New recovery evidence supersedes unused evidence for
that account. Successful recovery changes the password, enables the account,
increments its authentication version and revokes every previous session in one
transaction. It does not change the account's administrator status or create
project/approval permissions. A failed password or evidence validation does not
consume valid recovery evidence. There is no email or remote recovery channel.

Keep evidence in protected local custody. Only hashes of setup/recovery/session
and CSRF tokens are stored. Password verifiers use PBKDF2-HMAC-SHA256 with 600,000
iterations, a random 128-bit salt and a 256-bit derived key; legacy and malformed
verifiers deny. If writing newly issued evidence fails, the CLI removes its
new output file where possible. Issue fresh evidence to a working destination;
there is no recovery of the plaintext token from the database.

## HTTP profiles and trusted transport

`DEPLOYWHISPER_IDENTITY_PROFILE` defaults to `disabled`. Identity operations fail
closed until a supported profile and `DEPLOYWHISPER_IDENTITY_ORIGIN` are set.
Legacy routes remain available under their existing contracts.

| Profile | Example origin | Session cookie |
| --- | --- | --- |
| `disabled` | unset | No login/session authority |
| `https` | `https://deploywhisper.example` | `__Host-dw-session`, Secure |
| `local-development` | `http://127.0.0.1:8080` | `dw-local-session`, HTTP allowed |

Origins must be exact scheme/host/port strings, with **no trailing slash**, path,
userinfo, query or fragment. The local-development origin must use HTTP and host
`localhost`, `127.0.0.1` or `[::1]`; this is an explicit local exception. Both
cookies have `HttpOnly`, `SameSite=Strict`, `Path=/` and no Domain. They are browser
session cookies; server expiry remains authoritative. Sessions persist their
origin and profile. Changing either invalidates their use. Local-development
sessions report `production_eligible=false` and cannot be reused as HTTPS
production sessions. Production eligibility is a transport property, not a
workflow authorization grant.

Serve production identity over direct TLS, or a strictly trusted reverse proxy.
For direct TLS, run the existing ASGI app with your protected TLS key and
certificate paths, for example:

```sh
DEPLOYWHISPER_IDENTITY_PROFILE=https \
DEPLOYWHISPER_IDENTITY_ORIGIN=https://deploywhisper.example:8443 \
./.venv/bin/python -m uvicorn app:fastapi_app --host 127.0.0.1 --port 8443 \
  --no-proxy-headers --ssl-keyfile /private/tls/key.pem \
  --ssl-certfile /private/tls/certificate.pem
```

For TLS termination at a proxy, restrict backend reachability to that proxy,
preserve the configured external Host (including its port), and have the proxy
replace caller forwarding headers with its verified transport information. Enable
Uvicorn proxy processing only for the proxy's exact trusted address through
`--proxy-headers --forwarded-allow-ips <trusted-proxy-address>`. Never use wildcard
forwarding trust. Auth checks use the ASGI effective scheme and Host; they do not
interpret arbitrary `X-Forwarded-*` headers themselves. A proxy that does not
establish the correct trusted effective HTTPS scheme fails the HTTPS check.
`python app.py` explicitly disables proxy-header processing and serves HTTP; it
is appropriate for the explicit local profile, not proof of production TLS
configuration.

## API contract

All endpoints below use `/api/v1/auth`. The generated contract is available at
`/api/v1/openapi.json`. Identity responses send `Cache-Control: no-store`,
`Pragma: no-cache`, and a nonsecret `X-Correlation-ID`.

| Method and path | Request | Successful `data` |
| --- | --- | --- |
| `POST /login` | JSON `{username, password, audience?: "human"}` | `{principal, csrf_token}` plus session cookie |
| `GET /session` | Session cookie | Verified principal |
| `POST /session/rotate` | Cookie, Origin and CSRF header | `{principal, csrf_token}` plus replacement cookie |
| `POST /logout` | Cookie, Origin and CSRF header | `{logged_out: true}` plus cookie deletion |
| `POST /accounts` | Administrator cookie, Origin, CSRF; JSON `{username, password, is_admin?: false}` | Account |
| `POST /accounts/{principal_id}/revoke` | Administrator cookie, Origin and CSRF | Disabled account |

Successful envelopes are `{data, meta: {app, version, correlation_id}}`. Account
fields are `principal_id`, `username`, `principal_type`, `is_admin`, `enabled`,
and `authentication_version`. A verified principal adds `credential_audience`,
`session_id`, `expires_at` (UTC timestamp), `security_profile`, and
`production_eligible`. Opaque session credentials are delivered only in cookies;
`session_id` is a nonsecret record identifier. CSRF material is returned in the
**JSON `data.csrf_token` field**, and must be sent as `X-CSRF-Token` on subsequent
mutations. Refresh it from each login or rotation response; it is never a bearer
credential.

Login and all mutations require one exact matching Origin; session reads permit
no Origin or one matching Origin. All operations require the configured effective
scheme/host/port. Mutations other than login require a valid session and its CSRF
token. Cross-origin, missing/incorrect CSRF and duplicate security headers/cookies
deny. Bearer/API/service/agent/runner/receiver Authorization credentials are not
accepted on human endpoints, even alongside a valid cookie. Caller actor and role
headers confer no authority. Login request bodies cannot request roles or a
nonhuman audience.

Login and account-creation bodies require `application/json` and at most 4,096
streamed bytes, independently of Content-Length. They are closed JSON objects:
duplicate/unknown fields, coercions, malformed UTF-8 and invalid scalar values
deny. Username limits are 1–128 UTF-8 bytes; passwords are bounded at 1,024 bytes
and new account passwords additionally require at least 15 bytes.

Errors use `{error: {code, message: "Authentication denied.", details:
{retryable, correlation_id}}}`. Malformed bodies return 400; failed/expired human
credentials return 401; profile/Origin/CSRF/admin denials return 403; throttling
returns 429; unavailable database authority returns 503. Account existence and
secret inputs are omitted. `retryable` is true for 429/503; re-read the current
state after recovery rather than blindly replaying a mutation.

## Session lifecycle and operational bounds

Each login issues fresh 256-bit session and CSRF tokens and revokes that account's
previous sessions. Session fixation cookies are not inherited. Sessions expire
after 300 idle seconds or 3,600 absolute seconds. Rotation revokes the prior token
and preserves the original absolute deadline. Logout, account revocation and
secured recovery invalidate old tokens. Account creation/revocation requires a
currently enabled administrator session; headers cannot assert that status.

Login limits are five attempts per username and twenty globally per fixed
60-second window, persisted in the database across restarts/workers. The bounded
record hashes usernames and admits at most twenty username slots per window.
Unknown accounts undergo dummy verifier work. One nonblocking derivation slot
per application process bounds password work; concurrent saturation fails closed.
The supported deployment is one application process with local SQLite. Separate
process tests prove transaction and restart boundaries; they do not qualify
multiworker or high-availability production. Limits can temporarily deny legitimate users during
an attack. Malformed login bodies fail before password derivation and count
toward the same persisted global budget plus a shared anonymous bucket of five
attempts per minute; valid login requests are not double-counted. Local setup and
recovery operations rely on trusted host custody, finite evidence lifetimes,
one-use consumption and the same per-process derivation bound, not a remote
password-reset rate limiter.

This backend-only slice has no rendered UI changes: **UI validation not
applicable**. Full production browser/TLS/proxy deployment validation and later
scope-aware automation integration remain separate deployment/story evidence.

## Owned authorization and regression matrix

The executable contracts are in `tests/test_services/test_identity_service.py`,
`tests/test_api/test_auth.py`, `tests/test_cli/test_identity.py`, and
`tests/test_infra/test_identity_migration.py`.

| Presented authority or condition | Owned result |
| --- | --- |
| Enabled human account, correct password, configured origin | New session and CSRF; earlier sessions revoked |
| Valid human session, administrator | Account creation/revocation allowed with matching Origin/CSRF |
| Valid human session, nonadministrator, forged admin headers | Administration denied |
| Service, agent, runner or receiver principal | Human login denied, independently for all four types |
| Service, agent, runner or receiver session audience | Human resolution denied, independently for all four audiences |
| Nonhuman login audience or Authorization credential, even alongside cookie | Human HTTP operation denied |
| Caller actor/role headers without a session | No human identity |
| Missing/wrong/duplicate CSRF, foreign/null/missing Origin on mutation | No mutation or idle-time extension |
| Exact idle/absolute expiry, revoked/version-stale/logout/recovered session | Old session denied |
| Explicit local HTTP session copied into HTTPS cookie | Denied; origin/profile binding is persisted |
| Malformed, oversized, duplicate-field or nonobject body | Generic bounded error; repeated login failures throttled |
| Concurrent setup consumers in separate processes | Exactly one first administrator |
| Expired, superseded, wrong or replayed setup/recovery evidence | No account mutation |
| Fresh, upgrade, downgrade/reupgrade or incomplete identity schema | Expected migration; incomplete authority fails closed |

Project/workspace/object permission matrices and real machine enrollment are not
provided by this identity slice. The tests above establish the prerequisite
human boundary; Story 16.2 owns scoped authorization and later stories own
publication, approvals, runner and receiver operations.
