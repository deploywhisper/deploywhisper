# Enforcement Guardrails

DeployWhisper's canonical report is always advisory. An integration may turn a
separate policy interpretation into a warning or blocking workflow result only
after an authorized operator explicitly configures either its
integration-specific override or the project-level default it inherits. The
adapter decision is a review control; it is not a safety certificate,
deployment approval, or remediation instruction.

Use this guide before changing an integration from `advisory` or `warn` to
`soft-block` or `hard-block`, onboarding an integration under an inherited
blocking default, deleting an override, or expanding an existing integration to
a new scope.

GitHub Action effects in this guide apply only to an enforcement-capable
revision whose manifest exposes the four policy outputs and whose runtime has
passed the required smoke cases. The published `@v1` ref validated on
2026-09-09 does not expose those outputs and remains advisory-only; enforcement
is not a released `@v1` capability yet. Recheck the installed immutable
revision rather than relying on this dated observation.

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

Run enforcement from an immutable protected workflow. Require review ownership
for workflow changes. Keep the checkout ref, artifact selection,
`changed-files`, project and workspace scope, and working directory—along with
endpoint and integration identity—in protected configuration rather than
pull-request-controlled data. The required job must fail when the enforcement
step is skipped. The job result must be bound to the protected commit, not
merely to a reusable check name.

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
the resolved setting source and configured enforcement mode and complete the
same review before deleting an override. Do not assume that reset means
`advisory`.

The same risk applies when a new integration is added after a project default
has become blocking. Create an integration-specific `advisory` override before
onboarding a new consumer, then complete this guide for that consumer before
raising its mode. The new consumer must complete its own benchmark and
guardrail review; recording that an older project review exists is not a
substitute for evidence about the new consumer revision and scope.

Treat a new repository, environment, change class, or other scope added to an
existing integration the same way as a new consumer. Inspect the resolved
setting source and configured enforcement mode first. An integration-wide
override would also downgrade every existing scope using that integration key,
so do not use it to stage one new repository. Complete the new-scope review
before attachment, or isolate the scope behind a separate project or integration
identity that can remain `advisory` without weakening existing protections.

Limit policy-setting write access to named operators, require approval from a
different authorized reviewer for every move into or out of a blocking mode,
and retain a durable before/after audit record with actor, approver, timestamp,
scope, reason, and resolved setting source. If those ordinary settings-change
controls are unavailable, do not enable blocking.

After any mode, threshold, override, or protection-rule change, invalidate or
rerun the protected result for every open pull-request head and pending
deployment in scope. A result produced under earlier settings is not evidence
that the current enforcement configuration evaluated that commit.

## Treat an unavailable decision as an operational failure

An enforcement decision must be rejected for an HTTP or transport failure,
non-JSON or missing data, unsupported contract or status values, report or
integration mismatch, and any decision-invariant failure. HTTP consumers must
also require authenticated transport, a trusted server identity, a fixed
operator-controlled endpoint, and a least-privilege credential loaded from
protected secrets. In-process consumers must call the same trusted service
boundary. These conditions must never be reported as a pass. Do not fabricate
an `advisory` result, reuse a prior decision, or derive a replacement from
score, severity, recommendation, or narrative text.

A decision is current only when it comes from the decision path used by the
actual consumer: the enforcement endpoint for HTTP adapters or the shared
in-process enforcement service for the GitHub App. Bind the returned report ID
to the report created by that protected workflow invocation, and bind that
invocation to the protected commit SHA and submitted artifact manifest. Record
the integration/project scope and verify the complete nested `applied_settings`
snapshot. Immediately before publishing the result, verify that the protected
target identity is still current for that consumer. A PR-head workflow must
verify that its tested commit SHA equals the current PR head SHA. A merge-ref or
merge-queue workflow must bind the report to the current generated merge commit
and record its base and PR-head parents; it must not compare the synthetic commit
directly with the head. A non-PR consumer must bind the decision to its actual
protected deployment ref, commit, or immutable artifact digest. Never accept a
report ID, endpoint, target identity, or manifest from untrusted change content.

The v1 contract has no atomic settings revision or evaluate-and-publish
operation. Retrieval immediately before publication cannot eliminate a
settings-change race. Serialize policy-setting changes with enforcement runs,
freeze mutations for the publication window, and verify the returned settings
snapshot against the approved expected values. If the organization cannot
enforce that change-control boundary, keep the integration non-blocking until a
revision token or atomic contract exists. Treat a decision as stale after the
report ID, manifest, protected commit, integration scope, settings, consumer
revision, or workflow changes; rerun instead of reusing a passing check.

