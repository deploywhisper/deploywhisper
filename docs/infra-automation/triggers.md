# Signed trigger intake and automation CLI

Story 16.17 adds scoped service/agent requests and a thin authenticated HTTP CLI.
The existing workflow, engine, analysis, target-lock and decision services remain
authoritative. A signed request is permission to request or read assigned work;
it never becomes a human session, workflow publication or approval.

The server fails closed when identity, the protected key manifest, an environment
key, scope membership or an admitted source profile is unavailable. Configure
[identity](identity.md), [project permissions](permissions.md),
[workflow publication](workflows.md) and [collection profiles](collection.md)
before enabling a sender. Production transport uses the configured HTTPS origin.
The explicit loopback HTTP development profile is not production TLS proof.

## Provision a machine principal

A verified human global administrator with project-wide automation administration
and role-management permission may call
`POST /api/v1/infra-automation/triggers/principals`. Human Cookie, Origin and CSRF
rules apply. Use real project/workspace IDs:

```json
{
  "project_id": 100,
  "workspace_id": 100,
  "username": "ci-preflight",
  "principal_type": "service",
  "role": "contributor",
  "reason": "Allow the approved CI preflight scope"
}
```

`principal_type` is `service` or `agent`; role is `contributor` or `read-only`.
The response supplies the principal ID, authentication/membership versions and
restore epoch for the manifest. Copy those actual returned values, not the
synthetic versions in an example. Provisioning creates an enabled nonhuman account
with inert password material and no global-admin flag. It creates no human
session or signing secret. No machine account is created during application
startup. The account count is bounded; exhausted capacity returns a quota error.

Contributor keys can read and request their allowed scope. Read-only keys can
validate/read but cannot start runs. Other machine membership roles are rejected
by this issuer even if an administrator assigns them through another interface.
Account disable, membership/version changes, expiry, key removal/rotation and
restore state invalidate authority; changing a role is not a way to acquire
publication or decision capability.

## Install protected key references

Use a distinct random 32-byte key for each intended credential boundary, encoded
as exactly 64 hexadecimal characters in an operator-managed environment variable.
The API process and sender need the same key bytes. Keep the value out of source,
command arguments, URLs, settings records and logs. Only its environment variable
name belongs in configuration.

Copy and adapt the
[manifest template](../../examples/infra-automation/triggers/key-manifest.example.json).
The file has explicit `version: 1` and at most 32 keys. Each entry binds:

- A key ID and existing service/agent principal.
- One concrete project/workspace and current authentication/membership versions.
- The current restore epoch and a finite UTC expiry.
- Explicit published revision IDs, repository/immutable-commit pairs and origins.
- A `secret_env_ref` naming the environment variable containing the key.

Each revision/source allowlist has 1–32 unique entries. Origins are `webhook`,
`cli` and/or `pull_request`. The example manifest is deliberately expired and
uses synthetic IDs; it cannot stand in for operator configuration.

Install the manifest as a regular single-link mode 0400/0600 file owned by the
application user or root. Use its absolute canonical path, without symlink
components, in a directory that is not group/world writable. The server verifies
the exact file bytes against the configured digest:

```text
DEPLOYWHISPER_TRIGGER_KEYS_PATH=/absolute/operator/trigger-keys.json
DEPLOYWHISPER_TRIGGER_KEYS_SHA256=sha256:<SHA-256 of those exact file bytes>
```

Supply the referenced key variables through the operator's secret facility.
Do not put a secret in the manifest. Install configuration through the deployment's
normal restart/reload procedure; editing a shell environment does not alter an
already-running API process. The file digest and live key bytes are rechecked by
authority resolution. Changes to the effective key definition or bytes invalidate
pending machine effects even if the account version is unchanged.

Human authority stamps retain their original canonical serialization. New machine
stamps separately bind the credential policy and expiry; the key expiry caps the
run window. The durable clock prevents a backwards clock step from reviving
already-stale machine authority. Restore procedures must advance the restore
epoch and reinstall appropriately rotated credentials; do not remove replay
records or reset the clock to recover access.

## Version-1 request and signing representation

The webhook endpoint is exactly:

