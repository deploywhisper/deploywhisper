# DeployWhisper Security Policy

DeployWhisper analyzes infrastructure artifacts, deployment context, incident memory, scanner output, and AI-agent workflows. Treat all submitted artifacts and related context as potentially sensitive.

## Reporting Vulnerabilities

Do not open public issues for vulnerabilities that could expose credentials, private infrastructure, unsafe parsing behavior, prompt-injection paths, or deployment-risk bypasses.

Use [GitHub private vulnerability reporting](https://github.com/deploywhisper/deploywhisper/security/advisories/new)
to submit a report to the maintainers. Private reporting is enabled for this
repository. See [GitHub's reporting instructions](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/privately-reporting-a-security-vulnerability)
for the reporter's workflow.

If that form is unavailable, open a public issue containing only a request for
a private contact channel. Do not include credentials, infrastructure artifacts,
incident details, or an exploit in that request.

Include enough information for maintainers to reproduce and assess the issue without sharing real secrets or production artifacts.

## Supported Versions

| Version | Security support |
| --- | --- |
| Latest 1.4.x release | Current supported release line |
| Earlier releases | Upgrade to the current release before applying a fix |
| develop | Development branch; fixes land here before release |

Consult the [release history](https://github.com/deploywhisper/deploywhisper/releases)
for published versions and remediation notes.

## Supported Scope

Security reports may cover:

- Secret handling and redaction failures.
- Unsafe artifact persistence, logging, or prompt construction.
- Parser behavior that mishandles untrusted input.
- Prompt-injection or agent-output boundary failures.
- Cross-project data leakage.
- Authentication, authorization, or API exposure defects.
- Supply-chain, release, or dependency concerns.

## Local-First Boundary

DeployWhisper's default posture is self-hosted and local-first. Raw infrastructure artifacts should remain local by default. External model providers, connectors, or integrations must be explicit and should receive only the minimum safe context required.

The [secrets and artifact boundary audit](docs/security/secrets-and-artifact-boundaries.md)
documents credential screening, blocked snapshots/model output, safe logging,
reviewer-visible redaction status, and operator responsibilities for older data.

Repository security scans and finding dispositions follow the
[Scorecard and CodeQL review process](docs/security/supply-chain-scanning.md).
High-priority findings need an owner and a follow-up issue or evidence-backed
rationale; vulnerability details retain the private disclosure boundary above.

## Disclosure Expectations

Maintainers should acknowledge credible private reports, triage severity, and coordinate a fix before public disclosure. Public advisories should avoid exposing exploit details before users have a reasonable opportunity to update or mitigate.

The target is acknowledgement within seven business days and an initial
assessment within fourteen business days. These are response targets, not a
guaranteed fix deadline. Maintainers and reporters should agree on a disclosure
date based on severity, reproducibility and available mitigations. Release notes
and a [GitHub security advisory](https://github.com/deploywhisper/deploywhisper/security/advisories)
will document affected versions, fixed versions and any mitigation when a
confirmed issue is disclosed.

## Sensitive Data Guidance

When reporting an issue:

- Use synthetic examples whenever possible.
- Remove API keys, credentials, hostnames, customer names, incident details, and production identifiers.
- Prefer minimal reproduction files over full real-world artifacts.
- Call out whether the issue affects local-only mode, external provider mode, shared-team usage, or workflow integrations.
