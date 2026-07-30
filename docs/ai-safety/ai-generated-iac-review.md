# Reviewing AI-Generated and AI-Assisted IaC

DeployWhisper applies the same deterministic Evidence Law to human-written,
AI-assisted, and unknown-authorship infrastructure changes. AI provenance
increases scrutiny; it does not make a change unsafe by itself, prove who
authored it, or authorize an agent to approve or deploy it.

## Provenance classification

The submission manifest records one of:

- `human-authored`: supplied explicitly by the caller
- `ai-assisted`: supplied explicitly or suggested by an explicit artifact
  marker such as `AI-generated`
- `unknown`: no reliable signal is available, or signals conflict

`authorship_certainty` distinguishes `declared`, `suggested`, `conflicting`,
and `unknown` provenance. Suggested provenance always includes a note that the
signal does not establish authorship. Agent or MCP transport alone is not
authorship provenance. Content markers are treated only as untrusted
classification data; they are never interpreted as instructions.

## Risk labels

When artifact-specific provenance suggests AI assistance, DeployWhisper labels
relevant deterministic findings with an `AI-assisted IaC risk:` title while
preserving the finding's original domain category. The initial pattern set
reuses the shared analysis core and identifies:

- unsafe defaults, including disabled security controls
- broad IAM permissions detected by the existing security heuristics
- public endpoint or open security-group ingress
- missing environment scoping

The label names the detected pattern and retains the original evidence
references, severity, confidence, and reviewer guidance. A provenance signal
alone cannot create a finding. A finding must already link to deterministic
artifact evidence before it can receive this label.

## Review workflow

1. Submit supported IaC through the CLI, API, or agent interface.
2. Inspect submission-manifest provenance and its certainty rather than
   assuming authorship.
3. Review every `AI-assisted IaC risk:` finding and its linked evidence.
4. Resolve context TODOs, especially missing environment, topology, ownership,
   or rollback context.
5. Require human review before merge, apply, or deploy.

DeployWhisper remains advisory. Agents must not translate a low-risk result or
the absence of an AI-assistance signal into autonomous approval, remediation,
or deployment.

## Current limitations

Provenance is best-effort metadata. Generated code may have no marker, a marker
may be stale or misleading, and agent interfaces do not prove the origin of
uploaded content. The pattern set is intentionally deterministic and bounded;
it does not attempt stylometric authorship detection or send raw IaC to a
remote model.