```text
POST /api/v1/infra-automation/triggers/webhook
Content-Type: application/json
```

Its closed body is a `TriggerRequest`: explicit integer `version: 1`,
`workflow_revision_id`, `project_id`, `workspace_id`, `source`, typed `inputs` and
`idempotency_key`. See the
[schema](../../schemas/infra-automation/trigger-v1.json) and
[webhook template](../../examples/infra-automation/triggers/webhook-request.example.json).
Source has `repository_id`, a lowercase 40-hex immutable `commit_sha`, and
`origin`. Webhook origin is `webhook` or `pull_request`; only `pull_request`
requires `pr_ref`. A PR reference is a bounded plain reference, not a URL or
command. A signed PR claim is an authenticated sender's declared context, not
an independent GitHub-provider attestation.

The revision, scope and source must match the server's current allowlists and the
resolved immutable workflow sources. Signed admission uses collected sources;
it does not accept uploaded artifacts as pinned repository evidence. Unknown
fields, invalid typed inputs, an unpinned/disallowed source or oversized content
schedule nothing. Machine account/role/actor headers do not supply authority.

Four headers carry the signing fields:

```text
X-DeployWhisper-Key-Id: <configured key ID>
X-DeployWhisper-Timestamp: <canonical positive decimal Unix seconds>
X-DeployWhisper-Nonce: <fresh 16–128 character A–Z/a–z/0–9/_/- value>
X-DeployWhisper-Signature: sha256=<64 lowercase hexadecimal characters>
```

Use a fresh cryptographically random nonce, such as `secrets.token_urlsafe(24)`.
The timestamp has no sign, whitespace or leading zeros. The server requires an
aware UTC clock and `abs(server_time - timestamp) < 300` seconds; both exact
300-second boundaries reject.

The bytes authenticated by HMAC-SHA256 are:

1. The literal bytes `b"deploywhisper-signed-trigger-v1\x00"`.
2. Six fields, in order: ASCII key ID, ASCII method (`POST`), ASCII exact path,
   ASCII timestamp, ASCII nonce, and the **32 raw bytes** of SHA-256 of the body.
3. Every field is preceded by its unsigned four-byte big-endian byte length.

The body digest is binary, not hexadecimal text. Sign and send the same body
bytes: parsing/reencoding JSON, changing whitespace or changing escaping changes
the signature input. The repository's `sign_request()` implements this framing;
[the signing recipe](../../examples/infra-automation/triggers/signing_recipe.py)
reuses it. Do not invent another canonical JSON representation.

Signed requests are limited to 128 KiB, JSON depth 16 and bounded integer/scalar
models. Duplicate signing headers, query strings, encoded/path aliases and
unsupported methods reject. Signed routes accept no Cookie or Authorization
credentials. An Origin header is optional for the signed nonbrowser channel;
if supplied it must match the configured origin. Actual host, scheme and identity
profile checks still apply. Human mutation routes continue to require Origin/CSRF.

Constant-time MAC comparison precedes request-body parsing. A valid credential's
nonce is then durably reserved before parsing; invalid JSON and later rejected
admission still consume it. Nonces are retained until `timestamp + 300` and are
bounded to 1,024 per key and 4,096 globally, with shared project/global storage
accounting. Saturation returns a bounded quota error rather than bypassing replay
protection. Known signing-key material is rejected in decoded data and resolved
snapshots instead of being persisted or echoed.

## Replay, status and origin

A nonce protects an individual signed delivery. The idempotency key identifies
the authenticated operation. A repeated nonce rejects; a **fresh nonce over the
same exact operation body** can retrieve its durable original run. Changed bytes
with the same operation identity conflict with HTTP 409. An uncertain response is not
permission to invent a replacement run key. Retain the original file, key ID,
endpoint and idempotency key; make an explicit fresh signed delivery or inspect
authorized status/history. The CLI never retries automatically.

Machine status/list queries are filtered before pagination by the current key,
requester, concrete scope, allowed revisions and source pairs. They do not expose
other keys' or principals' runs. Revoked or unavailable authority cannot be
substituted with caller headers. Existing historical results never create fresh
approval authority.

