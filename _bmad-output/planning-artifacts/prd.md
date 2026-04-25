# DeployWhisper Product Requirements Document

**Product:** DeployWhisper
**Document type:** Product Requirements Document
**Version:** 1.0
**Date:** April 2026
**Owner:** Pramod Kumar Sahoo

---

## 1. Executive Summary

DeployWhisper is a **local-first, evidence-backed pre-deployment intelligence platform** for infrastructure changes. It helps platform engineers, SREs, and DevOps teams answer the real pre-release question:

> **Is this deployment safe to ship, what could break, who would be affected, and what should we do before rollout?**

DeployWhisper analyzes infrastructure artifacts across Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation, then produces a **single trusted deployment briefing** built from explicit evidence, confidence scoring, and uncertainty indicators — not generic AI prose.

### What's in the briefing

- Unified risk verdict with contributor breakdown
- Evidence-backed findings (every claim points to an artifact, topology, or incident)
- Cross-tool interaction warnings
- Blast radius with context-completeness indicator
- Rollback readiness and complexity
- Incident-memory similarity matches
- Plain-English narrative that runs **after** scoring, never before
- Machine-friendly summaries for PRs and approval workflows

### Category

DeployWhisper is not trying to replace CI/CD, policy engines, or static scanners. Its category is:

> **Pre-deployment intelligence for infrastructure changes**

### Five pillars of differentiation

1. **Evidence-backed intelligence, not generic AI prose**
2. **Local-first security boundary** — raw IaC never leaves the machine
3. **Cross-tool understanding** — not single-tool analysis
4. **Decision-ready briefing** — not raw findings
5. **Workflow-native delivery** — PR comments and approval threads, not just dashboards

### Strategic bet

The product wins by becoming the **most trusted intelligence layer before production**, delivered through open-source adoption, a community AI Skills marketplace, and measurable benchmark superiority over competitors.

---

## 2. Product Vision

### Vision statement

Build the most trusted system for understanding infrastructure deployment risk before production.

### Mission

Help infrastructure teams make better deployment decisions by combining deterministic analysis, historical context, and grounded AI explanation into one deployment briefing.

### Long-term outcome

A team should feel uncomfortable deploying critical infrastructure changes **without** a DeployWhisper report — the same way engineers today feel uncomfortable merging code without CI checks.

---

## 3. Competitive Landscape

### Adjacent categories and why DeployWhisper is different

| Category | Example tools | What they do well | What DeployWhisper does that they don't |
|----------|---------------|-------------------|------------------------------------------|
| IaC security scanners | Checkov, TFLint, KICS, Terrascan, tfsec | Rule-based static analysis for single tools | Multi-tool correlation, evidence model, narrative, rollback planning, incident memory |
| AI Kubernetes troubleshooting | K8sGPT | Plain-English K8s diagnosis with LLM backends | Multi-tool scope, pre-deploy intelligence (not runtime), evidence grounding |
| Terraform platforms | Spacelift, env0, HCP Terraform, Atlantis | Terraform orchestration + AI-assisted review | Open-source, self-hosted, cross-tool, incident memory, Skills ecosystem |
| Policy engines | OPA, Rego, Sentinel | Enforce known codified rules | Novel risk patterns, narrative explanation, advisory-first |
| Cloud security posture | Wiz, Aikido, Tenable, Orca, Red Hat ACS | Enterprise-grade risk scoring, attack path graphs | Open-source, bottom-up adoption, workflow-native, 10x cheaper |
| AI DevOps platforms | StackGen, Arnica | Commercial AI agents for infrastructure | Open-source, Skills marketplace, self-hosted, no vendor lock-in |

### DeployWhisper's unique position

Nobody else combines:
- Multi-tool (5 IaC tools) + tool-specific AI Skills
- Evidence model with deterministic + inferred separation
- Blast radius + incident memory + rollback planning
- Open-source + self-hosted + BYO-LLM
- Community-driven Skills marketplace

The closest single competitor is K8sGPT in terms of open-source adoption model, but they are Kubernetes-only and runtime-focused (post-deploy). DeployWhisper is multi-tool and pre-deploy. The closest in commercial space is Spacelift's Saturnhead AI, but it is proprietary, Terraform-scoped, and not community-extensible.

