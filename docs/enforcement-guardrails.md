# Enforcement Guardrails

DeployWhisper's canonical report is always advisory. An integration may turn a
separate policy interpretation into a warning or blocking workflow result only
after an authorized operator explicitly configures either its
integration-specific override or the project-level default it inherits. The
adapter decision is a review control; it is not a safety certificate,
deployment approval, or remediation instruction.

Use this guide before changing an integration from `advisory` or `warn` to
`soft-block` or `hard-block`.

## Choose the least forceful mode that works

| Effective status | Workflow effect | Appropriate use |
| --- | --- | --- |
| `advisory` | GitHub Action exits `0` after a valid decision; GitHub App reports `success` for `GO` and `neutral` otherwise. | Default, initial rollout, incomplete context, or an uncalibrated project. |
| `warn` | GitHub Action exits `0` after a valid decision; GitHub App reports `neutral`. | Teams have reviewed signal quality and want consistent reviewer attention. |
| `soft-block` | GitHub Action exits nonzero; GitHub App reports `action_required`. | Every blocking prerequisite below is satisfied, and a human-owned exception path has been exercised. |
| `hard-block` | GitHub Action exits nonzero; GitHub App reports `failure`. | Every blocking prerequisite below is satisfied, and the organization has approved strict enforcement for this scope. |

A mode-table row describes runtime behavior, not sufficient readiness criteria.
Both blocking modes require the complete prerequisites and rollout checklist in
this guide. A required workflow remains blocked until the policy conditions
change or an authorized human follows the documented exception procedure.

The table is keyed by the decision's effective status, not its configured mode.
The configured mode is a ceiling, not a severity override: `advisory` always
produces effective `advisory`; `warn` permits effective `advisory` or `warn`;
`soft-block` permits effective `advisory`, `warn`, or `soft-block`; and
`hard-block` preserves any raw status. Integrations must consume the shared
enforcement decision and must not infer blocking from risk score, severity,
recommendation, or narrative text. If any prerequisite below is missing, keep
the integration in `advisory` or `warn`.

An installed Action ref must expose the `policy-status`, `configured-mode`,
`effective-status`, and `should-block` outputs and must consume
`/enforcement-decision` before it can enforce these modes. Older Action refs
remain advisory-only even if the server has blocking settings.

For a required enforcement workflow, pin the Action to an immutable reviewed
commit SHA rather than a moving major tag. Before making it required, run a
synthetic fail-closed smoke test against that exact SHA: prove a valid
non-blocking decision passes, a valid blocking decision fails, and an
unavailable or malformed decision fails as an operational error.

## Wire blocking into the protected workflow

A blocking adapter result only controls delivery when its GitHub check or
workflow job must succeed. The selected check must be a required status check
or required job in the repository or deployment protection rules and must be
bound to the expected GitHub App or workflow source. Do not rely on the check
name alone when protection settings can restrict its source. The Action step
and its containing job must not use `continue-on-error: true`, and later jobs
must not ignore or replace its failed result.

Test the protected branch or environment with a synthetic blocking result and
an authorized exception before rollout. If the change can still merge or
deploy, the integration is not operating as a block regardless of its reported
mode.

## Review inherited settings before changing scope

Project-level settings are inherited by every integration that has no
integration-specific override. Treat a project-level enforcement change as a
change to every inheriting CI, GitHub, and future adapter: inventory those
consumers, verify their owners and prerequisites, and communicate the rollout
before saving the new mode.

Deleting an integration override immediately exposes the project default,
which may be more restrictive and may begin blocking that integration. Inspect
the effective project mode and complete the same review before deleting an
override. Do not assume that reset means `advisory`.

The same risk applies when a new integration is added after a project default
has become blocking. Create an integration-specific `advisory` override before
onboarding a new consumer, then complete this guide for that consumer before
raising its mode. If an override is intentionally omitted, record that the
project default and its completed guardrail review apply to the new integration.

After any mode, threshold, override, or protection-rule change, invalidate or
rerun the protected result for every open pull-request head and pending
deployment in scope. A result produced under earlier settings is not evidence
that the current enforcement configuration evaluated that commit.

## Treat an unavailable decision as an operational failure

An enforcement decision must be rejected for an HTTP or transport failure,
non-JSON or missing data, unsupported contract or status values, report or
integration mismatch, and any decision-invariant failure. These conditions
must never be reported as a pass. Do not fabricate an `advisory` result, reuse
a prior decision, or derive a replacement from score, severity,
recommendation, or narrative text.

