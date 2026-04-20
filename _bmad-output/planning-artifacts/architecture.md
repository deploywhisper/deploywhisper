# DeployWhisper Architecture Document

**Product:** DeployWhisper
**Document type:** Architecture Decision and Target-State Design
**Version:** 1.0
**Date:** April 2026
**Owner:** Pramod Kumar Sahoo

---

## 1. Purpose

This architecture defines how DeployWhisper evolves into the **most trusted pre-deployment intelligence layer** for infrastructure changes while preserving the strongest parts of the current implementation:

- Shared NiceGUI + FastAPI runtime
- API / CLI / UI over one analysis core
- Local-first raw IaC boundary
- Advisory-only product posture
- Self-hosted simplicity for early teams

The architecture is intentionally designed in two layers:

1. **Trusted v1 architecture** — for product-market fit and trust building
2. **Scale-ready path** — for PR-native delivery, richer context, community ecosystem, and higher concurrency

This version (3.0) extends v2.0 by adding **three new architectural pillars** required for market leadership:

- **Skills Marketplace infrastructure** (ecosystem moat)
- **Benchmark Corpus infrastructure** (proof engine)
- **GitHub Adapter layer** (workflow-native adoption)

---

## 2. Architecture Goals

The architecture must support seven product goals:

1. Evidence-backed risk intelligence
2. Workflow-native delivery
3. Local-first security
4. Context-rich decision support
5. Community ecosystem extensibility (new)
6. Measurable accuracy through benchmarks (new)
7. Clean migration path from early self-hosted deployment to broader organizational use

---

## 3. Architectural Principles

### 3.1 Evidence first
Every major risk decision must be traceable to evidence objects, not only narrative text.

### 3.2 One analysis core
UI, API, CLI, and PR integrations must call the same orchestration pipeline.

### 3.3 Advisory-first core
The core system produces reports and recommendations. Enforcement, if ever added, should consume report output through adapters.

### 3.4 Local-first boundary
Raw artifacts stay local. External model usage is limited to structured summaries.

### 3.5 Uncertainty as first-class output
Missing context, weak matches, low confidence, and partial coverage are not edge cases — they are product outputs.

### 3.6 Evolve without rewrite
Keep current repo strengths and extend them instead of replacing the application.

### 3.7 Community extension by design (new)
Skills, parsers, and context connectors must be extensible by community contributors without core code changes.

### 3.8 Measurable by construction (new)
Every risk decision must be testable against a benchmark corpus. Accuracy must be a published, tracked metric.

---

## 4. Recommended Architecture Direction

DeployWhisper uses a layered architecture:

- **Access layer** — Web UI, API, CLI, PR/CI integrations
- **Orchestration layer** — Shared analysis pipeline
- **Intelligence layer** — parsers, evidence engine, scoring, blast radius, rollback, similarity, narrative preparation
- **Context layer** — topology, incidents, deployment history, criticality, ownership
- **Ecosystem layer** (new) — Skills registry, benchmark corpus, contribution workflows
- **Persistence layer** — reports, evidence, history, settings, context, feedback
- **Platform layer** — config, secrets boundary, logging, health, jobs, observability

---

## 5. System Context

### Actors
- Platform engineer
- SRE / production approver
- Platform admin
- CI pipeline / PR workflow
- Skills contributor (new)
- Benchmark reviewer (new)
- Local or remote LLM provider
- Context sources (topology, incidents, deployment history, service ownership)

### External Systems
- GitHub (first-priority integration; Action + App)
- GitLab / Jenkins / Atlantis / HCP Terraform (future adapters)
- Ollama or external model providers
- Optional incident or ticket sources
- Optional Terraform state or service-catalog data sources
- Skills registry (community contribution repository)
- Benchmark corpus (public dataset)

---

## 6. High-Level Component View

