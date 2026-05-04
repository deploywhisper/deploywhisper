# DeployWhisper Governance

DeployWhisper is an open-source, self-hosted project for evidence-backed pre-deployment risk review. Governance is intended to keep the project useful to platform engineers, SREs, security reviewers, maintainers, and AI-agent workflow users without tying core capabilities to a hosted service or private roadmap.

## Principles

- **Open by default:** Planning, contribution, security, and release processes should be documented in public repository files.
- **Advisory-first:** DeployWhisper helps humans understand deployment risk. Governance must not turn the project into an automatic approval, deployment, or remediation authority.
- **Local-first:** Raw infrastructure artifacts and sensitive context should stay under the operator's control by default.
- **Evidence-backed:** Roadmap and design decisions should be traceable to PRD requirements, architecture decisions, benchmarks, incidents, or maintainer-approved RFCs.
- **Community-extensible:** Supported parsers, connectors, integrations, and Skills should have public contribution paths.

## Decision Making

Day-to-day changes are reviewed through pull requests. Larger changes that affect architecture, governance, security posture, public roadmap, supported interfaces, or compatibility expectations use the public RFC process in `docs/rfcs/README.md`.

Accepted RFCs must record the decision outcome and link back to relevant PRD or architecture sections. When an accepted RFC changes the current PRD or architecture, maintainers must track the required planning update in the RFC decision record.

## Maintainer Model

Maintainer ownership and promotion rules are planned as separate governance artifacts. Until those files are published, the repository owner and CODEOWNERS entries define review responsibility for protected areas.

Future maintainer documentation should cover:

- Major ownership areas.
- Review expectations.
- Promotion and inactivity process.
- Coverage gaps.
- Conflict-of-interest handling.

## Roadmap Control

The roadmap is public and should reflect community needs, product requirements, implementation reality, security posture, and benchmark evidence. External funding, sponsorship, cloud credits, or foundation support must not grant private control over public roadmap priority.

## Scope Boundaries

Core DeployWhisper capabilities should remain usable in a self-hosted environment. Optional services, integrations, hosted deployments, or vendor-specific adapters must not become prerequisites for the main deployment-risk briefing workflow.

## Related Files

- `CONTRIBUTING.md` explains contribution workflow and development expectations.
- `CODE_OF_CONDUCT.md` defines participation standards.
- `SECURITY.md` explains vulnerability reporting and security boundaries.
- `SUPPORT.md` explains community support expectations.
- `ROADMAP.md` publishes current roadmap direction.
- `docs/rfcs/README.md` defines the public RFC and decision process for major changes.