A decision is current only when the consumer retrieves
`/enforcement-decision` for the report ID immediately before publishing the
protected result and verifies the response's integration/project scope and
complete nested `applied_settings` snapshot. The current contract exposes no
report or settings revision token, so consumers must not cache decisions or
invent one. For reproducible audit identity, retain the original JSON response
and a SHA-256 digest of its canonical serialization. Treat a decision as stale
after the report ID, integration scope, project or integration settings,
enforcement consumer, or protected commit changes. Retrieve a new decision and
rerun the protected workflow; do not reuse a previously passing check.

Sensitive, unsupported, or otherwise excluded artifacts do not produce a policy
decision. In a blocking workflow, a missing decision must not be accepted as an
enforcement pass. Surface the excluded scope, stop enforcement-dependent
automation, and require documented human disposition or a protection-layer
bypass. The current GitHub App reports `neutral` when intake has no analyzable
artifact, and GitHub may treat `neutral` as satisfying a required check. Do not
use that App check as the sole blocking control for a scope where exclusions can
occur; add a separate required intake-coverage control that fails on a missing
decision, or keep the integration non-blocking.

The current GitHub Action exits nonzero when it cannot retrieve and validate
the shared decision. The GitHub App reports a failed enforcement result when
its configured decision cannot be validated and check delivery succeeds.
Future consumers must surface a distinct operational error, stop the
enforcement-dependent automation, and require documented human disposition
under the organization's outage or break-glass procedure. Failure handling
must not become autonomous approval or remediation.

A protection-layer bypass does not change the DeployWhisper decision and does
not require an unchanged analysis rerun to pretend that the result changed.
Prefer a report- and integration-scoped protection bypass approved by a human;
record the failed decision and the separate bypass event. If the organization
instead authorizes a temporary settings change, use the narrowest
integration-specific override, freeze other deliveries in the affected scope,
record the original settings, apply the approved mode, retrieve a new decision,
and rerun the workflow. Restore the original settings at expiry and require
fresh protected results for every open commit before lifting the freeze.

The audit record must retain the invocation timestamp, report ID, original
decision payload and its canonical SHA-256 digest, integration and project
scope, complete `applied_settings` snapshot, raw policy status, configured and
effective modes, approver, reason, expiry, and bypass mechanism. For a
protection-layer bypass, record the protected-delivery or bypass event; for a
temporary settings change, record the replacement workflow run. Review
repeated exceptions as a calibration signal.

## Evidence Law is a prerequisite, not an approval

No high or critical finding may drive enforcement without deterministic
evidence. Reviewers must be able to trace the finding to the changed artifact,
resource, operation, and available project context. Narrative text, an LLM
explanation, an external scanner label, or an incident similarity score is not
a substitute for that evidence.

Before enabling a blocking mode:

- verify that high and critical findings satisfy the Evidence Law;
- inspect the referenced evidence, not only the summary or check conclusion;
- treat missing, partial, stale, or conflicting context as a reason for human
  investigation;
- keep the canonical severity, evidence, findings, uncertainty, and policy
  reasons available in the audit trail.

`Satisfied` means the report met the evidence contract. It does not mean the
change is correct, complete, authorized, or safe to deploy.

The built-in Evidence Law specifically governs high and critical findings.
Blocking thresholds below `high` do not receive an additional Evidence Law
guarantee. The current shared decision contract cannot apply an additional
deterministic-evidence gate below `high`. Keep lower thresholds non-blocking.
A future consumer may block below `high` only after a separate, documented,
tested gate is implemented in the shared decision path and requires
deterministic evidence for every signal that can produce `should_block=true`.

## Set benchmark thresholds before blocking

DeployWhisper does not define a universal numeric threshold for enabling
blocking modes. Each organization must approve thresholds for its own change
types, environments, risk tolerance, and representative benchmark corpus.
Until those thresholds exist and are met, use `advisory` or `warn`.

The current benchmark runner emits scenario-level results and honest-failure
categories; it does not emit a universal enforcement-readiness score or
precomputed precision, recall, false-reassurance, or false-positive rates.
Capture the runner JSON, corpus ID and version, sample size, scenario labels and
change classes, supported and unsupported counts, and every exclusion. If the
organization calculates rates from those results or from deployment outcomes,
document the formulas and denominators so the decision can be reproduced.

Define ground-truth labels and the mapping from scenario or production outcomes
to true positives, false positives, true negatives, false negatives, false
reassurance, and unsupported results before calculating rates. Record exclusion
rules and zero-denominator handling. The organization must approve minimum
positive and negative sample sizes for every covered change class and a stated
statistical confidence method; a tiny or undefined sample cannot authorize
blocking merely because its observed rate is perfect.

