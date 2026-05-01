# DeployWhisper Security Policy

DeployWhisper analyzes infrastructure artifacts, deployment context, incident memory, scanner output, and AI-agent workflows. Treat all submitted artifacts and related context as potentially sensitive.

## Reporting Vulnerabilities

Do not open public issues for vulnerabilities that could expose credentials, private infrastructure, unsafe parsing behavior, prompt-injection paths, or deployment-risk bypasses.

Use the most private available repository reporting path:

1. GitHub private vulnerability reporting, if enabled for the repository.
2. A private maintainer contact path listed by the repository owner or CODEOWNERS.
3. If no private path is available, open a public issue with only a minimal, non-sensitive summary and ask maintainers to establish a private channel before sharing details.

Include enough information for maintainers to reproduce and assess the issue without sharing real secrets or production artifacts.

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

## Disclosure Expectations

Maintainers should acknowledge credible private reports, triage severity, and coordinate a fix before public disclosure. Public advisories should avoid exposing exploit details before users have a reasonable opportunity to update or mitigate.

## Sensitive Data Guidance

When reporting an issue:

- Use synthetic examples whenever possible.
- Remove API keys, credentials, hostnames, customer names, incident details, and production identifiers.
- Prefer minimal reproduction files over full real-world artifacts.
- Call out whether the issue affects local-only mode, external provider mode, shared-team usage, or workflow integrations.
