# DeployWhisper Roadmap

DeployWhisper's roadmap is public, evidence-backed, and subject to change as implementation, benchmarks, maintainer capacity, and community feedback evolve.

## Product Posture

DeployWhisper is a self-hosted, advisory-first deployment-risk briefing tool. The roadmap should preserve:

- Local-first handling of raw infrastructure artifacts.
- Deterministic evidence before severe claims.
- Explicit uncertainty when context is missing or stale.
- Human review authority for deployment decisions.
- Public contribution paths for parsers, connectors, integrations, Skills, docs, benchmarks, and governance.

## Current Roadmap Phases

### Phase 0: Governance and Traceability

- Publish core governance, support, security, conduct, contributing, and roadmap files.
- Add maintainer ownership and CODEOWNERS coverage.
- Maintain requirement traceability from PRD to epics, stories, and implementation artifacts.
- Establish public RFC and decision recording process.

### Phase 1: Project-Scoped Evidence Core

- Strengthen project and workspace records.
- Preserve report persistence and audit metadata.
- Keep Evidence Law visible in reports and tests.
- Expand report history and filtering.

### Phase 2: Review Experience and Operational Context

- Improve report review surfaces for verdicts, evidence, confidence, uncertainty, and comparison.
- Add incident ingestion management and indexing.
- Expand risk trend review and calibration signals.
- Improve topology, ownership, freshness, and context graph support.

### Phase 3: Workflow and Ecosystem Integrations

- Maintain versioned API and CLI contracts.
- Improve GitHub-first delivery while preserving adapter-neutral report contracts.
- Expand scanner ingestion and conflict handling.
- Grow the Skills ecosystem with validation, contribution, analytics, and trust signals.

### Phase 4: Safety, Hardening, and Community Maturity

- Harden provider, connector, credential, and raw artifact boundaries.
- Add supply-chain checks, release verification, and restricted-network guidance.
- Improve AI-agent interfaces and prompt-injection test coverage.
- Track CNCF readiness through public governance, security, release, adoption, benchmark, and community-health evidence.

### Phase 5: Live Environment Grounding (accepted, not implemented)

Status: [RFC 0002](docs/rfcs/0002-live-environment-grounding.md) accepted 2026-10-19. Targeting **v1.5.0**, shipping alongside Epic 16 under one release tag (retargeted 2026-10-20 from v1.6.0). Acceptance authorizes qualification work only. **Nothing in this phase is implemented**, and no capability below is a claim about current behaviour.

DeployWhisper reasons well about change but currently has a thin supply of real environment facts: blast radius depends on a hand-authored topology, and severity is derived from resource categories rather than from the specific instance being changed. This phase closes that gap with a read-only, plan-directed cloud context provider, starting with AWS.

- Ground blast radius in real dependency edges instead of a missing-mapping warning.
- Detect plan-versus-reality divergence so a stale plan is never approved as if it were current.
- Verify recoverability from actual protection, backup and snapshot attributes rather than inferring it from resource type.
- Ground environment and ownership classification in the real account, live tags and network placement, surfacing disagreement rather than silently preferring one source.
- Publish a provider connector contract and conformance suite so the community can extend grounding without core changes.
- Preserve air-gapped parity through digest-bound snapshot export and import.

Boundaries for this phase: read-only by construction and by mechanical CI enforcement; opt-in per project and disabled by default; plan-directed rather than account-wide; local-first with direct operator-to-provider calls and no intermediary; and advisory, with the only gate being a CI exit code the caller opts into. No apply, destroy, remediation, drift daemon, cost estimation or policy engine is in scope.

Tracked as Epic 17. Development is independent of Epic 16 — separate modules, tests, branches and review — but both epics share the v1.5.0 release tag, so the release ships only when both close. Grounding is opt-in and disabled by default, so Epic 17 can be cut back to a later release without affecting Epic 16. See the [feature PRD](_bmad-output/planning-artifacts/prd-live-environment-grounding.md), [architecture §26](_bmad-output/planning-artifacts/architecture.md) and the [operator guide](docs/live-environment-grounding/README.md).

## Non-Goals

- DeployWhisper should not automatically approve, deploy, or remediate production changes.
- DeployWhisper should not hide uncertainty when evidence or context is incomplete.
- DeployWhisper should not require a hosted control plane for core analysis.
- DeployWhisper should not replace existing security tools; it should add deployment-risk context around their signals.

## How Roadmap Changes Happen

Roadmap changes should be proposed through public issues, pull requests, benchmark findings, incident learnings, or RFCs once the RFC process is available. Changes should explain user value, evidence, scope, risks, and affected requirements.