| Signed POST path under `/api/v1/infra-automation/triggers` | Body |
| --- | --- |
| `/webhook` | `TriggerRequest`, origin `webhook` or `pull_request` |
| `/cli/run` | `TriggerRequest`, origin `cli` |
| `/validate` | Existing `ValidateWorkflowRequest` (`project_id`, concrete `workspace_id`, `definition`) |
| `/status` | `{ "version": 1, "run_id": "..." }` |
| `/list` | `{ "version": 1, "workflow_id": null, "limit": 25, "cursor": null }` |

List limit is 1–100; each response is one bounded page with an explicit cursor.
No query parameters carry unsigned list scope. Machine validation uses the shared
pure validator under read permission; it does not grant draft/publication rights.

Run `origin` records server-selected channel, actual authenticated principal type,
principal ID and requested source pins. It is immutable. A later human decision
has its own attribution and cannot turn a service/agent request into a human
acknowledgement. `cli` means the server's CLI entrypoint, not proof that a specific
binary or physical person sent the request. Older runs without retained origin
remain explicitly unavailable. Requested pins are distinct from successful
collector provenance.

## Authenticated CLI

The existing entrypoint dispatches the new group before legacy role/environment
handling:

```text
python cli.py automation --credential-file FILE [--url EXACT_ORIGIN] [--timeout 15] COMMAND
```

Use a private owner-only regular single-link credential file (mode 0400/0600).
The origin is pinned in that file; `--url` must match it. HTTPS uses normal TLS
verification. HTTP is limited to the explicit loopback development origin.
Redirects and proxy-environment forwarding are disabled. The CLI accepts no raw
signing-key argument and never uses legacy actor/role environment variables as
automation identity.

A signed credential file contains only metadata:

```json
{"kind":"signed","origin":"https://deploywhisper.example","key_id":"example-ci","secret_env_ref":"DEPLOYWHISPER_EXAMPLE_TRIGGER_SECRET"}
```

The named variable holds the 64-hex key in the sender process. A human credential
file contains `kind: "human"`, the exact `origin`, `session_token` and `csrf_token`.
Obtain those through the existing Auth API using the recipe below; do not copy
keys into requests, print session files or commit them.

| Command | Human channel | Signed channel |
| --- | --- | --- |
| `validate --request FILE` | Existing workflow validation API and its draft permission | Signed validation, read permission |
| `run --request FILE` | Existing `RunRequest` through `/cli/runs` | Exact `TriggerRequest` through `/triggers/cli/run` |
| `run --preflight --request FILE` | Existing `PreflightRequest` through `/cli/preflights` | Denied |
| `status RUN_ID` | Existing run detail API | Signed status |
| `list` | Requires `--project-id`; optional `--workspace-id`, `--limit`, `--cursor` | Key scope; optional `--workflow-id`, `--limit`, `--cursor` |
| `decision APPROVAL_ID --request FILE` | Existing exact-bound decision API | Denied |

Normal/signed bodies and responses are bounded to 128 KiB; human preflight request
bodies use the existing 12 MiB wire bound. The timeout is 1–60 seconds. Output is a
versioned JSON envelope: success uses stdout/exit 0; validation/local usage uses
stderr/exit 2; other denials, conflicts, transport failures and interruption use
stderr/exit 1. A network error or interrupt can have an uncertain server outcome.

```sh
# First copy/edit the synthetic examples for actual authorized scope.
python cli.py automation --credential-file /private/operator/human.json validate --request validate.json
python cli.py automation --credential-file /private/operator/human.json run --preflight --request preflight.json
python cli.py automation --credential-file /private/operator/signed.json run --request cli-run.json
python cli.py automation --credential-file /private/operator/signed.json status RUN_ID
python cli.py automation --credential-file /private/operator/signed.json list --limit 25
python cli.py automation --credential-file /private/operator/human.json list --project-id 100 --workspace-id 100 --limit 25
python cli.py automation --credential-file /private/operator/human.json decision APPROVAL_ID --request decision.json
```

The uppercase IDs above are command placeholders. A human decision body must use
the current review packet's `expected_version`, `binding_digest`, explicit
`outcome`, `reason` and any required confirmation phrase. Review the evidence in
the existing UI/API first. Shared mode requires a distinct eligible reviewer;
single-operator acknowledgement remains server-selected. A signed service/agent
credential cannot replace that human credential or decision.

