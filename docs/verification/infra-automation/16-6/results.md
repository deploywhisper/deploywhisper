# Story 16.6 bounded qualification

Date: 2026-10-27. Scope: runner-less uploaded preflight, synthetic collection
provenance verification, immutable report linkage and existing consumer parity.
No production collector/custody/receiver, approval grant, frontend or release
qualification is claimed. UI validation not applicable.

## Packet acceptance and independent review

1. Intake: `artifact_intake.py`, named `preflight-screening-v1` fixture, intake/API
   tests. Red→green screening proof includes every split of eight known synthetic
   secret cases, aggregate bounds, type/path classification, metadata and fixed
   errors. Independent review found BOM/legacy-state disguises; regressions now
   reject both. API error JSON and SQLite dumps contain zero declared corpus
   patterns after rejected submissions. This is a finite known-pattern guarantee.
2. Persistence: `preflight_contracts.py`, repository, ORM metadata, migration033 and
   bootstrap support. Ten repository methods prove immutable manifests/links,
   exact-scope prerequisite/output binding, authenticated retained synthetic
   envelope/digest/source/command/collector/attempt/fence checks, quotas and actual
   032→033 migration/bootstrap. Independent review found reparenting/REPLACE with
   SQLite recursive_triggers=0; child guards now check old/new parents and existing
   conflicting identities. The regression failed before correction and passes.
3. Analysis adapter: root-owned private wrapper operation/factory binding, shared
   pipeline callback, two real registered handlers, HTTP/facade and snapshot guards.
   Sixteen adapter/lifespan methods pass, including real spawned off-loop work,
   AI-disabled/narrative failure, cross-surface scoring/Evidence Law, cancellation,
   mid-analysis revocation, wrong scopes/fake private secret/global admin denial,
   report/filesystem rollback, linked legacy/share/export/delete/role-header guards,
   split-log secrets and artifact snapshot immutability. Root found app.py's
   __mp_main__ entrypoint could restart Uvicorn on spawn; red→green regression locks
   the corrected __main__ guard. Native independent review found no remaining
   authority/atomicity blocker.
4. Consumers: four dedicated compatibility methods plus 31 subtests prove existing
   v1/v2 schema readers, absent/v1/unknown provenance handling, agent advisory output,
   permanent URLs and frozen manifest/reference hashes. Six actual CLI cases run
   inside the frozen isolated consumer probe. New automation tests were already
   registered by earlier stories in local CI and the dedicated infra-automation GitHub shard.

The existing shared analysis/scoring/provider boundaries are reused. Report schema
stays v2; provenance v1 is relational. No new dependency or risk engine was added.
Snapshot guards supplement existing report authorization because the public local
artifact helpers could otherwise replace/delete a linked snapshot without SQL.

## Verification record

- Focused packets: upload, persistence, API, adapter, lifecycle and compatibility
  tests pass; final complete counts recorded in the story Dev Agent Record.
- Migration compatibility shard: 57 tests + 44 subtests passed.
- Services CI shard: `./.venv/bin/python -m pytest tests/test_services -v --tb=short`
  passed 1,232 tests + 2,248 subtests.
- `python app.py` was launched against a temporary SQLite database and artifact
  directory on a temporary loopback port: `/api/v1/health` returned 200; shutdown
  completed normally. No user database or live infrastructure was used for smoke.
- Repo-wide Ruff lint/format and `git diff --check` pass. Bandit's high/high gate
  passes; its existing unrelated medium B104 in sample_incident_pack.py remains
  outside this slice.
- Pinned dependencies were synchronized with `./.venv/bin/python -m pip install -r requirements.txt`; the existing local environment had an older Anthropic SDK and lacked the already-declared httpx2. No dependency manifest changed. `pip check` is clean.
- Final API/CLI/infra pytest shard: 671 passed + 2,230 subtests; one opt-in disposable real Linux collector/custody test skipped. Final services pytest shard: 1,232 passed + 2,248 subtests.
- `./.venv/bin/python -m unittest discover -q`: 1,112 tests passed, two skips.
- `bash scripts/ci-local.sh`: passed all ten registered test directories (2,558 unittest methods), plus its prompt-injection/skill harness, compile, lint, format, dependency and Bandit gates. Automation discovery collected and local CI executed 393 methods. The dedicated automation pytest CI shard also passed 393 tests and 1,311 subtests, proving exact runner parity.
- Broad runs use `LLM_API_BASE=http://127.0.0.1:9` to exercise unavailable-provider fallback without the operator's live model. Initial live-provider runs were interrupted; no pass is claimed for interrupted runs. Initial full checks found the obsolete implicit-empty-registry test assumption, reload-stale snapshot exception and stale local dependency installation; all were corrected, the focused regressions pass, and root/local CI were rerun successfully.


## Limits and reviewer handoff

Known patterns do not detect every possible secret. Source identity and exact-plan
custody remain unavailable for uploaded evidence; eligibility is false even for a
complete advisory report. Synthetic collected envelopes do not establish collector
admission or raw saved-plan integrity. Later stories own human workflow screens,
policy/approval, canonical decision snapshots, real collection and release proof.
Independent code-review workflow must verify the final branch, commit/push and PR
closure before this story is marked done. This dev-story hands off at review. Implementation commit: 5289b8d. Final story/sprint/status map all record review.
