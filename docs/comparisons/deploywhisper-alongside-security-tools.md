# DeployWhisper Alongside Security Tools

DeployWhisper does not replace scanners. Keep SAST, SCA, container, secrets,
CSPM, policy-as-code, and IaC scanners in the workflow for the vulnerability,
misconfiguration, policy, and inventory classes they already cover.
DeployWhisper consumes selected scanner output as external evidence, then adds
deployment context: blast radius, rollback readiness, topology freshness,
incident memory, ownership, confidence, uncertainty, and an advisory briefing
for the change under review.

Deployment context is DeployWhisper's domain: what changed, where it is being
deployed, what depends on it, how fresh the supporting context is, and how hard
rollback will be if the deployment fails.

## Responsibility Split

| Responsibility | Scanners and policy tools | DeployWhisper |
| --- | --- | --- |
| Primary question | Does this code, dependency, image, cloud resource, or policy violate a known rule? | What does this deployment change mean in its project, workspace, topology, rollback, and incident context? |
| Best inputs | Source code, dependencies, container images, IaC, cloud inventory, policy bundles, baseline scanner rules. | IaC diffs, Terraform plans, Kubernetes manifests, scanner output, topology, ownership, incidents, deployment outcomes, and project/workspace metadata. |
| Output ownership | Rule IDs, scanner severity, vulnerability metadata, policy pass/fail, remediation text. | Evidence-backed deployment briefing, advisory severity, recommendation, conflict context, confidence, and next verification steps. |
| Enforcement fit | Use scanner gates for known vulnerability, policy, and secret classes. | Use DeployWhisper for deployment-specific risk briefing and human review context. |

External scanner evidence is review context. It can enrich a report, support a
finding when combined with deterministic DeployWhisper evidence, and explain why
reviewers should investigate. But scanner severity alone must not become a high
or critical DeployWhisper finding. High and critical DeployWhisper findings
still require Evidence Law-backed deterministic evidence and scoring.

## Ingestion Setup

DeployWhisper currently documents two scanner ingestion paths:

- SARIF 2.1.0: `POST /api/v1/scanner-imports/sarif`
- Semgrep native JSON: `POST /api/v1/scanner-imports/semgrep`

Each import should include a project scope such as `project_key` or
`project_id`. Use `workspace_key` or `workspace_id` when the scanner result
belongs to a specific environment, deployment lane, or workspace. DeployWhisper
stores normalized scanner fields such as tool, rule, severity, location,
source identity, and bounded report-safe metadata. Raw scanner artifacts and
arbitrary scanner-defined fields stay outside the persisted report contract.

Use [Scanner Imports](../scanner-imports.md) for endpoint payloads, validation
rules, supported scanner fields, and local-first boundaries. Use
[CI Advisory Consumption](../ci-advisory-consumption.md) when wiring scanner
context into PR comments, CI annotations, or workflow summaries.

## Conflict Handling

DeployWhisper does not silently choose one source when scanner output conflicts
with deterministic evidence or context. Reports expose conflicts through
`share_summary.json_payload.scanner_conflicts`. Each conflict should preserve:

- scanner source and deterministic evidence source
- scanner freshness and deterministic context freshness
- confidence impact
- recommended verification

Reviewers should treat conflicts as investigation prompts, not automatic
severity overrides. If scanner output is current but DeployWhisper context is
stale, refresh topology or runtime context before acting. If DeployWhisper has
strong deterministic evidence but scanner output is stale or scoped to the
wrong workspace, keep the scanner result visible while prioritizing the fresh
deployment evidence.

## Team Usage

AppSec teams should keep scanner ownership for rule tuning, vulnerability
triage, policy exceptions, and scanner-specific remediation. DeployWhisper can
show which scanner signals matter for a deployment, whether they affect a
critical service, and which verification step would reduce uncertainty.

Platform teams should import scanner findings into the same project/workspace
scope used for reports, topology, ownership, and workflow summaries. That keeps
scanner context from leaking across projects and gives reviewers one briefing
instead of a separate scanner tab, plan diff, topology view, and incident search.

SRE teams should use DeployWhisper to connect scanner output to operational
blast radius, rollback complexity, stale context, incidents, and deployment
history. A scanner can say a rule fired; DeployWhisper should explain whether
the deployment context makes that signal urgent, uncertain, or lower priority.

## Examples

### Scanner reports critical public ingress

An IaC scanner reports critical public ingress in a security group change.
DeployWhisper should label the scanner result as external evidence, inspect the
deployment artifact and topology context, and explain whether the changed
resource fronts a critical service, has stale topology, or needs owner review.
If deterministic evidence supports exposure, the briefing can elevate the
deployment risk under DeployWhisper scoring. If deterministic evidence is
missing, the scanner signal remains visible without becoming high or critical
by itself.

### Scanner reports no issue, but DeployWhisper flags high rollback risk

A scanner passes the change because no vulnerability or policy rule fires.
DeployWhisper may still flag high deployment risk if a Terraform plan replaces
stateful infrastructure, rollback steps are complex, topology shows downstream
dependencies, or incident history suggests similar changes failed. Scanner
success does not clear deployment risk.

### Scanner output is stale

A SARIF or Semgrep result is imported from an older branch or workspace.
DeployWhisper should surface freshness and scope uncertainty instead of hiding
the scanner result or treating it as current proof. Reviewers should rerun the
scanner in the correct project/workspace, refresh live context when needed, and
then compare the updated scanner evidence with deterministic deployment
evidence.

## Operating Rules

- Keep scanners in CI and security workflows for their owned detection classes.
- Import scanner output into DeployWhisper when it helps deployment review.
- Preserve project and workspace scope for every scanner import.
- Render scanner findings as external evidence, not DeployWhisper severity
  proof.
- Preserve `share_summary.json_payload.scanner_conflicts` in PR comments and
  workflow summaries.
- Do not silently choose one source when scanner output and deterministic
  evidence disagree.
- Escalate or de-escalate only through DeployWhisper evidence, scoring,
  confidence, and human review, not through scanner severity passthrough.
