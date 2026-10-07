# Prompt-Injection Threat Model

DeployWhisper analyzes material controlled by repository authors, integration
users, scanners, incident importers, and AI agents. All such content is
untrusted data, including text that looks like instructions. This threat model
covers the model-facing narrative path and agent-readable output; deterministic
parsing, scoring, and Evidence Law remain authoritative.

## Assets and security goals

Protect these assets:

- the integrity of deterministic findings, severity, confidence, and evidence;
- the invariant that DeployWhisper output is advisory, not approval;
- project/workspace isolation and report confidentiality;
- credentials, provider keys, connector secrets, and deployment authority;
- the local-first boundary under which raw IaC and sensitive context stay local;
- the expected schema and bounded shape of agent output.

An attacker succeeds if untrusted content changes system instructions, invents
or suppresses material findings, claims approval, exfiltrates secrets, invokes
tools, crosses project scope, or causes an agent to merge, apply, deploy, or
remediate without human authorization.

## Untrusted sources

Treat each of these as attacker-controlled:

- IaC comments, strings, names, annotations, and metadata;
- pull-request descriptions, comments, titles, and commit messages;
- incident descriptions and imported operational context;
- scanner findings, rule text, evidence, and artifact names;
- documentation-like files and AI Skill Markdown;
- agent messages and any quoted tool output.

Pull-request text that is not an analysis artifact is isolated from the
analysis pipeline. Content that is legitimately included remains data and must
never be promoted into the system instruction channel.

## Trust boundaries and controls

### Prompt isolation

Model-facing inputs use `llm/prompt_security.py` to place artifact-derived
values under `untrusted_data` with an explicit `prompt_boundary`. The system
instruction tells the model not to follow role changes, approval claims, tool
requests, or output-format overrides found there. Skill content is untrusted
reference data, not a system prompt.

### Redaction and data minimization

Shared intake rejects sensitive artifact classes. Redaction runs before model
calls, and raw IaC is not sent to remote providers by default. A self-hosted or
local model does not make untrusted text safe; the same isolation rules apply.
No model receives credentials or secrets as intentional context.

### Tool and authority restrictions

The narrative model has no authority to approve, merge, deploy, modify project
state, or create high or critical findings. Agent integrations should expose
only bounded analysis and report-read operations. They must not expose
credentials, unrestricted shell/filesystem access, or deployment tools to the
reviewing model.

### Structured output and deterministic evidence

Typed agent output fixes `advisory_only=true`, `deployment_approval=false`, and
`human_decision_required=true`. High and critical findings require
deterministic evidence. Narrative text cannot escalate severity, override the
canonical report, or satisfy Evidence Law.

### Scope and output limits

Project/workspace authorization occurs before agent analysis or retrieval.
Agent responses bound string and collection sizes, report truncation
explicitly, and avoid echoing raw artifacts. Scoped callers receive
non-disclosing errors for missing or inaccessible resources.

## Residual risks and reviewer obligations

Prompt isolation reduces but does not eliminate model misbehavior. Models can
still summarize incorrectly, omit nuance, or repeat hostile text. Redaction can
miss novel secret formats, and provenance markers can be false. Output limits
can omit relevant context.

Therefore a human must inspect deterministic evidence and original artifacts,
resolve material context TODOs, and make the final decision. Operational
errors, degraded narrative, missing findings, low confidence, or truncated
output are never approval signals.

## Detection, testing, and response

The blocking regression suite covers injection attempts in IaC comments,
pull-request content, incident text, scanner output, and documentation-like
artifacts:

```bash
./.venv/bin/python -m pytest tests/test_llm/test_prompt_injection.py -v --tb=short
```

See [Prompt-Injection Testing](../ai-safety/prompt-injection-testing.md) for the
CI and release gates. If a boundary test fails or injected text affects output
authority, stop the release, preserve a synthetic reproducer, remove any
exposed credential, inspect logs and persisted reports for disclosure, repair
the shared boundary, and add a regression before resuming.
