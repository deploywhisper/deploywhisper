# Prompt-Injection Testing

DeployWhisper treats uploaded artifacts and imported reference material as
untrusted data, even when that material contains text that resembles model
instructions. This applies to IaC comments, pull-request text, incident records,
scanner findings, and docs-like AI Skill content.

For assets, attacker goals, trust boundaries, controls, and incident response,
read the [Prompt-Injection Threat Model](../security/prompt-injection-threat-model.md).

## Trust boundary

Model-facing structured inputs use the shared helper in
`llm/prompt_security.py`. The helper places all artifact-derived values under an
`untrusted_data` key and includes an explicit `prompt_boundary` declaration.
System prompts separately instruct the model never to follow role changes,
approval claims, tool requests, or output-format overrides embedded in that
data.

AI Skill Markdown is reference data. It is sent in the untrusted user payload,
not appended to the system message. Pull-request descriptions and comments are
not analysis artifacts and are not forwarded to the analysis pipeline.

Agent responses enforce advisory behavior in the typed output contract:
`advisory_only` remains true, `deployment_approval` remains false, and
`human_decision_required` remains true regardless of text found in evidence,
findings, scanner output, incidents, or narrative guidance.

## Regression suite and release gate

Run the focused suite with:

```bash
./.venv/bin/python -m pytest tests/test_llm/test_prompt_injection.py -v --tb=short
```

The suite includes representative injection strings for all five untrusted
input classes and verifies that they remain in the data channel. Complementary
service tests verify GitHub pull-request text isolation and immutable
agent-output safety fields.

`scripts/ci-local.sh` runs the focused suite before the broader test targets.
GitHub CI includes it in the blocking `tests/test_llm` shard, and the release
workflow runs it as an explicit gate before the full release suite. Any failure
therefore stops the corresponding CI or release workflow until remediated.