Sensitive, unsupported, rejected, or otherwise excluded artifacts do not
produce findings. A blocking workflow must validate complete and partial intake
coverage against the changed-file set and submitted artifact manifest; it must
not accept a decision that covers only supported siblings while silently
excluding other in-scope changes. A missing or partial decision must not be
accepted as an enforcement pass. Surface the excluded scope, stop
enforcement-dependent automation, and require documented human disposition or
a protection-layer bypass.

Use the exact persisted report `submission_manifest` returned by the analysis
response. Require `submitted_artifact_count` to equal the trusted in-scope
changed-file count and `len(items)`, with one item for every trusted path.
Require `accepted_artifact_count` to equal the count of items with status
`accepted` or `failed`, `analyzed_artifact_count` to equal the count with status
`accepted`, and each excluded, sensitive, failed, and partial counter to equal
its corresponding item count. `partial_analysis` must equal whether
`partial_artifact_count` is nonzero. Complete enforcement coverage additionally
requires `analyzed_artifact_count == submitted_artifact_count`, every item to be
`accepted`, and `partial_analysis=false`; any other result is incomplete. Do not
infer completeness from the enforcement-decision envelope alone; it does not
repeat the manifest.

The current GitHub App reports `neutral` when intake has no analyzable artifact,
and GitHub may treat `neutral` as satisfying a required check. Do not use that
App check as the sole blocking control for a scope where exclusions can occur;
add a separate required intake-coverage control that fails on missing or partial
coverage, or keep the integration non-blocking.

The GitHub App also reports `neutral` for a project-scope resolution failure,
before any report or decision exists. A blocking deployment must add a separate
required project-scope control that fails closed, or keep the App check
non-blocking until that runtime path produces a failing conclusion.

An enforcement-capable Action revision must exit nonzero when it cannot retrieve
and validate the shared decision; the published `@v1` ref does not implement
this behavior yet. The GitHub App reports a failed enforcement result when its
configured decision cannot be validated and check delivery succeeds.
Future consumers must surface a distinct operational error, stop the
enforcement-dependent automation, and require documented human disposition
under the organization's outage or break-glass procedure. Failure handling
must not become autonomous approval or remediation.

A protection-layer bypass does not change the DeployWhisper decision and does
not require an unchanged analysis rerun to pretend that the result changed.
Prefer a report- and integration-scoped protection bypass approved by a human
who cannot write the applicable settings; this separation of duties prevents a
settings writer from self-approving a downgrade. Record the failed decision and
the separate bypass event in a durable operator-owned audit system because the
v1 settings API does not provide a complete bypass audit log.

For GitHub, use a scoped repository-ruleset bypass actor or a protected
environment approval rather than changing DeployWhisper policy when those
controls can express the required scope. Record the ruleset/environment ID,
protected target, provider audit-event identifier or URL, approver, reason, and
expiry; verify afterward that the bypass applied only to the intended delivery.

If the organization instead authorizes a temporary settings change, use the
narrowest integration-specific override, freeze other deliveries in the
affected scope, record the original and temporary settings, apply the approved
mode, retrieve a new decision, and rerun the workflow. The API has no enforced
expiry or compare-and-swap field, so a separate read followed by write cannot
make compare-and-restore atomic. Use this temporary-settings path only while an
enforced exclusive settings lock prevents every other writer from the initial
read through restoration. An external watchdog must restore the setting before
releasing that lock. Without such a lock, do not change settings for break glass;
use the protection-layer bypass. If restoration fails, keep delivery frozen for
human recovery. Require fresh protected results for every open commit before
lifting the freeze.

The audit record must retain the invocation timestamp, report ID, original
decision payload, integration and project scope, complete `applied_settings`
snapshot, raw policy status, configured and effective modes, approver, reason,
expiry, and bypass mechanism. For HTTP consumers, hash the exact retained
authenticated response bytes with SHA-256; do not reserialize the response and
call it canonical. In-process consumers must persist the exact decision bytes
they emitted to the audit system and hash that retained byte sequence. Record a
retention period, restrict access to authorized reviewers, encrypt stored audit
evidence, and redact secrets or sensitive artifact metadata not required to
reconstruct the decision. For a protection-layer bypass, record the
protected-delivery or bypass event; for a temporary settings change, record the
replacement workflow run. Review repeated exceptions as a calibration signal.

