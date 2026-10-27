# Python dependency maintenance

## Automatic update PRs paused

At the maintainer's request on 2026-10-27, automatic dependency PRs are paused.
Every ecosystem in `.github/dependabot.yml` has
`open-pull-requests-limit: 0`. The weekly schedule is retained for a future
explicit opt-in, but a zero limit prevents version-update PR creation. Closing
existing PRs alone would not disable their scheduled replacements.

Dependabot security-update PRs are separately disabled in the repository settings;
the version-update limit does not control them. Dependency alerts, CI dependency
audits, CodeQL, fuzzing and Scorecard checks remain available. Resolve dependency
and security failures through deliberate maintenance changes while updates are
paused; this pause does not waive the existing Vite audit blocker on Story16.5.

The Refresh Skill Analytics workflow is also disabled in GitHub, and its YAML
now permits only `workflow_dispatch`, with no cron trigger. No analytics PR mode
is currently opted in (`DEPLOYWHISPER_REVIEWED_UPDATES` is unset). To resume,
explicitly enable the workflow and dispatch it; restoring automatic refreshes
or dependency PRs requires a reviewed configuration change. All 15 unwanted
Dependabot PRs (#180–194) were closed; Story16.5 PR #195 was preserved.

## Deliberate dependency maintenance

Keep runtime declarations in `pyproject.toml` and `requirements-runtime.txt`
aligned. Use `uv 0.11.2` and `bash scripts/lock-dependencies.sh` to regenerate
both universal, hashed application locks. Regenerate the fuzzer lock with:

```bash
uv pip compile .clusterfuzzlite/requirements-source.txt --universal \
  --python-version 3.10 --generate-hashes \
  --output-file .clusterfuzzlite/requirements.txt
```

Upgrade Pydantic and its exact `pydantic-core` dependency together. Keep the
application and fuzzer validation stack at the same versions; the dependency
contract tests check this. A separate core-only Dependabot bump cannot satisfy
Pydantic's exact requirement. Do not edit individual generated entries instead
of resolving the complete dependency graph.

Anthropic 1.13.0 requires `httpx2` and its transitive dependencies. They must be
present with exact versions and hashes in both application locks. Existing
providers that use `httpx` retain that separately pinned package. Starlette's
test client selects `httpx2` when installed, so log-secrecy tests capture the
emitted logs without depending on one transport logger name.

Anthropic's current Messages SDK does not accept `temperature`. The adapter
omits it and retains its existing messages, system prompt, JSON prefill,
timeout and error handling. The SDK round-trip regression uses its real client
with a synthetic HTTP transport and makes no external requests. Deterministic
risk scoring remains independent of provider narrative sampling.

Before merging a dependency update, verify hash-enforced installation and
`python -m pip check`, the provider tests, API/CLI/infrastructure shard,
root unittest smoke suite and full `scripts/ci-local.sh`. Run repo-wide Ruff
lint and formatting. Require hosted CI, Docker/migration checks and production
redaction fuzzing. A mocked provider transport proves SDK compatibility rather
than live model availability. Python 3.11 remains the production runtime.
