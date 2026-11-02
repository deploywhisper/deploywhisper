# Story 16.10 R4/R5 resolution and closeout evidence

Status: **accepted scoped implementation**. R4/R5 and the validation-derived
supervision correction passed independent reviews and final validation. Story
16.10 is done for its declared scope; git-flow closeout follows these gates.

## R4: consistent graph material authority

`DecisionService.recheck_approved` requires the server-owned `MaterialReadScope`
and `MaterialWitness` port documented in handoff-contract-v1.md. Exact scoped
receipt identities/binding digests and provider domain/monotonic generations
bracket every graph material callback. Changes, ABA or scope/domain replacement
deny; missing/malformed/unavailable witness fails503. No repeated-pass or hash
fallback is used. Final handoff scope/receiver/reviewer/target/policy/time guards
follow the end read. Ports remain unavailable by default; production generation
and custody/lease qualification remains the owning integration work.

Four original all-boundary regressions failed before implementation. New graph
matrix:12 methods,92 subtests passed, covering selected/ancestor changes, both
orders, custody/evidence/binding, ABA, unavailable/malformed/scope/count/domain/
regressed generations, receipt supersession, final-read expiry/reviewer and
rollback/no-send/no-consume. Synthetic fixture setters increment per-step epochs
on every immutable replacement. The controlled crash child's material is truly
immutable and legitimately uses a constant witness. All five service constructor
sites and the two new server-only DTO consumers were searched repository-wide.

## R5: reserve future scalar bookkeeping before authority exists

Fresh blind review identified a separate Medium storage undercount: consumption
added timestamp/digest metadata after only raw receipt bytes were charged, and
lock terminal changes could enlarge reason/status beyond initial admission.
Red proof: receipt actual10928 bytes vs10836 charged; dispatch metadata8662 vs8627;
lock allocation299 bytes vs1312/1314 required for max UTF8 terminal reasons.

Preparation now reserves the longest operation/outbox/grant states, signed64
counter widths, optional timestamps and receipt digest. Admission reserves the
one terminal lock transition plus the maximum256-character printable reason,
using the shared validation bound. Actual initial database row values are not
changed. Consumption still separately charges raw receipt bytes before commit.
These are logical retained-copy quotas, not an SQLite/audit-stream file estimate.
New handoff metadata tests:3 methods/2 subtests passed. New lock tests:2 methods/
4 subtests passed; full target-capacity module12 methods/9 subtests passed.
All three review layers independently accepted the corrected bounded accounting.

## Verification

- Current-source handoff/decision/process suites:103 passed,124 subtests,51.69s.
- R4-only full story corpus before R5:176 host tests passed; production Python 3.11
  ran176 tests, OK (one optional skip),104.052s; startup/health/OpenAPI/schema035/
  zero-identities/nonroot/no-Node smoke passed and witness DTOs stay internal.
- The first broad R4 runs were deliberately interrupted when R5 was found, before
  source changes; they are partial evidence, not final passes. Logs:
  `/tmp/story16-10-r4-{root,shard,ci}.log`.
- Final source validation is complete as recorded below. Earlier interrupted
  and failing host runs remain historical evidence, not final passes.
- UI validation not applicable: backend-only scope and generated API declarations.


### Intermediate R4/R5 validation before the supervision correction

- All15 story-focused host modules:181 passed,490 subtests,61.77s.
- Scoped mypy including lifecycle/decision/handoff/target modules:12 source files,
  no issues.
- Rebuilt final image: `sha256:f6446e77d012f5823374e28f19fb1f631c97140e87ca2cf0486b7a093e58834b`.
  Python 3.11.17 focused corpus:181 tests run, OK (one optional JSON-schema skip),
  102.215s. Isolated startup/health/OpenAPI/schema035/zero-identities/nonroot/
  no-Node smoke passed; witness DTOs are absent from public OpenAPI.
- Exact `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`:
  709 passed,1 skipped,2,316 subtests,540.78s.
- Root `./.venv/bin/python -m unittest discover -q`:1,464 tests, OK (2 skips),734.907s.
- That host CI attempt subsequently hit the supervision race described below.
  Final Linux qualification supersedes this intermediate attempt.
- All three independent review layers accepted R4's material consistency fence
  and R5's corrected reservations. Their independently executed graph/metadata/
  lock boundary regressions passed. Production source stayed frozen throughout
  final validation.