```
          +---------------------+
          |  Web UI (NiceGUI)   |
          +----------+----------+
                     |
          +----------v----------+
          |  REST API (FastAPI) |
          +----------+----------+
                     |
          +----------v----------+
          |      CLI / CI       |
          +----------+----------+
                     |
          +----------v----------+
          |   GitHub Adapter    |  <-- NEW in v3
          +----------+----------+
                     |
          +----------v-------------------------------+
          |     Shared Analysis Orchestration        |
          | intake -> parse -> evidence -> context   |
          | -> score -> narrate -> persist -> deliver|
          +----------+-------------------------------+
                     |
     +---------------+---------------+------------------+
     |                               |                  |
+----v-----+                  +------v------+    +------v------+
| Parsers  |                  | Context     |    | Narrative   |
| registry |                  | services    |    | service     |
+----+-----+                  +------+------+    +------+------+
     |                               |                  |
+----v-----------------+      +------v------+    +------v------+
| Evidence / Findings  |      | Topology    |    | LLM provider|
| Risk / Rollback      |      | Incidents   |    | adapters    |
| Similarity / Scoring |      | History     |    | (structured |
+----+-----------------+      +------+------+    |  summary    |
     |                               |           |  only)      |
     +---------------+---------------+           +-------------+
                     |
     +---------------+--------------------------+
     |                                          |
+----v----------+                    +----------v----------+
| Skills        |  <-- NEW in v3    | Benchmark Runner    |  <-- NEW in v3
| Registry      |                    | + Corpus            |
+----+----------+                    +----------+----------+
     |                                          |
     +---------------+--------------------------+
                     |
             +-------v--------+
             | Persistence    |
             | reports        |
             | evidence       |
             | settings       |
             | history        |
             | feedback       |
             | context        |
             | skills cache   |
             | benchmark runs |
             +----------------+
```

---

## 7. What We Keep From the Current Baseline

The current repo already aligns with several correct decisions and those stay:

- One shared analysis core across UI, API, and CLI
- NiceGUI + FastAPI shared runtime
- SQLite for early self-hosted simplicity
- SQLAlchemy / Alembic / Pydantic
- Local-first raw IaC handling
- Advisory-only posture
- History and audit persistence

The v3 rewrite is **not** a call for a rewrite-from-scratch. It adds the missing architectural capabilities that support market leadership:

- First-class evidence model (v2 + v3)
- PR-native integration layer (v2 + v3)
- Feedback and calibration loop (v2 + v3)
- Context connectors (v2 + v3)
- Skills marketplace infrastructure (v3 new)
- Benchmark corpus infrastructure (v3 new)
- Scale path beyond SQLite-only usage (v2 + v3)

---

## 8. Core Domain Model

The architecture standardizes around these core domain objects. (Same as v2 — kept as-is because they are correctly specified.)

### 8.1 ArtifactBundle
Represents the user or automation submission.

Fields:
- `bundle_id`
- `source_surface` (`web`, `api`, `cli`, `github`, etc.)
- `trigger_context`
- `environment`
- `submitted_at`
- `artifact_manifest`

### 8.2 ArtifactRecord
Represents each uploaded or referenced artifact.

Fields:
- `artifact_id`
- `bundle_id`
- `filename`
- `detected_tool`
- `classification_status`
- `sensitivity_status`
- `parse_status`
- `content_hash`
- `size_bytes`

### 8.3 NormalizedChange
Canonical internal representation of parsed change data.

Fields:
- `change_id`
- `artifact_id`
- `resource_type`
- `resource_name`
- `operation`
- `before_summary`
- `after_summary`
- `environment_scope`
- `service_scope`
- `tags`

### 8.4 EvidenceItem
The most important missing domain object in the original planning set.

Fields:
- `evidence_id`
- `analysis_id`
- `source_type` (`artifact`, `topology`, `incident`, `history`, `heuristic`, `skill`)
- `source_ref`
- `summary`
- `severity_hint`
- `deterministic` (bool)
- `confidence`
- `related_change_ids`

### 8.5 Finding
A reviewer-facing risk observation.

Fields:
- `finding_id`
- `analysis_id`
- `title`
- `description`
- `severity`
- `category`
- `deterministic`
- `confidence`
- `uncertainty_note`
- `evidence_refs`
- `skill_id` (new — points to the skill that contributed this finding, if any)

