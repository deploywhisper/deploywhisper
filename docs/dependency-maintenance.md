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
paused; this pause does not waive dependency audit failures or permit ignored
advisories. The repair below addresses the audit failures observed on Story16.5.

The Refresh Skill Analytics workflow is also disabled in GitHub, and its YAML
now permits only `workflow_dispatch`, with no cron trigger. No analytics PR mode
is currently opted in (`DEPLOYWHISPER_REVIEWED_UPDATES` is unset). To resume,
explicitly enable the workflow and dispatch it; restoring automatic refreshes
or dependency PRs requires a reviewed configuration change. All 15 unwanted
Dependabot PRs (#180–194) were closed; Story16.5 PR #195 was preserved.

## Deliberate dependency maintenance

### October 2026 audit repair

CI on Story 16.5 PR #195 and configuration PR #196 failed because their inherited
locks still selected Vite 8.0.16 and certifi 2026.7.22. The frontend audit failed
before typechecking/building, causing the dependent test matrix to be skipped;
the separate Python security audit also failed. Re-running unchanged locks
could not resolve either failure.

The targeted repair raises the Vite declaration to `^8.1.6` and locks 8.1.6, the
smallest patched Vite 8 minor for the reported advisories. Its required
Rolldown/native-binding and Oxc/WASM dependencies are resolved together. The
application and development Python locks now select certifi 2026.10.19 with
distribution hashes. Runtime declarations remain unchanged because certifi is
an existing transitive dependency. Regenerating the fuzzer lock is byte-identical:
its Pydantic/YAML graph does not contain certifi.

Auditing the development lock as well exposed vulnerable filelock 4.0.12 in the
pip-audit caching dependency chain. The patched filelock 4.2.1 requires Python
3.11+. Development security-audit tooling is therefore explicitly scoped to
Python 3.11+ in `requirements-dev-input.txt`; its exclusive transitive packages
carry the same generated markers. There is no older vulnerable filelock fallback.
Application runtime and the remaining test tooling retain Python 3.10 support.
Use Python 3.11+ for local security-audit commands, matching hosted CI. The CI
Security Scan now audits both application and development locks so vulnerable
developer tools cannot silently escape the gate.

Use the canonical targeted regeneration command rather than manually replacing
generated hashes:

```bash
bash scripts/lock-dependencies.sh \
  --upgrade-package certifi==2026.10.19 \
  --upgrade-package filelock==4.2.1
npm install --prefix frontend --package-lock-only --ignore-scripts --save-dev vite@8.1.6
```

Both root/frontend `npm audit --audit-level=low` gates report zero vulnerabilities.
A clean `npm ci --prefix frontend`, frontend typecheck, all 56 frontend tests and
the production Vite build passed. Python validation uses a fresh synchronized
Python 3.11 virtualenv, so missing packages in an unrelated developer environment
cannot masquerade as application failures. Existing audit gates and the
automatic-PR pause remain in force. These results address the current advisory
database; future advisories still require deliberate maintenance.

On the local macOS host, pip-audit's temporary resolver environment aborted in
`ensurepip`. Hash-enforced installation and `pip check` were verified separately,
then the fully pinned/hash-locked application and development manifests were
audited with `pip-audit --strict --disable-pip`. This skips only the redundant
temporary resolution, not packages or advisories. Hosted Ubuntu CI retains the
normal strict resolver-backed audit commands.

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
