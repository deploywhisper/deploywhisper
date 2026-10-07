---
title: 'Remediate confirmed supply-chain and SAST vulnerabilities'
type: 'bugfix'
created: '2026-10-07'
status: 'done'
baseline_commit: '7a5fbd8d3ed25fcf634188c4109758eca52efb89'
context: ['_bmad-output/project-context.md']
---

<frozen-after-approval reason="user explicitly authorized ordered remediation directly on develop">

## Intent

**Problem:** The integrated Scorecard reports 21 advisories, no dependency-update tool and broad workflow write permissions. Current frontend audit confirms vulnerable packages; GitHub also reports source-level CodeQL findings that need evidence-backed triage. Green scanner execution cannot be treated as repaired security posture.

**Approach:** Map each advisory and source alert to current code, repair confirmed risks while retaining existing product behavior, then configure dependency updates and restrict workflow privileges. Validate the complete application and scanner paths. Keep scope to these explicitly authorized hardening goals and execute in the requested order.

## Boundaries & Constraints

**Always:** Work on `develop` as explicitly requested, overriding normal short-lived branch guidance for this task. Preserve local-first/advisory-first behavior, API schemas, canonical analysis and UI design. Use existing dependencies and helpers. Record confirmed, stale and false-positive findings separately with evidence. Keep repository secrets out of logs/artifacts. Lock behavior with regressions before security code edits. Maintain developer docs and tracking artifacts. Future updates need CI/review; no automatic merge of dependency changes.

**Ask First:** A destructive repository/data change, an incompatible API or product-policy change, or extra runtime dependency without a verified remediation need. No such change is currently required.

**Never:** Dismiss alerts merely to increase a badge, invent independent approvals, weaken scanners/tests, persist secrets or alter branch protection. Do not claim a numeric score increase before a fresh published report. Remote pushes require completing review and verification first; current scope is implementation and proper tests.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Affected package | Locked version within advisory range | Resolve patched compatible dependency and synchronized lock | Audit/build/test failure blocks completion |
| Historical alert | Package absent from current manifest | Record obsolete dependency evidence | Do not suppress active current risks |
| Source alert | Untrusted input crosses security boundary | Validate/escape/block at boundary with regression | Malicious input rejected without exposing secrets |
| Benign artifact | Safe local content | Existing rendering, parsing and review still work | Preserve response/schema contracts |
| Automated updates | Python/npm/action manifests | Weekly updates target develop under normal review | No auto-merge or broad bot token |
| Release/analytics | Workflow needs publication | Write privileges only on responsible jobs | No GitHub token forwarded to unrelated metrics endpoint |

</frozen-after-approval>

## Code Map

- `frontend/package.json`, `frontend/package-lock.json`, `package-lock.json` — actual current npm graph; root graph empty, frontend affected.
- `requirements.txt`, `pyproject.toml` — pinned Python runtime; initial pip-audit reports zero vulnerabilities.
- `services/content_security.py`, `services/report_service.py`, `services/artifact_snapshot_service.py`, `app.py` — source alerts and guarded artifact boundaries.
- `integrations/github/app_service.py`, `api/routes/github_app.py`, `api/routes/analyses.py` — GitHub download, error and cookie boundaries.
- `.github/workflows/ci.yml`, `release.yml`, `refresh-skill-analytics.yml`, `codeql.yml` — delivery privileges and SAST coverage.
- `scripts/refresh_skill_analytics.py` — external metrics must not receive GitHub bearer token.
- `.github/dependabot.yml` — scheduled update configuration to add.
- `tests/test_infra/`, `tests/test_services/`, `tests/test_api/`, `frontend/e2e/` — security, delivery and application verification.
- `docs/security/supply-chain-findings.md`, `docs/ci.md` — triage dispositions and operational guidance.

## Tasks & Acceptance