### 8.6 RiskAssessment
Overall report verdict.

Fields:
- `analysis_id`
- `overall_severity`
- `recommendation`
- `score`
- `confidence`
- `top_risk_contributors`
- `context_completeness`

### 8.7 ContextSnapshot
Frozen contextual state used during one analysis.

Fields:
- `topology_version`
- `incident_index_version`
- `history_window`
- `criticality_inputs`
- `owner_mapping_version`
- `skills_active` (new — list of skill IDs + versions active during analysis)

### 8.8 Report
Persisted analysis object that all surfaces render.

Fields:
- `analysis_id`
- `summary`
- `findings`
- `risk_assessment`
- `blast_radius`
- `rollback_plan`
- `incident_matches`
- `share_summary`
- `report_schema_version`

### 8.9 FeedbackEvent
Supports the learning loop.

Fields:
- `feedback_id`
- `analysis_id`
- `reviewer_role`
- `useful`
- `correctness_rating`
- `false_positive_flag`
- `false_negative_note`
- `outcome_label`
- `captured_at`

### 8.10 Skill (new)
Represents a community-contributed or first-party Skill in the registry.

Fields:
- `skill_id`
- `name`
- `version`
- `author`
- `license`
- `tool_type` (terraform, kubernetes, ansible, jenkins, cloudformation, docker, git, custom)
- `tags`
- `description`
- `manifest` (parsed frontmatter)
- `content` (markdown body)
- `test_suite_path`
- `test_pass_rate`
- `download_count`
- `published_at`
- `last_updated`

### 8.11 BenchmarkScenario (new)
Represents a labeled scenario in the benchmark corpus.

Fields:
- `scenario_id`
- `title`
- `tool_types` (list)
- `artifacts` (list of file content + paths)
- `expected_findings` (list with severity and title pattern)
- `expected_verdict`
- `rationale`
- `annotator_credits`
- `license`

### 8.12 BenchmarkRun (new)
Represents one execution of the benchmark corpus.

Fields:
- `run_id`
- `deploywhisper_version`
- `commit_hash`
- `started_at`
- `completed_at`
- `corpus_version`
- `results` (JSON array of per-scenario outcomes)
- `metrics` (precision, recall, F1 by severity and by tool)

---

## 9. Service Architecture

### 9.1 Intake Service
Responsibilities:
- Validate request surface
- Classify and register artifacts
- Detect sensitive/unsupported files
- Create artifact manifest
- Enforce raw-content security boundary

### 9.2 Parser Registry
Responsibilities:
- Detect supported tool type
- Dispatch to correct parser
- Isolate parser failures
- Return `NormalizedChange` objects and parser warnings

Supported parsers: Terraform, Kubernetes, Ansible, Jenkins, CloudFormation (and Docker, Git as auxiliary).

### 9.3 Evidence Engine
Responsibilities:
- Turn parsed changes + heuristics + context + active skills into `EvidenceItem`
- Maintain traceability from findings to evidence
- Separate deterministic evidence from inferred interpretation
- Feed scoring and narrative preparation

### 9.4 Risk Engine
Responsibilities:
- Compute severity and score
- Detect cross-tool interactions
- Generate risk contributors
- Compute recommendation
- Emit confidence and uncertainty

The risk engine remains mostly deterministic in v1/v1.5. LLMs are not the primary decision-maker.

### 9.5 Context Service
Responsibilities:
- Serve topology, incidents, deployment history, criticality, ownership
- Expose freshness / version information per context domain
- Feed the evidence engine and blast-radius calculator

### 9.6 Narrator Service
Responsibilities:
- Accept frozen risk assessment + findings + evidence references
- Produce plain-English narrative
- Never mutate severity, findings, or evidence

### 9.7 Report Service
Responsibilities:
- Assemble final Report from pipeline outputs
- Persist Report with schema version
- Serve Report to all access surfaces
- Generate share summaries (markdown + machine-readable JSON)