### Obtain a human CLI session

This terminal-only recipe uses the existing login endpoint. It issues no machine
credential and preserves normal login behavior, including revoking previous
sessions for that account. Run it from the repository environment, choose a new
private output path, and provide the password only to the non-echoing prompt.
It makes one login request, refuses redirects/proxies, bounds the response, and
prints no password, Cookie or CSRF value. It is an operator recipe, not an added
CLI login command.

```python
import getpass
import http.cookiejar
import json
import os
from pathlib import Path
import re
import ssl
import sys
import urllib.request
from urllib.parse import urlsplit
import warnings

from cli.automation import _origin

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

fd = -1
target = None
identity = None
try:
    if not sys.stdin.isatty():
        raise ValueError()
    origin = _origin(input("Configured origin: "))
    username = input("Human username: ")
    target = Path(input("New private credential file: ")).expanduser()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.fchmod(fd, 0o600)
    info = os.fstat(fd)
    identity = (info.st_dev, info.st_ino)
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("Password: ")
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect(),
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )
    payload = json.dumps({"username": username, "password": password}).encode()
    if len(payload) > 4096:
        raise ValueError()
    request = urllib.request.Request(
        origin + "/api/v1/auth/login", data=payload, method="POST",
        headers={"Origin": origin, "Content-Type": "application/json"},
    )
    with opener.open(request, timeout=15) as response:
        raw = response.read(8193)
    if len(raw) > 8192:
        raise ValueError()
    data = json.loads(raw)["data"]
    if data["principal"]["principal_type"] != "human" or data["principal"]["credential_audience"] != "human":
        raise ValueError()
    secure = urlsplit(origin).scheme == "https"
    name = "__Host-dw-session" if secure else "dw-local-session"
    cookies = [c for c in jar if c.name == name and c.path == "/" and c.secure == secure]
    if len(cookies) != 1:
        raise ValueError()
    token, csrf = cookies[0].value, data["csrf_token"]
    if any(not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", v) for v in (token, csrf)):
        raise ValueError()
    with os.fdopen(fd, "w") as output:
        fd = -1
        json.dump({"kind": "human", "origin": origin, "session_token": token, "csrf_token": csrf}, output)
        output.flush()
        os.fsync(output.fileno())
    print("Human credential file created.")
except (Exception, KeyboardInterrupt):
    if fd >= 0:
        os.close(fd)
    if target is not None and identity is not None:
        try:
            current = target.lstat()
            if (current.st_dev, current.st_ino) == identity:
                target.unlink()
        except OSError:
            pass
    raise SystemExit("Credential acquisition did not complete.") from None
```

### Send a webhook using the repository signer

For the webhook/PR channel, import `build_headers` from the signing recipe. Load
the signed credential metadata and exact body using the same CLI helpers, then
make one bounded request through its transport. These private helpers are
version-matched repository examples, not a separate SDK contract:

```python
from cli.automation import _credentials, _exchange, _read_file
import runpy

recipe = runpy.run_path("examples/infra-automation/triggers/signing_recipe.py")

credential = _credentials("/private/operator/signed.json")
if credential.kind != "signed":
    raise ValueError("A signed credential is required.")
body = _read_file("webhook-request.json", 131072)
headers = recipe["build_headers"](
    key_id=credential.key_id, secret_env_ref=credential.secret_env_ref, body=body
)
status, response_bytes = _exchange(
    credential.origin, "POST", recipe["WEBHOOK_PATH"], headers, body, 15
)
# Handle the bounded versioned envelope; keep headers and credentials out of logs.
```

## Proof boundary

The sender templates and recipes are setup guidance, not executed acceptance.
Record real commands and results in the story verification directory. Synthetic
ASGI/HTTP, source, collector, custody or receiver fixtures prove only their named
contracts. They do not establish production TLS, real isolated collection or
deployment support. The separate Story 16.15 positive HTTPS/real-runner browser
gates remain open unless their own evidence closes them. Story 16.17 adds no
apply/destroy/remediation capability, and advisory reports retain
`should_block=False`.
