# Bounded mixed-plan measurement

This disposable qualification measures planning and controlled replay. It makes no live AWS latency, billing, transport-cancellation or IAM authorization claim. `benchmark.py` prevents network connections. Actual AWS requests and charges are zero.

The recorded synthetic fixture contains 1,000 resources across 25 risk-bearing AWS families, in 40 child modules: 800 updates, 100 deletes, 100 creates. It carries synthetic identifiers and tags, never raw production state. Creates have no prior counterpart. The exact 900 intended identity-directed read requests are built without credentials. Botocore 1.44.1 validates all 900 input parameter shapes. This is separate from real Terraform/OpenTofu producer evidence.

Reproduction from the repository root:

```sh
./.venv/bin/python -m unittest discover -s docs/verification/live-environment-grounding/17-0/measurement -v
/tmp/dw17-qualification-venv/bin/python docs/verification/live-environment-grounding/17-0/measurement/benchmark.py --fixture docs/verification/live-environment-grounding/17-0/measurement/large-plan.json --usd-per-1000-calls 0.005
./.venv/bin/ruff check docs/verification/live-environment-grounding/17-0/measurement
./.venv/bin/ruff format --check docs/verification/live-environment-grounding/17-0/measurement
./.venv/bin/bandit -r docs/verification/live-environment-grounding/17-0/measurement --severity-level medium --confidence-level medium
```

The disposable SDK environment uses the approved isolated package set in `../sdk-versions.json`. It is not required by the application. The benchmark writes JSON to stdout; the recorded output is `../bounded-measurement-results.json`. The fixture digest uses sorted compact UTF-8 JSON without a trailing newline, matching the committed file bytes.

Twenty-nine tests pass. Tests first failed with `ModuleNotFoundError: benchmark` before implementation; a later per-call-timeout regression failed with 4 incorrectly completed reads, then passed after timed-out reads were classified unread. All requests render the frozen family templates in `../coverage/coverage.json`; no separate benchmark action catalog exists. Regression checks validate operation membership, exact parameter keys and fixed values for every request, reject broadened list calls, enforce mapping UUID/parent filtering and reconstruct queue URLs rather than forwarding arbitrary URLs. The fixture records the function/event-source parent identifiers used for each mapping request. All other tests cover strict budget, labelled partial results, concurrency, deadline, cancellation before and during collection, throttling backoff without retries, and invalid bounds. Scoped Ruff and Bandit pass with zero findings.

Named host: Apple M3 Pro, Mac15,7, Darwin ARM64, 12 logical CPUs, Python versions are recorded per interpreter (repo tests use3.14.3; isolated SDK benchmark uses3.13.12). The result file records exact platform versions and observed timings. SDK parameter validation and fixture planning are timed separately from replay latency.

Defaults selected for later implementation: 15-second total deadline, 4 concurrent reads, 100-call attempt budget, 2-second per-call timeout, zero hidden SDK retries. The 200-ms replay takes about 5.1 seconds for 100 reads, leaving deadline headroom for scheduling and throttling. At the injected slow-failure profile, the 1-second scaled deadline returns partial results at about 1.005 seconds. These values bound work; they do not promise complete reflection of every large plan. A 900-call plan intentionally returns at least 800 unread results under the default budget. Production surfaces must display that truncation and never lower severity or increase confidence.

## Provider-based request estimate (R5)

`cost_model.py` now derives request charges from the dated us-east-1 [33-operation catalog](cost-rates.json), with [official source URLs, retrieved-content hashes and selected AWS Price List SKU/term fields](pricing-evidence.json). The regional public AWS offers retrieved on 2026-11-12 are AmazonS3 version `20261109154310` and AWSQueueService version `20261111153551`. Both selected first-paid-tier request rates are USD 0.0000004 per request. S3 bucket versioning/tagging use the published GET-and-other category; SQS uses Standard queue request units, assuming the selected attribute exchange is at most 64 KiB. The estimate deliberately applies no free-tier credits or volume discounts.

The original recorded primary manifest has 36 S3 `GetBucketVersioning` and 36 SQS `GetQueueAttributes` requests. Their gross estimated request fees total **USD 0.0000288 for all 900 intended reads**. Its first 100 calls contain four of each, yielding **USD 0.0000032 for that ordered budget prefix**. This is a provider-based estimate under the catalog's stated assumptions, not a bill or a guaranteed ceiling. It is calculated from the actual ordered call manifest, not by applying one invented rate to all operations.

IAM and Auto Scaling have explicit no-additional-charge classifications from AWS documentation. The remaining selected control-plane operations have a separately labelled **control-plane meter inference**: the cited published service pricing meters concern existing resource hours/capacity, function invocation, item-data reads/writes or DNS resolution, none of which these metadata Describe/Get/List operations initiate. Their zero incremental request-fee estimate is an explicit, reviewable inference from those billing meters, not a claim that every read API is free. Existing resource costs, transfer/NAT/private-endpoint charges, tax, CloudTrail/logging/monitoring charges, discounts and free tiers remain outside this request-fee estimate.

Unknown operations never default to zero: they produce `estimated_request_usd: null`, an `unknown_rates` status, a separately named known subtotal and the unpriced action list. Other regions require a new catalog. FIFO/noncanonical SQS URL profiles and unsupported S3 directory/access-point profiles are not priced by the initial catalog. The former command-line USD 0.005/1,000-call calculation remains available only as a separate **sensitivity scenario**, not the AC6 provider-price proof.

Cost regression command: `./.venv/bin/python -m unittest discover -s docs/verification/live-environment-grounding/17-0/measurement -p test_cost_model.py -v` — **11 tests pass**. Before `cost_model.py` existed the same command failed with `ModuleNotFoundError: cost_model`. Green checks cover published metered rates, ordered budget accounting, all 33 catalog classifications/sources, unknown operations/regions, invalid/non-finite rates and budgets, missing catalog rates, unsupported queue/bucket profiles and per-action aggregation. Scoped Ruff and Bandit medium/high checks pass; no dependencies or live AWS calls are introduced.


Replay is cooperative and bounded by construction; real SDK sockets, credential providers and thread/process teardown must be qualified in Story 17.3's production collector. SDK model validation alone does not establish that all generated synthetic identifiers are valid live identities. The product permission map is frozen separately in `../coverage/`.

## Reviewer regression repairs

All R1/R2/R3/R4/R6/R8 benchmark repairs and R5 pricing integration are covered by17benchmark checks plus12cost checks (29total), run using the isolated SDK interpreter above. New regression cases failed against the former behavior. An independent verifier used in-memory rollback mutations for every finding and confirmed the targeted tests go red. R7 coverage validation has11checks separately. See [review-fix-verification.md](../review-fix-verification.md).