### 9.8 Feedback Service
Responsibilities:
- Capture reviewer feedback per finding and per report
- Link deployment outcomes back to reports
- Feed calibration dashboards

### 9.9 Integration Service
Responsibilities:
- Orchestrate GitHub Action, App, and Check Run interactions
- Format PR comments
- Handle rerun-on-commit logic
- Generate shareable report URLs

### 9.10 Skills Registry Service (new)
Responsibilities:
- Expose Skills registry API (list, detail, versions)
- Run Skill validators on submissions
- Serve the Skills browser UI
- Manage skill install/update/remove lifecycle
- Track skill analytics (downloads, test pass rates, ratings)

### 9.11 Skill Validator (new)
Responsibilities:
- Parse and validate skill manifests
- Run skill test harness (known-risky-scenarios per skill)
- Produce pass/fail report for every skill version

### 9.12 Benchmark Runner (new)
Responsibilities:
- Load benchmark corpus
- Execute DeployWhisper analysis per scenario
- Compare against expected findings and verdict
- Optionally execute comparator tools (tflint, kube-score, K8sGPT, vanilla LLM)
- Compute precision, recall, F1 per tool and per severity
- Publish results to dashboard

---

## 10. Analysis Pipeline (canonical order)

Every analysis — regardless of trigger surface — flows through this pipeline:

```
1. INTAKE      Validate submission, create manifest, classify artifacts
2. PARSE       Dispatch parsers, produce NormalizedChange list
3. LOAD SKILLS Resolve active Skills for detected tools
4. EVIDENCE    Extract EvidenceItem list from changes + heuristics + skills
5. CONTEXT     Load frozen ContextSnapshot (topology, incidents, history)
6. BLAST       Compute blast radius with completeness indicator
7. SIMILARITY  Match against incident memory
8. ROLLBACK    Generate rollback plan and complexity
9. SCORE       Produce RiskAssessment with contributors
10. NARRATE    Generate narrative from frozen verdict (LLM, optional)
11. ASSEMBLE   Build Report with share summary
12. PERSIST    Save report with audit metadata before returning
13. DELIVER    Return via UI / API / CLI / PR comment
```

Key invariants:
- Steps 1-9 are deterministic and must not depend on LLM availability.
- Step 10 can fail or be disabled; the report still renders without narrative.
- Step 12 must complete before step 13 — reports are never shown unless persisted.
- Skills (step 3) are resolved once and frozen for the analysis — no mid-pipeline skill changes.

---

## 11. Security and Privacy Architecture

### 11.1 Security principles
- Secrets never logged
- Raw IaC stays local
- Sensitive-file filtering is always on
- Provider credentials remain external to persistence
- Report objects store metadata and structured outputs, not secrets or raw private inputs

### 11.2 Shared-deployment model
Early shared deployments may rely on network boundary / reverse-proxy controls. However, the architecture should reserve clean insertion points for:
- SSO
- RBAC
- Team scoping
- Audit access controls

### 11.3 Audit model
Every analysis captures:
- Who or what triggered it
- When it ran
- Artifact manifest
- Provider mode
- Report schema version
- Risk verdict
- Context versions
- Active skills (version hashes)
- Feedback and later outcome where available

### 11.4 Skill security (new)
Skills are markdown files with structured frontmatter. They contain no executable code. Skill content is treated as trusted input to the LLM context but never executed. Skills are signed or hashed at registry time so installed skills can be verified against registry version.

---

## 12. Persistence Architecture

### 12.1 v1 schema
SQLite database with the following tables:

- `artifact_bundles`
- `artifact_records`
- `analysis_reports`
- `findings`
- `evidence_items`
- `incident_records`
- `topology_versions`
- `settings`
- `feedback_events`
- `skills` (new)
- `skill_versions` (new)
- `skill_test_runs` (new)
- `benchmark_scenarios` (new)
- `benchmark_runs` (new)

### 12.2 vNext storage path
When the product moves beyond single-team usage:
- Migrate operational persistence to PostgreSQL
- Keep repository interfaces stable
- Optionally introduce object storage for large retained artifacts
- Optionally introduce Redis / queue only when async workers become necessary