## Validation-derived supervision race correction

The macOS/Python 3.14 host CI run reached707 infra-automation methods but hit
three errors from one inherited cancellation test and its cleanup. R4/R5 tests,
1,464-test root discovery and709-pass exact shard had passed. The same
pre-existing shutdown failure had appeared before these fixes and was not
correctly explained by an earlier timeout hypothesis.

A spawn-aware diagnostic captured `os.killpg(SIGTERM)` raising EPERM(errno1)
while the worker sentinel was not ready; immediate confirmation failed, and the
supervisor exited71. The trace does not prove that the group was already dead at
that instant. No process-group inspection timeout was observed.

The narrow correction treats EPERM as ambiguous, not successful termination:
`send` returns the existing `confirmed_dead` predicate, whose false result enters
the original bounded1.5-second stop loop. Sentinel readiness AND clear
whole-group execution remain required before join/close/slot reuse. Persistent
EPERM or live descendants remain fatal/unconfirmed and retain dirty recovery
metadata. The PID-reuse guard and separate caller shutdown budget are unchanged.

Two added mocked regression methods produced3 failing observations before the
fix. After the fix:2 methods/2 subtests passed; the full supervision module15
methods passed;20 instrumented exact cancellation cases passed65.189s with no
diagnostic errors. Three independent review layers accepted the safety/bounds;
no guard or test was relaxed. Raw diagnostic logs remain outside the repository
at `/tmp/story16-10-supervisor-cause.log` and
`/tmp/story16-10-supervisor-fixed-repeat.log`.

The final source was qualified in isolated LinuxARM64/Python 3.11 containers
using the existing hash-locked dev requirements and standard root/exact-shard/
local-CI commands. No project dependency file changed. Network is disabled;
ignored env/data/cache files are excluded from the source archive. All562 code/
config/script/generated-source hashes are checked before AND after each lane.
The exact Linux shard completed709 passed/1 skipped,2,316 subtests,464.81s, with
its post-run manifest unchanged. Final root and CI results are recorded below.


## Final review and qualification — 2026-11-02

All three review layers accepted R4's exact-graph consistency witness, R5's
bounded metadata reservations and the supervision correction. No High/Medium
finding remains. Qualified source matches the archived 562-file manifest before
AND after each Linux command, and matches the current host source. The witness
port stays unavailable by default; no unqualified source becomes authority.

The ephemeral CI-tooling image uses the same pinned Python 3.11 base and the
existing hash-locked `requirements-dev.txt`, with Git/procps prerequisites and
built frontend assets. Each lane gets a private source/Git-history copy; network
is disabled and ignored env/data/cache files are excluded. This changes no
project dependencies, runtime Dockerfile, operator data or frozen protocol.

| Final command/check | Actual result |
| --- | --- |
| Linux `./.venv/bin/python -m unittest discover -q` | 1,466 tests, OK (6 optional skips),897.940s; manifest unchanged |
| Linux exact `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` | 709 passed,1 skipped;2,316 subtests,464.81s; manifest unchanged |
| Linux `bash scripts/ci-local.sh` | Exit 0;2,912 tests across 10 directories, OK (6 skips); manifest unchanged |
| Host optional JSON Schema validators | 4 passed,30 subtests,0.36s; covers the four optional schema cases skipped in Linux |
| Nonroot production Python 3.11.17 image | 196 tests, OK (1 optional JSON Schema skip),116.498s; all 15 story modules plus supervision module |
| Final production startup smoke | Health/OpenAPI/schema035/zero seeded identities/nonroot/no Node; witness DTOs internal |
| Scoped mypy | 13 source modules passed |
| Ruff lint / repo-wide Ruff formatting | Passed;474 files formatted |
| Pip consistency, Bandit high/high gate, compileall, skill matrix, prompt injection | Passed via local CI |
| `git diff --check` | Passed |

The six full-CI skips are four optional JSON Schema cases (separately passed on
the host), one opt-in live-provider test and one opt-in container test. The latter
is complemented by the explicitly rebuilt production-image qualification and
runtime smoke. No credentialed live provider or real receiver/collector was
contacted. The Bandit medium report retains the existing synthetic sample B104
warning; changed authority/storage/supervision code is clean at medium/high.

Final full-CI directory breakdown:

| Directory | Tests | Result |
| --- | --- | --- |
| `tests/test_analysis` | 69 | OK |
| `tests/test_api` | 324 | OK |
| `tests/test_cli` | 102 | OK |
| `tests/test_docs` | 51 | OK |
| `tests/test_infra` | 284 | OK (1 skipped) |
| `tests/test_infra_automation` | 709 | OK (4 skipped) |
| `tests/test_llm` | 76 | OK (1 skipped) |
| `tests/test_models` | 22 | OK |
| `tests/test_parsers` | 43 | OK |
| `tests/test_services` | 1232 | OK |

Production image:
`sha256:d8836f0ce59582583727b96afaae51accdac7b717bd4b1cc0e6d7681f942c6be`.
Final logs: `/tmp/story16-10-linux-{ci,root,shard}.log`,
`/tmp/story16-10-closeout-runtime{,-smoke}.log`,
`/tmp/story16-10-closeout-mypy.log`,
`/tmp/story16-10-final-optional-schema.log`.

Linux full CI exercises real controlled process recovery and the persistent
EPERM negative tests. The actual macOS failure was reproduced and corrected;
post-fix mocked tests, the complete supervision module and 20 instrumented exact
cancellation repetitions passed. The earlier macOS full run was not silently
reclassified as green; final full qualification is the declared Linux/Python 3.11
profile. Host-power-loss durability, production witness/lease/receiver/collector
integration and generalized execution remain outside this story's accepted
scope. UI validation not applicable.

BMad Help's next delivery step is planning Story 16.11 after integration of this
story. This task's authorized next action is git add/commit/push and a PR to
`develop`; no merge or release is part of closeout.


## PR206 audit-gate follow-up

The initial pushed commit3c18585 passed the source qualification above, but
GitHub's online dependency audits found newly published advisories in existing
pins. These were real gate failures, not suppressed or reclassified as passes.

- Python: pyasn10.6.4→0.6.5 in runtime/dev hash locks, with all other lock bytes
  unchanged. [Upstream0.6.5 release](https://github.com/pyasn1/pyasn1/releases/tag/v0.6.5)
  fixes the four ASN.1 advisories reported by CI. Strict runtime AND dev pip-audit
  now report no known vulnerabilities; isolated exact recompiles, hash-verified
  installs and pip consistency checks passed.
- Frontend: scoped Redocly minimatch11.0.1 override fixes
  [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249), keeping
  openapi-typescript7.13.0. A plain override broke Redocly's old callable matcher
  in configured remote-header matching; red regressions reproduced that error.
  The generator-only preload preserves all named export identities and provides
  the callable API in that process's cache only, with no node_modules file patch.
  A fresh subprocess retains the original export. Upstream Redocly2.x override
  was rejected because the generator's private import is not exported there.
- No new direct application dependency was introduced. The fixed matcher has its
  required locked transitive helper. Root/frontend npm audits both report zero
  vulnerabilities. Two Node compatibility tests,256 frontend unit tests,
  typecheck and production build passed. Current-source API generation succeeded
  with no schema.d.ts diff. Tooling-only changes require no rendered UI gate.
- Python provider/auth affected checks:89 passed,1 opt-in skip,112 subtests.
  No live credentials or provider calls were used. Backend authority source is
  unchanged from the full2912-test qualified snapshot.

The dependency follow-up is committed separately with Lore trailers and pushed
to the existing PR; current remote gate outcomes are recorded at closeout.


CodeQL's initial PR check also reported an implicit SSL protocol floor at
`infra_automation/target_transport.py:383`. The transport now explicitly sets
`SSLContext.minimum_version=ssl.TLSVersion.TLSv1_2` before wrapping, while keeping
certificate/hostname verification, numeric peer pinning and redirect denial.
Two regressions failed before the change and pass afterward; the full transport
suite29 methods/183 subtests passed and independent security review was clean.
A context unable to enforce the floor fails before any credential bytes are sent.
The [Python SSL minimum-version contract](https://docs.python.org/3.11/library/ssl.html#ssl.SSLContext.minimum_version)
is the implementation reference. The follow-up Docker build and nonroot health/
OpenAPI smoke with patched pyasn10.6.5 passed; current source-schema generation
remained unchanged. Remote CodeQL/Frontend/Security gates are rerun after push.