### Competitive risks we must address

- **K8sGPT adoption momentum** — they got into the open-source ecosystem first. Counter with multi-tool scope and Skills marketplace.
- **Commercial platforms adding "AI" features** — Spacelift, Wiz, Aikido all shipping AI. Counter with open-source positioning and measurable benchmark superiority.
- **"Just use ChatGPT" alternative** — teams may cobble together DIY solutions. Counter with evidence model and benchmark data showing accuracy difference.

---

## 4. Product Strategy

### 4.1 Category definition

DeployWhisper belongs to a new-but-emerging category: **Pre-deployment intelligence for infrastructure changes**.

This category sits between IaC scanners, CI/CD orchestration, observability-based deployment verification, and generic AI code review assistants.

### 4.2 Explicit non-positioning

DeployWhisper should explicitly avoid being positioned as:
- A Terraform runner
- A generic PR bot
- A policy engine
- A post-deploy observability product
- A generic LLM wrapper
- An enforcement or gatekeeping tool

### 4.3 Core product thesis

Infrastructure risk is a **context problem**, not just a syntax or policy problem.

A deployment becomes risky when:
- Multiple tools interact
- Environment context changes the meaning of a diff
- Blast radius is larger than it appears
- Rollback is harder than the change seems
- The change resembles a prior incident
- Topology or history is incomplete but users are not told clearly

DeployWhisper creates value by turning all of that into one trusted briefing with explicit evidence and uncertainty.

### 4.4 Strategic wedge

The initial wedge is intentionally narrow:

**Infrastructure and platform teams running production changes across Terraform and Kubernetes, often with related pipeline or config changes, where a bad rollout is expensive and human review quality varies by reviewer experience.**

### 4.5 Non-goals

DeployWhisper v1 and v1.5 are explicitly **not** intended to be:
- A deployment executor
- A replacement for Atlantis, HCP Terraform, Spacelift, or env0
- A full policy engine (OPA replacement)
- A runtime remediation or auto-rollback system
- A broad multi-tenant enterprise platform
- A cost-optimization platform
- A broad observability platform
- A ticketing or incident-management system

---

## 5. Target Customers and Users

### 5.1 Ideal customer profile

- Platform engineering and SRE teams
- 10 to 300 engineers
- Production infrastructure managed via IaC
- Mixed tooling across Terraform, Kubernetes, CI/CD pipelines, and configuration automation
- Manual pre-deploy review still depends on senior reviewer experience
- Regulated or security-conscious enough to value self-hosting and local-first analysis

### 5.2 Primary users

**Platform Engineer** — needs a fast, trustworthy deploy briefing before merge or release.

**SRE / Production Approver** — needs enough signal to make or support a go/no-go call.

**Platform Admin** — maintains topology, incidents, provider settings, and trust boundaries.

### 5.3 Secondary users

**Junior Engineer** — learns from grounded explanations and remediation guidance.

**Engineering Manager** — tracks whether deploy risk is improving, where risk concentrates, and whether the product is actually trusted.

**CI / Automation Consumer** — consumes structured output via API, CLI, or PR integration.

### 5.4 Non-users (explicit)

- End developers submitting application code changes (DeployWhisper analyzes infrastructure)
- Security auditors looking for compliance-only views (DeployWhisper is advisory, not audit-first)

---

## 6. Jobs To Be Done

### Core JTBD
When I am preparing an infrastructure change for release, help me understand whether it is safe to deploy and what deserves more review before I ship.

### Supporting JTBDs
- Help me explain the risk to an approver
- Help me see what systems or teams may be affected
- Help me understand whether rollback is realistic
- Help me compare this change against past failures
- Help my team learn from deployments over time
- Help me embed this intelligence into PR and approval workflows
- Help me prove that our deployment review quality is getting better

---

## 7. Product Principles