**Execution:**
- [x] Map all 21 Scorecard advisories and open Dependabot/CodeQL alerts to current manifests/source, severity and remedy in the security ledger.
- [x] Repair confirmed frontend vulnerabilities with compatible patched versions and lockfile; fix confirmed source risks with regression tests, record evidence for benign/synthetic cases.
- [x] Add dependency updates for Python, both npm manifests and GitHub Actions targeting develop; add CI audit coverage for npm graph and regression for update configuration.
- [x] Minimize CI/release/analytics default and job permissions; fix external analytics token boundary; preserve release/publication contracts with tests.
- [x] Verify current all-language SAST coverage and pin flagged third-party workflow actions to verified upstream commits; explain historical-score limits.
- [x] Run dependency audits, Ruff/type checks, actionlint, full local CI, exact API/CLI/infra shard, production frontend tests/build and composed-app Playwright with isolated synthetic data; review final diff and record results.

**Acceptance Criteria:**
- Given current dependency manifests, when audits run, then no confirmed known vulnerability remains and all original advisory IDs have a recorded disposition.
- Given untrusted source inputs, when guarded paths execute, then confirmed vulnerabilities are blocked while existing safe behavior passes regressions.
- Given dependency update configuration, when a scheduled check runs, then supported ecosystems can propose reviewed updates to develop without granting runtime write privileges.
- Given release, CI and analytics workflows, when tasks run, then only publication jobs hold necessary write scopes and external metrics receive no GitHub credential.
- Given the rebuilt composed app, when browser tests exercise report/history/settings/security flows, then existing end-to-end behavior passes without operator data mutation.

## Spec Change Log

## Design Notes

SAST 7 reflects recent merged PR scan history, not missing current source languages. Preserve all three extended-query matrices and actual output provenance; direct develop work cannot manufacture independent PR review history. Dependency fixes should use compatible versions without `--force`. The stale root alerts must be distinguished from frontend advisories still present.

## Verification

- Python/root/frontend dependency audits: zero confirmed current vulnerabilities.
- Focused boundary/workflow tests and `./.venv/bin/ruff check .`, `ruff format --check .`, actionlint: pass.
- `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh`, affected pytest shard: pass.
- Frontend typecheck/unit/build, isolated compose health, `BASE_URL=http://localhost:8080 npm run test:ui-review`: pass.
- Final BMad layered review and documentation evidence before completion.

## Implementation and Review Record

- User-authorized direct develop work; starting tree clean at `7a5fbd8`. No branch settings, approvals, remote alerts or runtime secrets changed.
- Advisory triage mapped all 21 IDs and verified severity/ranges using official OSV records; five open root Dependabot alerts concern absent packages. Compatible frontend resolution repaired all affected package families, without forced major updates or overrides. Root/frontend npm audits and Python requirements audit report zero known vulnerabilities.
- Confirmed source fixes: PBKDF2 password hashing with legacy upgrade; two redaction backtracking paths; fixed webhook errors; contained artifact storage; in-memory browser fixtures. Supported false-positive dispositions and limits are recorded in `docs/security/remediation-2026-10-07.md`.
- Added weekly reviewed updates, npm CI audits, job-scoped writes and SHA-pinned actions. External popularity metrics receive no GitHub Authorization header; issue search retains authentication. Release metadata dependency corrected. Reused existing helpers and standard-library crypto; no new application dependency.
- Three independent review layers completed. Blind: no introduced defect. Edge: valid legacy authentication could fail when upgrade writes fail; regression reproduced and patch now catches bounded DBAPI errors with generic logging, preserving access and rollback. Edge recheck clean. Acceptance: missing advisory severity column corrected from OSV; no implementation deviation. No unresolved review finding remains.
- Final full local CI: **1,794 tests run across nine directories; all suites passed**, with one optional live-provider skip. Final smoke: **510 tests**, one optional skip. Frontend typecheck, **56 unit tests**, production build, Ruff lint/format (**297 Python files**) and actionlint across all workflows passed. Dependency consistency/compilation/Skill gates and high-severity Bandit gate passed; existing medium sample-data B104 remains unchanged.
- Production browser verification: isolated `deploywhisper-hardening` Compose project on `http://localhost:8080`, fresh synthetic database, all **17 Playwright tests passed, zero browser skips**, including connector and provider mutation fixtures. Tests cover redaction, artifact review, report/history/dashboard, settings, incidents, skills, keyboard/a11y and provider persistence behavior. Five screenshots retained under `frontend/test-results`. Original app restored healthy; only the disposable test volume removed.
- Strict local mypy: **312 existing errors** on both baseline and final source, **zero introduced errors** after comparing normalized diagnostic multisets using shadowed baseline files. This is a pre-existing, nonblocking CI lane; no claim of a clean repository type check. Tool installed in local dev environment only.
- Logs/evidence: `/private/tmp/deploywhisper-hardening-final-{ci,smoke,e2e}.log`; final shard **447 passed +193 subtests**; root/frontend/Python audit JSON; baseline/current mypy logs and comparison. No live exploit or malicious upload performed.
- Remaining publication limits: a push/default-branch scan is required to refresh Scorecard and GitHub alert state. No numeric score increase or automatic alert closure claimed. Existing password hashes upgrade on successful authentication/reconfiguration; opportunistic migration failures retry on a later login. Storage root/local filesystem remains trusted. Branch/review policy and Story 12.6 signing remain separate owned follow-ups under #131.

