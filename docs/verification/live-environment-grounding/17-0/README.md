# Story 17.0 qualification packet

Status: **DONE — governance and feasibility qualified**. All six packets and AC1–8 are evidenced. All eight formal review findings were fixed and independently verified. No downstream story is automatically promoted or marked done.

The maintainer approved choosing the SDK/design and completing the remaining qualification, then explicitly requested all reviewer findings fixed and properly tested. Existing default application dependencies and runtime behavior are unchanged. This story introduces no product API, migrations or production connector.

## Decisions and evidence

| Packet | Adopted result | Evidence |
| --- | --- | --- |
| 0.1 | Accepted RFC, scope agreement, read-only exclusions and CODEOWNERS coverage. | [RFC 0002](../../../rfcs/0002-live-environment-grounding.md) |
| 0.2 | Optional boto3 extra approved; mandatory default SDK and custom signer rejected. Qualified package set hash-locked and scanned. | [Decision](dependency-decision.md), [SDK lock](sdk-requirements.lock), [metadata](sdk-versions.json), [audit](sdk-audit.json) |
| 0.3 | Explicit credential mechanisms, canonical TLS endpoints, trusted packaged SDK models, safe error projection and credential-free dry-run. | [SDK probes](sdk/README.md), [results](sdk-results.json), [threat model](threat-model.md) |
| 0.4 | Terraform 1.17.2/1.16.7 and OpenTofu 1.13.9/1.12.12 real exports, plan format 1.2; nested and absent/null prior-state fallbacks. | [Producer commands](producer/README.md), [results](producer-results.json) |
| 0.5 | Mixed 1,000-resource primary-read replay, bounded deadline/concurrency/budget, correct completion accounting, detected hardware and provider-based request-fee estimates. | [Measurement](measurement/README.md), [results](bounded-measurement-results.json), [pricing sources](measurement/pricing-evidence.json) |
| 0.6 | Exact 25-family set, 42 templates, 33 IAM actions, request selectors, response fields and permission scopes frozen and validated. | [Permission map](coverage/permission-map.md), [contract](coverage/coverage.json), [policy](coverage/policy.json), [readiness](../../../../_bmad-output/planning-artifacts/implementation-readiness-report-2026-11-12-live-environment-grounding.md) |

All six RFC questions are resolved. Snapshot retention is seven days unreferenced from observation, extended by live report references; imports never reset age. [Retention proof](retention/README.md). Initial credential mechanisms are environment and trusted operator-selected shared credentials; all others remain default-deny until separately qualified.

Static requests derive only from recorded plan identities. Responses never schedule recursive collection. First-page tokens, unsupported reverse relations, missing identities and budget truncation remain incomplete/unknown. Lambda mapping and Route53 routing-variant filters are mandatory and fail closed. Severity cannot decrease and confidence cannot increase because evidence is absent.

## Review fixes and tests

[Original review](code-review.md) and [resolution verification](review-fix-verification.md) retain R1–R8 and their red/green proof. New regressions cover required postfilters, routing variants, malicious SDK model paths, throttle accounting, sourced pricing, detected hardware, exact family references and finite bounds. A separate reviewer restored each bug in memory and confirmed its targeted test failed. It also verified both official regional pricing downloads and the generated fixture hash. No blocking findings remain.

68 qualification checks passed; fresh root discovery passed 2,128 tests (3 skipped); full local CI passed 3,603 tests across 10 shards (3 skipped), plus skill scenarios and 8 prompt-injection tests with 96 subtests. Repo-wide Ruff lint/format (647 files), Bandit medium/high gate, compilation, Python 3.10 syntax and fixture/link checks passed. Exact results and hashes: [final-verification.json](final-verification.json). Full ephemeral logs are `/tmp/story17-0-fixes-unittest.log` and `/tmp/story17-0-fixes-ci.log`. UI validation not applicable.

```sh
uv venv /tmp/dw17-qualification-venv
uv pip install --python /tmp/dw17-qualification-venv/bin/python --require-hashes -r docs/verification/live-environment-grounding/17-0/sdk-requirements.lock
./.venv/bin/python -m unittest discover -s docs/verification/live-environment-grounding/17-0/spike -q
./.venv/bin/python -m unittest discover -s docs/verification/live-environment-grounding/17-0/producer -q
/tmp/dw17-qualification-venv/bin/python -m unittest discover -s docs/verification/live-environment-grounding/17-0/sdk -q
/tmp/dw17-qualification-venv/bin/python -m unittest discover -s docs/verification/live-environment-grounding/17-0/measurement -q
./.venv/bin/python -m unittest discover -s docs/verification/live-environment-grounding/17-0/retention -q
/tmp/dw17-qualification-venv/bin/python -m unittest discover -s docs/verification/live-environment-grounding/17-0/coverage -q
./.venv/bin/python -m unittest discover -q
bash scripts/ci-local.sh
./.venv/bin/ruff check .
./.venv/bin/ruff format --check .
./.venv/bin/bandit -r docs/verification/live-environment-grounding/17-0 --severity-level medium --confidence-level medium
```

Provider fee estimates use official regional S3/SQS tariffs and explicitly labelled inferences from published control-plane billing meters. Unsupported operations, regions and profiles never silently become free. Arbitrary-rate sensitivity remains separate. Estimates exclude network, tax, credits/discounts and standing resource charges; replay makes no actual account calls or charges.

Controlled replay, projected synthetic plans and SDK Stubber checks do not qualify live AWS IAM/transport, production credentials or release-wide behavior. Those remain in their owning later stories. No product LEG-FR implementation or Epic 16 dependency is claimed. Original three-family/spike records are historical experiments superseded by this final packet.
