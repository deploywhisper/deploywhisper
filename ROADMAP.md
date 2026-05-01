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

## Non-Goals

- DeployWhisper should not automatically approve, deploy, or remediate production changes.
- DeployWhisper should not hide uncertainty when evidence or context is incomplete.
- DeployWhisper should not require a hosted control plane for core analysis.
- DeployWhisper should not replace existing security tools; it should add deployment-risk context around their signals.

## How Roadmap Changes Happen

Roadmap changes should be proposed through public issues, pull requests, benchmark findings, incident learnings, or RFCs once the RFC process is available. Changes should explain user value, evidence, scope, risks, and affected requirements.
