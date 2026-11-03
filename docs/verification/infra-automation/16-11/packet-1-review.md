# Story 16.11 Packet 1 local review — 2026-11-02

Scope: isolated adapter, internal DTOs, fixed registered GET transport and their
tests. This is a local packet review, not whole-story acceptance or a substitute
for `bmad-code-review` after all implementation packets.

## Review results

Independent read-only review found no remaining actionable findings in the
final five Python files. Review covered fixed paths and origin/peer policy,
API-version isolation, secret-free inputs/errors, protected refs, response
correlation, delivery uncertainty and historical polling.

Four regressions were reproduced before fixes:

1. Historical polling consulted the current ref and denied captured-run reads
   after movement. Poll now checks the immutable accepted run; new effects
   separately require current admission.
2. Metadata GET uncertainty was classified as if a dispatch POST had occurred.
   Dispatch now tracks whether the POST was attempted and preserves the
   transport's more precise POST uncertainty.
3. A missing custom API/web-origin mapping was detected after dispatch. It now
   denies before network activity, avoiding a knowingly unrecordable acceptance.
4. Pydantic `Literal[1]` accepted boolean/float version values despite strict
   model configuration. Both new DTOs now reuse the repository's strict integer
   `decisions.Version`; the regression covers Python and JSON paths. Independent
   review confirmed the narrow correction, with no new finding.

The legacy-version check executes the existing App client with a mocked opener
and inspects its actual request header after exercising the new adapter.
It confirms `2022-11-28` independently of the new transport's `2026-03-10` wire
assertion. No legacy production code changed.

## Focused evidence

- `./.venv/bin/python -m unittest tests.test_infra_automation.test_github_adapter tests.test_infra_automation.test_target_transport -q`
  — final 46 tests passed. Initial independent pytest passed 45 tests with 234
  subtests before the additional strict-version regression.
- `./.venv/bin/ruff check infra_automation/github_contracts.py infra_automation/target_transport.py integrations/github/infra_automation_adapter.py tests/test_infra_automation/test_github_adapter.py tests/test_infra_automation/test_target_transport.py`
  — passed.
- `./.venv/bin/ruff format --check .` — 477 files already formatted.
- `./.venv/bin/bandit -q integrations/github/infra_automation_adapter.py infra_automation/github_contracts.py infra_automation/target_transport.py --severity-level medium --confidence-level medium`
  — passed with no findings.
- `./.venv/bin/mypy --follow-imports=silent --ignore-missing-imports infra_automation/github_contracts.py infra_automation/target_transport.py integrations/github/infra_automation_adapter.py`
  — passed, no issues in three source files.
- The same final 46 focused unittest methods passed in the existing qualified Linux
  Python 3.11 development image `deploywhisper-story16-10:ci-secured`
  (`sha256:c8ff9663b904870b1e98ea9123a7de9228bb593ded646196b9738ab698ff3364`).
  `docker run --rm --network none --read-only` used current three production
  files and the current tests as read-only `/app` mounts, with disposable `/tmp`.
  No image rebuild, host data mount, application startup or live network request
  was involved. Output: `/tmp/story16-11-linux-adapter.log`.

Transient initial failing-test evidence is at
`/tmp/story16-11-packet1-red.log`; the final strict-version red/green outputs are
`/tmp/story16-11-packet1-version-{red,green}.log`. These local scratch paths are not portable
release evidence. The test cases and this result record are retained in git.

## Broader regression evidence

`./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`
passed: **709 passed, 1 skipped, 2,316 subtests**, 500.28 seconds. Output:
`/tmp/story16-11-ci-shard.log`.

`./.venv/bin/python -m unittest discover -q` passed: **1,484 tests, 2 existing
skips**, 691.555 seconds. Output: `/tmp/story16-11-unittest.log`.

Root discovery and the exact API/CLI/infra shard preceded the final internal
strict-version correction. The final 46-test focused runs and lint/format,
Bandit and mypy checks passed again after that change. Local CI's separate
infra-automation process started after the final files were stable and includes
the additional regression.

Repository-wide Ruff lint/format and `pip check` passed through
`bash scripts/ci-local.sh`; its configured security gate passed. The script
exited **0**, with **2,931 tests across all 10 directories, 2 existing skips**.
It also passed compileall, the skill test matrix and the separate eight-method
prompt-injection check (96 subtests). Output: `/tmp/story16-11-ci-local.log`.

| Local CI directory | Tests | Result |
| --- | --- | --- |
| `tests/test_analysis` | 69 | OK |
| `tests/test_api` | 324 | OK |
| `tests/test_cli` | 102 | OK |
| `tests/test_docs` | 51 | OK |
| `tests/test_infra` | 284 | OK, 1 existing opt-in container skip |
| `tests/test_infra_automation` | 728 | OK, includes final strict-version regression |
| `tests/test_llm` | 76 | OK, 1 existing opt-in live-provider skip |
| `tests/test_models` | 22 | OK |
| `tests/test_parsers` | 43 | OK |
| `tests/test_services` | 1,232 | OK |

The configured Bandit high/high gate passed. Its medium report contains the
existing B104 sample-address finding in `services/sample_incident_pack.py`;
the three touched production files have no medium/high findings. No suppression
was added. Generated report output was moved to
`/tmp/story16-11-bandit-report.json`, outside the source diff.

Final `git diff --check` and local documentation link resolution passed. The
adapter reuses the pinned request implementation for both methods instead of
adding a second network boundary. No dependency or default authority was added.

Repository-wide constructor searches covered `DispatchAcceptance`,
`GithubRunObservation` and `PinnedGithubTransport`. No existing required
constructor fields changed. `scripts/ci-local.sh` and the GitHub CI shard already
discover `tests/test_infra_automation`; no discovery registration edit is needed.
UI validation is not applicable to this adapter-only diff; whole-story AC6
browser evidence remains required in Packet 5.

## Acceptance still open

Actual sandbox dispatch is **not run**: the operator-selected sandbox and
dedicated credential reference are missing. No live API mutation occurred.
Local tests use metadata/socket/TLS doubles. No receiver operation, custody,
callback, parent-run reconciliation or composed UI qualification is claimed.
Packet 1 remains unchecked until its sandbox evidence is supplied; Packets 2–5
remain outstanding. See [entry-readiness.md](entry-readiness.md) and the
[adapter contract/invocation](../../../infra-automation/github-adapter-v1.md).