The persistence abstraction is designed now to make that migration low-risk later.

---

## 13. Deployment Architecture

### 13.1 v1 deployment
- One application container
- One SQLite persistent volume
- Optional separate Ollama runtime for local model execution
- Reverse proxy when shared internal deployment is needed

This is the correct early deployment model and stays.

### 13.2 vNext deployment
When adoption grows:
- Web/API process
- Background worker(s)
- PostgreSQL
- Optional queue (Redis or similar)
- Optional object storage
- Observability stack
- SSO-enabled reverse proxy or app-native auth

Introduced as a migration path, not a prerequisite.

---

## 14. Interface Architecture

### 14.1 Web UI
Purpose:
- Verdict-first report review
- Admin workflows
- History and analytics
- Context maintenance
- Skills browsing and management (new)

Key principle:
- Present high-signal summary first, evidence second, raw details last.

### 14.2 REST API
Purpose:
- Programmatic analysis
- Report retrieval
- Context management
- Integration surfaces
- Skills registry access (new)

Core endpoints:

```
POST   /api/v1/analyses
GET    /api/v1/analyses
GET    /api/v1/analyses/{analysis_id}
POST   /api/v1/context/topology
POST   /api/v1/context/incidents
POST   /api/v1/feedback/{analysis_id}
POST   /api/v1/integrations/github/summary

GET    /api/v1/skills                      (new)
GET    /api/v1/skills/{skill_id}           (new)
GET    /api/v1/skills/{skill_id}/versions  (new)
POST   /api/v1/skills/install              (new)

GET    /api/v1/benchmarks                  (new)
GET    /api/v1/benchmarks/runs             (new)
GET    /api/v1/benchmarks/runs/{run_id}    (new)
POST   /api/v1/benchmarks/run              (new; admin only)
```

### 14.3 CLI
Purpose:
- Local and CI usage
- Headless testing
- Benchmark corpus execution
- Skill management (new)

Core commands:

```
deploywhisper analyze <path>
deploywhisper report <analysis_id>
deploywhisper topology import --from terraform --state <uri>
deploywhisper skill install <name>           (new)
deploywhisper skill list                     (new)
deploywhisper skill update <name>            (new)
deploywhisper benchmark run                  (new)
deploywhisper github init                    (new)
```

### 14.4 GitHub Integration (new section in v3)

**GitHub Adapter layer** — first-class adoption surface after trusted core.

Capabilities:
- PR analysis trigger (GitHub Action)
- Summary comment with verdict, top risks, blast radius, rollback, uncertainty
- Rerun on new commit (updates existing comment, shows diff)
- Compare old vs new report
- Link to full report (shareable URL)
- Check Run integration (advisory-only, never required)
- GitHub App for richer interactions (checks API, OAuth, installation wizard)

Adapter pattern:
- Core analysis pipeline is surface-agnostic
- GitHub adapter translates GitHub events into `ArtifactBundle` submissions
- Comment formatter translates `Report` into GitHub-flavored markdown
- All adapter logic lives in `integrations/github/` — no core code changes required to add GitLab, Atlantis, HCP Terraform, or Jenkins adapters later

---

## 15. Skills Marketplace Architecture (new in v3)

### 15.1 Why this matters architecturally

The Skills marketplace is DeployWhisper's **ecosystem moat**. No competitor has built this. Architecturally, it requires three components:

1. **Skills Registry Service** — API, storage, versioning
2. **Skill Validator** — manifest validation + test harness
3. **Skill Installer** — CLI that fetches skills into `skills/custom/`

### 15.2 Skill manifest schema

Skills are markdown files with YAML frontmatter:

```yaml
---
name: helm-rollout-risks
version: 1.2.0
author: community@example.com
license: MIT
tool_type: kubernetes
tags: [helm, rollout, probes]
description: Detects Helm chart rollout risks including missing probes and unsafe upgrade strategies
triggers:
  - file_glob: "**/*.yaml"
    content_pattern: "kind: HelmRelease"
  - file_glob: "Chart.yaml"
token_budget: 2000
test_suite_path: tests/scenarios/
---

# Helm Rollout Risks

## Risk patterns
...
```