1. **Evidence before narrative** — AI wording must never come before grounded evidence
2. **Advisory-first** — DeployWhisper recommends; humans decide. Enforcement comes later through adapters if trust is earned
3. **Local-first by default** — raw IaC remains local; external models only receive structured summaries
4. **Uncertainty must be visible** — missing topology, partial artifact coverage, weak similarity matches, and low-confidence inference must be explicit
5. **One report, many surfaces** — Web UI, API, CLI, and PR workflows all present the same underlying analysis object
6. **Trust beats cleverness** — better to be precise and explainable than broad and impressive-looking
7. **Workflow-native wins adoption** — if the report is not present inside PRs and approval threads, usage remains optional
8. **Context is the moat** — parser coverage matters, but topology, incident memory, deployment history, and feedback learning matter more
9. **Community extends the product** — AI Skills marketplace, benchmark corpus, and incident patterns are community-contributed, not vendor-locked

---

## 8. What Makes DeployWhisper Different

Our message to the market is:

> **The local-first, evidence-backed deployment briefing for infrastructure changes.**

The competitive edge is the combination of:

- Multi-artifact infrastructure review (5 tools)
- Cross-tool reasoning
- Evidence-backed scoring with deterministic + inferred separation
- Confidence and uncertainty as first-class outputs
- Blast radius with freshness and completeness indicators
- Rollback readiness
- Incident-memory matching
- PR-native delivery
- Self-hosted / BYO-LLM posture
- Community-driven AI Skills marketplace
- Measurable accuracy benchmarks published publicly

---

## 9. Problem Statement

Today, teams review infrastructure changes using a fragmented set of tools:

- Terraform plans
- Kubernetes manifests
- Ansible playbooks
- Jenkins pipeline diffs
- Scanner output
- Tribal knowledge
- Memory of past incidents
- Manual judgment in chat or approval threads

This creates five recurring failures:

1. Reviewers miss cross-tool interactions
2. Risk quality depends on reviewer seniority
3. Blast radius is guessed rather than shown
4. Rollback is considered too late
5. Teams cannot tell whether a warning is grounded or AI-generated guesswork

DeployWhisper exists to solve all five.

---

## 10. Success Metrics

### 10.1 Product adoption metrics
- 80%+ of production-relevant infrastructure changes analyzed within 90 days of team rollout
- 60%+ of qualifying PRs show a DeployWhisper summary inside the review flow within 90 days of PR integration launch
- 50%+ of production approvals reference a DeployWhisper report or summary within 6 months

### 10.2 Trust metrics
- Precision of high/critical warnings acceptable to senior reviewers (published benchmark precision > 80%)
- False reassurance rate for material incidents kept below 5%
- 70%+ of reviewers rate evidence quality as "clear enough to defend"
- 70%+ of reviewers rate narrative as "useful but not overbearing"
- Context completeness warnings shown whenever topology/history quality is weak

### 10.3 Workflow metrics
- Median time from upload/trigger to initial report under 15 seconds for standard analyses
- PR summary generation under 5 seconds after report persistence
- Rerun-on-commit support for GitHub-based workflows in v1.5

### 10.4 Business outcome metrics
- 2-3 materially risky changes caught per month in early teams
- Measurable reduction in deployment-related severe incidents over 6-12 months
- Measurable reduction in senior-reviewer dependency for routine deploy reviews
- Growing benchmark win rate against manual review and competitor tools

### 10.5 Learning metrics
- % of reports with captured human feedback
- % of high-risk reports later confirmed by incident or postmortem outcome
- % of warnings later marked as false positive
- % of reports enriched with topology, incident, and deployment-history context

### 10.6 Community metrics (new)
- Number of community-contributed AI Skills in the marketplace
- Number of active external contributors per month
- Number of GitHub stars
- Number of deployed installations (opt-in telemetry)
- CNCF Sandbox status achieved

---

## 11. Scope by Phase

### 11.1 Phase 1 — Trusted Advisory Core (Weeks 1-10)
**Purpose:** Prove the product can create a trustworthy briefing.

**Included:**
- Multi-file artifact upload and intake
- Parser detection and normalization for 5 IaC tools
- **Explicit evidence model** with deterministic + inferred separation
- Unified risk assessment with contributors breakdown
- Cross-tool interaction detection
- Blast radius from maintained topology
- Rollback guidance
- Incident matching
- Plain-English narrative **downstream of scoring**
- Web UI, API, CLI
- Persisted reports and history
- Confidence and uncertainty indicators
- Context completeness badge

**Excluded:**
- Deep enterprise auth
- Policy gating
- Auto-remediation
- Multi-tenancy with org hierarchy
- Queue-based distributed workers
- Topology auto-discovery
- Advanced integrations beyond basic automation

