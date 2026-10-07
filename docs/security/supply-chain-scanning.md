# Scorecard and CodeQL

Story 12.4 provides repository security checks alongside the existing dependency,
Bandit, secret-pattern and test gates. These scans inspect repository source and
GitHub configuration. They do not upload operator databases, IaC uploads,
incident exports or provider credentials.

## Workflows and result locations

| Workflow | Coverage | Maintainer results |
| --- | --- | --- |
| [CodeQL](../../.github/workflows/codeql.yml) | Python, JavaScript/TypeScript and GitHub Actions; extended security queries | Security → Code scanning, PR annotations, per-language SARIF artifacts and the analysis job summary |
| [OpenSSF Scorecard PR](../../.github/workflows/scorecard.yml) | Local PR supply-chain checks | Security → Code scanning, `scorecard-sarif` SARIF artifact and the analysis job summary |
| [Scorecard publisher](../../.github/workflows/scorecard-publish.yml) | Full default-branch repository posture and public badge | Security → Code scanning, `scorecard-repository-sarif`, the official Scorecard API/viewer and README badge |

CodeQL and PR-local Scorecard run on ordinary pull requests targeting
`develop`/`main`. CodeQL and the separate Scorecard publisher also run on trusted
branch pushes, a weekly schedule and manual dispatch. Actions are pinned to reviewed
full commit SHAs, tokens are job-scoped, and checkout does not persist credentials.
CodeQL uses `build-mode: none`; no project installation, build or test command
runs in its analysis job. Runtime dependencies and product behavior are unchanged.

Scorecard accepts non-PR events only on the repository default branch. Its publishing job
therefore skips manual dispatch or push on a non-default ref. The current default
is `develop`; the guard follows GitHub's default-branch metadata if this changes.
PR Scorecard mode inspects the checked-out directory. Hosted settings checks are
unavailable in that mode and a successful PR run does not establish the full
repository posture. Full repository mode begins on default-branch pushes or its
schedule after the workflow is integrated. GitHub documents PR/dispatch support
as experimental in Scorecard; workflow execution in fork repositories is unsupported.

PR-local Scorecard publication remains disabled (`publish_results: false`) and
that job has no OIDC permission. The user-requested README badge uses a separate
single-job publisher with `publish_results: true` and job-scoped `id-token: write`
only on the non-fork default branch. Publication uses only approved SHA-pinned
actions; no environment/default overrides, services, shell steps or repository
scripts run in that workflow. A PAT or new repository secret is not required.
The badge will reflect the scan only after the first default-branch publishing run;
PR-local SARIF and the CLI baseline cannot populate that public badge.
A missing/failed analysis stays a failed check;
an unavailable Scorecard check is unknown, not a passing control.

## Maintainer review and follow-up

Review new results after each default-branch scan and at least weekly. The
repository maintainer listed in [MAINTAINERS.md](../../MAINTAINERS.md) owns triage.
Use the tool's findings and individual checks rather than the aggregate score or
a green workflow exit.

1. For CodeQL, start with Critical/High **security severity**, inspect the
   source-to-sink evidence and affected branch, and distinguish production paths
   from intentionally synthetic tests. Keep genuine vulnerabilities open until
   remediation is verified by a new scan. Follow [SECURITY.md](../../SECURITY.md)
   for private disclosure; do not paste exploit or credential details into a
   public issue.
2. For Scorecard, prioritize `Dangerous-Workflow` and `Webhooks` (Critical), then
   `Token-Permissions`, `Branch-Protection`, `Code-Review`, `Vulnerabilities` and
   `Dependency-Update-Tool` and `Signed-Releases` (High). A score below 10 warrants review; a score of
   -1 means the check was unavailable. `SAST` and `Pinned-Dependencies` are Medium but also
   deserves follow-up when mutable action references remain.
3. Every high-priority finding needs an assigned follow-up issue (private where
   required) or an evidence-backed accepted rationale. Record the rule/check,
   severity, scan commit/run, owner, disposition, issue or rationale, next review
   date and verification result in the [findings ledger](supply-chain-findings.md).
   CodeQL dismissals must also retain the corresponding GitHub dismissal reason.
4. Do not waive findings because a scanner lacks permission. Scorecard's default
   token can inspect repository rulesets, while classic branch protection may
   require additional administration access. Record this as a coverage limit
   and have the maintainer verify settings. Do not add a broad PAT to CI merely
   to improve the displayed score.

SARIF artifacts are retained for a bounded period configured in each workflow.
Scorecard report filenames bind to the immutable checkout SHA, workflow run ID
and attempt, so checkout-supplied `results.sarif` or a previous run's output
cannot masquerade as fresh evidence. PR artifact/code-scanning uploads also
require a successful scanner step. The restricted publisher can retain a fresh
report after publication fails, without repository cleanup scripts or accepting
old checkout data. Workflow regressions exercise both failure phases.
Download them from the run's Artifacts section when troubleshooting or reviewing
details absent from annotations. Missing artifacts on a failed analysis are not
evidence that no vulnerabilities exist. Code-scanning upload failures must be
resolved rather than hidden by `continue-on-error`.

The baseline disposition regression covers Critical as well as High checks,
including failed or unknown `Dangerous-Workflow` and `Webhooks` results. Its
negative fixtures require an owned disposition; positive fixtures verify valid
follow-up rows are accepted.

## Verification and operation

Local checks cover triggers, permissions, action pinning, categories, retained
results and safe PR behavior:

```bash
./.venv/bin/python -m unittest discover -s tests/test_infra -p 'test_supply_chain_workflows.py' -q
bash scripts/ci-local.sh
```

Validate GitHub execution on an ordinary draft PR: all three CodeQL matrix jobs
and PR-local Scorecard must finish and retain SARIF. Verify code-scanning analyses
through the repository Security tab. Workflow dispatch is available only once
the publishing workflow is registered on the default branch; select that branch
for a full Scorecard scan and badge refresh. Default-branch repository-mode verification is distinct from
PR-local validation and must be recorded after integration.

For a full pre-integration repository baseline, maintainers may run the official
Scorecard CLI against `github.com/deploywhisper/deploywhisper` with a read-scoped
token supplied only through its supported environment variable. Inspect the
result locally, avoid printing or saving the token, and record the baseline
commit/coverage limits in the ledger. This is not a substitute for verifying the
default-branch workflow after merge.

## Upstream references

- [Official Scorecard action and restrictions](https://github.com/ossf/scorecard-action)
- [Scorecard check definitions and risk levels](https://github.com/ossf/scorecard/blob/main/docs/checks.md)
- [CodeQL advanced workflow options](https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options)
- [CodeQL SARIF upload permissions on PRs](https://docs.github.com/en/code-security/reference/code-scanning/troubleshoot-analysis-errors/resource-not-accessible)
- [Assessing CodeQL alerts](https://docs.github.com/en/code-security/how-tos/manage-security-alerts/manage-code-scanning-alerts/assess-alerts)
