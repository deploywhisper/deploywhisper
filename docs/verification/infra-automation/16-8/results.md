# Story 16.8 verification

Execution date: 2026-10-29. Scope: immutable decisions, policy/freshness and
runtime graph eligibility, authenticated service/API and migration034. Positive
collection/target/custody fixtures are synthetic scoped contract evidence; no
production collector, remote receiver, grants or dispatch support is qualified.

## Recorded checks

| Check | Result |
| --- | --- |
| `./.venv/bin/python -m unittest discover -q` | 1,194 tests passed, 2 skips |
| `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` | 688 passed, 1 opt-in Linux skip, 2,273 subtests |
| `./.venv/bin/python -m pytest tests/test_infra -q --tb=short` | 274 passed, 1 opt-in skip, 2,100 subtests |
| Focused decision/domain/graph/service/API matrix | 59 passed, 140 subtests; includes actual nonempty HTTP read/decision with verified session and CSRF |
| `LLM_API_BASE=http://127.0.0.1:1 bash scripts/ci-local.sh` | Passed, exit 0; 2,670 directory tests across all 10 directories |
| `./.venv/bin/ruff check .` | Passed |
| `./.venv/bin/ruff format --check .` | Passed repo-wide, 438 files |
| New decision modules: mypy `--follow-imports=silent --ignore-missing-imports` | Passed |
| Repository CI mypy command | 312 existing errors; isolated `git archive b2e87ecb41e0bdafc5904586969db396a45ce390` baseline has 314. Comparing file/message multisets with line offsets removed found no introduced errors. Nonblocking CI type debt remains. |
| Scoped Bandit, medium severity/confidence | No findings |
| `python -m compileall -q infra_automation services models api migrations` | Passed |
| Actual `python app.py`, isolated database, port 18088 | Health 200; GET approvals and POST decision present in OpenAPI |
| Generated frontend API declarations; `npm run ui:typecheck` | Passed |
| `git diff --check` | Passed |

Root discovery ran during integration. The exact affected shard was repeated after the final API fix: 688 passed, 1 skip and 2,274 subtests with the unavailable local model endpoint. Final focused tests
cover subsequent graph and HTTP response review fixes; final every-directory CI passed before the story moved to review. The first local-CI invocation was interrupted
because an installed Ollama model caused repeated slow real inference. The
replacement uses an unavailable loopback endpoint to exercise the supported
optional narrative fallback deterministically. No production setting was changed.

That run passed analysis/API/CLI/docs/infra, then reported six errors from two
existing coordinator test cases: worker termination could not be confirmed, with
two cleanup errors following each primary failure. Both exact cases passed an
isolated rerun (2 tests, 6.257 seconds). Read-only diagnosis found unchanged
macOS supervision has finite process-inspection/termination proof budgets; load
sensitivity is plausible, not established as the cause. Termination safeguards
were preserved. The final serial retry passed: 69 analysis, 312 API, 102 CLI, 51 docs, 275 infra, 488 automation, 76 LLM, 22 model, 43 parser and 1,232 service tests (2,670 total). The opt-in infrastructure and LLM skips remain explicit. Initial failure and successful retries are retained here rather than omitted.

UI validation not applicable: no rendered surface or browser behavior changed;
the TypeScript change is generated API declarations only. Actual Compose/browser,
external receiver, host-power-loss and production isolation/load qualification
remain their owning later stories.

## Independent review and fixes

Native reviewers independently checked readiness, immutable domain/persistence,
service trust boundaries and all six ACs. Review corrections include:

- Recognize current SQLite AUTOINCREMENT schema after restart; retain exact
  columns, constraints, indexes and trigger checks at the new migration head.
- Verify report → successful analysis attempt → exact manifest → current source
  output/fence/envelope, including collector identity and supported exit status.
- Derive report flags, policy interpretation and freshness from durable captured
  facts; ports cannot replace them with caller assertions.
- Persist typed denial reasons and derive recovery guidance; expired initial
  requests retain terminal denial without creating approvable pending authority.
- Retain reviewer authentication/membership generations and honest server-selected
  acknowledgement versus independent approval. Regrant cannot revive old approval.
- Check exact-run latest generations independently of inbox pagination; deny
  superseded receipts even when their tuple is identical.
- Parse strict immutable response values through their JSON boundary so nonempty
  approval lists/receipts accept wire arrays while preserving scalar/unknown-field
  rejection. Real HTTP tests enforce CSRF and keep raw snapshots private.
- Project current approved human prerequisites without recursive graph rechecks;
  request-time checks cover the decision's own prerequisites, while dispatch and
  consumption check complete handoff ancestry. Include serial and parallel DAGs.

Independent final review closed every reported finding; four graph/generation regressions and the nonempty HTTP roundtrip were independently rerun successfully.
Application-level immutability does not protect against a privileged database/host
administrator. Historical receipt status alone is never current authorization.

## Completion boundary

Implementation commit: `bc05965`. Branch:
`feature/16-8-evidence-bound-decisions-freshness`. The story is ready for the
separate BMad code-review workflow and Git Flow push/PR closure. No remote push,
release, production collection or receiver execution is claimed. New decision
modules have no scoped typing/security findings; existing repository-wide typing
debt and the observed pre-existing worker teardown retry remain documented limits.

## Formal code-review follow-up

The subsequent BMad code review fixed six additional deadline/storage/recovery
issues. Final verification passed 1,242 root tests (2 skips), 688 affected-shard
tests /2,274 subtests (1 skip), 77 focused tests /154 subtests and all 2,688 local
CI directory tests. Formatting covers 439 Python files. The final review record
is [code-review.md](code-review.md). Earlier counts and retry chronology above
remain historical dev-story evidence, superseded by this final review outcome.

Formal review closure: the compliant story branch is pushed and [PR #203](https://github.com/deploywhisper/deploywhisper/pull/203) is open against `develop`. Story/sprint status is done for the declared slice.