### 11.2 Phase 1.5 — Workflow-Native Adoption (Weeks 9-18)
**Purpose:** Make DeployWhisper unavoidable in real review flows.

**Included:**
- GitHub Action + GitHub App
- PR comment formatter with rerun-on-commit
- Comparison between report revisions
- Shareable report links (read-only mode)
- Report status summary for approvers
- Machine-friendly verdict payload
- **AI Skills marketplace v1** with 20+ seed skills
- Skills authoring toolkit + CLI installer

### 11.3 Phase 2 — Context Moat (Weeks 15-24)
**Purpose:** Become materially smarter through organizational context.

**Included:**
- Topology auto-discovery from Terraform state
- Richer incident ingestion
- Deployment history ingestion with outcome capture
- Environment criticality mapping
- Service ownership mapping
- Reviewer feedback capture
- **Published benchmark corpus** with quarterly regression results
- Trend and calibration dashboards

### 11.4 Phase 3 — Enterprise and Scale (Week 24+)
**Purpose:** Support wider adoption without losing trust.

**Included:**
- PostgreSQL migration path
- Async workers / queue
- RBAC / SSO
- Stronger audit governance
- Team and org boundaries
- Policy export or policy adapter layer
- Optional downstream enforcement by integration, not core product takeover

---

## 12. Primary User Journeys

### 12.1 Platform Engineer — Pre-Deploy Review
A platform engineer uploads or triggers analysis for Terraform, Kubernetes, and related pipeline/config changes. They need a single verdict with top risks, evidence, blast radius, and what to verify next.

**Success condition:** The user can decide whether to proceed, fix, or escalate in minutes, not after manual cross-tool review.

### 12.2 SRE Approver — Go / No-Go Decision
An approver opens a shared report or PR summary before production rollout. They want high signal only: verdict, impact, rollback difficulty, incident similarity, and uncertainty.

**Success condition:** The approver can defend a go/no-go decision using the report.

### 12.3 Junior Engineer — Learning and Remediation
A junior engineer sees why a change is risky, what evidence caused the finding, and how to fix or verify it.

**Success condition:** The report teaches without being vague or patronizing.

### 12.4 Platform Admin — Context Maintenance
An admin updates topology, provider settings, incident records, and custom skills, and can tell whether context is stale.

**Success condition:** The system stays trustworthy because the context it depends on is visibly current.

### 12.5 PR Workflow — Automated Advisory Review
A PR changes infrastructure artifacts. DeployWhisper posts a report summary with verdict, evidence highlights, blast radius, rollback, and uncertainty. Reviewers can rerun after fixes.

**Success condition:** DeployWhisper becomes part of normal review, not a separate dashboard people forget.

### 12.6 Skills Contributor — Community Extension (new)
A platform engineer discovers DeployWhisper doesn't know about their internal tool (Helm, ArgoCD, Pulumi). They read the Skills authoring guide, write a markdown file with risk patterns, add test cases, and submit a PR.

**Success condition:** Contributor can go from idea to published skill in under 2 hours. Skill passes automated test harness and is reviewed by maintainers within 1 week.

---

## 13. Functional Requirements

### 13.1 Intake and classification
- **ING-01** Accept one or more artifacts from supported toolchains in a single analysis
- **ING-02** Auto-detect artifact type without requiring manual labeling for normal cases
- **ING-03** Support partial analysis when not all related artifacts are available
- **ING-04** Detect unsupported artifacts and explain why they were excluded
- **ING-05** Detect sensitive files and block unsafe downstream handling
- **ING-06** Preserve a submission manifest showing which artifacts were accepted, excluded, partially parsed, or failed

### 13.2 Normalization and evidence
- **EVD-01** Normalize supported artifacts into a shared internal change model
- **EVD-02** Each finding shall reference one or more concrete evidence items
- **EVD-03** Evidence items shall identify artifact, location, resource, change operation, or contextual source where applicable
- **EVD-04** The report shall distinguish deterministic findings from model-inferred explanations
- **EVD-05** The report shall surface confidence and uncertainty for key findings and overall verdict
- **EVD-06** The report shall explain the main contributors to overall risk score
- **EVD-07** When context is incomplete, the report shall show explicit uncertainty instead of implying certainty
- **EVD-08** Evidence items persist with the report for audit and comparison

