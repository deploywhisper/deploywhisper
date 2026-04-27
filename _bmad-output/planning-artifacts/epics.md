# DeployWhisper — Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for deploywhisper, decomposing the requirements from the PRD, UX Design if it exists, and Architecture requirements into implementable stories.

**Companion to:** `prd.md` v1.0 and `architecture.md` v1.0
**Total timeline:** 24 weeks (6 epics, 2 phases)
**Format:** Epic → Stories → Acceptance Criteria

---

## Table of Contents

- [Baseline vs Roadmap](#baseline-vs-roadmap)
- [Compact FR/NFR Traceability Matrix](#compact-frnfr-traceability-matrix)
- [Brownfield Hardening Track](#brownfield-hardening-track)
- [Epic 1: Trusted Evidence Core](#epic-1)
- [Epic 2: Report & Review Experience](#epic-2)
- [Epic 3: GitHub-Native Delivery](#epic-3)
- [Epic 4: AI Skills Marketplace](#epic-4)
- [Epic 5: Context Moat](#epic-5)
- [Epic 6: Benchmarks & Calibration](#epic-6)

---

## Baseline vs Roadmap

This epic pack should be read as a **delta roadmap over the current repository baseline**, not as a claim that the repo starts from zero.

The current codebase already provides meaningful baseline capabilities:

- Multi-artifact intake, classification, sensitive-file rejection, and partial analysis handling
- Parser coverage and shared normalized change model for Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation
- Shared analysis pipeline with risk scoring, cross-tool interaction risk, blast radius, rollback guidance, incident similarity, and narrative fallback
- Persisted reports, audit metadata, history browsing, and basic trend summaries
- Versioned REST API and CLI over the same analysis core
- Provider settings, local-only mode, topology upload/validation, and custom-skill override support

The current baseline should also be read carefully in one provider-specific area:

- provider settings and local-only operation are part of the supported baseline
- the previous meta-provider-backed implementation is **not** a permanent architecture constraint
- brownfield hardening may replace the provider abstraction layer as long as shared-core behavior, degraded fallback, local-first guarantees, and persisted report contracts remain stable

The six epics below focus on the **remaining roadmap delta** needed to reach the latest PRD and architecture target state:

- Epic 1 upgrades the baseline into a first-class evidence model
- Epic 2 upgrades the current report UX into the target verdict/evidence review experience
- Epic 3 adds GitHub-native workflow delivery
- Epic 4 expands local skill support into a public marketplace ecosystem
- Epic 5 adds the feedback, topology automation, and deployment-outcome moat
- Epic 6 adds the benchmark and backtesting proof engine

When a PRD requirement is already partially or substantially present in the current repo, treat the relevant story as **hardening / refactoring / target-state completion**, not as permission to rebuild the baseline from scratch.

---

## Compact FR/NFR Traceability Matrix

This matrix is intentionally compact. It maps requirement families to either:

- **Baseline**: already present in the current repository and should be preserved
- **Delta**: explicitly delivered by the refreshed roadmap
- **Baseline + Delta**: existing capability plus roadmap expansion or re-architecture

| Requirement IDs | Primary Coverage | Coverage Type | Notes |
| --- | --- | --- | --- |
| `ING-01..06` | Existing repo baseline; preserve during Epic 1 migration | Baseline | Intake/classification already exists and should not be accidentally reimplemented or regressed. |
| `EVD-01` | Existing normalized change model + `E1-S2` / `E1-S3` | Baseline + Delta | Current normalization exists; Epic 1 upgrades it into evidence-first scoring. |
| `EVD-02..08` | `E1-S1..E1-S8`, `E2-S2..E2-S4`, `E2-S7` | Delta | These are core gaps the refreshed plan is explicitly designed to close. |
| `RSK-01..08` | Existing repo baseline + `E1-S3`, `E1-S6`, `E1-S7`, `E2-S1`, `E2-S6`, `E2-S7` | Baseline + Delta | Unified risk exists today; Epic 1/2 make it evidence-backed, confidence-aware, and review-ready. |
| `CTX-01..07` | Existing topology / incidents baseline + `E1-S5`, `E2-S4`, `E2-S5`, `E5-S1..E5-S12` | Baseline + Delta | Current context is manual and partial; Epic 5 turns it into a moat. |
| `REV-01..07` | Existing dashboard/history baseline + `E2-S1..E2-S8` | Baseline + Delta | The current UI supports review, but Epic 2 is the target-state UX pass. |
| `WRK-01..02` | Existing API and CLI baseline | Baseline | Preserve shared-core API/CLI behavior while adding new workflow adapters. |
| `WRK-03..07` | `E3-S1..E3-S11` | Delta | GitHub-native delivery is new roadmap work. |
| `HIS-01..04` | Existing persistence/history baseline + `E5-S4`, `E5-S8` | Baseline + Delta | Persistence and history exist; Epic 5 expands them into richer learning and operations data. |
| `HIS-05..07` | `E5-S5..E5-S8`, `E6-S1..E6-S12` | Delta | Reviewer feedback, outcomes, calibration, and backtesting are roadmap work. |
| `ADM-01..05` | Existing settings/local-mode/topology/custom-skill baseline + `BH-S1..BH-S5` + `E4-S1..E4-S12`, `E5-S1..E5-S4` | Baseline + Delta | Admin basics exist now; marketplace and context automation extend them, and the brownfield provider track hardens the provider boundary. |
| `ADM-06` | `E5-S11` | Delta | Threshold and reporting-default management has explicit admin story ownership. |
| `ADM-07` | `E5-S12` | Delta | Policy adapter consumption has explicit output-contract story ownership while preserving advisory-first behavior. |
| `COM-01..07` | `E4-S1..E4-S12` | Delta | Community ecosystem requirements are fully owned by Epic 4. |
| `NFR-SEC-01..06` | Existing local-first/security baseline + `BH-S1..BH-S5` + Epic 1, 4, and 5 hardening | Baseline + Delta | Preserve raw-local boundaries and secret handling while expanding ecosystem and context features and reducing provider-path dependency surface. |
| `NFR-PERF-01..04` | Cross-cutting across `E1`, `E2`, `E3`, and `E5` | Delta | Performance budgets are not their own epic; they must be pulled into story ACs during implementation. |
| `NFR-REL-01..04` | Existing degradation/persistence baseline + `E1-S7`, `E5-*` | Baseline + Delta | Reliability exists partially today; Epic 1 and 5 raise the bar. |
| `NFR-XAI-01..04` | `E2-S1..E2-S8` | Delta | Explainability and accessibility are primarily enforced through Epic 2. |
| `NFR-OPS-01..05` | Existing shared-core architecture + `BH-S1..BH-S5` + `E1-S8`, `E3-*`, `E5-*`, `E6-*` | Baseline + Delta | Architecture stability exists now; schema, adapter, and future worker migration concerns remain roadmap work, with the brownfield track owning provider-interface hardening. |

Implementation note:

- If a requirement family is marked `Baseline`, do not add replacement stories unless the capability is missing or unstable in the current repo.
- If a requirement family is marked `Baseline + Delta`, the story intent is to extend or re-architect the existing implementation without losing current behavior.

---

<a id="brownfield-hardening-track"></a>
## Brownfield Hardening Track

This track is intentionally separate from the six main epics.

Its purpose is to harden already-shipped or already-planned behavior without pretending the repo starts from zero again. The current provider settings and local-only operation remain valid baseline capabilities; this track updates the implementation boundary behind them.

### Goal

Replace the previous meta-provider-centered abstraction with a DeployWhisper-owned adapter boundary while preserving:

- local-first raw-artifact handling
- narrative-after-scoring sequencing
- deterministic degradation behavior
- shared UI/API/CLI/report behavior
- persisted provider/model audit metadata

### Stories

#### BH-S1: Lock provider-boundary behavior with regression tests
**As a** maintainer,
**I want** current provider resolution, validation, degraded fallback, and persisted metadata behavior locked with tests,
**so that** the migration does not silently change user-visible semantics.

**Acceptance:**
- Tests cover provider resolution across environment and persisted settings
- Tests cover readiness validation behavior for local and hosted modes
- Tests cover narrative JSON parsing and deterministic fallback behavior
- Tests verify persisted report metadata still records provider, model, and local-mode fields

#### BH-S2: Introduce provider adapter contract and registry
**As a** developer,
**I want** a repo-owned provider adapter interface and registry,
**so that** callers keep one stable boundary while provider implementations change underneath.

**Acceptance:**
- `llm/providers.py` becomes a facade over an internal adapter registry
- Adapter interface defines completion, validation, and capability reporting semantics
- `llm/narrator.py` caller behavior remains unchanged
- API/UI/CLI do not gain provider-specific branching

#### BH-S3: Migrate OpenAI, Anthropic, Gemini, and Ollama to direct SDK adapters
**As a** platform admin,
**I want** first-class providers to run through direct SDK adapters,
**so that** DeployWhisper reduces dependency surface while preserving supported provider choice.

**Acceptance:**
- OpenAI uses the official `openai` SDK
- Anthropic uses the official `anthropic` SDK
- Gemini uses the official `google-genai` SDK
- Ollama uses a direct local adapter path
- Existing provider settings UX and API contracts stay stable

#### BH-S4: Migrate OpenRouter, Groq, and xAI to a compatibility adapter and remove the legacy meta-provider dependency
**As a** maintainer,
**I want** lower-priority providers preserved through a compatibility path,
**so that** DeployWhisper keeps current breadth without keeping the legacy meta-provider dependency in the runtime path.

**Acceptance:**
- OpenRouter, Groq, and xAI remain selectable providers
- Compatibility-provider behavior is implemented through one explicit compatibility adapter
- The legacy meta-provider package is removed from runtime dependencies after parity is verified
- README and provider docs no longer describe an external meta-provider as the core abstraction

#### BH-S5: Add provider capability metadata and MCP readiness hooks
**As a** future integrator,
**I want** provider capabilities modeled explicitly,
**so that** MCP and tool-integration work can be planned intentionally instead of being hidden in provider-specific codepaths.

**Acceptance:**
- Provider metadata includes structured output, local-only, remote MCP, local MCP, and tool-approval capability flags
- Settings and validation logic can surface capability differences without changing report semantics
- MCP readiness remains optional and does not block legacy dependency removal

### Exit Criteria

- The legacy meta-provider package is removed from the runtime dependency path
- Tier 1 providers run through direct adapters
- Tier 2 providers run through an explicit compatibility adapter
- Degraded fallback and report contracts remain stable
- Planning docs and generated project context reflect the repo-owned provider boundary

---

<a id="epic-1"></a>
## Epic 1: Trusted Evidence Core

**Phase:** 1
**Weeks:** 1-6
**Priority:** P0 (blocks everything)

### Goal
Introduce the evidence model as first-class domain objects. Every finding must trace to evidence. Scoring must run before narrative. Confidence and uncertainty must be explicit.

### Why this epic must ship first
Without the evidence model, DeployWhisper is "AI output with extra steps". With it, the product has a defensible trust claim that differentiates us from every LLM wrapper and generic AI DevOps tool.

### Stories

#### E1-S1: Domain model foundations
**As a** developer,
**I want** `EvidenceItem`, `Finding`, `RiskAssessment`, and `ContextSnapshot` defined as Pydantic models + SQLAlchemy tables,
**so that** all downstream logic has stable types to work with.

**Acceptance:**
- Pydantic models defined in `evidence/models.py`
- SQLAlchemy tables defined in `models/tables.py` with foreign keys linking Finding → EvidenceItem (1:many) and Report → Finding (1:many)
- Alembic migration `005_add_evidence_model.py` tested against clean DB and existing DB
- Unit tests for every model (construction, serialization, validation)

#### E1-S2: Evidence Extractor service
**As a** developer,
**I want** a service that converts parser output into EvidenceItem instances,
**so that** every change detected by a parser generates traceable evidence.

**Acceptance:**
- `evidence/extractor.py` with one extractor method per supported tool type
- Input: `NormalizedChange`; output: list of `EvidenceItem`
- Each evidence item includes: source_type, source_ref, summary, severity_hint, deterministic flag, related_change_ids
- Test coverage: 20 fixture scenarios across all 5 tools produce expected evidence

#### E1-S3: Refactor risk scorer to consume evidence
**As a** developer,
**I want** the risk scorer to consume `EvidenceItem` lists instead of raw changes,
**so that** the final verdict traces to concrete evidence.

**Acceptance:**
- `analysis/risk_engine.py` accepts `List[EvidenceItem]` and emits `RiskAssessment`
- `RiskAssessment` includes `top_risk_contributors` pointing to specific evidence IDs
- Unit tests verify that disabling any single evidence item changes the score appropriately

#### E1-S4: Confidence field on every finding
**As a** reviewer,
**I want** each finding to show a confidence score (0-1),
**so that** I can distinguish high-confidence deterministic findings from low-confidence inferred ones.

**Acceptance:**
- `Finding.confidence` is required, not optional
- Deterministic findings default to 1.0
- Inferred findings show LLM's stated confidence or a heuristic floor
- UI displays confidence as a badge (high/medium/low) with numeric tooltip

#### E1-S5: Context completeness on RiskAssessment
**As a** reviewer,
**I want** the report to tell me how complete the context was,
**so that** I can discount warnings when topology or history is stale.

**Acceptance:**
- `RiskAssessment.context_completeness` is a structured object with: topology_freshness_days, incident_index_size, parser_success_rate, context_score (0-1)
- Context score below 0.7 triggers a prominent UI warning
- Tests verify stale topology (>30 days) reduces context_score appropriately

#### E1-S6: Narrator runs after scoring
**As a** developer,
**I want** the LLM narrator to run as the last pipeline stage, consuming the frozen verdict,
**so that** AI wording never influences severity.

**Acceptance:**
- Pipeline order: intake → parse → evidence → score → **narrate** → persist
- Narrator receives: `RiskAssessment`, `List[Finding]` with evidence refs, and cannot mutate any of them
- Test: mock narrator returns garbage; risk score is unchanged
- Test: disable narrator entirely; report renders with deterministic summary fallback

#### E1-S7: Deterministic degradation
**As a** reviewer,
**I want** the report to still work if the LLM fails,
**so that** I never lose the core analysis because of a provider outage.

**Acceptance:**
- LLM timeout or exception produces a report with: all findings, all evidence, risk assessment, blast radius, rollback — just no narrative
- A visible notice indicates narrative generation failed
- Health check endpoint reports LLM provider status separately from core system health

#### E1-S8: Report schema v2
**As a** developer,
**I want** the report schema to be versioned,
**so that** API consumers and stored reports remain readable across upgrades.

**Acceptance:**
- `Report.report_schema_version` persisted on every report
- v2 schema documented in `docs/schemas/report-v2.md`
- API response includes schema version in envelope
- Forward-compat guarantee: v3 clients can read v2 reports

### Epic 1 Exit Criteria
- Every finding in every report has at least one evidence item
- Every finding has a confidence score
- Disabling the LLM still produces a complete (minus-narrative) report
- Score contributors visible in the UI with click-to-inspect
- 20 known-risky test scenarios all pass with expected severity

### Epic 1 Effort Estimate
- Solo developer: 5-6 weeks
- With 1 collaborator: 3-4 weeks

### Epic 1 Key Risks
- Schema migration breaking existing reports — accept a clean v2 break since pre-GA
- Refactor hitting every module — introduce behind a feature flag, flip when stable
- Confidence scores feeling arbitrary — start with three-bucket (low/med/high) before granular

---

<a id="epic-2"></a>
## Epic 2: Report & Review Experience

**Phase:** 1
**Weeks:** 5-10 (overlaps with Epic 1)
**Priority:** P0

### Goal
Build the report UI and share summary that make evidence, confidence, and uncertainty easy to scan. Verdict above the fold. One click to evidence. Context warnings always visible.

### Stories

#### E2-S1: Verdict card redesign
**As a** reviewer,
**I want** the verdict, top risk, and key signals above the fold,
**so that** I can decide in 5 seconds whether to dig deeper.

**Acceptance:**
- Verdict card shows: risk score, GO/CAUTION/NO-GO badge, top risk one-liner, confidence badge, context completeness badge
- Renders in the first 700px of the page at 1440×900
- Passes a 5-second scan test with 3 test users

#### E2-S2: Findings table with evidence badges
**As a** reviewer,
**I want** the findings table to show which are deterministic vs. inferred,
**so that** I know which claims to trust most.

**Acceptance:**
- Column order: severity, title, tool, evidence count, confidence, actions
- Each row has a "deterministic" or "inferred" badge
- Clicking a row expands the evidence panel
- Sortable by severity and confidence

#### E2-S3: Evidence inspector panel
**As a** reviewer,
**I want** to see exactly what evidence backs a finding,
**so that** I can defend or challenge the verdict.

**Acceptance:**
- Click a finding → panel shows each evidence item with: source_type icon, source_ref (artifact path + line number), summary, severity hint, deterministic flag
- Link to the original artifact when source is an uploaded file
- Evidence items from topology/incidents show source-system badge

#### E2-S4: Context completeness panel
**As a** reviewer,
**I want** to see how complete the analysis context was,
**so that** I understand the limits of the report.

**Acceptance:**
- Panel shows: topology freshness (age, last-import date), incident index size, parser success rate per tool
- Warning banner when context_score < 0.7
- Link to the admin panel to fix stale context

#### E2-S5: Blast radius visualization
**As a** reviewer,
**I want** to see which services are affected,
**so that** I understand the real impact.

**Acceptance:**
- Graph rendered via streamlit-agraph or Plotly
- Directly affected services tinted by severity
- Transitively affected services shown at lower saturation
- Textual equivalent: "3 services directly affected, 5 transitively" for screen readers

#### E2-S6: Rollback plan panel
**As a** reviewer,
**I want** to see a step-by-step rollback plan,
**so that** I know the recovery path before I deploy.

**Acceptance:**
- Ordered steps with time estimate per step
- Complexity score (1-5) with explanation
- Critical path steps flagged
- Copy-to-clipboard action for the full plan

#### E2-S7: Share summary generator
**As a** PR reviewer,
**I want** a clean markdown summary I can paste into approval threads,
**so that** I don't have to hand-write briefings.

**Acceptance:**
- Markdown summary: verdict banner, top 3 findings, evidence count, blast radius summary, rollback link, context completeness
- Max 1,500 characters (fits GitHub PR comment)
- Generates from the same Report object the UI renders
- Machine-friendly JSON variant for API consumers

#### E2-S8: Keyboard navigation
**As a** reviewer,
**I want** full keyboard access to the report,
**so that** I can work efficiently without a mouse.

**Acceptance:**
- Tab order: verdict card → findings → evidence → context → blast radius → rollback
- Arrow keys navigate within findings table
- Space or Enter expands evidence inspector
- Escape closes any modal
- Tested with VoiceOver and NVDA

### Epic 2 Exit Criteria
- Verdict visible above the fold on 1440×900
- Every finding has a clickable evidence inspector
- Context completeness warning appears when stale
- Share summary copy-pastes cleanly to GitHub PRs
- Color is never the only severity signal
- Full keyboard navigation

### Epic 2 Effort Estimate
- Solo: 5-6 weeks
- With design help: 3-4 weeks

---

<a id="epic-3"></a>
## Epic 3: GitHub-Native Delivery

**Phase:** 1.5
**Weeks:** 9-14
**Priority:** P0 (biggest adoption lever)

### Goal
Ship an official GitHub Action plus advanced self-hosted GitHub App support so DeployWhisper reports appear inside PRs automatically, updating on every commit. This is how DeployWhisper stops being optional.

### Stories

#### E3-S1: GitHub Action v1
**As a** maintainer,
**I want** to add DeployWhisper to my CI workflow in 3 lines of YAML,
**so that** every PR with infrastructure changes gets analyzed.

**Acceptance:**
- `deploywhisper/analyze-action@v1` in GitHub Marketplace
- Reads changed files in the PR
- POSTs to configured DeployWhisper API endpoint
- Returns exit code 0 (report generated, humans decide)
- Documented in README with copy-paste example

#### E3-S2: PR comment formatter
**As a** reviewer,
**I want** to see the DeployWhisper verdict in the PR comments,
**so that** I don't need to open a separate dashboard.

**Acceptance:**
- Comment includes: verdict banner, top 3 findings, evidence count, blast radius summary, rollback link, context completeness, link to full report
- Markdown-formatted for GitHub
- Max 2,000 characters
- Uses collapsible sections for detail
- Handles comment updates gracefully on re-run

#### E3-S3: Rerun-on-commit
**As a** reviewer,
**I want** the PR comment to update when new commits are pushed,
**so that** I always see analysis of the latest state.

**Acceptance:**
- New commit triggers new analysis
- Existing comment is updated (not duplicated)
- Comment shows diff from previous analysis: "Risk score changed 78 → 34, previously HIGH, now LOW"
- Historical analyses preserved with timestamps

#### E3-S4: Shareable report URLs
**As a** reviewer,
**I want** a public URL for any report,
**so that** I can share it in Slack or tickets without exposing internal infra.

**Acceptance:**
- URL pattern: `https://install.example.com/reports/{analysis_id}`
- Read-only mode for unauthenticated viewers
- Optional password protection for sensitive reports
- Redacts file names when sharing externally (opt-in redaction)

#### E3-S5: Report comparison view
**As a** reviewer,
**I want** to compare analyses between commits,
**so that** I understand what changed when a fix is pushed.

**Acceptance:**
- UI shows side-by-side diff: findings added, findings removed, severity changes
- Risk score delta prominently displayed
- Evidence-level changes highlighted
- Accessible via "Compare with previous" button on the report page

#### E3-S6: GitHub App
**As a** DeployWhisper maintainer,
**I want** a minimal self-hosted GitHub App runtime that complements the Action,
**so that** advanced teams can install the app without mixing all GitHub capabilities into one oversized story.

**Acceptance:**
- App runtime can receive and validate GitHub webhook events in a self-hosted deployment
- Installation configuration supports repository and organization scope
- Operator guide documents required GitHub App permissions and local-first deployment assumptions
- Runtime can enqueue or trigger DeployWhisper analysis for configured PR events
- Check-run posting, manual setup verification, and combined-mode docs are handled by follow-on stories

#### E3-S7: Check run integration
**As a** reviewer,
**I want** a GitHub check showing DeployWhisper status,
**so that** verdicts are visible in the PR status area.

**Acceptance:**
- Check run labeled "DeployWhisper / Risk Analysis"
- Status: neutral for CAUTION, success for GO, failure for NO-GO — but **never required**
- Details link opens full report
- Never blocks merge (advisory-first principle)

#### E3-S8: Installation wizard
**As a** new user,
**I want** to install DeployWhisper on my repo in under 5 minutes,
**so that** the friction-to-first-value is as low as possible.

**Acceptance:**
- One-command CLI: `deploywhisper github init`
- Asks: repo, workflow path, API endpoint
- Commits a PR to the repo with the workflow file
- Includes README updates and example secrets configuration
- Links to docs for common setup questions

#### E3-S9: Self-hosted GitHub App setup documentation
**As a** team admin,
**I want** clear instructions for creating and installing the GitHub App from GitHub Developer Settings,
**so that** my team can run GitHub App mode without relying on a DeployWhisper-hosted SaaS app.

**Acceptance:**
- Operator docs walk through GitHub Developer Settings → GitHub Apps → New GitHub App
- Docs specify webhook URL, optional callback URL, required permissions, pull request events, and app visibility settings
- Docs explain how users install the app into their own account or organization and select repositories from GitHub's UI
- Secrets and private keys remain environment-backed and are not persisted in application tables
- Verification checklist covers webhook delivery, PR artifact analysis, advisory check-run creation, and report-link behavior
- Troubleshooting covers missing permissions, revoked installation, unreachable webhook URL, invalid signature, and required status-check misconfiguration

#### E3-S10: GitHub delivery mode documentation
**As a** platform maintainer,
**I want** Action-first, App-only, and combined-mode setup documented clearly,
**so that** teams can choose the least complex delivery path for their environment.

**Acceptance:**
- Documentation explains when to use the GitHub Action, self-hosted GitHub App, or both
- Example workflows include secrets configuration and advisory-only behavior
- Operator guide covers webhook URL, permissions, private key management, and local-first data boundaries
- Troubleshooting section covers missed events, duplicate comments, missing check runs, and rerun behavior

#### E3-S11: Advisory policy adapter output contract
**As a** CI/CD integrator,
**I want** a stable advisory report output contract for future policy adapters,
**so that** policy engines can consume DeployWhisper results without changing core advisory behavior.

**Acceptance:**
- JSON contract exposes verdict, risk score, findings, evidence counts, confidence, context completeness, and advisory flags
- Contract explicitly sets merge-blocking or enforcement decisions outside DeployWhisper core behavior
- API and CLI can emit the same policy-adapter payload
- Contract is documented with examples for GitHub checks and future CI adapters
- Tests verify that NO-GO output remains advisory and does not mutate `should_block` semantics

### Epic 3 Exit Criteria
- Install DeployWhisper on a new repo in under 5 minutes
- PR comment posted within 30 seconds
- Rerun updates the existing comment
- Share link works for external viewers
- At least 3 real teams using it in production

### Epic 3 Effort Estimate
- Solo: 5-6 weeks
- With help: 3-4 weeks

---

<a id="epic-4"></a>
## Epic 4: AI Skills Marketplace

**Phase:** 1.5
**Weeks:** 11-18 (overlaps Epic 3)
**Priority:** P1 (long-term moat)

### Goal
Launch a community-driven Skills registry with browser UI, authoring toolkit, and curation process. Every Skill is versioned, tested, and attributable. This is DeployWhisper's structural moat — no competitor can easily replicate an open ecosystem.

### Stories

#### E4-S1: Skills registry API
**As a** DeployWhisper user,
**I want** to browse and install community Skills via API,
**so that** I can extend the product without writing Python.

**Acceptance:**
- `GET /api/v1/skills` lists all skills with metadata
- `GET /api/v1/skills/{id}` returns a single skill
- `GET /api/v1/skills/{id}/versions` returns version history
- Pagination, filters (tool, tag, author), search by keyword
- OpenAPI documented

#### E4-S2: Skills manifest spec v1
**As a** skill author,
**I want** a formal schema for my skill manifest,
**so that** I know the required fields and format.

**Acceptance:**
- Frontmatter schema: name, version, author, license, triggers, token_budget, tags, description, test_suite_path
- JSON Schema published at `/schemas/skill-manifest-v1.json`
- Validator CLI: `deploywhisper skill lint my-skill.md`
- Spec documented in `docs/skills/authoring-guide.md`

#### E4-S3: Skill test harness
**As a** maintainer,
**I want** automated tests for every skill,
**so that** quality doesn't degrade as the marketplace grows.

**Acceptance:**
- Each skill ships with test scenarios in `tests/skill-tests/<skill>/`
- Test harness runs all scenarios and reports pass/fail
- CI integration: every PR runs the harness for changed skills
- Test results shown publicly per skill (e.g. "47/50 scenarios passing")

#### E4-S4: Skills installer CLI
**As a** user,
**I want** to install a skill with one command,
**so that** I don't hand-copy markdown files.

**Acceptance:**
- `deploywhisper skill install helm` fetches and installs
- `deploywhisper skill list` shows installed skills
- `deploywhisper skill update helm` upgrades to latest version
- `deploywhisper skill remove helm` uninstalls
- Installs to `skills/custom/` by default

#### E4-S5: Skills browser UI
**As a** potential user,
**I want** to browse skills on the marketing website,
**so that** I can see the ecosystem before downloading.

**Acceptance:**
- Public page at `deploywhisper.deploywhisper.dev/skills`
- Search, filter by tool, filter by author, sort by popularity/recency
- Each skill has a detail page with: description, install command, test results, version history, author, contributors
- Download count, star count, last updated visible

#### E4-S6: Contribution workflow
**As a** would-be contributor,
**I want** a clear path from idea to published skill,
**so that** I'm not guessing what reviewers want.

**Acceptance:**
- PR template in `.github/PULL_REQUEST_TEMPLATE/skill.md`
- Automated linter runs on skill PRs
- Automated test harness runs on skill PRs
- Reviewer assignment via CODEOWNERS
- Merge → auto-publish to registry
- Contribution guide at `docs/contributing/skills.md`

#### E4-S7: Seed 20 community skills
**As a** launcher,
**I want** an initial first-party seed batch published,
**so that** the marketplace has useful launch content before the full catalog is complete.

**Acceptance:**
- 5 first-party skills published at launch covering a representative Terraform/Kubernetes/GitHub Actions mix
- Each skill has: complete manifest, at least 3 test scenarios, working installation, documented risk patterns
- Seed skill publishing process is documented so later batches use the same manifest, test, and review standards

#### E4-S8: Skill analytics
**As a** user choosing a skill,
**I want** to see how popular and reliable it is,
**so that** I pick high-quality ones.

**Acceptance:**
- Per-skill: install count, test pass rate, last updated, active issues
- Shown on browser page and in CLI output
- Updated daily

#### E4-S9: Editorial curation
**As a** user,
**I want** featured and vetted skills highlighted,
**so that** I don't have to evaluate everything myself.

**Acceptance:**
- "Official" badge for DeployWhisper-maintained skills
- "Featured" badge for curated community skills
- Curation guidelines in `docs/skills/curation.md`
- Removal process for low-quality or abandoned skills

#### E4-S10: Seed marketplace catalog batch 2
**As a** launcher,
**I want** the second seed batch to add GitOps and policy skills,
**so that** early users see credible coverage beyond the core launch tools.

**Acceptance:**
- 5 additional first-party skills published for GitOps, ingress, certificate, and policy use cases
- Each skill has complete manifest metadata, at least 3 test scenarios, working installation, and documented risk patterns
- Registry browser clearly labels official seed skills versus community submissions
- Test harness passes for all batch 2 skills in CI

#### E4-S11: Seed marketplace catalog batch 3
**As a** launcher,
**I want** the third seed batch to cover observability and cloud-IaC skills,
**so that** the marketplace supports realistic platform review scenarios.

**Acceptance:**
- 5 additional first-party skills published for observability and cloud-IaC review patterns
- Each skill has complete manifest metadata, at least 3 test scenarios, working installation, and documented risk patterns
- Skill detail pages show last updated, test pass rate, and official-maintainer status for the batch
- Test harness passes for all batch 3 skills in CI

#### E4-S12: Seed marketplace catalog batch 4
**As a** launcher,
**I want** the final seed batch to bring the launch catalog to 20 skills,
**so that** first-time visitors see an ecosystem without one oversized delivery story.

**Acceptance:**
- 5 additional first-party skills published, bringing the total official seed catalog to 20
- Coverage includes Helm, ArgoCD, Pulumi, Crossplane, Istio, Nginx Ingress, Cert-Manager, Flux, Tekton, OPA Gatekeeper, Datadog monitors, Prometheus rules, AWS CDK, Bicep, Pulumi GCP, Pulumi Azure, Kustomize, Helmfile, Tanka, and Jsonnet across the full seed set
- All 20 skills have complete manifests, at least 3 test scenarios, working installation, and documented risk patterns
- Registry analytics and curation surfaces can distinguish seed batch, official status, and test reliability

### Epic 4 Exit Criteria
- Skills browser live at /skills with 20+ published skills
- Any user can install via `deploywhisper skill install <n>`
- 5+ external contributors have submitted skills via PR
- Each skill has a public test pass rate
- Idea-to-published-skill in under 2 hours

### Epic 4 Effort Estimate
- Solo: 7-8 weeks
- With community help: 4-6 weeks

---

<a id="epic-5"></a>
## Epic 5: Context Moat

**Phase:** 2
**Weeks:** 15-22 (overlaps Epics 3-4)
**Priority:** P1

### Goal
Automate topology discovery. Capture deployment outcomes. Build the feedback loop. This epic turns DeployWhisper from "smart on day 1" to "measurably smarter every month".

### Stories

#### E5-S1: Terraform state import
**As a** admin,
**I want** to import AWS topology from Terraform state,
**so that** I can stop hand-maintaining the most common topology source first.

**Acceptance:**
- CLI: `deploywhisper topology import --from terraform --state s3://my-bucket/terraform.tfstate`
- Supports AWS Terraform provider resources needed for the initial topology graph
- Builds service topology graph automatically for supported AWS resources
- Reports topology diff when re-imported
- Unsupported providers are skipped with explicit warnings instead of failing the whole import

#### E5-S2: Topology drift detection
**As a** admin,
**I want** to know when topology is out of sync,
**so that** I can trigger a re-import.

**Acceptance:**
- Scheduled drift check (configurable, default daily)
- Alerts when >10% of resources changed since last import
- Drift report lists added/removed/modified resources
- Configurable via settings UI

#### E5-S3: Topology freshness badge
**As a** reviewer,
**I want** to see how fresh the topology is in every report,
**so that** I know when to discount blast radius.

**Acceptance:**
- Every report shows topology age prominently
- Warning at 30+ days stale
- Critical warning at 90+ days stale
- Link to topology management page

#### E5-S4: Deployment history capture
**As a** engineering manager,
**I want** every deployment and its outcome tracked,
**so that** I can measure risk trends over time.

**Acceptance:**
- Webhook endpoint accepts deployment outcome notifications
- Webhook payload: analysis_id, outcome (success/failure/rolled_back), deployed_at, linked_incident_id
- CLI alternative: `deploywhisper outcome record --analysis-id X --outcome success`
- History queryable via API

#### E5-S5: Reviewer feedback capture
**As a** reviewer,
**I want** to rate findings as useful/false-positive/missed,
**so that** the product learns from my expertise.

**Acceptance:**
- Thumbs up/down on each finding in the UI
- False positive flag with optional reason
- False negative note for missed findings
- Feedback stored in FeedbackEvent table
- Feedback summary visible to admins

#### E5-S6: Outcome linking
**As a** system,
**I want** to link post-deploy incidents back to pre-deploy reports,
**so that** I can measure predictive accuracy.

**Acceptance:**
- Incident records can reference DeployWhisper analysis IDs
- Backtesting job runs weekly to compute: for each failed deploy, did DeployWhisper warn?
- Results feed the calibration dashboard

#### E5-S7: Calibration dashboard
**As a** admin,
**I want** to see our precision/recall over time,
**so that** I can trust the product is calibrated.

**Acceptance:**
- Dashboard shows: overall precision, overall recall, precision by severity, recall by severity
- Time window selector (7d / 30d / 90d)
- Trend line over past 12 weeks
- Exports for audit

#### E5-S8: Trend analysis
**As a** manager,
**I want** to see risk trends by tool, environment, and engineer,
**so that** I can target improvements.

**Acceptance:**
- Risk score histogram by tool
- Risk score distribution by environment
- Risk by engineer (opt-in, privacy-respecting)
- Exportable as CSV

#### E5-S9: GCP Terraform state import
**As a** admin,
**I want** to import GCP topology from Terraform state,
**so that** GCP-backed services improve blast-radius accuracy without manual topology files.

**Acceptance:**
- CLI supports GCP Terraform provider resources through the existing topology import command
- Builds service topology graph for supported GCP resources
- Reports unsupported GCP resources in an import warning summary
- Re-import produces a topology diff consistent with the AWS import behavior
- Tests cover representative GCP state fixtures and partial unsupported-resource handling

#### E5-S10: Azure Terraform state import
**As a** admin,
**I want** to import Azure topology from Terraform state,
**so that** Azure-backed services improve blast-radius accuracy without manual topology files.

**Acceptance:**
- CLI supports Azure Terraform provider resources through the existing topology import command
- Builds service topology graph for supported Azure resources
- Reports unsupported Azure resources in an import warning summary
- Re-import produces a topology diff consistent with AWS and GCP import behavior
- Tests cover representative Azure state fixtures and partial unsupported-resource handling

#### E5-S11: Threshold and reporting defaults management
**As a** admin,
**I want** to manage risk thresholds and report defaults without changing core code,
**so that** teams can tune DeployWhisper behavior while preserving stable analysis semantics.

**Acceptance:**
- Settings surface exposes threshold bands, context warning defaults, and report display defaults
- API and CLI can read the same defaults through shared configuration services
- Changes are audit logged with actor, timestamp, and previous/new values
- Defaults never disable sensitive-file handling or local-first protections
- Tests verify threshold/default changes affect presentation or classification only through the approved shared boundary

#### E5-S12: Policy adapter consumption boundary
**As a** platform integrator,
**I want** future policy adapters to consume DeployWhisper report outputs through a stable boundary,
**so that** integrations can evaluate reports without changing the advisory-first core.

**Acceptance:**
- Shared service emits a policy-consumption payload from persisted Report data
- Payload includes advisory verdict, evidence references, confidence, uncertainty, and recommended next actions
- Payload excludes raw uploaded artifacts, prompts, raw model responses, and provider secrets
- Documentation states that external policy adapters own enforcement decisions
- Tests verify adapter payload generation does not change report persistence, UI/API/CLI semantics, or advisory-only defaults

### Epic 5 Exit Criteria
- Topology auto-import works for AWS/GCP/Azure
- Drift detection surfaces manual changes
- At least 1 real team has >100 deployments tracked
- Calibration dashboard shows real FP/FN rates
- Feedback loop captures ratings on 50%+ of findings

### Epic 5 Effort Estimate
- Solo: 7-8 weeks
- With help: 4-5 weeks

---

<a id="epic-6"></a>
## Epic 6: Benchmarks & Calibration

**Phase:** 2
**Weeks:** 19-24
**Priority:** P1 (proof engine)

### Goal
Build a public benchmark corpus. Run DeployWhisper, competitors, and generic LLMs against it. Publish results quarterly. This is how we prove the accuracy claim that wins enterprise trust.

### Stories

#### E6-S1: Benchmark corpus v1
**As a** maintainer,
**I want** the corpus schema and first labeled scenario batch,
**so that** benchmark work starts with a reviewable foundation instead of one oversized corpus story.

**Acceptance:**
- Corpus schema supports artifacts, expected findings, expected severity, rationale, reviewer labels, and tool category
- First 20 scenarios include a balanced safe/risky mix across Terraform and Kubernetes
- Scenario fixtures are stored in `benchmark/corpus/` as YAML or JSON
- Validation command checks schema completeness and duplicate IDs
- Expansion to 100 scenarios is handled by follow-on corpus batch stories
- Stored in `benchmark/corpus/` as YAML or JSON
- Open-source under MIT license

#### E6-S2: Scenario annotation
**As a** maintainer,
**I want** senior SREs to label each scenario,
**so that** ground truth reflects real-world expertise.

**Acceptance:**
- Each scenario has at least 2 SRE reviewers
- Disagreements resolved with notes
- Annotation guidelines documented
- Reviewer credits published (with permission)

#### E6-S3: Benchmark runner
**As a** developer,
**I want** an automated runner for the corpus,
**so that** I can regression-test accuracy.

**Acceptance:**
- CLI: `deploywhisper benchmark run --corpus benchmark/corpus`
- Outputs per-scenario results: expected vs. actual findings
- Overall metrics: precision, recall, F1 by severity
- JSON and human-readable output

#### E6-S4: Comparative runner
**As a** marketer,
**I want** the comparative runner to support local/open-source comparators first,
**so that** the result format is proven before adding every external comparator.

**Acceptance:**
- Runner supports at least tflint and kube-score through explicit comparator adapters
- Each competitor's output mapped to comparable finding format
- Results table: tool X scenario matrix
- Winner-by-scenario and overall-winner reported
- Additional comparator adapters are handled by follow-on stories

#### E6-S5: Published results dashboard
**As a** potential user,
**I want** to see comparative accuracy on the marketing site,
**so that** I can trust the product claims.

**Acceptance:**
- Public page at `deploywhisper.deploywhisper.dev/benchmarks`
- Updated quarterly
- Shows precision/recall by tool and by competitor
- Methodology documented publicly
- Raw results downloadable

#### E6-S6: Quarterly regression
**As a** maintainer,
**I want** to re-run the benchmark every quarter,
**so that** I can show version-over-version improvement.

**Acceptance:**
- Scheduled job runs corpus every quarter
- Results archived with version and commit hash
- Improvement chart on results dashboard
- Regressions flagged for investigation

#### E6-S7: Open-source the corpus
**As a** maintainer,
**I want** the corpus publicly available,
**so that** the community can contribute scenarios and labels.

**Acceptance:**
- Corpus in a public repo at `deploywhisper/benchmark-corpus`
- Contribution guide for scenarios
- Pull request template for new scenarios
- At least 5 external contributions in first 6 months

#### E6-S8: Incident backtesting
**As a** user who experienced a P1,
**I want** to backtest DeployWhisper against my pre-deploy state,
**so that** I know if it would have caught my incident.

**Acceptance:**
- CLI: `deploywhisper backtest --pre-deploy-artifacts <path> --incident <incident-report>`
- Runs DeployWhisper against the state and scores against the incident
- Publishes anonymized case studies with permission
- At least 1 case study published in Epic 6 timeframe

#### E6-S9: Benchmark corpus expansion batch
**As a** maintainer,
**I want** to expand the benchmark corpus across all supported tool types,
**so that** the corpus reaches meaningful cross-tool coverage in reviewable increments.

**Acceptance:**
- Adds at least 40 scenarios beyond the initial corpus batch
- Covers Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation with at least 8 scenarios each across the expanded set
- Maintains safe/risky balance and expected severity labels
- Validation command passes for all new scenarios
- Review notes capture assumptions for ambiguous scenarios

#### E6-S10: Benchmark corpus completion and quality gate
**As a** maintainer,
**I want** the corpus to reach 100 labeled scenarios with quality checks,
**so that** published results have defensible ground truth.

**Acceptance:**
- Corpus reaches at least 100 scenarios: 50 risky and 50 safe
- Each supported tool has at least 20 scenarios
- Every scenario includes artifacts, expected findings, expected severity, rationale, and reviewer label metadata
- Quality gate rejects unlabeled scenarios, duplicate IDs, missing expected findings, and invalid severity values
- Corpus summary report documents tool coverage and risk distribution

#### E6-S11: Hosted and LLM comparator adapters
**As a** marketer,
**I want** comparative runner adapters for K8sGPT and a vanilla LLM prompt,
**so that** public comparisons include both deterministic tools and AI baselines.

**Acceptance:**
- Runner supports K8sGPT through an explicit adapter with documented setup assumptions
- Runner supports a vanilla LLM prompt baseline without sending raw sensitive production artifacts
- Adapter outputs map into the same comparable finding format as local comparators
- Failure or missing credentials for hosted/LLM comparators does not fail local comparator runs
- Tests cover adapter output normalization and degraded comparator availability

#### E6-S12: Comparative result normalization and reporting
**As a** maintainer,
**I want** normalized comparator results and repeatable reports,
**so that** published benchmark claims can be audited.

**Acceptance:**
- Results table records per-tool, per-scenario, and overall metrics for DeployWhisper and comparators
- Winner-by-scenario and overall-winner logic is deterministic and documented
- JSON and human-readable reports include corpus version, DeployWhisper version, comparator versions, and run timestamp
- Published dashboard can consume the normalized result artifact without re-running the benchmark
- Tests cover metric calculation, tie handling, and missing comparator outputs

### Epic 6 Exit Criteria
- Benchmark corpus has 100+ annotated scenarios
- DeployWhisper beats or matches comparators on 3+ of 5 tools
- Results published quarterly
- At least 1 anonymized incident case study published
- CNCF Sandbox application submitted or accepted

### Epic 6 Effort Estimate
- Solo: 5-6 weeks
- With SRE network for annotations: 3-4 weeks

---

## Epic sequencing and parallelism

```
Week:  1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16  17  18  19  20  21  22  23  24
Epic 1: ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
Epic 2:                 ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
Epic 3:                                 ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
Epic 4:                                         ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
Epic 5:                                                         ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
Epic 6:                                                                         ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
```

Epic 1 must finish before Epic 2 UI work on evidence. Epic 2 must finish before Epic 3 share summary work. Epic 4 can start as soon as Epic 2 is rendering the new schema. Epics 5 and 6 can run in parallel with 4 once the report schema is stable.

---

## Summary by effort

| Epic | Solo weeks | With help weeks | Critical path |
|------|-----------|-----------------|---------------|
| 1 | 5-6 | 3-4 | Yes |
| 2 | 5-6 | 3-4 | Yes |
| 3 | 5-6 | 3-4 | Yes |
| 4 | 7-8 | 4-6 | No (but strategic) |
| 5 | 7-8 | 4-5 | No |
| 6 | 5-6 | 3-4 | No |

**Total critical path (solo):** 15-18 weeks for Epics 1+2+3
**Total full plan (solo):** 24 weeks for all 6 epics