### 15.3 Skill test harness

Every skill ships with a test suite:

```
skills/registry/helm-rollout-risks/
├── skill.md                    (the skill content)
├── manifest.yaml               (parsed frontmatter, auto-generated)
└── tests/
    └── scenarios/
        ├── missing-readiness-probe.yaml
        ├── maxunavailable-100.yaml
        └── expected.json       (expected findings for each scenario)
```

The Skill Validator runs every scenario through DeployWhisper with only that skill active, compares against expected findings, and computes a pass rate.

### 15.4 Skills storage

Skills are stored in three places:

- **Registry (canonical)** — public Git repository at `github.com/deploywhisper/skills-registry`; each skill is a directory
- **Cache (local)** — installed skills live in `skills/custom/` in the user's DeployWhisper install
- **Database (metadata)** — `skills` and `skill_versions` tables hold manifest metadata, analytics, and test results

### 15.5 Registry API

The Skills Registry Service exposes a read API for the browser UI and the installer CLI:

```
GET /api/v1/skills                      -> list all skills with filters
GET /api/v1/skills/{id}                 -> skill detail
GET /api/v1/skills/{id}/versions        -> version history
GET /api/v1/skills/{id}/content         -> raw skill markdown
GET /api/v1/skills/{id}/test-results    -> test suite pass/fail
POST /api/v1/skills/install             -> install request (auth required)
```

Write operations (contribute, update, remove) happen via GitHub PR to the registry repository — not via API. This keeps the contribution process transparent and auditable.

### 15.6 Skill loading at analysis time

During step 3 of the analysis pipeline (Load Skills):

1. Inspect `NormalizedChange` list to determine detected tool types.
2. Query local skill cache for skills matching those tools.
3. Apply skill trigger patterns against artifact contents.
4. Freeze the active skill set in the `ContextSnapshot`.
5. Make skill content available to the Evidence Engine (as heuristic context) and Narrator (as LLM context).

Skills do not execute code. They provide structured domain knowledge to both deterministic heuristics and the LLM narrator.

---

## 16. Benchmark Architecture (new in v3)

### 16.1 Why this matters architecturally

The benchmark corpus is DeployWhisper's **proof engine**. You cannot claim measurable accuracy without one. Architecturally it requires:

1. **Corpus storage** — labeled scenarios as versioned data
2. **Benchmark Runner** — executes corpus through DeployWhisper and comparators
3. **Results publication** — scheduled runs published to public dashboard

### 16.2 Corpus structure

Benchmark corpus lives in a separate public repo: `github.com/deploywhisper/benchmark-corpus`.

```
benchmark-corpus/
├── scenarios/
│   ├── terraform/
│   │   ├── sg-0000-open/
│   │   │   ├── scenario.yaml       (metadata + expected)
│   │   │   └── artifacts/
│   │   │       └── main.tf
│   │   └── iam-wildcard/...
│   ├── kubernetes/...
│   ├── ansible/...
│   ├── jenkins/...
│   └── cloudformation/...
├── annotations/
│   └── reviewers.yaml              (SRE reviewer credits)
└── LICENSE
```

Each `scenario.yaml`:

```yaml
scenario_id: terraform-sg-0000-open
title: Security group opened to 0.0.0.0/0 on port 5432
tool_types: [terraform]
expected_verdict: HIGH
expected_findings:
  - severity: HIGH
    title_pattern: "security group.*0\\.0\\.0\\.0/0"
    tool: terraform
rationale: |
  Opening a database port to the public internet is a known critical
  misconfiguration. Any scanner or AI reviewer worth using should flag
  this unambiguously.
annotators: [reviewer_01, reviewer_02]
license: MIT
```

### 16.3 Benchmark Runner

The Benchmark Runner is a CLI command and an API endpoint:

```bash
deploywhisper benchmark run --corpus ./benchmark-corpus --comparators tflint,kube-score
```

