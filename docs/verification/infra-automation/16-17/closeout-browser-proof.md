# Story 16.17 publication closeout browser proof — 2026-11-09

**Passed:** one composed Chromium journey, **28.7 seconds** (29.7 seconds total
runner time), twelve 1440×1000 / 760×1000 screenshots, and **zero critical or
serious axe violations** across twelve scans. Native keyboard login, Tab and
Shift+Tab traversal, arrow-key tab selection, and keyboard activation of history
and run-detail navigation passed. The visual comparison against the prior
accepted proof is **94/100, pass**; no visual refinements were made.

- [Structured proof, exact source hashes, image identity, screenshot hashes and cleanup](closeout-browser-proof.json)
- [Sanitized Playwright output](closeout-browser-output.txt)
- [Visual verdict](closeout-visual-verdict.json)
- [Fresh screenshots](closeout-screenshots/)
- [Production image build](closeout-build.txt)
- [Compose startup](closeout-compose-up.txt) / [cleanup](closeout-compose-down.txt)

## Exact execution

The current production runtime image was built **before** stopping the original
app. Image: `sha256:751f927ce9edcc9147aef6948f57da7192d4186e244b2c638a3722dd18cddacf`.
This rerun follows the CodeQL-driven explicit TLS minimum correction.
The working tree included the current CLI fix on top of
`165a420c40c922d1d216580b7f400e16f77cb7ea`, including the explicit CLI
TLS 1.2 minimum; the structured proof pins the exact
source bytes rather than claiming that this base commit alone contains the fixes.
The earlier passing proof metadata is retained under `previous_proof` in the
JSON; these current screenshots and log hashes supersede its captures.
This HTTP browser lane does not itself prove TLS negotiation; the separate
CLI TLS tests own that validation.
The image uses Python 3.11.17; the host used Node 24.7.0, Playwright 1.63.0 and
Docker 29.1.3.

```sh
docker compose -f scripts/compose-story16-17.yaml build
# Record and stop the exact healthy original container only after build succeeds.
docker compose -f scripts/compose-story16-17.yaml up -d --no-build
# Wait for http://localhost:8080/api/v1/health -> 200.
# Copy only the browser fixture to an owner-only temporary directory/file (0700/0600).
BASE_URL=http://localhost:8080 TRIGGER_UI_CONTAINER=deploywhisper-story16-17-deploywhisper-1 TRIGGER_UI_FIXTURE=<private0600> npm run test:ui-review -- infra-automation-triggers.spec.ts
docker compose -f scripts/compose-story16-17.yaml down
# Restart the exact original container and verify Docker health plus HTTP200.
```

The unchanged npm command ran from an isolated temporary command workspace with
a package.json copy and a symlink to the checkout's frontend. This redirected the
test's fixed relative screenshot output without changing product/test source or
overwriting historical proof. Fresh captures were copied to `closeout-screenshots`;
the private command workspace and credential fixture were then removed. The
browser spec disables traces, videos and automatic failure screenshots around
credential entry. Public logs contain no fixture contents or signing credentials. Trailing whitespace
and extra terminal blank lines were normalized for git; raw and normalized log
hashes are retained in the structured proof.

## What passed

FastAPI served the production static React build at the composed root SPA URLs.
The guarded nonroot fixture used a tmpfs database and only synthetic accounts,
workflows, source pins and key material. The test performed actual HTTP requests
through the shipped CLI dispatcher and independent HMAC sender, then exercised
the browser UI using authenticated human credentials.

The manual-human and human-CLI uploaded preflights both succeeded and retained
one report each. Agent-CLI, service-webhook and service-PR requests passed signed
admission and retained their exact machine attribution. Run history and all five
detail views displayed channel independently from principal type and ID. Machine
views retained public signing-key ID and exact requested repository, immutable
commit and profile digest; the PR view retained its declared PR reference.
Reading a machine-origin run as a human did not relabel its origin or create a
human acknowledgement. Forged role/actor headers did not change the authenticated
service principal. Requested-source copy continued to distinguish request pins
from collected provenance or approval.

The collection profile is structural fixture metadata only. No runner or human
approval provider was installed. Collected requests therefore fail closed when
remote assignment is unavailable. This proof covers actual signed admission,
origin retention and presentation; it does **not** qualify production TLS,
successful isolated collection, real repository custody, approval-material
integration or external deployment. The separate Story 16.15 HTTPS/real-runner
browser gates remain unchanged.

## Cleanup and restoration

The exact pre-existing application container was
`5970d092f40105574b40ba43996b4af1b770a85697f085318d1fb4360c83b31f`.
It was HTTP200 and Docker-healthy before the lane, stopped only after successful
build, then restarted after disposable Compose cleanup. Final inspection
confirmed the same full container ID running, Docker health `healthy`, and
`http://localhost:8080/api/v1/health` HTTP200.

Disposable Compose `down` exited0 and no containers remained in that project.
The private host directory and fixture were removed. The tmpfs database and
container-held synthetic secrets disappeared with the disposable container.
Original data was never mounted into the proof lane. Historical screenshots and
product/test source remained unchanged by this verification task.

## Public log normalization

Before recording final hashes, public logs had trailing whitespace removed per
line, trailing empty lines removed, and one final newline retained. The JSON
records both raw command-output SHA-256 values and the final normalized log
SHA-256 values. Test outcomes and messages were not changed.
