# Story17.0 review-fix verification — 2026-11-12

Status: **all eight fixes closed; independent review and final repository regression passed**. This supplements the original changes-requested review, not a rewrite of its history.

| Finding | Implemented repair | Regression evidence |
| --- | --- | --- |
|R1 Mandatory filters | Compare recorded family and exact required postfilter fields before accepting calls; matcher fails closed when required filters are absent. | Missing, empty, wrong-parent and lost-metadata Lambda filter cases reject unrelated rows. |
|R2 Route53 variants | Include SetIdentifier in expected name/type/variant identity, including None for simple records. | Weighted/failover variant mismatch and absent/simple identity tested. |
|R3 Model injection | Load only installed botocore package data during benchmark shape validation. | Malicious AWS_DATA_PATH and home models cannot admit forged request fields. |
|R4 Backoff accounting | Drain completed futures independently of dispatch cooldown and at finalization; count only observations completed before the original deadline. | Deterministic four-future throttle/deadline regression, partial/cancel/timeout cases. |
|R5 Provider pricing | New source-backed33-operation regional catalog with selected official S3/SQS rate dimensions. Explicit documented-meter inferences cover unmetered control-plane reads. Unknown operations/regions/profiles stay unknown or reject. |12cost tests; complete900-call estimate USD0.0000288 and100-prefix USD0.0000032, before credits/discounts and excluded infrastructure charges. Arbitrary rate remains only a separate sensitivity scenario. |
|R6 Hardware | Detect CPU/model on the current host through bounded platform-specific inspection; missing fields are unknown. | Mocked other-host and failed-detection cases cannot fabricate Apple hardware. |
|R7 Freeze | Verify contract version, exact approved25-family set, valid unique nonempty operation references and no orphaned allowed operations. |11coverage tests; renamed family, missing/empty/duplicate references, orphan and version cases reject. |
|R8 Numeric bounds | Reject boolean/fractional attempt/concurrency counts and non-finite or invalid durations/rates before dispatch. Guard JSON monetary overflow after multiplication/aggregation. | Invalid-bound/CLI-rate cases plus per-rate and aggregate overflow cases. |

## Independent verification

A separate read-only verifier ran the latest29measurement checks and11coverage checks. It temporarily restored each of R1–R8 in memory without writing project files; each targeted regression went red. It found no remaining blocking findings. The generated fixture matches retained bytes and SHA256. Both official public AWS regional price-list offers were freshly fetched independently: their SHA256, versions, SKU attributes and price dimensions exactly match `measurement/pricing-evidence.json`. No credentials or live account operations were used.

## Reproduction

```sh
/tmp/dw17-qualification-venv/bin/python -m unittest discover -s docs/verification/live-environment-grounding/17-0/measurement -v
/tmp/dw17-qualification-venv/bin/python -m unittest discover -s docs/verification/live-environment-grounding/17-0/coverage -v
/tmp/dw17-qualification-venv/bin/python docs/verification/live-environment-grounding/17-0/measurement/benchmark.py --fixture docs/verification/live-environment-grounding/17-0/measurement/large-plan.json --usd-per-1000-calls 0.005
./.venv/bin/ruff check .
./.venv/bin/ruff format --check .
./.venv/bin/bandit -r docs/verification/live-environment-grounding/17-0 --severity-level medium --confidence-level medium
```

Per-packet red/green commands are retained in coverage/results.json and measurement/README.md. Measurement regression red run: `/tmp/dw17-measure-review-red.log`; cost-integration red run: `/tmp/dw17-measure-cost-integration-red.log`. Root and full localCI fresh logs: `/tmp/story17-0-fixes-unittest.log`, `/tmp/story17-0-fixes-ci.log`; final summaries will be recorded after exit. UI validation not applicable. Live AWS transport/security/release qualification remains downstream work.

## Final result

68 qualification checks passed; fresh root discovery passed 2,128 tests (3 skipped); full local CI passed 3,603 tests across 10 shards (3 skipped), plus skill scenarios and 8 prompt-injection tests with 96 subtests. Repo-wide Ruff lint/format (647 files), Bandit medium/high gate, compilation, Python 3.10 syntax and fixture/link checks passed. Story17.0 is done for governance/feasibility. The resolved review is approved; source branch is feature/17-0-grounding-contract. Live-cloud qualification is not claimed.