### 13.3 Risk intelligence
- **RSK-01** Produce a unified deployment risk verdict for the whole submission
- **RSK-02** Classify findings and verdicts by severity level
- **RSK-03** Detect cross-tool interactions that increase risk
- **RSK-04** Generate a reviewer-oriented explanation of why a risk matters operationally
- **RSK-05** Generate actionable remediation or verification guidance
- **RSK-06** Produce rollback guidance and rollback complexity score
- **RSK-07** Distinguish between product recommendation and human decision
- **RSK-08** Continue to return deterministic results if narrative generation fails

### 13.4 Context enrichment
- **CTX-01** Compute blast radius using maintained topology context
- **CTX-02** Indicate when topology is stale, missing, or incomplete
- **CTX-03** Ingest incident records for similarity matching
- **CTX-04** Surface relevant incident similarity results with match confidence
- **CTX-05** Support service criticality and environment-aware risk context
- **CTX-06** Store deployment history sufficient for comparison and trend analysis
- **CTX-07** Support future topology auto-discovery and context connectors without replacing the core report format

### 13.5 Review and reporting experience
- **REV-01** The web report shall present verdict first, then evidence, then details
- **REV-02** The report shall show top findings, blast radius, rollback, and uncertainty above the fold
- **REV-03** Users shall be able to inspect full findings and evidence details on demand
- **REV-04** Users shall be able to retrieve prior reports and compare analyses over time
- **REV-05** The system shall generate a concise share summary for PRs and approval threads
- **REV-06** Shared summaries shall remain explicitly advisory
- **REV-07** The report shall support both expert quick scan and detailed investigation

### 13.6 Workflow-native delivery
- **WRK-01** Expose a stable versioned REST API
- **WRK-02** Expose CLI access using the same analysis core
- **WRK-03** Support GitHub-first workflow delivery for PR review
- **WRK-04** Post a formatted PR summary including verdict, top risks, blast radius, rollback context, and uncertainty
- **WRK-05** Support rerun after new commits or changed artifacts
- **WRK-06** Support report links and machine-friendly summary payloads
- **WRK-07** Support future GitLab / Atlantis / HCP Terraform / Jenkins adapters without redesigning the core analysis object

### 13.7 History, analytics, and learning
- **HIS-01** Persist completed reports before showing final success
- **HIS-02** Retain audit metadata with each report
- **HIS-03** Users shall be able to search and filter historical reports
- **HIS-04** Managers shall be able to review risk trends over time
- **HIS-05** Capture reviewer feedback on report quality and correctness
- **HIS-06** Support outcome capture after deployment for later calibration
- **HIS-07** Support benchmark and backtest workflows against historical incidents

### 13.8 Administration and customization
- **ADM-01** Admins shall configure narrative provider settings through a DeployWhisper-owned provider adapter boundary that preserves shared UI/API/CLI behavior and keeps provider secrets out of persistence
- **ADM-02** Admins shall enable fully local-only operation
- **ADM-03** Admins shall manage topology data and freshness status
- **ADM-04** Admins shall manage incident ingestion and indexing
- **ADM-05** Admins shall add or override custom skills and organization-specific heuristics
- **ADM-06** Admins shall manage thresholds and reporting defaults without changing core code
- **ADM-07** Future policy adapters shall consume report outputs without changing advisory-first core behavior

### 13.9 Community ecosystem (new)
- **COM-01** Expose a Skills registry API for listing, fetching, and installing community-contributed skills
- **COM-02** Support versioned Skills with a formal manifest schema
- **COM-03** Automated test harness runs on every Skill submission
- **COM-04** Skills installer CLI: `deploywhisper skill install <name>`
- **COM-05** Public Skills browser UI with search, filters, and ratings
- **COM-06** Skill analytics: download counts, test pass rates, last-updated timestamps
- **COM-07** Contribution workflow: PR template, automated linting, reviewer assignment

---

## 14. Non-Functional Requirements

