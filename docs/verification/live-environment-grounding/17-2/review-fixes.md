# Story17.2 review fixes

Date:2026-11-17. Baseline:`1ea1a40`. All five review findings have implementation fixes and targeted regression evidence. Final regression results are recorded below after commands finish. This packet does not qualify live AWS.

| Finding | Fix | Regression evidence |
| --- | --- | --- |
| P1 hidden SDK requests | Fresh one-use SDK clients; operation-specific pre-parameter and pre-retry guards run before service redirect handlers. Error/redirect paths stop without nested operations or retry requests. | Optional `test_sdk.py`:301/302/307/308, header/no-header redirect,500, timeout, HTTP200 parsed error; no hidden HEAD, one transport send, failed partial result. Direct unlisted/write/second operation denied before construction. |
| P1 false completeness | `response_status.py` checks every catalog capability, provider failures, required containers, direct identities and applicable relation selectors; missing/malformed responses remain incomplete. | `test_response_status.py`:all42capabilities; empty/missing/malformed/pagination/failure corpus. `test_completion.py`:ECS failures, missing/wrong instance and DNS successor identities. |
| P2 false permission diagnosis | Fixed cause vocabulary distinguishes session, credentials, transport, invalid request, provider and throttling errors. Only confirmed provider authorization denial names missing_permission. | Offline exception corpus plus independent probes using real botocore exception types. |
| P2 unrelated logging suppression | SDK payload namespaces remain suppressed; urllib3 levels/disabled flags are untouched. | Optional SDK suite captures raw signing records using environment and trusted shared-file credentials, and checks unrelated urllib3 warnings remain observable. |
| P2 wildcard DNS identity | Parameter-specific DNS validation accepts literal/escaped leading wildcard labels, exact optional trailing dot and exact response name/type matching. | Raw/escaped wildcard records pass; embedded wildcard, inventory selector, malformed/double trailing dot and unrelated successor record fail. |

## Red/green evidence

- Session regression red run:`/tmp/story17-2-session-red.log`;8tests,3failures on reviewed code.
- Client regression red run:`/tmp/story17-2-client-red.log`;4tests with failing assertions/errors on reviewed code.
- Final focused AWS suite:28passed. Optional pinned SDK suite:11passed. Independent read-only verifier reran both and checked safe real-SDK error categories and exact DNS scope; no remaining concrete blockers against the five findings.
- SDK command: `PYTHONPATH="$PWD/.venv/lib/python3.14/site-packages:$PWD" /tmp/dw17-2-sdk/bin/python -m unittest discover -s docs/verification/live-environment-grounding/17-2 -q`. Pinned boto3/botocore1.44.1, Python3.14.3 local harness; socket/network access denied. These results are not a Python3.11/live production profile qualification.
- Repo-wide Ruff lint/format passed684files after code stabilization. Full repository constructor search recorded in `/tmp/story17-2-fix-constructor-search.log`; new CallResult cause is additive and all direct uses were reviewed.
- Cloud shard65tests, SDK-free isolation118tests and protected-source qualification guard3tests passed. Bandit over `cloud/aws` found zero issues. New AWS modules parse with Python3.10 grammar.
- Python3.11.17/botocore1.44.1 runtime harness additionally passed11SDKtests and28AWStests with `docker run --rm --network none`, current source and approved pure-Python SDK packages mounted read-only. Existing image `deploywhisper:story-17-1-closeout`, digest `sha256:3f1580d0893b8f00505c1c2e8c807ad155d23b5b6f481399a361ef872c75fa04`. This is a test harness using the existing image, not a rebuilt production image or live AWS qualification. Logs:`/tmp/story17-2-fixes-{sdk,aws}-python311.log`.
- Runtime command prefix: `docker run --rm --network none --entrypoint python -e PYTHONPATH=/workspace:/sdk -v "$PWD:/workspace:ro" -v /tmp/dw17-2-sdk/lib/python3.14/site-packages:/sdk:ro -w /workspace deploywhisper:story-17-1-closeout`; SDK suffix:`-m unittest discover -s docs/verification/live-environment-grounding/17-2 -q`; AWS suffix:`-m unittest discover -s tests/test_cloud/aws -q`.
- Qualified shared sources/default locks are unchanged; no dependency changes. No UI surface changed: UI validation not applicable.

## Final regression

API/CLI/infra CI-parity command `LLM_API_BASE=http://127.0.0.1:1 ./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` passed834tests (1skip) and2,456subtests. Root command `LLM_API_BASE=http://127.0.0.1:1 ./.venv/bin/python -m unittest discover -q` passed2,258tests (3skips). Full local CI command `LLM_API_BASE=http://127.0.0.1:1 bash scripts/ci-local.sh` passed all12registered shards:3,758tests (3skips), plus118isolation tests, skill scenarios and prompt-injection checks. Final service shard:1,257passed. Logs: `/tmp/story17-2-fixes-{root,ci,api-cli-infra}.log`.

Outcome:all five review findings resolved, independently checked, and full regression gates passed. Story returned to review. Live AWS/profile/composed-egress qualification remains later-story work.
