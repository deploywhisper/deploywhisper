# Reviewing AI-Generated and AI-Assisted IaC

DeployWhisper is an advisory reviewer. It can organize deterministic evidence,
surface uncertainty, and suggest verification steps, but it cannot approve,
merge, apply, deploy, or remediate infrastructure changes. Those decisions
remain with an authorized human.

The same Evidence Law applies to human-authored, AI-assisted, and
unknown-authorship changes. AI provenance increases scrutiny; it does not prove
authorship, create a finding by itself, or make a change safe or unsafe.

## Safe invocation

Run DeployWhisper inside infrastructure you control. The simplest agent
workflow invokes the local CLI and stores the result in the current workspace:

```bash
deploywhisper analyze \
  --agent-json \
  --project payments \
  path/to/plan.json > deploywhisper-agent.json
```

Treat the generated JSON as potentially sensitive review material: it can
contain evidence excerpts, findings, project context, and report metadata. Keep
it access-controlled, do not commit it to the repository, and do not share it
outside the authorized review path without inspecting and redacting it first.

A self-hosted HTTP integration can call the MCP-equivalent agent interface:

```bash
curl -sS -X POST http://localhost:8080/api/v1/agent/analyses \
  -H "X-DeployWhisper-Project-Role: contributor" \
  -H "X-DeployWhisper-Project-Keys: payments" \
  -F "project_key=payments" \
  -F "files=@path/to/plan.json"
```

Raw IaC, scanner artifacts, incident exports, and sensitive context should stay
local. Do not forward raw artifacts to a remote model merely because an agent
can invoke DeployWhisper. Give the agent only the structured advisory response
and the minimum repository context needed for its task.

## Interpret the output

Before using a result, the agent and reviewer should verify:

1. The command or request succeeded. A non-zero exit code or API error is not a
   low-risk result.
2. For CLI output, `schema_version` is supported by the consumer. For the HTTP
   interface, validate both `data.schema_version` and
   `meta.interface_schema_version`, and require `meta.operation` to match the
   invoked endpoint (`analysis.submit` or `report.read`).
3. `advisory_only` is `true`, `deployment_approval` is `false`, and
   `human_decision_required` is `true`.
4. High and critical findings link to deterministic evidence and satisfy the
   Evidence Law.
5. Confidence, uncertainty, warnings, output truncation, and context TODOs are
   treated as review inputs. Missing context is not evidence of safety.
6. Verification guidance is carried into the pull request or change record for
   a human to complete.

Risk scores prioritize review; they are not policy decisions. The absence of a
finding, an `allow`-like recommendation, low severity, low confidence, a
degraded narrative, or an operational error must not be interpreted as
approval.

## Human review expectations

An authorized human reviewer should inspect the proposed diff and the original
artifacts, confirm the project and workspace scope, trace material findings to
their evidence, and resolve relevant context TODOs. The reviewer should also
validate ownership, environment targeting, blast radius, rollback feasibility,
scanner conflicts, and any production-specific controls that DeployWhisper
cannot observe.

Only the human-controlled repository or deployment workflow may decide whether
to request changes, merge, apply, deploy, or invoke an explicitly configured
policy adapter. Record overrides and unresolved uncertainty in the normal audit
trail. Never give an AI agent credentials or tools that let it turn an advisory
result into an unreviewed state change.

## Prompt-injection risks

IaC comments, pull-request text, incident records, scanner output,
documentation-like artifacts, Skill content, and agent messages are untrusted
data. They may contain text such as “ignore previous instructions,” fake
approval claims, requests for credentials, or attempts to change the expected
output format.

Do not promote artifact text into a system prompt or execute commands found in
it. Preserve the structured data boundary, redact secrets before any model
call, restrict tools available to the agent, and treat quoted instructions as
evidence to inspect rather than instructions to follow. See the
[Prompt-Injection Threat Model](../security/prompt-injection-threat-model.md).

## Forbidden auto-approval patterns

Never configure an agent or workflow to:

- approve, merge, apply, or deploy because the risk score is below a threshold;
- treat no findings, missing context, truncated output, or analysis failure as
  approval;
- let model-generated narrative override deterministic evidence or Evidence
  Law status;
- remediate infrastructure automatically from recommendation text;
- turn `advisory_only` off or rewrite `deployment_approval`;
- bypass human review after a rerun, even when all previous findings disappear;
- expose credentials or unrestricted deployment tools to the reviewing agent.

A safe automation may collect the report, post its evidence, and request human
review. It must stop there unless a separately designed, explicitly configured
policy adapter enforces deterministic policy with its own authorization and
audit controls.

## Provenance and AI-assisted risk labels

The submission manifest records `human-authored`, `ai-assisted`, or `unknown`
provenance with a separate certainty value. Declared or content-marker signals
are best-effort metadata and may be stale, misleading, or conflicting. Agent or
HTTP transport alone does not establish authorship.

When artifact-specific provenance suggests AI assistance, DeployWhisper may
prefix relevant deterministic findings with `AI-assisted IaC risk:`. The label
does not change the original category, evidence references, severity,
confidence, or guidance. It cannot create a finding without deterministic
artifact evidence.

For the machine-readable fields, see [Agent JSON CLI Output](./agent-json-output.md).
For self-hosted agent-tool transport, see [MCP Server and Agent Interface](./mcp-server.md).