### 14.1 Trust and security
- **NFR-SEC-01** Raw infrastructure artifacts shall never be sent to external LLM providers
- **NFR-SEC-02** Provider credentials shall not be persisted in the application database
- **NFR-SEC-03** Logs shall exclude secrets, raw IaC, prompts, and raw model responses
- **NFR-SEC-04** Sensitive-file handling shall always remain enabled
- **NFR-SEC-05** Fully local operation shall be possible with local model execution (Ollama)
- **NFR-SEC-06** The narrative-provider integration path shall minimize unnecessary dependency and supply-chain surface when direct provider SDKs satisfy the required capability more safely than a multi-provider meta-abstraction

### 14.2 Performance
- **NFR-PERF-01** Standard analysis should complete in under 15 seconds for expected v1 workloads
- **NFR-PERF-02** PR summary generation should complete in under 5 seconds
- **NFR-PERF-03** History retrieval shall remain responsive for at least 1,000 stored reports in v1
- **NFR-PERF-04** The system shall support small-team concurrency without severe degradation

### 14.3 Reliability
- **NFR-REL-01** Parser failures shall be isolated per artifact where possible
- **NFR-REL-02** Narrative failure shall degrade gracefully to deterministic output
- **NFR-REL-03** Completed reports shall be persisted before being presented as final
- **NFR-REL-04** Health checks and startup validation shall make runtime issues visible early

### 14.4 Explainability and accessibility
- **NFR-XAI-01** Severity must never be communicated by color alone
- **NFR-XAI-02** Key visualizations must have textual equivalents
- **NFR-XAI-03** Evidence and uncertainty must be readable in both UI and shared summaries
- **NFR-XAI-04** The interface shall remain keyboard navigable for common review workflows

### 14.5 Operability and architecture
- **NFR-OPS-01** Web, API, CLI, and integration outputs shall share one analysis core
- **NFR-OPS-02** The product shall preserve a stable report schema across access surfaces
- **NFR-OPS-03** The architecture shall support migration from SQLite to PostgreSQL without redesigning domain models
- **NFR-OPS-04** The architecture shall support adding async workers later without breaking existing interfaces
- **NFR-OPS-05** Narrative provider integrations shall be isolated behind an internal adapter interface so providers can be added, removed, upgraded, or capability-scoped without rewriting UI, API, CLI, or report persistence flows

---

## 15. Epics

The product will be built through six sequential epics, with some parallelism. Details in the companion **Epic Breakdown** document.

| Epic | Phase | Duration | Status |
|------|-------|----------|--------|
| Epic 1: Trusted Evidence Core | Phase 1 | Weeks 1-6 | Not started |
| Epic 2: Report & Review Experience | Phase 1 | Weeks 5-10 | Not started |
| Epic 3: GitHub-Native Delivery | Phase 1.5 | Weeks 9-14 | Not started |
| Epic 4: AI Skills Marketplace | Phase 1.5 | Weeks 11-18 | Not started |
| Epic 5: Context Moat | Phase 2 | Weeks 15-22 | Not started |
| Epic 6: Benchmarks & Calibration | Phase 2 | Weeks 19-24 | Not started |

---

## 16. Differentiation Requirements

These are requirements because they are essential to market position.

- **DIF-01** Present evidence-backed findings rather than only natural-language summary
- **DIF-02** Explicitly show uncertainty and context completeness
- **DIF-03** Support PR-native workflow delivery as a first-class use case
- **DIF-04** Preserve local-first analysis boundaries as a primary product promise
- **DIF-05** Support learning loops from reviewer feedback and deployment outcomes
- **DIF-06** Enable community extension through the AI Skills marketplace (new)
- **DIF-07** Publish measurable benchmark results against competing approaches (new)

---

## 17. Release Exit Criteria

### 17.1 Phase 1 exit (target: Week 10)
- Mixed-artifact analysis works reliably
- Reports contain evidence and uncertainty
- Deterministic core works without narrative
- History and audit metadata persist correctly
- Senior reviewers consider high/critical findings credible enough to test in real workflows
- Evidence inspector is usable in the UI
- At least 3 internal or friendly-user teams using the product

### 17.2 Phase 1.5 exit (target: Week 18)
- GitHub workflow integration live and documented
- PR summaries reused in real reviews
- Rerun-on-commit works
- Report comparison and sharing are usable
- Deployment approvals start referencing reports regularly
- Skills marketplace live with 20+ seed skills
- First external Skill contribution merged

