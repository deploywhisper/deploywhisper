# Story 16.11 completion evidence — 2026-11-03

Follow-up branch: `feature/16-11-receiver-outcome-completion`, based on merged
PR207 at `d7d8fa1`. This record supersedes the earlier adapter-only missing-live-
configuration pause. The owner authorized the implementation choices, dedicated
harmless sandbox and skill correction; no acceptance requirement was removed.

## Implemented scope

- **Packet1 / AC1,4:** actual isolated GitHub adapter with protected reviewed ref,
  pinned API2026-03-10, distinct source/workflow identity, durable acceptance and
  bounded correlated observations. Large Connection-close responses retain their
  deadline-reader socket lifetime.
- **Packet2 / AC2,3,5:** receiver-only HTTPS bootstrap/consume/status/admission/
  signed outcome channel; durable local operation ledger, original receipt
  recovery, action fence and exact callback acknowledgement recovery.
- **Packet3 / AC2,3,5:** actual owner-restricted synthetic saved bytes, no-follow
  descriptor verification, exclusive publication, raw digest/source/expiry checks,
  retained bytes through the effect and actual Linux UID isolation.
- **Packet4 / AC3–5:** immutable replay fences/carrier sidecars in migration036,
  current authority/clock checks, sticky uncertainty, bounded poll reconciliation,
  guarded parent/sibling completion and lock retention.
- **Packet5 / AC1,4–6:** scoped run outcome facts, distinct acceptance/observation/
  verified completion/unknown, honest cancellation, manual CAS reconciliation,
  no blind resend, ambiguity/remount protection and revoked-access clearing.

Frozen receiver-v1 messages, workflow-v2 snapshots and report-v2 contracts remain
unchanged. Generated frontend OpenAPI types were refreshed. No dependencies were
added. Real collector/provider deployment admission remains later-story work;
this story qualifies its seeded synthetic reference receiver profile.

## Live GitHub qualification

Dedicated sandbox: `deploywhisper/receiver-smoke-consumer`; main is protected with
admin enforcement, required PRs, no force pushes and no deletion. No existing
operator repository or infrastructure was used. Workflows are retained under
[sandbox](sandbox/README.md), pinned to reviewed official action revisions.

