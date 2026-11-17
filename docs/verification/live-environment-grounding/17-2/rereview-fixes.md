# Story17.2 re-review fixes

Date:2026-11-17. Baseline:`709e167`. All four re-review findings have implementation fixes and red/green regressions. All final targeted, runtime and full-repository verification below passed.

| Finding | Resolution | Proof |
| --- | --- | --- |
| R2-1 partition admission | SDK-free region validation rejects noncommercial extra-segment region forms; qualified commercial regions remain admitted before any credential resolution. | Noncommercial/China/ISO/sovereign rejection corpus; all34commercial EC2 regions in pinned SDK metadata accepted. |
| R2-2 S3 targeting | Bucket capabilities accept ordinary DNS-style bucket names only. ARNs, URLs, paths, IP forms, access-point/multiregion/directory aliases are refused; SDK use_arn_region is explicitly false even under hostile ambient settings. | Manifest denial corpus; real SDK pre-send rejection of mismatched-region accesspoint ARN; positive canonical regular bucket endpoint; one-send failures retained for all12catalog services. |
| R2-3 Route53 identity | Any returned SetIdentifier marker is incomplete because the current manifest cannot select a routing variant. Malformed returned trailing-dot identities also fail closed. | Single nontruncated weighted record/empty/null marker corpus, simple exact/wildcard positive cases and malformed identity negatives. |
| R2-4 completion deadlines | Worker completion timestamps govern publication against per-call and total deadlines. Scheduler checks newly completed futures before expiring pending work and drains published completions after observing collection expiry. | Deterministic fake-clock/event tests cover true late completion, timely work under delayed polling, stale wait snapshot with two workers and publication between top-loop snapshot/deadline observation. Original real4ms/1ms reproduction now returns timeout/partial. |

## Red/green and independent verification

- Regional corpus failed before fixes: `/tmp/story17-2-r2-session-red.log`.
- SDK endpoint regression initially failed (ARN-region override still sent): `/tmp/story17-2-r2-sdk-red.log`.
- Initial client regression run:6tests,22failing subcases on reviewed code; `/tmp/story17-2-r2-client-red.log`.
- Independent verification found two closely related timely-publication races during development. Both received deterministic failing regressions before correction: `/tmp/story17-2-r2-client-race-red.log`, `/tmp/story17-2-r2-client-deadline-race-red.log`.
- Final independent verdict: all four findings closed, no remaining concrete blocker;8new boundary tests passed after final correction. AWS focused38passed; optional pinned SDK14passed. DynamoDB sibling endpoint probes kept configured us-east-1 for west-region table ARN parameters; no sibling region override found.
- SDK command: `PYTHONPATH="$PWD/.venv/lib/python3.14/site-packages:$PWD" /tmp/dw17-2-sdk/bin/python -m unittest discover -s docs/verification/live-environment-grounding/17-2 -q`. SDK dependencies remain the approved optional pinned set; no lock/dependency changes.
- Python3.11.17/botocore1.44.1 existing-image harness additionally passed52tests (AWS38+SDK14) with `docker run --rm --network none`, current source and approved SDK packages mounted read-only. Image:`deploywhisper:story-17-1-closeout`, digest:`sha256:3f1580d0893b8f00505c1c2e8c807ad155d23b5b6f481399a361ef872c75fa04`. This is a runtime test harness, not a rebuilt production image or live AWS qualification. Log:`/tmp/story17-2-r2fix-runtime-python311-final.log`.
- Runtime prefix: `docker run --rm --network none --entrypoint python -e PYTHONPATH=/workspace:/sdk -v "$PWD:/workspace:ro" -v /tmp/dw17-2-sdk/lib/python3.14/site-packages:/sdk:ro -w /workspace deploywhisper:story-17-1-closeout`; run unittest discovery for both `tests/test_cloud/aws` and `docs/verification/live-environment-grounding/17-2` in the interpreter.

## Verification

- Exact API/CLI/infra shard: `LLM_API_BASE=http://127.0.0.1:1 ./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`:834passed,1skipped,2,456subtests. Log:`/tmp/story17-2-r2fix-api-cli-infra.log`.
- Cloud75tests, SDK-free isolation128tests, protected-source guard3tests passed. Bandit cloud/aws scan found zero issues; Ruff lint/format passed685files after source stabilization. Qualified config.py/model sources and default locks unchanged. No public constructor changed; direct constructor search retained in `/tmp/story17-2-r2fix-constructors.log`.
- Root command `LLM_API_BASE=http://127.0.0.1:1 ./.venv/bin/python -m unittest discover -q` passed2,268tests (3skips). Full localCI command `LLM_API_BASE=http://127.0.0.1:1 bash scripts/ci-local.sh` passed all12registered shards:3,768tests (3skips), plus128isolation tests, skill scenarios and prompt-injection checks; logs:`/tmp/story17-2-r2fix-{root,ci}-final.log`. Earlier in-flight broad runs were interrupted for independent-review timing corrections; only final fresh runs qualify completion.
- UI validation not applicable. No live AWS/account/production-profile or composed-egress qualification claimed. User-facing provider registration, raw-plan mapping and later qualification gates remain in their owning stories.

Outcome:all four R2 findings resolved and independently verified. Story returned to review. Live AWS/production-profile and composed-egress qualification remain later-story gates.