### 17.3 Phase 2 exit (target: Week 24)
- Context completeness improves materially
- Incident similarity becomes useful in practice
- Deployment history and outcome capture exist
- Published benchmark corpus and quarterly results available
- False positive/false reassurance trends are measurable and improving
- CNCF Sandbox application submitted (or accepted)
- GitHub stars greater than 1,000

---

## 18. Risks and Open Questions

### Risk 1: Score credibility
If the product over-warns or falsely reassures, adoption will fail.

**Mitigation:** Conservative defaults; evidence traceability; benchmark corpus publication; feedback loop.

### Risk 2: Parser coverage
Real-world parser edge cases can destroy trust quickly.

**Mitigation:** Corpus of real-world samples per parser; isolated parser failures don't crash analysis; explicit parse_status per artifact.

### Risk 3: Weak evidence model
If findings cannot be defended with evidence, the product becomes "just AI text".

**Mitigation:** Evidence model is architectural, not optional. Every finding must reference evidence. Tests enforce this.

### Risk 4: Context freshness
Blast radius and incident matching are only as good as topology and history quality.

**Mitigation:** Context completeness is a first-class output. Warn when stale. Future: auto-discovery.

### Risk 5: Distribution delay
If PR-native delivery is delayed too long, DeployWhisper remains an optional dashboard.

**Mitigation:** Epic 3 (GitHub integration) scheduled for Week 9. Do not delay.

### Risk 6: Competitive compression (new)
K8sGPT, Spacelift, Wiz, and commercial AI DevOps tools are all moving fast.

**Mitigation:** Skills marketplace (Epic 4) is the long-term moat. Benchmark corpus (Epic 6) is the proof engine. Open-source + self-hosted positioning is defensible against commercial players.

### Risk 7: Community bootstrap (new)
Skills marketplace only works if contributors participate.

**Mitigation:** Seed with 20 first-party skills before launch. Active community engagement via Discord, YouTube, conferences.

### Open Questions

1. Should GitHub integration start as Action, App, or both?
   - **Decision:** Both. Action for CI, App for richer interactions. Ship Action first.
2. What is the minimum evidence standard for a "high" or "critical" finding?
   - **Decision:** At least one deterministic evidence item per high/critical finding, defined in the spec.
3. Which deployment history inputs should be captured first?
   - **Decision:** Analysis ID, timestamp, deploy outcome (success/failure/rolled back), linked incidents.
4. Which context connectors matter most after manual topology and incident ingestion?
   - **Decision:** Terraform state (auto-topology), GitHub PR history, Slack-based postmortem ingestion.
5. What threshold of benchmark accuracy is required before optional policy adapters are introduced?
   - **Decision:** 85% precision on high/critical findings across the public benchmark, sustained for 3 consecutive quarterly runs.
6. When and how do we introduce a hosted SaaS tier? (new)
   - **Decision:** After Phase 2 (Week 24+). Open-core model: free self-hosted, paid hosted, paid enterprise.

---

## 19. Product Roadmap Summary

### Now (Weeks 1-10) — Build trust
- Evidence model
- Report quality
- Confidence and uncertainty
- Parser hardening
- Clean positioning and docs

### Next (Weeks 9-18) — Build distribution
- GitHub workflow integration
- PR comments
- Shareable reports
- Compare-rerun flows
- Skills marketplace

### Then (Weeks 15-24) — Build moat
- Topology auto-discovery
- Richer incident memory
- Deployment history
- Feedback loop
- Calibration dashboards
- Benchmark corpus

### Later (Post-24 weeks) — Build enterprise path
- RBAC / SSO
- PostgreSQL / workers
- Audit hardening
- Policy adapters
- Hosted SaaS tier

---

## 20. Final Positioning Statement

DeployWhisper is the no. 1 choice when a team says:

> "We already have scanners and pipelines. We still need the most trusted pre-deployment briefing before production."

The product wins through:
- Open-source trust and distribution
- Evidence-backed intelligence (not AI hype)
- Community Skills marketplace (structural moat)
- Measurable benchmark superiority (defensible claim)
- Workflow-native delivery (unavoidable in review flows)

That is the market position this PRD is designed to support.