Output: per-scenario pass/fail, per-tool precision/recall/F1, overall metrics.

Results are persisted as `BenchmarkRun` rows and published to the public dashboard at `deploywhisper.kubechat.dev/benchmarks`.

### 16.4 Comparator execution

For public comparison, the runner can execute other tools:

- `tflint` — invoked via subprocess
- `kube-score` — invoked via subprocess
- `K8sGPT` — invoked via CLI
- Vanilla LLM prompt — sends artifacts to configured LLM with a generic "analyze this for risk" prompt

Each comparator's output is mapped to a common finding format so direct comparison is possible.

### 16.5 Quarterly publication

A scheduled job runs the corpus every quarter against:
- Current DeployWhisper main branch
- Previous DeployWhisper release
- All configured comparators

Results are published to the public dashboard with methodology, raw data download, and a version-over-version trend chart.

---

## 17. Trust Architecture

This is the most important architectural section.

DeployWhisper wins only if trust is structurally built into the system.

Trust requires:

1. **Evidence references** on findings
2. **Confidence** on judgments
3. **Uncertainty** on missing context
4. **Deterministic core** for risk logic
5. **Narrative as explanation, not authority**
6. **Backtesting and calibration**
7. **Outcome learning without silent model drift**
8. **Published benchmark accuracy** (new in v3)
9. **Community-auditable skills** (new in v3)

Architectural implications:

- Scoring must be understandable
- Narrative must be downstream of the report, not upstream of it
- Report schema must preserve source traceability
- Benchmark and feedback subsystems are not optional extras
- Skills are transparent markdown, not black-box code
- Accuracy is measured and published, not asserted

---

## 18. Observability and Quality

### 18.1 Logs
Use structured logs with:
- Analysis ID
- Stage
- Duration
- Parser outcomes
- Provider mode
- Severity result
- Error metadata
- Active skills (IDs + versions)

Never log:
- Raw IaC
- Secrets
- Prompts
- Full model responses

### 18.2 Health and readiness
Expose:
- Health endpoint
- Readiness endpoint
- Provider mode visibility
- Storage health
- Migration/version health
- Skills registry connectivity (new)

### 18.3 Test strategy
Must include:
- Parser fixture tests
- Cross-tool interaction tests
- Evidence traceability tests
- Report schema tests
- PR formatter tests
- Benchmark corpus tests
- Failure degradation tests
- Persistence-before-success tests
- Skill manifest validation tests (new)
- Skill test-harness regression tests (new)

---

## 19. Recommended Project Structure

This structure extends the current repo.

```
ai-deploy-whisper/
├── api/
├── ui/
├── cli/
├── services/
│   ├── analysis_pipeline.py
│   ├── intake_service.py
│   ├── report_service.py
│   ├── context_service.py
│   ├── feedback_service.py
│   ├── integration_service.py
│   ├── skills_registry_service.py       (new)
│   └── benchmark_service.py             (new)
├── parsers/
├── analysis/
│   ├── risk_engine.py
│   ├── rollback_planner.py
│   ├── blast_radius.py
│   ├── incident_matcher.py
│   └── confidence.py
├── evidence/
│   ├── models.py
│   ├── extractor.py
│   └── mappers.py
├── llm/
│   ├── narrator.py
│   ├── providers.py
│   └── summary_builder.py
├── integrations/
│   ├── github/
│   │   ├── action.py
│   │   ├── app.py
│   │   ├── comment_formatter.py
│   │   └── check_run.py
│   └── common/
├── skills/                              (new layout)
│   ├── registry_client.py
│   ├── validator.py
│   ├── installer.py
│   ├── loader.py
│   ├── custom/                          (user-installed skills)
│   └── builtin/                         (first-party skills)
├── benchmarks/                          (new)
│   ├── runner.py
│   ├── comparators.py
│   └── results_publisher.py
├── models/
│   ├── tables.py
│   ├── repositories/
│   └── schemas.py
├── analytics/
│   ├── benchmarks.py
│   ├── calibration.py
│   └── trend_queries.py
├── data/
├── tests/
└── docs/
```

