# DeployWhisper — Documentation

This directory contains the formal product and engineering documentation for DeployWhisper.

---

## Documents

### 1. Product Requirements Document (PRD)

**File:** `DeployWhisper_PRD.docx`
**Version:** 1.1 | April 2026

The PRD defines **what** DeployWhisper does and **why**. It is the source of truth for product scope, feature requirements, and success criteria.

**Contents:**

| Section | Description |
|---------|-------------|
| Executive Summary | One-page overview of the product and its value proposition |
| Problem Statement | Pain points in current DevOps deployment workflows and target user personas |
| Product Scope | Supported IaC tools (Terraform, K8s, Ansible, Jenkins, CloudFormation) and LLM providers |
| FR-01: Multi-Tool Parsing | Unified change extraction from 5 IaC tools into a common schema |
| FR-02: AI Risk Narrative | LLM-generated plain-English risk stories for every deployment |
| FR-03: Risk Scoring Engine | Weighted heuristic scoring (0–100) with environment multipliers |
| FR-04: Blast Radius Mapping | Dependency graph traversal showing affected services |
| FR-05: Automated Rollback Plan | Step-by-step rollback with time estimates and critical path flagging |
| FR-06: Historical Incident Matching | Embedding similarity search against past postmortems |
| FR-07: Multi-LLM Configuration | Bring-your-own-key support for Claude, OpenAI, Ollama, Groq, Azure |
| FR-08: Analysis History | SQLite persistence with browsing, comparison, and export |
| FR-09: AI Skills Knowledge Base | 7 tool-specific skill modules (Terraform, K8s, Ansible, Jenkins, CloudFormation, Git, Docker) with custom skill authoring |
| FR-10: Analysis Performance | Under 15s latency, 50-change parser throughput in under 2s, response streaming, content-hash caching |
| FR-11: Security & Data Privacy | API key memory-only storage, local-only IaC processing, sensitive file detection, air-gap mode |
| FR-12: Setup & Usability | Zero to first analysis in under 5 minutes, drag-and-drop upload, tool auto-detection |
| User Stories | 7 stories covering platform engineers, SRE leads, managers, and junior engineers |
| Success Metrics | Analysis accuracy, time saved, skill coverage, adoption rate, incident prevention |
| Release Plan | 3-phase delivery: core engine → full toolchain → intelligence layer |
| Risks & Mitigations | LLM hallucination, data privacy, skill staleness, context window limits |

---

### 2. Technical Architecture Document

**File:** `DeployWhisper_Architecture.docx`
**Version:** 1.1 | April 2026

The architecture document defines **how** DeployWhisper is built. It is the engineering reference for implementation, tech stack decisions, and system design.

**Contents:**

| Section | Description |
|---------|-------------|
| Architecture Overview | Design philosophy (pure Python, zero JS), system layer diagram with embedded architecture image |
| Why Streamlit, Not React | Detailed rationale for the Python-only frontend decision |
| Complete Tech Stack | Every dependency with version, purpose, and rationale across 4 tables (core, parser, visualization, development) |
| Project Structure | Full folder tree with 40+ files mapped to their responsibilities |
| AI Skills Engine | Skill file format (markdown with frontmatter), loader implementation code, prompt injection pattern, skill inventory table, custom skill authoring guide |
| Data Flow Architecture | 11-step request lifecycle from file upload to dashboard render |
| Unified Change Schema | Complete Pydantic model code for the central data contract |
| LLM Integration | LiteLLM adapter pattern code, provider configuration mapping for 5 providers |
| Database Schema | SQLAlchemy ORM models for analysis reports and incident records |
| Streamlit Dashboard | Page structure, risk gauge (Plotly) and blast radius graph (streamlit-agraph) implementation code |
| Deployment Architecture | Dockerfile, docker-compose.yml, and 4 run modes (dashboard, API, CLI, Docker) |
| Security Architecture | API key handling, data minimization, sensitive file detection, air-gap mode, log sanitization |
| Extensibility Guide | Step-by-step instructions for adding new parsers, LLM providers, and AI skills |
| Technology Decision Log | Rationale table for every major technical choice |

---

## How These Documents Relate

```
PRD (What & Why)                    Architecture (How)
─────────────────                   ──────────────────
FR-01: Multi-Tool Parsing      →    Section 2.2: Parser dependencies
                                     Section 3: Project structure (parsers/)
                                     Section 5: Unified Change Schema

FR-09: AI Skills               →    Section 4: AI Skills Engine (full chapter)
                                     Section 3: Project structure (skills/)

FR-10: Performance             →    Section 2.3: pytest-benchmark dependency
                                     Section 6: Database (content_hash caching)

FR-11: Security                →    Section 8: Security Architecture

FR-12: Usability               →    Section 7: Deployment (run commands)
                                     Section 9: Streamlit Dashboard
```

---

## Updating These Documents

Both documents are generated programmatically using `docx-js` (Node.js). The source scripts are:

- `scripts/gen_prd.js` — Generates the PRD
- `scripts/gen_arch.js` — Generates the Architecture document

To regenerate after making changes:

```bash
node scripts/gen_prd.js       # Outputs docs/DeployWhisper_PRD.docx
node scripts/gen_arch.js      # Outputs docs/DeployWhisper_Architecture.docx
```

The architecture diagram (`docs/assets/architecture_diagram.svg`) is maintained as a separate SVG and embedded during document generation.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | April 2026 | Initial PRD and Architecture documents |
| 1.1 | April 2026 | Promoted NFRs to FRs (FR-10, FR-11, FR-12). Added AI Skills engine (FR-09) with 7 tool skills. Added architecture diagram to Architecture doc. Created README files. |
