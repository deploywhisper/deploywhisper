# Story 16.17 composed origin proof

The final real Compose journey passed: **1 test, 27.7 seconds**, with zero axe critical/serious violations at 1440px and 760px. Twelve screenshots cover history and manual-human, CLI-human, CLI-agent, signed-service webhook and signed-service PR detail views. Visual inspection against the established InfraFlow screens scored **94/100, pass**. See [the verdict](visual-verdict.json), [screenshots](screenshots.json) and [source/image hashes](browser-source.json).

## Executed boundary

The production static React build is served by FastAPI at `http://localhost:8080`. The fixture requires a nonroot container, explicit disposable flags and a tmpfs application database. It creates synthetic human identities using the existing guarded seeder, then publishes workflows and provisions actual service/agent identities through the real authorized services. Signing manifests contain environment references; synthetic secrets and credential files remain in private container custody and are never copied into public artifacts.

After health succeeds, a separate process runs the shipped `python -m cli.analyze automation` dispatcher over actual HTTP. The human CLI submits an uploaded preflight; the agent CLI submits a signed pinned-source request. An independent HTTP sender performs actual HMAC service webhook and PR-origin requests, including forged actor/role headers that do not change the stored service principal. The browser signs in using native keyboard traversal and submits another real manual uploaded preflight. Both uploaded runs finish and persist reports.

The browser navigates the real run history and all five run details using Tab/Shift+Tab and the tabs' arrow-key behavior. It verifies channel independently from actual principal type/ID, public key ID and PR reference, plus exact requested repository/commit/profile pins. Human reading does not relabel machine origin. Source details explicitly distinguish requested pins from collected provenance or approval.

The collection profile is **structural fixture metadata only**. No runner is enrolled, so collected requests are admitted and then fail closed when remote assignment is unavailable. This proves signed intake and durable origin visibility, not successful collection, production TLS, real repository custody or deployment. No human approval provider is installed in this browser lane; the backend's separate signed-run/human-decision tests cover that boundary. Story16.15's positive HTTPS/real-runner browser gates remain open.

## Commands and versions

```sh
docker compose -f scripts/compose-story16-17.yaml build
docker compose -f scripts/compose-story16-17.yaml up -d --build
# Wait for GET http://localhost:8080/api/v1/health -> 200.
# Copy /tmp/trigger-ui-browser-fixture.json to a private host directory, mode0600.
BASE_URL=http://localhost:8080 TRIGGER_UI_CONTAINER=deploywhisper-story16-17-deploywhisper-1 TRIGGER_UI_FIXTURE=<private-file> npm run test:ui-review -- infra-automation-triggers.spec.ts
docker compose -f scripts/compose-story16-17.yaml down
```

The test invokes `docker exec … python /tmp/trigger_ui_fixture.py --exercise` to run the actual CLI/signed sender and reads only public run results. Production Python3.11.17, Playwright1.63.0, Docker29.1.3 and host Node24.7.0 were used. The source/image record pins the exact tested files. The [final command output](browser-verified.txt) is retained.

## Failures and visual iteration

Initial fixture invocation used checkout-only `cli.py`, which the runtime image does not ship. It was corrected to the shipped module dispatcher; no Dockerfile or product change was needed. Later test-only repairs used arrow navigation for the inactive roving tab and waited for root navigation to settle before selecting the Runs tab. These failures are preserved alongside this record; logs normalize trailing whitespace only and never print private credential contents.

Initial visual inspection scored87 because full principal IDs made narrow history rows excessively tall. The UI owner kept the history summary compact, retaining exact identity in run details. The initial screenshot and verdict are preserved. A successful26.2-second run was repeated solely to use viewport captures instead of full-page images with an empty internal-scroll tail; no product code changed between those two passing runs.

The exact pre-existing application container was recorded, stopped only after build, and restored healthy after every attempt. Disposable Compose resources and private host credential directories were removed. No operator data was mounted or altered by this proof.
