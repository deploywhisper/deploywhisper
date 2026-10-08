# Story Alignment Report

Date: 2026-05-01 (historical story-generation snapshot)

**Current delivery status:** Reconciled on 2026-10-07 in [Story Implementation Status Map](story-implementation-status-map.md) and `sprint-status.yaml`. The May statuses below describe creation readiness, not current implementation. Archives remain historical.

## Summary

The implementation story set has been reconciled with the updated PRD, architecture, epics, sprint status, and `implementation-readiness-report-2026-05-01.md`.

- Current required stories: 93
- Current epic coverage: 15 epics, Epic 0 through Epic 14
- Current story files created/aligned: 93
- Superseded numbered story files archived: 57
- Archive location: `_bmad-output/implementation-artifacts/archived-story-set-2026-05-01/`
- Readiness basis: READY verdict with 187/187 PRD functional IDs represented in epics, 38 NFR IDs represented, 0 critical issues, 0 major issues, and 1 minor story-format concern.

## Source Of Truth Used

- `_bmad-output/planning-artifacts/prd.md`
- `_bmad-output/planning-artifacts/architecture.md`
- `_bmad-output/planning-artifacts/epics.md`
- `_bmad-output/planning-artifacts/ux-design-specification.md`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`
- `_bmad-output/project-context.md`

## Story Inventory By Epic

- Epic 0: 4 stories
- Epic 1: 6 stories
- Epic 2: 9 stories
- Epic 3: 8 stories
- Epic 4: 7 stories
- Epic 5: 6 stories
- Epic 6: 6 stories
- Epic 7: 5 stories
- Epic 8: 5 stories
- Epic 9: 7 stories
- Epic 10: 5 stories
- Epic 11: 4 stories
- Epic 12: 8 stories
- Epic 13: 8 stories
- Epic 14: 5 stories

## Story Files at the May 1 Alignment

| Story Key | Story ID | Title | Status |
| --- | --- | --- | --- |
| `0-1-publish-core-governance-files` | Story 0.1 | Publish Core Governance Files | `review` |
| `0-2-define-maintainer-ownership-and-codeowners` | Story 0.2 | Define Maintainer Ownership and CODEOWNERS | `ready-for-dev` |
| `0-3-create-requirements-traceability-matrix` | Story 0.3 | Create Requirements Traceability Matrix | `ready-for-dev` |
| `0-4-establish-rfc-and-decision-process` | Story 0.4 | Establish RFC and Decision Process | `ready-for-dev` |
| `1-1-project-and-workspace-records` | Story 1.1 | Project and Workspace Records | `ready-for-dev` |
| `1-2-project-aware-analysis-submission` | Story 1.2 | Project-Aware Analysis Submission | `ready-for-dev` |
| `1-3-project-scoped-report-persistence` | Story 1.3 | Project-Scoped Report Persistence | `ready-for-dev` |
| `1-4-project-scoped-learning-and-context-records` | Story 1.4 | Project-Scoped Learning and Context Records | `ready-for-dev` |
| `1-5-lightweight-rbac-role-model` | Story 1.5 | Lightweight RBAC Role Model | `ready-for-dev` |
| `1-6-project-model-documentation` | Story 1.6 | Project Model Documentation | `ready-for-dev` |
| `2-1-submission-manifest-and-provenance` | Story 2.1 | Submission Manifest and Provenance | `ready-for-dev` |
| `2-2-terraform-plan-json-intake` | Story 2.2 | Terraform Plan JSON Intake | `ready-for-dev` |
| `2-3-evidence-item-model-and-extraction` | Story 2.3 | Evidence Item Model and Extraction | `ready-for-dev` |
| `2-4-finding-model-and-evidence-links` | Story 2.4 | Finding Model and Evidence Links | `ready-for-dev` |
| `2-5-evidence-law-runtime-gate` | Story 2.5 | Evidence Law Runtime Gate | `ready-for-dev` |
| `2-6-confidence-uncertainty-and-insufficient-context` | Story 2.6 | Confidence, Uncertainty, and Insufficient Context | `ready-for-dev` |
| `2-7-narrative-after-scoring-and-degraded-fallback` | Story 2.7 | Narrative After Scoring and Degraded Fallback | `ready-for-dev` |
| `2-8-report-schema-versioning` | Story 2.8 | Report Schema Versioning | `ready-for-dev` |
| `2-9-durable-report-persistence-and-audit-metadata` | Story 2.9 | Durable Report Persistence and Audit Metadata | `ready-for-dev` |
| `3-1-verdict-first-report-header` | Story 3.1 | Verdict-First Report Header | `ready-for-dev` |
| `3-2-findings-table-with-evidence-badges` | Story 3.2 | Findings Table With Evidence Badges | `ready-for-dev` |
| `3-3-evidence-inspector-panel` | Story 3.3 | Evidence Inspector Panel | `ready-for-dev` |
| `3-4-confidence-ledger-and-why-not-lower-higher` | Story 3.4 | Confidence Ledger and Why-Not-Lower/Higher | `ready-for-dev` |
| `3-5-context-completeness-and-todo-panel` | Story 3.5 | Context Completeness and TODO Panel | `ready-for-dev` |
| `3-6-report-diff-after-rerun` | Story 3.6 | Report Diff After Rerun | `ready-for-dev` |
| `3-7-keyboard-and-accessibility-review-pass` | Story 3.7 | Keyboard and Accessibility Review Pass | `ready-for-dev` |
| `3-8-historical-report-search-and-filtering` | Story 3.8 | Historical Report Search and Filtering | `ready-for-dev` |
| `4-1-public-risk-pattern-library-v1` | Story 4.1 | Public Risk Pattern Library v1 | `ready-for-dev` |
| `4-2-safe-sample-incident-pack` | Story 4.2 | Safe Sample Incident Pack | `ready-for-dev` |
| `4-3-incident-import-for-markdown-yaml-and-json` | Story 4.3 | Incident Import for Markdown, YAML, and JSON | `ready-for-dev` |
| `4-4-incident-similarity-with-match-explanation` | Story 4.4 | Incident Similarity With Match Explanation | `ready-for-dev` |
| `4-5-reviewer-feedback-capture` | Story 4.5 | Reviewer Feedback Capture | `ready-for-dev` |
| `4-6-deployment-outcome-capture` | Story 4.6 | Deployment Outcome Capture | `ready-for-dev` |
| `4-7-incident-ingestion-management-and-indexing` | Story 4.7 | Incident Ingestion Management and Indexing | `ready-for-dev` |
| `5-1-versioned-api-report-contract` | Story 5.1 | Versioned API Report Contract | `ready-for-dev` |
| `5-2-cli-project-aware-advisory-output` | Story 5.2 | CLI Project-Aware Advisory Output | `ready-for-dev` |
| `5-3-github-action-integration-contract` | Story 5.3 | GitHub Action Integration Contract | `ready-for-dev` |
| `5-4-pr-comment-formatter` | Story 5.4 | PR Comment Formatter | `ready-for-dev` |
| `5-5-rerun-on-commit-and-report-comparison` | Story 5.5 | Rerun-on-Commit and Report Comparison | `ready-for-dev` |
| `5-6-future-adapter-output-contract` | Story 5.6 | Future Adapter Output Contract | `ready-for-dev` |
| `6-1-benchmark-corpus-v1` | Story 6.1 | Benchmark Corpus v1 | `ready-for-dev` |
| `6-2-benchmark-runner` | Story 6.2 | Benchmark Runner | `ready-for-dev` |
| `6-3-honest-failure-report-generator` | Story 6.3 | Honest Failure Report Generator | `ready-for-dev` |
| `6-4-outcome-calibration-metrics` | Story 6.4 | Outcome Calibration Metrics | `ready-for-dev` |
| `6-5-incident-backtesting` | Story 6.5 | Incident Backtesting | `ready-for-dev` |
| `6-6-risk-trend-review` | Story 6.6 | Risk Trend Review | `ready-for-dev` |
| `7-1-project-scoped-topology-context` | Story 7.1 | Project-Scoped Topology Context | `ready-for-dev` |
| `7-2-terraform-state-connector` | Story 7.2 | Terraform State Connector | `ready-for-dev` |
| `7-3-kubernetes-live-state-connector` | Story 7.3 | Kubernetes Live-State Connector | `ready-for-dev` |
| `7-4-codeowners-and-ownership-mapping` | Story 7.4 | CODEOWNERS and Ownership Mapping | `ready-for-dev` |
| `7-5-context-graph-and-freshness-ledger` | Story 7.5 | Context Graph and Freshness Ledger | `ready-for-dev` |
| `8-1-sarif-ingestion` | Story 8.1 | SARIF Ingestion | `ready-for-dev` |
| `8-2-scanner-json-adapter-v1` | Story 8.2 | Scanner JSON Adapter v1 | `ready-for-dev` |
| `8-3-external-evidence-report-context` | Story 8.3 | External Evidence Report Context | `ready-for-dev` |
| `8-4-scanner-conflict-handling` | Story 8.4 | Scanner Conflict Handling | `ready-for-dev` |
| `8-5-existing-security-tools-comparison-guide` | Story 8.5 | Existing Security Tools Comparison Guide | `ready-for-dev` |
| `9-1-skill-manifest-spec-v1` | Story 9.1 | Skill Manifest Spec v1 | `ready-for-dev` |
| `9-2-skills-registry-api` | Story 9.2 | Skills Registry API | `ready-for-dev` |
| `9-3-skill-test-harness` | Story 9.3 | Skill Test Harness | `ready-for-dev` |
| `9-4-skills-installer-cli` | Story 9.4 | Skills Installer CLI | `ready-for-dev` |
| `9-5-skills-browser-ui` | Story 9.5 | Skills Browser UI | `ready-for-dev` |
| `9-6-skill-contribution-workflow` | Story 9.6 | Skill Contribution Workflow | `ready-for-dev` |
| `9-7-skill-analytics-and-deprecation-signals` | Story 9.7 | Skill Analytics and Deprecation Signals | `ready-for-dev` |
| `10-1-agent-json-cli-mode` | Story 10.1 | Agent JSON CLI Mode | `ready-for-dev` |
| `10-2-mcp-compatible-or-equivalent-agent-interface` | Story 10.2 | MCP-Compatible or Equivalent Agent Interface | `ready-for-dev` |
| `10-3-ai-generated-iac-provenance-and-risk-patterns` | Story 10.3 | AI-Generated IaC Provenance and Risk Patterns | `ready-for-dev` |
| `10-4-prompt-injection-test-suite` | Story 10.4 | Prompt-Injection Test Suite | `ready-for-dev` |
| `10-5-ai-safety-documentation` | Story 10.5 | AI Safety Documentation | `ready-for-dev` |
| `11-1-policy-adapter-output-contract` | Story 11.1 | Policy Adapter Output Contract | `ready-for-dev` |
| `11-2-threshold-and-reporting-defaults-management` | Story 11.2 | Threshold and Reporting Defaults Management | `ready-for-dev` |
| `11-3-integration-level-enforcement-settings` | Story 11.3 | Integration-Level Enforcement Settings | `ready-for-dev` |
| `11-4-enforcement-guardrail-documentation` | Story 11.4 | Enforcement Guardrail Documentation | `ready-for-dev` |
| `12-1-secrets-and-raw-artifact-boundary-audit` | Story 12.1 | Secrets and Raw Artifact Boundary Audit | `ready-for-dev` |
| `12-2-provider-settings-administration` | Story 12.2 | Provider Settings Administration | `ready-for-dev` |
| `12-3-connector-credential-handling-and-redaction-audit` | Story 12.3 | Connector Credential Handling and Redaction Audit | `ready-for-dev` |
| `12-4-openssf-scorecard-and-codeql` | Story 12.4 | OpenSSF Scorecard and CodeQL | `ready-for-dev` |
| `12-5-sbom-and-release-checksums` | Story 12.5 | SBOM and Release Checksums | `ready-for-dev` |
| `12-6-signing-and-provenance` | Story 12.6 | Signing and Provenance | `ready-for-dev` |
| `12-7-backup-restore-upgrade-and-retention-docs` | Story 12.7 | Backup, Restore, Upgrade, and Retention Docs | `ready-for-dev` |
| `12-8-air-gapped-and-restricted-network-guide` | Story 12.8 | Air-Gapped and Restricted-Network Guide | `ready-for-dev` |
| `13-1-documentation-information-architecture` | Story 13.1 | Documentation Information Architecture | `ready-for-dev` |
| `13-2-first-analysis-and-report-interpretation-guides` | Story 13.2 | First Analysis and Report Interpretation Guides | `ready-for-dev` |
| `13-3-api-and-report-schema-references` | Story 13.3 | API and Report Schema References | `ready-for-dev` |
| `13-4-cli-evidence-and-agent-output-references` | Story 13.4 | CLI, Evidence, and Agent Output References | `ready-for-dev` |
| `13-5-connector-guides` | Story 13.5 | Connector Guides | `ready-for-dev` |
| `13-6-workflow-integration-guides` | Story 13.6 | Workflow Integration Guides | `ready-for-dev` |
| `13-7-docs-ci-and-drift-checks` | Story 13.7 | Docs CI and Drift Checks | `ready-for-dev` |
| `13-8-release-notes-and-upgrade-notes` | Story 13.8 | Release Notes and Upgrade Notes | `ready-for-dev` |
| `14-1-cncf-readiness-checklist` | Story 14.1 | CNCF Readiness Checklist | `ready-for-dev` |
| `14-2-public-adopters-and-usage-signals` | Story 14.2 | Public Adopters and Usage Signals | `ready-for-dev` |
| `14-3-maintainer-coverage-and-promotion-process` | Story 14.3 | Maintainer Coverage and Promotion Process | `ready-for-dev` |
| `14-4-community-health-metrics` | Story 14.4 | Community Health Metrics | `ready-for-dev` |
| `14-5-cncf-application-package` | Story 14.5 | CNCF Application Package | `ready-for-dev` |

## Archived Superseded Story Files

- `1-1-domain-model-foundations.md`
- `1-2-evidence-extractor-service.md`
- `1-3-refactor-risk-scorer-to-consume-evidence.md`
- `1-4-confidence-field-on-every-finding.md`
- `1-5-context-completeness-on-riskassessment.md`
- `1-6-narrator-runs-after-scoring.md`
- `1-7-deterministic-degradation.md`
- `1-8-report-schema-v2.md`
- `2-1-verdict-card-redesign.md`
- `2-2-findings-table-with-evidence-badges.md`
- `2-3-evidence-inspector-panel.md`
- `2-4-context-completeness-panel.md`
- `2-5-blast-radius-visualization.md`
- `2-6-rollback-plan-panel.md`
- `2-7-share-summary-generator.md`
- `2-8-keyboard-navigation.md`
- `3-1-github-action-v1.md`
- `3-2-pr-comment-formatter.md`
- `3-3-rerun-on-commit.md`
- `3-4-shareable-report-urls.md`
- `3-5-report-comparison-view.md`
- `3-6-github-app.md`
- `3-7-check-run-integration.md`
- `3-8-installation-wizard.md`
- `3-9-self-hosted-github-app-setup-documentation.md`
- `4-1-skills-registry-api.md`
- `4-2-skills-manifest-spec-v1.md`
- `4-3-skill-test-harness.md`
- `4-4-skills-installer-cli.md`
- `4-5-skills-browser-ui.md`
- `4-6-contribution-workflow.md`
- `4-7-seed-20-community-skills.md`
- `4-8-skill-analytics.md`
- `4-9-editorial-curation.md`
- `5-1-project-workspace-foundation.md`
- `5-10-terraform-state-topology-source.md`
- `5-11-cloudformation-topology-source.md`
- `5-12-threshold-and-reporting-defaults-management.md`
- `5-13-policy-adapter-consumption-boundary.md`
- `5-14-kubernetes-manifest-topology-source.md`
- `5-15-ansible-topology-source.md`
- `5-16-custom-topology-source-boundary.md`
- `5-2-topology-import-foundation.md`
- `5-3-topology-drift-detection.md`
- `5-4-topology-freshness-badge.md`
- `5-5-deployment-history-capture.md`
- `5-6-reviewer-feedback-capture.md`
- `5-7-outcome-linking.md`
- `5-8-calibration-dashboard.md`
- `5-9-trend-analysis.md`
- `6-2-scenario-annotation.md`
- `6-3-benchmark-runner.md`
- `6-4-comparative-runner.md`
- `6-5-published-results-dashboard.md`
- `6-6-quarterly-regression.md`
- `6-7-open-source-the-corpus.md`
- `6-8-incident-backtesting.md`

## Notes

- Story 0.1 was preserved in `review` because implementation work already exists in the current working tree.
- At the May 1 alignment, all other stories were ready for `bmad-dev-story`; use the current status map for present sequencing.
- Older auxiliary review prompt files and validation reports were left in place when they were not numbered story files.