- GET-only preflight: [41668218369](https://github.com/deploywhisper/receiver-smoke-consumer/actions/runs/41668218369), passed.
- Qualification: [41668709128](https://github.com/deploywhisper/receiver-smoke-consumer/actions/runs/41668709128), passed.
- Correlated harmless receiver: [41668758592](https://github.com/deploywhisper/receiver-smoke-consumer/actions/runs/41668758592), passed.
- App revision: `75324acfc8a6c1e7aa5116ae908539ea4299b780`.
- Reviewed receiver workflow revision: `c490f8549d567ddde5598cd71bba87bc3d912579`;
  repository ID1444474458; workflow ID405886686.
- Actual dispatch returned HTTP200 with matching ID/API/web URLs. Workflow inputs
  contain only operation ID and binding digest. A separately generated synthetic
  source SHA stays distinct from the workflow revision.
- Credential was an ephemeral repository-scoped Actions GITHUB_TOKEN, explicitly
  passed under the dedicated dispatch reference. No token was requested in chat,
  serialized or stored in this repository. Exactly one harmless receiver run was
  observed; no deployment or grant consumption is claimed from this run.

Screened acceptance/observation DTOs are in [live-github-proof.json](live-github-proof.json).
A first invocation with a shortened app SHA failed its input guard before checkout.
The initial actual preflight failed on its first metadata GET; screened read-only
stage diagnostics established `dispatch_may_have_sent:false`, and no receiver runs
existed. The transport reader fix resolved that failure before the explicit one
harmless dispatch. No uncertain POST was automatically retried.

## Python, migration and static validation

Final broad commands ran outside the process-inspection sandbox with the test-
process-only `LLM_API_BASE=http://127.0.0.1:1` override. This permits real process
termination checks while keeping unmocked narrative calls on the unavailable-
provider path. No persistent operator configuration changed.

- `./.venv/bin/python -m unittest discover -q` — 1,546 tests, 3 expected skips,
  exit0, 746.408 seconds.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`
  — 716 passed, 1 skipped, 2,316 subtests, 305.19 seconds.
- `bash scripts/ci-local.sh` — exit0; 2,993 tests across all10 directories, 3 expected skips. Directory totals: analysis69, API327, CLI102, docs51, infra288, infra-automation783, LLM76, models22, parsers43, services1,232. The security gate, dependency consistency, compileall, skill matrix and prompt-injection lane also passed.
- Focused transport/adapter/qualifier: 60 unittest tests passed after the live
  response-reader fix, including the red-before-green 262,144-byte regression.
- Current migration restart/unversioned adoption/partial guard/downgrade: 4 passed.
  Historical six-file migration regression: 57 passed, 72 subtests. Prior direct
  revision035 tests and immutable SQL guard preservation remain covered.
- Real ReferenceReceiver→HTTPS TestClient→HandoffService tests cover a counted
  synthetic action, original receipt, duplicate denial, callback response loss,
  sticky uncertainty and parent reconciliation with local prerequisites/siblings.
- Scoped mypy: 6 new/touched modules passed. Focused Bandit medium/high: passed.
- Repository `ruff check .`, `ruff format --check .`: passed, 494 files formatted.
- `git diff --check`: passed before final publication records; rechecked at commit.
- Skill validator and independent workflow forward-test: passed.

The initial broad run exposed stale OpenAPI/migration-head assertions; those
fixtures were corrected and the final runs above use the corrected contracts.
Some broad processes began before the narrow transport reader correction; its
latest source has separate host and Linux focused verification below.

## Linux ARM64 custody and recovery

The actual production Python3.11 image was run read-only, without network, with
private disposable /tmp and current test/source mounts:

`docker run --rm --network none --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev,size=256m --user root ... deploywhisper-story16-11:ui-proof python -m unittest tests.test_infra_automation.test_target_transport tests.test_infra_automation.test_github_adapter tests.test_infra_automation.test_receiver_custody tests.test_infra_automation.test_receiver_runtime -q`

Result: **65 tests passed**, 11.022 seconds. Actual child UID10002 publishes and
verifies the original custody bytes; UID10003 with cleared supplementary groups
gets kernel PermissionError. Other cases exercise real symlinks/hardlinks,
replacement/overwrite/permissions/source/digest/expiry denial, six real process-
death boundaries, process races and retained callback acknowledgement. Local
process crash proof does not claim host-power-loss durability.

## Composed browser and screenshots

`docker compose -f scripts/compose-story16-11.yaml up -d --build` built the Vite
production assets and actual FastAPI runtime. The guarded nonroot tmpfs fixture
seeded11 scoped synthetic cases and verified all child service reads before
starting. Health8080 passed. No Vite server, production DB or route-intercept-
only happy-path evidence was used.

- `npm run ui:typecheck` — passed.
- `npm run ui:test` — 268 tests and 2 adapter checks passed.
- `npm run ui:build` — passed.
- `OPENAPI_URL=/tmp/story16-11-openapi.json npm run ui:gen-api`, then typecheck — passed.
- `BASE_URL=http://localhost:8080 OUTCOME_UI_FIXTURE=/tmp/story16-11-outcome-ui-fixture.json npm run test:ui-review -- frontend/e2e/infra-automation-outcomes.spec.ts`
  — **6 passed, 1.1 minutes**. Includes persisted outcome matrix, actual reconcile,
  definite server422 correction, committed response loss/equal-version blocking,
  in-flight control unmount/remount and actual principal revocation (GET401).
- Keyboard and axe checks on outcome and permanent report journeys at desktop and
  760px: **zero violations in the checked journeys**. Bounds/screenshots also
  include390px. Scope is the owning authenticated fixture; generic anonymous or
  other-story fixture suites are not interchangeable with it.
- Fifteen retained [screenshots](screenshots/): unknown, verified success,
  cancellation, reconciled and permanent report at1440/760/390.
- Final [visual verdict](visual-verdict.json): **95/pass**, threshold90, no remaining
  visual differences. No approved colors/fonts/spacing/radius values changed.

Browser first attempts exposed and fixed malformed disposable fixture records,
scoped read argument omission, narrow intrinsic width, a preexisting nested report
main and Low contrast. No axe violation was suppressed. The fixture resets only
its own synthetic setup login bucket; production limits are unchanged.

The final disposable stack was removed, original local app container restarted
without touching its data volume, and the private host credential fixture deleted.

## Evidence limits and next work

GitHub proof establishes transport acceptance/observation; local Linux and HTTPS
corpus separately establish this story's synthetic receiver/custody profile.
Neither is a claim of real infrastructure apply, real collected-plan admission,
universal production support or host-power-loss safety. Those later owning
stories remain unchanged. All findings in the owning scope have been addressed;
see [completion review](completion-review.md).


## Final publication checks

Repository-wide constructor/consumer search covered CallbackEnvelope,
BootstrapRequest, ConsumeRequest, ReconcileRequest, external-fact rows,
ReferenceReceiver and ProtectedCustody (18 direct Python locations); the exact
CI shard and all-directory CI exercised the consumers. Existing test discovery
already includes the infra-automation directory; no registration change needed.
The generated API types were regenerated from the current app schema and the
final frontend typecheck/build passed again. Original local app health returned
HTTP200 after cleanup. The skill validator passed, as did final repository Ruff
lint/format and diff checks. The generated Bandit report is kept outside Git.

The owner requested completion of all remaining work after the partial PR207.
The completion PR groups backend/API/migration and UI changes explicitly, carries
the backend-for-UI scope in its description, and includes the independently tested
component boundaries and screenshot evidence. No automatic application merge or
release is requested by this work.
