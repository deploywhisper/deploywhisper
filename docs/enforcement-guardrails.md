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

| Mode | Workflow effect | Appropriate use |
| --- | --- | --- |
| `advisory` | Reports the analysis without blocking. | Default, initial rollout, incomplete context, or an uncalibrated project. |
| `warn` | Makes the policy warning visible without blocking. | Teams have reviewed signal quality and want consistent reviewer attention. |
| `soft-block` | When the effective status reaches `soft-block`, the GitHub Action exits nonzero and the GitHub App check conclusion is `action_required`. | Every blocking prerequisite below is satisfied, and a human-owned exception or approval path has been exercised. |
| `hard-block` | When the effective status reaches `hard-block`, the GitHub Action exits nonzero and the GitHub App check conclusion is `failure`. | Every blocking prerequisite below is satisfied, and the organization has approved strict enforcement for this scope. |

A mode-table row describes runtime behavior, not sufficient readiness criteria.
Both blocking modes require the complete prerequisites and rollout checklist in
this guide. A required workflow remains blocked until the policy conditions
change or an authorized human follows the documented exception procedure.

The configured mode is a ceiling, not a severity override. Integrations must
consume the shared enforcement decision and must not infer blocking from risk
score, severity, recommendation, or narrative text. If any prerequisite below
is missing, keep the integration in `advisory` or `warn`.

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

## Treat an unavailable decision as an operational failure

An enforcement decision that is unavailable, timed out, stale or mismatched to
the report, or malformed must never be reported as a pass. Do not fabricate an
`advisory` result, reuse a prior decision, or derive a replacement from score,
severity, recommendation, or narrative text.

The current GitHub Action exits nonzero when it cannot retrieve and validate
the shared decision. The GitHub App reports a failed enforcement result when
its configured decision cannot be validated and check delivery succeeds.
Future consumers must surface a distinct operational error, stop the
enforcement-dependent automation, and require documented human disposition
under the organization's outage or break-glass procedure. Failure handling
must not become autonomous approval or remediation.

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

The decision record should identify the corpus and release evaluated, plus the
minimum acceptable precision and recall, maximum acceptable false-reassurance
and false-positive rates, minimum evidence coverage, zero Evidence Law
violations, an unsupported-scenario limit, and a regression-stability
tolerance. A nonzero Evidence Law violation count fails the blocking
prerequisite; it is not an organization-configurable tolerance. The record
should also identify who approved the thresholds and when they must be reviewed
again.

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
3. Evidence Law, context freshness, and audit-retention expectations.
4. Named human owners for review, exceptions, incident response, and rollback.
5. A tested rollback or forward-fix path and a time-bounded break-glass
   procedure.
6. Monitoring for false reassurance, false positives, regressions, and
   excessive overrides.
7. A review date and a trigger for returning to `warn` or `advisory`.

Enable one integration and scope at a time. Observe real outcomes before
expanding enforcement. Changing a mode does not change the canonical report;
it changes only how that integration consumes the separate policy decision.

See [Workflow Adapter Output Contract](./workflow-adapter-output-contract.md)
for the decision fields and settings precedence, and [Benchmark Corpus and
Runner](./benchmarks/corpus.md) for the available benchmark evidence. Use
[Deployment Outcome Linking](./outcome-linking.md) when production outcome data
supplements the synthetic corpus.