---

## 20. Architectural Decisions

### ADR-01: Keep shared NiceGUI + FastAPI runtime in v1
**Status:** Accepted
**Reason:** Low friction, already aligned with repo, correct for early self-hosted product.

### ADR-02: Add explicit evidence model
**Status:** Accepted
**Reason:** Required for trust, differentiation, and benchmarkability.

### ADR-03: Keep advisory-first core
**Status:** Accepted
**Reason:** Enforcement too early will damage trust and positioning.

### ADR-04: Introduce GitHub integration as first-class adapter
**Status:** Accepted
**Reason:** Workflow-native adoption is required for becoming the default choice.

### ADR-05: Preserve raw-local / structured-summary-only LLM boundary
**Status:** Accepted
**Reason:** One of the clearest product differentiators.

### ADR-06: Design for SQLite now, PostgreSQL later
**Status:** Accepted
**Reason:** Current product stage favors simplicity; future stage requires scale path.

### ADR-07: Add benchmark and feedback services before enterprise polish
**Status:** Accepted
**Reason:** Trust data is a stronger moat than early enterprise checkbox work.

### ADR-08: Skills as markdown, not executable plugins (new)
**Status:** Accepted
**Reason:** Markdown skills are transparent, community-auditable, and eliminate a whole class of plugin-security problems. Skills provide knowledge, not code.

### ADR-09: Skills contributed via PR to public registry repo, not via API (new)
**Status:** Accepted
**Reason:** Contribution process must be transparent and auditable. PR review + automated test harness is the quality gate. This mirrors the model used by Helm charts, Kubernetes Operators Hub, and VS Code extensions.

### ADR-10: Benchmark corpus is public, open-source, community-extendable (new)
**Status:** Accepted
**Reason:** The corpus's value is its trust — if it's private or vendor-controlled, nobody will believe it. Publishing under MIT and accepting PRs for new scenarios makes it a community asset, not a marketing claim.

### ADR-11: GitHub adapter uses Action + App in parallel (new)
**Status:** Accepted
**Reason:** Action is simpler (works in any workflow) — ship it first. App enables richer interactions (check runs, PR events, OAuth) — add it second. Both are needed for full workflow-native integration.

---

## 21. Migration Plan From Current Codebase

### Step 1
Keep current shared runtime and service architecture.

### Step 2
Introduce `EvidenceItem` and `Finding` schemas as first-class persisted entities (Epic 1).

### Step 3
Refactor scoring pipeline so verdicts are assembled from evidence and context before narrative (Epic 1).

### Step 4
Add `integrations/github/` with PR summary formatter and rerun support (Epic 3).

### Step 5
Add Skills Registry Service, Validator, and Installer (Epic 4).

### Step 6
Add feedback tables and benchmark harness (Epic 5 + 6).

### Step 7
Add context freshness/versioning for topology and incidents (Epic 5).

### Step 8
Prepare repository interfaces for PostgreSQL and async-worker migration (Phase 3).

---

## 22. What This Architecture Optimizes For

This architecture optimizes for:

- Trust
- Adoption in real workflows
- Local-first security
- Maintainable evolution
- Community extensibility (new)
- Measurable accuracy (new)
- Eventual enterprise path

It does **not** optimize for:

- Maximum feature breadth in v1
- Deep multi-tenant enterprise scope on day one
- Flashy AI behavior without evidence
- Pipeline ownership or enforcement ownership

---

## 23. Final Recommendation

Keep the current core technical direction, but evolve the system around five missing architectural pillars:

1. **Evidence-backed report objects** (Epic 1-2)
2. **Workflow-native integration layer** (Epic 3)
3. **Skills Marketplace infrastructure** (Epic 4) — new in v3
4. **Feedback / calibration loop** (Epic 5)
5. **Benchmark corpus infrastructure** (Epic 6) — new in v3

That is the shortest path from "interesting open-source product" to "trusted, community-extensible, measurably-accurate pre-deployment intelligence platform".