The decision record must identify the corpus and immutable application and
Action revisions evaluated, including the application commit or image digest,
Action commit SHA, dependency-lock identity, and configuration or feature flags.
It must also record the minimum acceptable precision and recall, maximum
acceptable false-reassurance and false-positive rates, minimum evidence
coverage, zero Evidence Law violations, an unsupported-scenario limit, and a
regression-stability tolerance. A nonzero Evidence Law violation count fails
the blocking prerequisite; it is not an organization-configurable tolerance.
The record should also identify who approved the thresholds and when they must
be reviewed again. Verify that the deployed application and Action revisions
match those evaluated artifacts before enabling or retaining enforcement.

Rerun the benchmark gate after behavior-affecting changes to parsers, evidence
extraction, scoring, policy interpretation, the benchmark corpus, or relevant
context connectors. Reapproval is required when the new result falls outside
any recorded threshold or introduces a new miss, unsupported scenario,
regression, or Evidence Law violation.

Do not hide misses behind one aggregate pass rate. Review the honest-failure
report, including scenarios missed, false reassurance, false positives,
unsupported cases, context limitations, and regressions. A material miss in a
change class that the integration will block or pass is a reason to delay or
narrow enforcement.

## Blocking does not prove a change is safe

A passing check can still be false reassurance. DeployWhisper can miss a risk
when a parser does not cover a construct, topology or ownership context is
missing or stale, an incident is absent from the index, a scanner input is
unavailable, or a novel interaction is outside the benchmark corpus.

Treat a pass as one review signal. Continue to apply code review, policy,
security scanning, change-management, testing, and deployment controls. Track
deployment outcomes and reviewer feedback so false reassurance and false
positives can be measured. If signal quality regresses, return the integration
to `warn` or `advisory` while the gap is investigated.

## Human review remains mandatory

No adapter output authorizes autonomous approval, deployment, or remediation.
An authorized human remains responsible for the deployment decision and must
review the underlying change, deterministic evidence, uncertainty, context
gaps, policy reasons, and operational impact.

Require explicit human review when:

- the effective status is `soft-block` or `hard-block`;
- a high or critical finding is present;
- Evidence Law status, context completeness, ownership, or topology freshness
  is uncertain;
- scanners and DeployWhisper disagree;
- the change is novel, production-sensitive, or outside the benchmark corpus;
- an exception, override, or break-glass path is requested.

Automation may route the report, request reviewers, or enforce an approved
check. It must not approve the change, apply a fix, deploy infrastructure, or
close the review on a person's behalf.

Configure repository review rules or protected-environment approvals so an
authorized human decision is an observable prerequisite for merge or
deployment. An automated required check by itself does not satisfy the human
review requirement.

## Rollback remains an operator responsibility

DeployWhisper may describe rollback steps and complexity, but DeployWhisper
does not execute, validate, or own the rollback. The service owner and release
operator remain accountable for recovery planning and execution.

Before making an integration blocking, verify that:

- the rollback or forward-fix procedure is current, tested, and appropriate
  for the affected environment;
- backups, state, credentials, tooling, and authorized responders are
  available;
- monitoring and stop conditions can detect a failed or harmful rollout;
- the approval path names who may accept risk or use break-glass;
- override use is time-bounded, logged, reviewed, and followed by corrective
  work.

A generated rollback plan must be reviewed against the actual deployment
system. Never auto-execute it from an adapter decision.

## Rollout checklist

Record the following before enabling `soft-block` or `hard-block` for an
integration:

1. The integration key, project scope, repositories, environments, and change
   classes covered.
2. The approved benchmark report and thresholds, including known misses and
   unsupported scenarios.
3. Evidence Law, decision and context freshness, and audit-retention expectations.
4. Named human owners for review, exceptions, incident response, and rollback.
5. A tested rollback or forward-fix path and a time-bounded break-glass
   procedure.
6. Monitoring for false reassurance, false positives, regressions, and
   excessive overrides.
7. Immutable application and Action revisions plus proof that deployed artifacts
   match the benchmarked build.
8. Repository review or protected-environment rules that require human approval.
9. A review date and a trigger for returning to `warn` or `advisory`.

Enable one integration and scope at a time. Observe real outcomes before
expanding enforcement. Changing a mode does not change the canonical report;
it changes only how that integration consumes the separate policy decision.

See [Workflow Adapter Output Contract](./workflow-adapter-output-contract.md)
for the decision fields and settings precedence, and [Benchmark Corpus and
Runner](./benchmarks/corpus.md) for the available benchmark evidence. Use
[Deployment Outcome Linking](./outcome-linking.md) when production outcome data
supplements the synthetic corpus.