The payload digest proves only the integrity of the retained bytes; it does not
prove server provenance, freshness, or which payload controlled delivery. Also
retain the authenticated server/principal identity, a trusted timestamp, the
protected workflow-run identifier, and an append-only audit receipt from a sink
the settings writer cannot rewrite.

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

A benchmark false negative is an expected benchmark finding or risk that the
analysis misses in the controlled corpus. False reassurance is a workflow pass
followed by an attributable adverse production outcome within the recorded
incident-attribution horizon. Keep those numerators and denominators separate;
do not count a benchmark miss as a production outcome or label a recent pass
before its observation window closes.

The decision record must identify the corpus, immutable application revision,
and actual enforcement consumer revision evaluated: for example an Action
commit SHA, GitHub App server commit or image digest, or another adapter's
immutable build identity. Include dependency-lock identity, endpoint contract
version, configuration, and feature flags. Export the workflow and protection
configuration snapshot used by the evaluation and retain a digest of its exact
bytes. When the provider offers a canonical export, retain that export and its
digest. Every allowed evidence form requires a digest so later approval can
identify mutable rules precisely.
It must also record the minimum acceptable precision and recall, maximum
acceptable false-reassurance and false-positive rates, minimum evidence
coverage, zero Evidence Law violations, an unsupported-scenario limit, and a
regression-stability tolerance. A nonzero Evidence Law violation count fails
the blocking prerequisite; it is not an organization-configurable tolerance.
The record should also identify who approved the thresholds and when they must
be reviewed again. Verify that the deployed application and consumer revisions
match those evaluated artifacts before enabling or retaining enforcement.

Rerun the benchmark gate after behavior-affecting changes to parsers, evidence
extraction, scoring, policy interpretation, the benchmark corpus, relevant
context connectors, the enforcement consumer or its dependencies, the endpoint
schema, or workflow or protection wiring. Reapproval is required when the new
result falls outside any recorded threshold or introduces a new miss,
unsupported scenario, regression, or Evidence Law violation. Every listed
consumer, dependency, schema, workflow, or protection identity change also
requires a fresh approval tied to the new immutable revisions even when all
metrics still pass. Every application, corpus, configuration, feature-flag, and
context change likewise requires fresh approval of the new benchmark record,
even when the resulting metrics still pass.

Before labeling production outcomes, define an organization-owned
outcome-observation window and incident-attribution horizon for each covered
change class. Do not label a deployment a true negative before that horizon has
elapsed; update prior labels when a later attributable incident is discovered.

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
Baseline human approval is required for every run whose resolved configured
enforcement mode is `soft-block` or `hard-block`, including runs whose effective
status is only `advisory` or `warn`. An authorized human remains responsible for
the deployment decision and must review the underlying change, deterministic
evidence, uncertainty, context gaps, policy reasons, and operational impact.

Elevated specialist review beyond that baseline approval is required when:

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
review requirement. Bind approval to the protected commit SHA, dismiss stale
approvals when that commit changes, and require a new review for the new head.

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
3. A source-bound required check or job in an immutable protected workflow,
   with no `continue-on-error`, ignored failure, or skippable enforcement step.
4. Run valid-pass, valid-block, and decision-error smoke cases against the exact
   consumer revision and protected workflow.
5. Verify complete and partial intake coverage against the submitted artifact
   manifest.
6. Evidence Law, decision and context freshness, and audit-retention expectations.
7. Named human owners for review, exceptions, incident response, and rollback.
8. A tested rollback or forward-fix path and a time-bounded break-glass
   procedure.
9. Monitoring for false reassurance, false positives, regressions, and
   excessive overrides.
10. Immutable application and actual consumer revisions plus proof that deployed
    artifacts match the benchmarked build.
11. Repository review or protected-environment rules that require human approval
    for the protected commit SHA and dismiss stale approvals after changes.
12. A review date and a trigger for returning to `warn` or `advisory`.

Enable one integration and scope at a time. Observe real outcomes before
expanding enforcement. Changing a mode does not change the canonical report;
it changes only how that integration consumes the separate policy decision.

See [Workflow Adapter Output Contract](./workflow-adapter-output-contract.md)
for the decision fields and settings precedence, and [Benchmark Corpus and
Runner](./benchmarks/corpus.md) for the available benchmark evidence. Use
[Deployment Outcome Linking](./outcome-linking.md) when production outcome data
supplements the synthetic corpus.
