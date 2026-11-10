# Story 16.17 implementation and verification

The backend, authenticated CLI and origin UI are implemented and verified.
Story16.17 is ready for review. No public push, PR or release is claimed.

## Delivered scope

- A versioned, length-delimited HMAC frame binds the key ID, method, exact raw
  path, timestamp, nonce and raw-body digest. Authentication and a committed
  replay fence precede bounded JSON construction.
- Protected manifests contain environment references and exact scope/source
  allowlists. Actual service/agent identities retain only read/request capability;
  human sessions, publication and decisions remain separate.
- Machine authority is revalidated against current key/config, account,
  membership, restore, expiry and durable clock state at effects. Existing human
  snapshot bytes retain their original serialization.
- Exact raw operations bind idempotency; fresh nonces may recover the original
  result. Keys cannot be reflected into decoded/resolved stored or returned data.
- The CLI uses the same API/envelopes, pinned origins and private credentials.
  Its total transport deadline includes DNS, TLS, headers and body, with bounded
  stalled workers, sealed outcomes and no late sends. It never retries by itself.
- Run history/details show actual authenticated principal and server entrypoint
  independently, with exact requested source pins and an honest legacy fallback.

Existing services, role capabilities, cursor machinery, engine, analysis and
canonical locks are reused. No dependencies or infrastructure execution steps were added.
Machine keys remain environment-backed; no signing key, raw state or binary plan
was committed. One local backend/CLI branch and one dependent UI branch preserve
the required delivery separation.

## Validation results

| Check | Result |
| --- | --- |
| Pure signing and schema | 12 tests, 63 subtests; independent review clear |
| Combined backend/API/engine/schema contracts | 77 tests, 161 subtests; schema subset13tests20subtests |
| Real credential/effect matrix | 9 tests, 68 subtests; actual signed admission, engine claims, human decision and handoff entrypoints |
| API negative parity | 10 tests, 43 subtests, including fresh-process replay denial |
| CLI deadline/credential/transport regressions | 24 tests, 5 subtests; independently verified |
| CLI directory via local CI | 126 tests pass |
| Frontend | 479 tests plus2compatibility checks; typecheck and production build pass |
| Actual Compose origin proof | 1 test,27.7s; five origins, two uploaded reports, keyboard/axe;12screenshots, visual94/100 |
| Real collection requalification | 49 checks qualified with expanded authority source hashes |
| Collection/isolation integrity | 9 tests, 86 subtests pass |
| Exact API/CLI/infra pytest shard | 797 passed,1skip,2423subtests;519.09s |
| Root unittest discovery | 1,921 tests pass,3skips;915.836s |
| Exact automation pytest shard | 1,099 passed,1skip,3236subtests;582.46s |
| Every-directory local CI | Analysis69/API372/CLI126/docs51/infra300/LLM76/models22/parsers43/services1232 pass; repaired automation target passed its full pytest rerun |
| Static/security | Ruff and scoped Bandit pass;317existing-code mypy diagnostics, zero on changed lines |

## Evidence boundaries

The privilege tests provision real identities and verify real HMAC requests. Their
handoff scenarios create new machine runs, seed explicitly synthetic collector/
material/custody evidence and obtain a real distinct human decision before using
actual dispatch/consume services. Those doubles are not live delivery proof.

The browser exercises actual manual/human-CLI reports and actual service, agent
CLI and PR-origin admission. Its collection metadata is structural and no runner
is enrolled: unavailable collection fails closed while origin remains truthful.
It does not claim successful collection, production TLS or repository custody.
Story16.15's separate positive HTTPS/real-runner browser gates remain open.

The real collection run retains the existing offline ARM64/OpenTofu1.13.1 profile;
Terraform, cloud IAM, remote-state and alternate-platform qualification are not
expanded. See [browser proof](browser-proof.md), [review repairs](review.md) and
[entry review](readiness.md).

## Verification history

The initial full `bash scripts/ci-local.sh` passed analysis69, API372, CLI126,
docs51 and infra300(one skip). Automation completed1100tests but exposed three
old assumptions about a fixed run version and a single admission charge. Origin
retention legitimately adds a charge/version mutation. Tests now verify persisted
version continuity and isolate target-lock allocation, preserving quota and
rollback assertions. Their focused rerun passed20tests13subtests. Stale parallel
runs were interrupted and restarted with the corrected fixtures; incomplete runs
are not counted as passing evidence.

Remaining local-CI targets use the same `scripts/run-test-targets.sh` entrypoint.
Exact shards and root discovery run in separate worktrees to isolate mutable test
data. CLI red tests, the interrupted startup-capacity reproduction, initial
browser fixture/navigation failures and the visual87 revision are retained in
local logs or the browser evidence packet.

Current commands include `unittest discover -q`, exact pytest API/CLI/infra and
infra-automation shards, `npm run ui:gen-api`, `ui:typecheck`, `ui:test`, `ui:build`,
Compose plus Playwright, the real collection qualifier, Ruff, Bandit and CI mypy.
The final summary records actual outputs and hashes after all runs finish.

## Final completion evidence

All ten local-CI targets were exercised. The initial run's three stale test
assumptions are preserved in its failure log; their fixes passed20tests13subtests,
and the complete automation pytest shard then passed1,099tests/1skip with3,236
subtests. Root discovery passed1,921tests/3skips on the corrected combined tree.
The exact API/CLI/infra shard passed797tests/1skip with2,423subtests. Final docs
and static checks pass. No introduced review findings remain.

The command sequence is preserved rather than reported as a single successful
ci-local invocation: `bash scripts/ci-local.sh`, the same
`PYTHON_BIN=./.venv/bin/python bash scripts/run-test-targets.sh` entrypoint for
remaining LLM/models/parsers/services directories, root
`python -m unittest discover -q`, and exact pytest shards
`tests/test_api tests/test_cli tests/test_infra -v --tb=short` and
`tests/test_infra_automation -v --tb=short`. Mutable test data was isolated in
separate worktrees. Current OpenAPI was exported from `create_app().openapi()`
then generated with `OPENAPI_URL=/tmp/story16-17-openapi.json npm run ui:gen-api`.

Local Python3.14.3, production Python3.11.17, Node24.7.0, Docker29.1.3 and
Playwright1.63.0 are recorded with the browser source/image manifest. The existing
317 mypy diagnostics lie outside changed lines. Collector/custody/delivery doubles
and the pending16.15 qualification gates remain explicitly distinguished from
actual HTTP/CLI/browser and offline collection evidence.

Next BMad handoff is code-review closure for the separate backend/CLI and origin-UI
branches. The original application container was restored healthy; private test
credentials and disposable Compose resources were removed.