## Suggested Review Order

**Dependency remediation**

- Patched compatible dependency graph; no forced major-version upgrades.
  [package-lock.json:1](../../frontend/package-lock.json#L1)

**Password boundary**

- Versioned PBKDF2 and retryable legacy migration preserve authenticated access.
  [report_service.py:469](../../services/report_service.py#L469)

**Content boundary**

- Disjoint alternatives avoid costly backtracking while preserving redaction.
  [content_security.py:41](../../services/content_security.py#L41)

**Storage and errors**

- Reject traversal and symlink escapes before filesystem access.
  [artifact_snapshot_service.py:37](../../services/artifact_snapshot_service.py#L37)

- Return fixed public messages rather than arbitrary exception details.
  [github_app.py:148](../../api/routes/github_app.py#L148)

**Delivery**

- Keep GitHub credentials out of public external metrics requests.
  [refresh_skill_analytics.py:112](../../scripts/refresh_skill_analytics.py#L112)

- Grant publication writes only to responsible jobs.
  [release.yml:27](../../.github/workflows/release.yml#L27)

**Supporting checks**

- Propose weekly reviewed ecosystem updates against develop.
  [dependabot.yml:1](../../.github/dependabot.yml#L1)

- Lock updater coverage, token boundaries and delivery permissions.
  [test_supply_chain_remediation.py:1](../../tests/test_infra/test_supply_chain_remediation.py#L1)

- Review evidence-backed advisory and source dispositions.
  [remediation-2026-10-07.md:1](../../docs/security/remediation-2026-10-07.md#L1)

Final affected CI shard: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -q --tb=short` — **447 passed +193 subtests**. Log: `/private/tmp/deploywhisper-hardening-final-shard.log`. All implementation tasks and review patches complete; local commit on user-authorized develop.

## Published Outcome — 2026-10-07

User subsequently authorized publishing/running workflows to increase and verify the public score. Commit `9190270` was pushed to `develop`; the previous manual scan had used old remote commit `7a5fbd8`. Publisher run `37585646199` succeeded and the official API/badge both verified **6.7/10**, up from **4.2/10**, at `2026-10-07T07:09:53Z`. Vulnerabilities, Dependency-Update-Tool and Token-Permissions are now 10; Pinned-Dependencies is 4. Full CI `37585645478` and CodeQL `37585645462` on the published source both passed. The accompanying evidence commit changes documentation only. Remaining branch/review/signing/pinning and other controls stay owner-tracked; no remote source alert was dismissed to obtain this result.
