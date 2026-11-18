# Story17.3 verification packet

Scope:plan-directed identity extraction, static bounded one-hop collection,
fail-safe degradation and additive budget serialization. Baseline:`64ef0fa`;
branch:`feature/17-3-plan-directed-reflection`. No dependency installation or
live provider reads were performed. Production profile qualification stays17.9.

## Implementation and acceptance proof

| AC | Implementation/proof |
| --- | --- |
| AC1 | `cloud/reflection.py`:recursive recorded-prior thenbefore extraction; four qualified Terraform/OpenTofu exports and noSDK/no-call regression |
| AC2 | Pure creates produce `no_live_counterpart` and zeroSDK calls; replacements/missingbefore remain distinct |
| AC3 | Authoritative-original manifest regeneration rejects broadened selectors, coherent replacement resource sets, target replay and deliberately enumerating connector requests before construction |
| AC4 | Static catalog one-hop templates and bounded selected endpoint facts; no response-driven follow-up requests; bounds/reasons stored with facts |
| AC5 | Provider failure matrix, explicitinsufficiency understrongcontext, cachedstale recomputation and monotonic severity/confidence floors; preciseIAM actions onlyforconfirmeddenials |
| AC6 | Separate reservations/actualSDK invocation accounting; sharedregionlimits/cancel/deadlines; real service outcomes round-trip through sharedpipeline,HTTP,CLI and agent JSON; legacyNonefieldabsence |

Retainedsnapshot-v1 JSON/digests and existingreference-provider collect contract
are unchanged. A separate typed outcome carries operational budgets. The SDK-free
default still cannot construct a provider without trusted server composition.
No new HTTP route, CLI flag, UI surface, schema version or credential store ships.

## Red/green and independent review

- Reflection packets:`/tmp/story17-3-reflection-packet3{1,2,3}-red.log`, then22tests passed. All25realistic resource families render42frozen capabilities.
- Collection/service first failing imports and behavior:`/tmp/story17-3-{collection-red,service-collection-red}.log`; added fault, shared-region, capacity, identity and retained-authorization tests.
- Absolute deadline/finalization regressions:`/tmp/story17-3-service-deadline-red.log`; pre-work consumes the original deadline and reported elapsed includes retention/commit.
- Degradation hook red missing-module check:`/tmp/story17-3-degradation-red.log`; final8tests coverall5fault classes acrossall4severity levels plus retention-metadata and scope checks.
- Sharedpipeline/API/CLI red tests:`/tmp/story17-3-budget-{core,surfaces}-red.log`;9tests+18subtests passed. Existingagentfixture AttributeError reproduced and fixed with the optional-field fallback; existing compatibility batch then138passed+67subtests.
- Independent Packet3.7 review found twoP1 projection leaks: lowercase ECS tag values/echoes and Lambda dynamic tag names. Implementer added failing worker/collector/retention regressions, normalized tag encodings and screened keys/finalpaths. Independent exact reproductions then showed no leak;119cloud and32focused tests passed. See [security-review.md](security-review.md) for initial evidence, dispositions and source hashes. No remainingP1/P2 identified in this offline review scope.
- Optional pinned SDK model proof in `test_selected_sdk.py`:native ECS lowercase tag model and Lambda dictionary-key canaries are screened beforeselected worker results;2tests passed with sockets forbidden. Existing17.2SDK suite14tests also passed; approved existing SDK environment was reused without installation.

## Validation status

- ExactAPI/CLI/infra shard:`LLM_API_BASE=http://127.0.0.1:1 ./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`:838passed,1skipped,2,474subtests. Log:`/tmp/story17-3-api-cli-infra.log`.
- Repo-wideRufflint/format:passed701Pythonfiles after source stabilization. Root `LLM_API_BASE=http://127.0.0.1:1 ./.venv/bin/python -m unittest discover -q` passed2,314tests (3existing skips). Full localCI `LLM_API_BASE=http://127.0.0.1:1 bash scripts/ci-local.sh` passed3,839tests across12registered shards (3existing skips), plus172SDK-free isolation tests, skill scenarios and prompt-injection checks. Final service shard:1,272passed.
- Root log:`/tmp/story17-3-root-final.log`; fullCI log:`/tmp/story17-3-ci-final.log`.
- Docker build `docker build -t deploywhisper:story17-3-validation .` passed; image `sha256:29a37dc08877e952d257f24eaee9fe084c4532f3eae9e2b8999c8d9e534bce2c`. Rebuilt default image is non-root, SDK-free/Node-free, pure-create reflection haszero calls and the AWS registry slot remains unavailable.
- Network-disabled Python3.11.17 harness using the rebuilt image, current source and already-installed approved SDK packages mounted read-only passed71new storytests and16SDKtests (14legacy+2native selected-model tests). This is offline runtime proof, not a live profile. Logs:`/tmp/story17-3-runtime-{new,sdk}-python311.log`.
- Changed production modules pass Python3.10 grammar checks. Bandit cloud/newgrounding scan found zero issues. Cloud/evidence shard isolation and the new grounding hook pass with providerSDK/network/execution-epic imports blocked. The existing shared application analysis/transport graph has pre-existing cross-layer schema imports; no claim is made that the entire application can import with those released modules removed.
- Application smoke:rebuilt container started with networking disabled; `/api/v1/health` returned HTTP200/core_status ok. The container was stopped/removed after the check; no provider connectivity or LLM inference was tested.
- UIvalidationnotapplicable:no rendered UI code or default rendered behavior changed.

## Qualification boundaries

Fixtures/fault injection prove only the contracts above. No live-account smoke,
production AWS profile, provider-independent machine authority or broad IAM/
egress qualification is claimed. The current HTTP/CLI tests install a trusted
fixtureUOW and supply real collected outcomes at the internal shared-service
boundary; they do not claim public operator enablement. SDK calls mean operation
invocations, not proof AWS received or processed them. Already-issued calls can
finish after cancellation, but cannot publish late facts or mutate frozen
returned accounting. Operational metadata does not mint evidence authority.

Outcome:all seven story packets completed for this scoped fixture/fault-injection implementation; independent security gate passed after fixes. Story is ready for bmad-code-review, not a production AWS qualification. No UI/CLI enablement or public authorization adapter is claimed.
